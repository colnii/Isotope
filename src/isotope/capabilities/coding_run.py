"""Product-level native coding capability metadata."""

from __future__ import annotations

from typing import Any, Mapping


CODING_TASK_RUN_CAPABILITY = "coding_task.run"


def is_coding_run_capability(capability_id: str) -> bool:
    return capability_id == CODING_TASK_RUN_CAPABILITY


def validate_coding_run_inputs(inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    input_mapping = dict(inputs or {})
    goal = input_mapping.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("goal must be a non-empty string")
    input_mapping["goal"] = goal.strip()
    return input_mapping


def reject_direct_coding_task_run() -> dict[str, Any]:
    raise ValueError("coding_task.run must be routed through Supervisor agent loop")
