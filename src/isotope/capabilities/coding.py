"""Native coding capability planning.

This module prepares native coding work for the existing isolated workspace
execution and reviewed apply chain.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


CODING_TASK_PLAN_CAPABILITY = "coding_task.plan"

_ARRAY_INPUTS = ("allowed_paths", "forbidden_paths", "verification_commands")
_NATIVE_CODING_REQUIREMENTS = [
    "policy_granted_writable_workspace",
    "controlled_code_read_search",
    "structured_patch_application",
    "allowlisted_test_execution",
    "artifact_backed_diff_and_changed_files",
    "optional_vcs_adapter",
]


def is_coding_capability(capability_id: str) -> bool:
    return capability_id == CODING_TASK_PLAN_CAPABILITY


def validate_coding_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if not is_coding_capability(capability_id):
        return dict(inputs or {})
    input_mapping = dict(inputs or {})
    for name in ("root", "cwd", "goal"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        input_mapping[name] = value.strip()
    for name in _ARRAY_INPUTS:
        input_mapping[name] = _string_list_input(input_mapping.get(name, []), name)
    return input_mapping


def run_coding_task_plan(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    missing_inputs = _missing_required(inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = validate_coding_inputs(
        capability_id=CODING_TASK_PLAN_CAPABILITY,
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    cwd = Path(input_mapping["cwd"]).expanduser()
    return {
        "kind": "capability_run_result",
        "capability_id": CODING_TASK_PLAN_CAPABILITY,
        "status": "completed",
        "runner_kind": "native_coding_plan",
        "plan": {
            "goal": input_mapping["goal"],
            "cwd_status": "exists" if cwd.exists() else "missing",
            "execution_mode": "isolated_workspace_execution",
            "allowed_path_count": len(input_mapping["allowed_paths"]),
            "forbidden_path_count": len(input_mapping["forbidden_paths"]),
            "verification_command_count": len(input_mapping["verification_commands"]),
            "execution_requirements": list(_NATIVE_CODING_REQUIREMENTS),
            "next_capabilities": [
                "coding_task.execute",
                "coding_task.apply_reviewed_diff",
            ],
        },
    }


def _missing_required(inputs: Mapping[str, Any] | None) -> list[str]:
    input_mapping = inputs or {}
    return [
        name
        for name in ("root", "cwd", "goal")
        if name not in input_mapping or input_mapping.get(name) in (None, "")
    ]


def _string_list_input(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of strings")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name}[{index}] must be a non-empty string")
        result.append(item.strip())
    return result


__all__ = [
    "CODING_TASK_PLAN_CAPABILITY",
    "is_coding_capability",
    "run_coding_task_plan",
    "validate_coding_inputs",
]
