"""Apply reviewed native-coding workspace changes back to source."""

from __future__ import annotations

import json
from json import JSONDecodeError
from hashlib import sha256
from pathlib import Path, PurePosixPath
import shutil
from typing import Any, Mapping

from .workspace_files import run_workspace_changed_files
from ..platform.schemas.input_contract import missing_required_input_keys
from ..workspace.artifacts import ArtifactStore


CODING_TASK_APPLY_REVIEWED_DIFF_CAPABILITY = "coding_task.apply_reviewed_diff"


def is_coding_apply_capability(capability_id: str) -> bool:
    return capability_id == CODING_TASK_APPLY_REVIEWED_DIFF_CAPABILITY


def validate_coding_apply_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if capability_id != CODING_TASK_APPLY_REVIEWED_DIFF_CAPABILITY:
        return dict(inputs or {})
    input_mapping = dict(inputs or {})
    for name in ("root", "cwd", "workspace_id"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        input_mapping[name] = value.strip()
    review_handle_id = input_mapping.get("review_handle_id")
    if review_handle_id is not None:
        if not isinstance(review_handle_id, str) or not review_handle_id.strip():
            raise ValueError("review_handle_id must be a non-empty string")
        input_mapping["review_handle_id"] = review_handle_id.strip()
    if "expected_source_digests" not in missing_inputs:
        input_mapping["expected_source_digests"] = _digest_mapping(
            input_mapping.get("expected_source_digests")
        )
    input_mapping["include_paths"] = _relative_path_list(
        input_mapping.get("include_paths", ["."]),
        field_name="include_paths",
    )
    expected_changed_files = input_mapping.get("expected_changed_files")
    if expected_changed_files is not None:
        input_mapping["expected_changed_files"] = _relative_path_list(
            expected_changed_files,
            field_name="expected_changed_files",
        )
    return input_mapping


def run_coding_task_apply_reviewed_diff(
    *, inputs: Mapping[str, Any] | None
) -> dict[str, Any]:
    resolved_inputs = _inputs_with_review_handle(inputs)
    required_inputs = ["root", "cwd", "workspace_id", "expected_source_digests"]
    missing_inputs = missing_required_input_keys(resolved_inputs, required_inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = validate_coding_apply_inputs(
        capability_id=CODING_TASK_APPLY_REVIEWED_DIFF_CAPABILITY,
        inputs=resolved_inputs,
        missing_inputs=missing_inputs,
    )
    changed = run_workspace_changed_files(
        inputs={
            "root": input_mapping["root"],
            "cwd": input_mapping["cwd"],
            "workspace_id": input_mapping["workspace_id"],
            "include_paths": input_mapping["include_paths"],
        }
    )["changed_files"]
    changed_files = [dict(item) for item in changed["changed_files"]]
    expected_changed_files = input_mapping.get("expected_changed_files")
    if expected_changed_files is not None and sorted(expected_changed_files) != sorted(
        item["path"] for item in changed_files
    ):
        return _blocked(
            input_mapping=input_mapping,
            changed_files=changed_files,
            reason="changed_files_mismatch",
        )

    source_root = Path(input_mapping["cwd"]).expanduser()
    workspace_root = _materialized_workspace_path(
        input_mapping["root"],
        input_mapping["workspace_id"],
    )
    pending_copies: list[tuple[Path, Path, str]] = []
    expected_digests = input_mapping["expected_source_digests"]
    for item in changed_files:
        path = _safe_relative_path(item.get("path"))
        status = item.get("status")
        if status == "deleted":
            return _blocked(
                input_mapping=input_mapping,
                changed_files=changed_files,
                reason="deletion_not_supported",
            )
        if status not in {"added", "modified"}:
            return _blocked(
                input_mapping=input_mapping,
                changed_files=changed_files,
                reason="unsupported_change_status",
            )
        if path not in expected_digests:
            return _blocked(
                input_mapping=input_mapping,
                changed_files=changed_files,
                reason="missing_source_digest",
            )
        source_path = _bounded_path(source_root, path)
        workspace_path = _bounded_path(workspace_root, path)
        if not workspace_path.exists() or not workspace_path.is_file() or workspace_path.is_symlink():
            return _blocked(
                input_mapping=input_mapping,
                changed_files=changed_files,
                reason="materialized_file_missing",
            )
        if source_path.is_symlink():
            return _blocked(
                input_mapping=input_mapping,
                changed_files=changed_files,
                reason="symlink_not_supported",
            )
        current_digest = _file_digest(source_path) if source_path.exists() else None
        if current_digest != expected_digests[path]:
            return _blocked(
                input_mapping=input_mapping,
                changed_files=changed_files,
                reason="source_conflict",
            )
        pending_copies.append((workspace_path, source_path, path))

    for workspace_path, source_path, _path in pending_copies:
        source_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(workspace_path, source_path)

    applied_files = [path for _workspace_path, _source_path, path in pending_copies]
    return {
        "kind": "capability_run_result",
        "capability_id": CODING_TASK_APPLY_REVIEWED_DIFF_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_local",
        "reviewed_apply": {
            "status": "applied",
            "workspace_id": input_mapping["workspace_id"],
            "review_handle_id": input_mapping.get("review_handle_id"),
            "changed_files": changed_files,
            "applied_files": applied_files,
            "source_workspace_write": "performed" if applied_files else "not_performed",
            "content_policy": "diff_result_projection",
            "event_append": "not_performed",
        },
    }


def _inputs_with_review_handle(inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    input_mapping = dict(inputs or {})
    handle_id = input_mapping.get("review_handle_id")
    if not isinstance(handle_id, str) or not handle_id:
        return input_mapping
    root = input_mapping.get("root")
    if not isinstance(root, str) or not root:
        raise ValueError("root is required when review_handle_id is used")
    try:
        payload = json.loads(
            ArtifactStore(Path(root).expanduser()).get_content(handle_id)
        )
    except JSONDecodeError as exc:
        raise ValueError("review handle content must be JSON") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("kind") != "native_coding_reviewed_apply_request"
    ):
        raise ValueError(
            "review_handle_id must reference a native coding reviewed apply request"
        )
    input_mapping["review_handle_id"] = handle_id.strip()
    for key in ("workspace_id", "expected_source_digests", "expected_changed_files"):
        if key in payload:
            input_mapping[key] = payload[key]
    if "include_paths" in payload and "include_paths" not in input_mapping:
        input_mapping["include_paths"] = payload["include_paths"]
    return input_mapping


def reviewed_apply_source_digests(
    *, cwd: str, changed_files: list[Mapping[str, Any]]
) -> dict[str, str | None]:
    source_root = Path(cwd).expanduser()
    result: dict[str, str | None] = {}
    for item in changed_files:
        path = _safe_relative_path(item.get("path"))
        source_path = _bounded_path(source_root, path)
        result[path] = _file_digest(source_path) if source_path.exists() else None
    return result


def _blocked(
    *,
    input_mapping: Mapping[str, Any],
    changed_files: list[dict[str, Any]],
    reason: str,
) -> dict[str, Any]:
    return {
        "kind": "capability_run_result",
        "capability_id": CODING_TASK_APPLY_REVIEWED_DIFF_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_local",
        "reviewed_apply": {
            "status": "blocked",
            "workspace_id": input_mapping["workspace_id"],
            "review_handle_id": input_mapping.get("review_handle_id"),
            "changed_files": changed_files,
            "applied_files": [],
            "blocked_reason": reason,
            "source_workspace_write": "not_performed",
            "content_policy": "diff_result_projection",
            "event_append": "not_performed",
        },
    }


def _digest_mapping(value: Any) -> dict[str, str | None]:
    if not isinstance(value, Mapping):
        raise ValueError("expected_source_digests must be an object")
    result: dict[str, str | None] = {}
    for raw_key, raw_digest in value.items():
        path = _safe_relative_path(raw_key)
        if raw_digest is not None and (
            not isinstance(raw_digest, str) or not raw_digest.strip()
        ):
            raise ValueError("expected_source_digests values must be strings or null")
        result[path] = raw_digest.strip() if isinstance(raw_digest, str) else None
    return result


def _relative_path_list(value: Any, *, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list of relative paths")
    return [_safe_relative_path(item, allow_dot=True) for item in value]


def _safe_relative_path(value: Any, *, allow_dot: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("path must be a non-empty relative path")
    candidate = value.strip().replace("\\", "/")
    path = PurePosixPath(candidate)
    if candidate == "." and allow_dot:
        return "."
    if not candidate or candidate == "." or path.is_absolute() or ".." in path.parts:
        raise ValueError("path must stay inside the workspace")
    return candidate


def _materialized_workspace_path(root: str, workspace_id: str) -> Path:
    root_path = Path(root).expanduser()
    candidate = (root_path / "workspaces" / workspace_id).resolve(strict=False)
    workspaces_root = (root_path / "workspaces").resolve(strict=False)
    if not candidate.is_relative_to(workspaces_root):
        raise ValueError("workspace_id must resolve under root/workspaces")
    return candidate


def _bounded_path(root: Path, relative_path: str) -> Path:
    root_resolved = root.resolve(strict=False)
    candidate = (root / relative_path).resolve(strict=False)
    if not candidate.is_relative_to(root_resolved):
        raise ValueError("path must stay inside the workspace")
    return candidate


def _file_digest(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise ValueError("source path must be a regular file")
    return sha256(path.read_bytes()).hexdigest()


__all__ = [
    "CODING_TASK_APPLY_REVIEWED_DIFF_CAPABILITY",
    "is_coding_apply_capability",
    "reviewed_apply_source_digests",
    "run_coding_task_apply_reviewed_diff",
    "validate_coding_apply_inputs",
]
