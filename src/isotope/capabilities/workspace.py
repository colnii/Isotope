"""Workspace capability proposals for native coding.

The first isolated writable workspace slice is proposal-only. It fixes the
path-safety and low-sensitive contract for a future materialized workspace, but
does not create directories, copy files, mutate repositories, or append events.
"""

from __future__ import annotations

from pathlib import PurePosixPath, Path
import re
import shutil
from typing import Any, Mapping


WORKSPACE_ISOLATED_RW_CAPABILITY = "workspace.isolated_rw"
WORKSPACE_LEASE_CREATE_CAPABILITY = "workspace.lease_create"
WORKSPACE_MATERIALIZE_CAPABILITY = "workspace.materialize"
WORKSPACE_CAPABILITIES = {
    WORKSPACE_ISOLATED_RW_CAPABILITY,
    WORKSPACE_LEASE_CREATE_CAPABILITY,
    WORKSPACE_MATERIALIZE_CAPABILITY,
}

_ARRAY_INPUTS = ("allowed_paths", "forbidden_paths")
_NEXT_REQUIRED_CAPABILITIES = [
    "workspace.lease_create",
    "workspace.materialize",
    "workspace.changed_files",
    "workspace.release",
]
_WORKSPACE_ID_RE = re.compile(r"[^a-z0-9]+")
_STABLE_WORKSPACE_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_SKIPPED_MATERIALIZE_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".venv",
        ".worktrees",
        "__pycache__",
    }
)


def is_workspace_capability(capability_id: str) -> bool:
    return capability_id in WORKSPACE_CAPABILITIES


