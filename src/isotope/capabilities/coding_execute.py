"""Limited native coding execution loop."""

from __future__ import annotations

import json
from typing import Any, Mapping

from .artifact_outputs import run_artifact_changed_files, run_artifact_diff_summary
from .coding_apply import reviewed_apply_source_digests
from .code_edit import run_code_apply_patch
from .testing import run_test_run
from .tools.terminal import default_terminal_capabilities, validate_argv
from .workspace import run_workspace_materialize
from ..platform.schemas.input_contract import missing_required_input_keys
from ..workspace.artifacts import ArtifactStore


CODING_TASK_EXECUTE_CAPABILITY = "coding_task.execute"


def is_coding_execute_capability(capability_id: str) -> bool:
    return capability_id == CODING_TASK_EXECUTE_CAPABILITY


def validate_coding_execute_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if capability_id != CODING_TASK_EXECUTE_CAPABILITY:
        return dict(inputs or {})
    input_mapping = dict(inputs or {})
    for name in ("root", "cwd", "workspace_id", "goal", "patch", "run_id", "execution_id"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        input_mapping[name] = value if name == "patch" else value.strip()
    if "argv" not in missing_inputs:
        input_mapping["argv"] = validate_argv(input_mapping.get("argv"))
    input_mapping["include_paths"] = _string_list(
        input_mapping.get("include_paths", ["."]),
        field_name="include_paths",
    )
    input_mapping["forbidden_paths"] = _string_list(
        input_mapping.get("forbidden_paths", []),
        field_name="forbidden_paths",
        allow_empty=True,
    )
    input_mapping["allowed_commands"] = _string_list(
        input_mapping.get(
            "allowed_commands",
            default_terminal_capabilities()["allowed_commands"],
        ),
        field_name="allowed_commands",
    )
    input_mapping["timeout_seconds"] = _limited_int(
        input_mapping.get("timeout_seconds", 30),
        field_name="timeout_seconds",
        minimum=1,
        maximum=120,
    )
    input_mapping["max_output_bytes"] = _limited_int(
        input_mapping.get(
            "max_output_bytes",
            default_terminal_capabilities()["max_output_bytes"],
        ),
        field_name="max_output_bytes",
        minimum=1,
        maximum=65536,
    )
    return input_mapping


def run_coding_task_execute(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    required_inputs = [
        "root",
        "cwd",
        "workspace_id",
        "goal",
        "patch",
        "argv",
        "run_id",
        "execution_id",
    ]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = validate_coding_execute_inputs(
        capability_id=CODING_TASK_EXECUTE_CAPABILITY,
        inputs=inputs,
        missing_inputs=missing_inputs,
    )

    materialized = run_workspace_materialize(
        inputs={
            "root": input_mapping["root"],
            "cwd": input_mapping["cwd"],
            "workspace_id": input_mapping["workspace_id"],
            "include_paths": input_mapping["include_paths"],
            "forbidden_paths": input_mapping["forbidden_paths"],
        }
    )["materialized_workspace"]
    workspace_root = materialized["workspace_root"]
    patch_result = run_code_apply_patch(
        inputs={
            "root": input_mapping["root"],
            "cwd": workspace_root,
            "patch": input_mapping["patch"],
        }
    )["patch_result"]
    verification_result = run_test_run(
        inputs={
            "root": input_mapping["root"],
            "cwd": workspace_root,
            "argv": input_mapping["argv"],
            "allowed_commands": input_mapping["allowed_commands"],
            "timeout_seconds": input_mapping["timeout_seconds"],
            "max_output_bytes": input_mapping["max_output_bytes"],
        }
    )["test_result"]
    changed_files_artifact = run_artifact_changed_files(
        inputs=_artifact_inputs(input_mapping)
    )["artifact"]
    diff_summary_artifact = run_artifact_diff_summary(
        inputs=_artifact_inputs(input_mapping)
    )["artifact"]
    changed_files = list(patch_result["changed_files"])
    expected_source_digests = reviewed_apply_source_digests(
        cwd=input_mapping["cwd"],
        changed_files=[
            {"path": path, "status": "modified"} for path in changed_files
        ],
    )
    review_handle = ArtifactStore(input_mapping["root"]).create_artifact(
        input_mapping["run_id"],
        input_mapping["execution_id"],
        "native_coding.reviewed_apply_request",
        "Reviewed native coding apply request",
        json.dumps(
            {
                "kind": "native_coding_reviewed_apply_request",
                "workspace_id": input_mapping["workspace_id"],
                "changed_files": changed_files,
                "expected_changed_files": changed_files,
                "expected_source_digests": expected_source_digests,
                "include_paths": input_mapping["include_paths"],
                "content_policy": "digest_and_path_only",
            },
            sort_keys=True,
        ),
    )

    return {
        "kind": "capability_run_result",
        "capability_id": CODING_TASK_EXECUTE_CAPABILITY,
        "status": "completed",
        "runner_kind": "deterministic_local",
        "coding_execution": {
            "status": (
                "verified"
                if verification_result["status"] == "passed"
                else "needs_revision"
            ),
            "goal": input_mapping["goal"],
            "workspace_id": input_mapping["workspace_id"],
            "workspace_root": workspace_root,
            "step_count": 5,
            "source_workspace_write": "not_performed",
            "codex_delegation": "not_performed",
            "patch_result": _patch_summary(patch_result),
            "verification": _verification_summary(verification_result),
            "artifact_refs": {
                "changed_files": changed_files_artifact["ref"],
                "diff_summary": diff_summary_artifact["ref"],
            },
            "reviewed_apply": {
                "workspace_id": input_mapping["workspace_id"],
                "changed_files": changed_files,
                "expected_source_digests": expected_source_digests,
                "review_handle_id": review_handle.artifact_id,
                "review_handle_ref": review_handle.ref.to_dict(),
                "source_workspace_write": "requires_explicit_apply",
                "content_policy": "digest_and_path_only",
            },
            "event_append": "not_performed",
        },
    }


def _artifact_inputs(input_mapping: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "root": input_mapping["root"],
        "cwd": input_mapping["cwd"],
        "workspace_id": input_mapping["workspace_id"],
        "run_id": input_mapping["run_id"],
        "execution_id": input_mapping["execution_id"],
        "include_paths": input_mapping["include_paths"],
    }


def _patch_summary(patch_result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": patch_result["status"],
        "changed_files": list(patch_result["changed_files"]),
        "file_count": patch_result["file_count"],
        "hunk_count": patch_result["hunk_count"],
        "write_policy": patch_result["write_policy"],
        "content_policy": patch_result["content_policy"],
    }


def _verification_summary(test_result: Mapping[str, Any]) -> dict[str, Any]:
    summary = {
        "status": test_result["status"],
        "argv": list(test_result["argv"]),
        "exit_code": test_result["exit_code"],
        "output_truncated": test_result["output_truncated"],
        "shell": test_result["shell"],
    }
    if "reason_code" in test_result:
        summary["reason_code"] = test_result["reason_code"]
    return summary


def _missing_inputs(
    required_inputs: list[str], inputs: Mapping[str, Any] | None
) -> list[str]:
    return missing_required_input_keys(inputs, required_inputs)


def _string_list(
    value: Any,
    *,
    field_name: str,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ValueError(f"{field_name} must be a non-empty list of strings")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name}[{index}] must be a non-empty string")
        result.append(item.strip())
    return result


def _limited_int(value: Any, *, field_name: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}")
    return value


__all__ = [
    "CODING_TASK_EXECUTE_CAPABILITY",
    "is_coding_execute_capability",
    "run_coding_task_execute",
    "validate_coding_execute_inputs",
]
