"""Materialized workspace file summary and release capabilities."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Any, Mapping

from ..platform.schemas.input_contract import missing_required_input_keys


WORKSPACE_CHANGED_FILES_CAPABILITY = "workspace.changed_files"
WORKSPACE_RELEASE_CAPABILITY = "workspace.release"
WORKSPACE_FILE_CAPABILITIES = frozenset(
    {WORKSPACE_CHANGED_FILES_CAPABILITY, WORKSPACE_RELEASE_CAPABILITY}
)

_STABLE_WORKSPACE_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_SKIPPED_DIRS = frozenset(
    {".git", ".hg", ".mypy_cache", ".pytest_cache", ".venv", ".worktrees", "__pycache__"}
)


def is_workspace_file_capability(capability_id: str) -> bool:
    return capability_id in WORKSPACE_FILE_CAPABILITIES


def validate_workspace_file_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if capability_id == WORKSPACE_CHANGED_FILES_CAPABILITY:
        return _validate_changed_files_inputs(
            inputs=inputs,
            missing_inputs=missing_inputs,
        )
    if capability_id == WORKSPACE_RELEASE_CAPABILITY:
        return _validate_release_inputs(inputs=inputs, missing_inputs=missing_inputs)
    return dict(inputs or {})


def run_workspace_changed_files(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    required_inputs = ["root", "cwd", "workspace_id"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_changed_files_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    source_root = Path(input_mapping["cwd"]).expanduser()
    workspace_root = _materialized_workspace_path(
        input_mapping["root"],
        input_mapping["workspace_id"],
    )
    _require_existing_source(source_root)
    _require_existing_materialized_workspace(workspace_root)

    include_paths = input_mapping["include_paths"]
    source_files = _collect_files(source_root, include_paths)
    workspace_files = _collect_files(workspace_root, include_paths)
    changed_files: list[dict[str, str]] = []
    for path in sorted(set(source_files) | set(workspace_files)):
        source_digest = source_files.get(path)
        workspace_digest = workspace_files.get(path)
        if source_digest == workspace_digest:
            continue
        if source_digest is None:
            status = "added"
        elif workspace_digest is None:
            status = "deleted"
        else:
            status = "modified"
        changed_files.append({"path": path, "status": status})

    return {
        "kind": "capability_run_result",
        "capability_id": WORKSPACE_CHANGED_FILES_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_projection",
        "changed_files": {
            "status": "clean" if not changed_files else "changed",
            "workspace_id": input_mapping["workspace_id"],
            "changed_file_count": len(changed_files),
            "changed_files": changed_files,
            "include_paths": list(include_paths),
            "artifact_write": "artifact_write_action_handoff",
            "content_policy": "diff_result_projection",
        },
    }


def run_workspace_release(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    required_inputs = ["root", "workspace_id"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_release_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    workspace_root = _materialized_workspace_path(
        input_mapping["root"],
        input_mapping["workspace_id"],
    )
    _require_existing_materialized_workspace(workspace_root)
    shutil.rmtree(workspace_root)
    return {
        "kind": "capability_run_result",
        "capability_id": WORKSPACE_RELEASE_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_local",
        "released_workspace": {
            "status": "released",
            "workspace_id": input_mapping["workspace_id"],
            "removed_path": str(workspace_root),
            "event_append": "state_event_append_handoff",
            "delete_policy": "deletes_only_materialized_workspace",
        },
    }


def _missing_inputs(
    required_inputs: list[str], inputs: Mapping[str, Any] | None
) -> list[str]:
    return missing_required_input_keys(inputs, required_inputs)


def _validate_changed_files_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = _validate_common_workspace_file_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
        fields=("root", "cwd", "workspace_id"),
    )
    include_paths = input_mapping.get("include_paths", ["."])
    if include_paths is None:
        include_paths = ["."]
    input_mapping["include_paths"] = _safe_relative_paths(include_paths, "include_paths")
    return input_mapping


def _validate_release_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    return _validate_common_workspace_file_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
        fields=("root", "workspace_id"),
    )


def _validate_common_workspace_file_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
    fields: tuple[str, ...],
) -> dict[str, Any]:
    input_mapping = dict(inputs or {})
    for name in fields:
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        input_mapping[name] = value.strip()
    workspace_id = input_mapping.get("workspace_id")
    if isinstance(workspace_id, str) and not _STABLE_WORKSPACE_ID_RE.fullmatch(workspace_id):
        raise ValueError("workspace_id must be a stable lowercase identifier")
    return input_mapping


def _safe_relative_paths(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list of relative paths")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name}[{index}] must be a non-empty relative path")
        candidate = item.strip().replace("\\", "/")
        path = PurePosixPath(candidate)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"{field_name}[{index}] must stay inside the workspace")
        if candidate in {"", "."}:
            result.append(".")
        else:
            result.append(candidate)
    return result


def _materialized_workspace_path(root: str, workspace_id: str) -> Path:
    root_path = Path(root).expanduser()
    candidate = (root_path / "workspaces" / workspace_id).resolve(strict=False)
    workspaces_root = (root_path / "workspaces").resolve(strict=False)
    if not candidate.is_relative_to(workspaces_root):
        raise ValueError("workspace_id must resolve under root/workspaces")
    return candidate


def _require_existing_source(path: Path) -> None:
    if not path.exists() or not path.is_dir():
        raise ValueError("cwd must be an existing source workspace")


def _require_existing_materialized_workspace(path: Path) -> None:
    if not path.exists() or not path.is_dir():
        raise ValueError("materialized workspace is required")


def _collect_files(root: Path, include_paths: list[str]) -> dict[str, str]:
    files: dict[str, str] = {}
    for include_path in include_paths:
        source = _limited_path(root, include_path)
        if not source.exists():
            continue
        if source.is_file() and not source.is_symlink():
            files[_relative_path(root, source)] = _file_digest(source)
            continue
        if source.is_dir():
            for child in _iter_files(source):
                files[_relative_path(root, child)] = _file_digest(child)
    return files


def _limited_path(root: Path, relative_path: str) -> Path:
    root_resolved = root.resolve(strict=False)
    candidate = (root / relative_path).resolve(strict=False)
    if not candidate.is_relative_to(root_resolved):
        raise ValueError("include_paths must stay inside the workspace")
    return candidate


def _iter_files(root: Path):
    for child in sorted(root.iterdir(), key=lambda candidate: candidate.name):
        if child.is_dir():
            if child.name not in _SKIPPED_DIRS:
                yield from _iter_files(child)
        elif child.is_file() and not child.is_symlink():
            yield child


def _relative_path(root: Path, path: Path) -> str:
    return path.resolve(strict=False).relative_to(root.resolve(strict=False)).as_posix()


def _file_digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


__all__ = [
    "WORKSPACE_CHANGED_FILES_CAPABILITY",
    "WORKSPACE_FILE_CAPABILITIES",
    "WORKSPACE_RELEASE_CAPABILITY",
    "is_workspace_file_capability",
    "run_workspace_changed_files",
    "run_workspace_release",
    "validate_workspace_file_inputs",
]