def validate_workspace_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if not is_workspace_capability(capability_id):
        return dict(inputs or {})
    if capability_id == WORKSPACE_LEASE_CREATE_CAPABILITY:
        return _validate_lease_create_inputs(inputs=inputs, missing_inputs=missing_inputs)
    if capability_id == WORKSPACE_MATERIALIZE_CAPABILITY:
        return _validate_materialize_inputs(inputs=inputs, missing_inputs=missing_inputs)
    input_mapping = dict(inputs or {})
    for name in ("root", "cwd", "workspace_name"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        input_mapping[name] = value.strip()
    for name in _ARRAY_INPUTS:
        input_mapping[name] = _safe_relative_paths(input_mapping.get(name, []), name)
    return input_mapping


def run_workspace_isolated_rw(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    missing_inputs = _missing_required(inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = validate_workspace_inputs(
        capability_id=WORKSPACE_ISOLATED_RW_CAPABILITY,
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    workspace_id = _workspace_id(input_mapping["workspace_name"])
    cwd = Path(input_mapping["cwd"]).expanduser()
    return {
        "kind": "capability_run_result",
        "capability_id": WORKSPACE_ISOLATED_RW_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_proposal",
        "workspace_proposal": {
            "workspace_id": workspace_id,
            "mode": "isolated_rw",
            "execution_mode": "proposal_only",
            "cwd_status": "exists" if cwd.exists() else "missing",
            "root_ref": f"workspace://{workspace_id}/isolated_rw",
            "allowed_paths": list(input_mapping["allowed_paths"]),
            "forbidden_paths": list(input_mapping["forbidden_paths"]),
            "path_policy": {
                "relative_paths_only": True,
                "parent_traversal_allowed": False,
                "absolute_paths_allowed": False,
            },
            "next_required_capabilities": list(_NEXT_REQUIRED_CAPABILITIES),
        },
    }


def run_workspace_lease_create(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    missing_inputs = _missing_lease_create_required(inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_lease_create_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    payload = {
        "workspace_id": input_mapping["workspace_id"],
        "run_id": input_mapping["run_id"],
        "mode": input_mapping["mode"],
        "lease_status": "created",
        "bound_to": {"agent_id": input_mapping["agent_id"]},
        "granted_by": {"decision_id": input_mapping["decision_id"]},
        "created_by": {
            "proposal_id": input_mapping["proposal_id"],
            "execution_id": input_mapping["execution_id"],
        },
        "provenance": {
            "decision_id": input_mapping["decision_id"],
            "proposal_id": input_mapping["proposal_id"],
            "execution_id": input_mapping["execution_id"],
            "grant_basis": {"workspace": {"mode": input_mapping["mode"]}},
            "path_policy": {
                "relative_paths_only": True,
                "parent_traversal_allowed": False,
                "absolute_paths_allowed": False,
            },
        },
    }
    return {
        "kind": "capability_run_result",
        "capability_id": WORKSPACE_LEASE_CREATE_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_proposal",
        "append_required": True,
        "lease_event": {
            "event_type": "workspace.lease_created",
            "run_id": input_mapping["run_id"],
            "payload": payload,
        },
    }


def run_workspace_materialize(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    missing_inputs = _missing_materialize_required(inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_materialize_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    root = Path(input_mapping["root"]).expanduser()
    cwd = Path(input_mapping["cwd"]).expanduser()
    if not cwd.exists():
        raise ValueError("cwd must exist before workspace materialization")
    if not cwd.is_dir():
        raise ValueError("cwd must be a directory before workspace materialization")

    target = root / "workspaces" / input_mapping["workspace_id"]
    cwd_resolved = cwd.resolve(strict=False)
    target_resolved = target.resolve(strict=False)
    if target.exists():
        raise FileExistsError("workspace target already exists")
    if target_resolved.is_relative_to(cwd_resolved):
        raise ValueError("workspace target must not be inside source cwd")

    target.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target.with_name(f".{target.name}.tmp")
    if temp_target.exists():
        raise FileExistsError("workspace temporary target already exists")
    copied_paths: list[str] = []
    skipped_file_count = 0
    try:
        temp_target.mkdir()
        forbidden_paths = set(input_mapping["forbidden_paths"])
        for include_path in input_mapping["include_paths"]:
            copied, skipped = _copy_include_path(
                cwd,
                temp_target,
                include_path,
                forbidden_paths=forbidden_paths,
            )
            copied_paths.extend(copied)
            skipped_file_count += skipped
        temp_target.rename(target)
    except Exception:
        if temp_target.exists():
            shutil.rmtree(temp_target)
        raise

    copied_paths = sorted(dict.fromkeys(copied_paths))
    return {
        "kind": "capability_run_result",
        "capability_id": WORKSPACE_MATERIALIZE_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_local",
        "materialized_workspace": {
            "status": "materialized",
            "workspace_id": input_mapping["workspace_id"],
            "mode": "isolated_rw",
            "workspace_root": str(target),
            "root_ref": f"workspace://{input_mapping['workspace_id']}/materialized",
            "source_cwd_status": "exists",
            "copied_file_count": len(copied_paths),
            "skipped_file_count": skipped_file_count,
            "copied_paths": copied_paths,
            "include_paths": list(input_mapping["include_paths"]),
            "forbidden_paths": list(input_mapping["forbidden_paths"]),
            "path_policy": {
                "relative_paths_only": True,
                "parent_traversal_allowed": False,
                "absolute_paths_allowed": False,
                "writes_only_under_state_root": True,
            },
            "event_append": "not_performed",
        },
    }


def _missing_required(inputs: Mapping[str, Any] | None) -> list[str]:
    input_mapping = inputs or {}
    return [
        name
        for name in ("root", "cwd", "workspace_name")
        if name not in input_mapping or input_mapping.get(name) in (None, "")
    ]


def _missing_lease_create_required(inputs: Mapping[str, Any] | None) -> list[str]:
    input_mapping = inputs or {}
    return [
        name
        for name in (
            "root",
            "run_id",
            "workspace_id",
            "agent_id",
            "decision_id",
            "proposal_id",
            "execution_id",
        )
        if name not in input_mapping or input_mapping.get(name) in (None, "")
    ]


def _missing_materialize_required(inputs: Mapping[str, Any] | None) -> list[str]:
    input_mapping = inputs or {}
    return [
        name
        for name in ("root", "cwd", "workspace_id")
        if name not in input_mapping or input_mapping.get(name) in (None, "")
    ]


def _validate_lease_create_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = dict(inputs or {})
    for name in (
        "root",
        "run_id",
        "workspace_id",
        "agent_id",
        "decision_id",
        "proposal_id",
        "execution_id",
    ):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        input_mapping[name] = value.strip()
    mode = input_mapping.get("mode", "isolated_rw")
    if mode != "isolated_rw":
        raise ValueError("mode must be isolated_rw")
    input_mapping["mode"] = mode
    return input_mapping


def _validate_materialize_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = dict(inputs or {})
    for name in ("root", "cwd", "workspace_id"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        input_mapping[name] = value.strip()
    if "workspace_id" not in missing_inputs:
        workspace_id = input_mapping["workspace_id"]
        if not _STABLE_WORKSPACE_ID_RE.fullmatch(workspace_id):
            raise ValueError("workspace_id must be a stable lowercase identifier")
    include_paths = input_mapping.get("include_paths", ["."])
    if include_paths is None:
        include_paths = ["."]
    input_mapping["include_paths"] = _safe_relative_paths(
        include_paths,
        "include_paths",
        allow_dot=True,
    )
    input_mapping["forbidden_paths"] = _safe_relative_paths(
        input_mapping.get("forbidden_paths", []),
        "forbidden_paths",
    )
    return input_mapping


def _safe_relative_paths(
    value: Any,
    field_name: str,
    *,
    allow_dot: bool = False,
) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of relative paths")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name}[{index}] must be a non-empty relative path")
        candidate = item.strip().replace("\\", "/")
        path = PurePosixPath(candidate)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"{field_name}[{index}] must stay inside the workspace")
        if candidate == "." and allow_dot:
            result.append(candidate)
            continue
        if candidate in {".", ""}:
            raise ValueError(f"{field_name}[{index}] must name a workspace-relative path")
        result.append(candidate)
    return result


def _copy_include_path(
    source_root: Path,
    target_root: Path,
    include_path: str,
    *,
    forbidden_paths: set[str],
) -> tuple[list[str], int]:
    source = _source_path(source_root, include_path)
    if not source.exists():
        return [], 0
    if source.is_dir():
        return _copy_directory(
            source_root,
            target_root,
            source,
            forbidden_paths=forbidden_paths,
        )
    if source.is_file() and not source.is_symlink():
        relative_path = _relative_path(source_root, source)
        if _is_forbidden(relative_path, forbidden_paths):
            return [], 1
        _copy_file(source, target_root / relative_path)
        return [relative_path], 0
    return [], 1


def _copy_directory(
    source_root: Path,
    target_root: Path,
    source: Path,
    *,
    forbidden_paths: set[str],
) -> tuple[list[str], int]:
    copied_paths: list[str] = []
    skipped_file_count = 0
    for child in sorted(source.iterdir(), key=lambda candidate: candidate.name):
        relative_path = _relative_path(source_root, child)
        if child.is_dir():
            if child.name in _SKIPPED_MATERIALIZE_DIRS:
                continue
            copied, skipped = _copy_directory(
                source_root,
                target_root,
                child,
                forbidden_paths=forbidden_paths,
            )
            copied_paths.extend(copied)
            skipped_file_count += skipped
        elif child.is_file() and not child.is_symlink():
            if _is_forbidden(relative_path, forbidden_paths):
                skipped_file_count += 1
                continue
            _copy_file(child, target_root / relative_path)
            copied_paths.append(relative_path)
        else:
            skipped_file_count += 1
    return copied_paths, skipped_file_count


def _source_path(source_root: Path, include_path: str) -> Path:
    source_root_resolved = source_root.resolve(strict=False)
    candidate = (source_root / include_path).resolve(strict=False)
    if not candidate.is_relative_to(source_root_resolved):
        raise ValueError("include_paths must stay inside the workspace")
    return candidate


def _relative_path(source_root: Path, path: Path) -> str:
    return path.resolve(strict=False).relative_to(
        source_root.resolve(strict=False)
    ).as_posix()


def _is_forbidden(relative_path: str, forbidden_paths: set[str]) -> bool:
    relative = PurePosixPath(relative_path)
    return any(
        relative_path == forbidden
        or PurePosixPath(forbidden) in relative.parents
        for forbidden in forbidden_paths
    )


def _copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _workspace_id(value: str) -> str:
    normalized = _WORKSPACE_ID_RE.sub("_", value.strip().lower()).strip("_")
    if not normalized:
        raise ValueError("workspace_name must contain a stable identifier")
    return f"workspace_{normalized}"


__all__ = [
    "WORKSPACE_CAPABILITIES",
    "WORKSPACE_ISOLATED_RW_CAPABILITY",
    "WORKSPACE_LEASE_CREATE_CAPABILITY",
    "WORKSPACE_MATERIALIZE_CAPABILITY",
    "is_workspace_capability",
    "run_workspace_isolated_rw",
    "run_workspace_lease_create",
    "run_workspace_materialize",
    "validate_workspace_inputs",
]
