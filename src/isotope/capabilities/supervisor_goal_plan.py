"""Supervisor goal-planning capability runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..features.supervisor.llm_action.llm_pool import resolve_summary_provider_from_env
from ..features.supervisor.planner.goal_planner import plan_supervisor_goals
from .supervisor import (
    LEGACY_SUPERVISOR_STATE_ROOT_INPUT,
    SUPERVISOR_STATE_ROOT_INPUT,
    normalize_supervisor_state_root_inputs,
)


SUPERVISOR_GOAL_PLAN_CAPABILITY = "supervisor.goal_plan"


def is_supervisor_goal_plan_capability(capability_id: str) -> bool:
    return capability_id == SUPERVISOR_GOAL_PLAN_CAPABILITY


def validate_supervisor_goal_plan_inputs(
    *,
    capability_id: str,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    if not is_supervisor_goal_plan_capability(capability_id):
        return dict(inputs or {})
    return _validate_supervisor_goal_plan_inputs(
        inputs=normalize_supervisor_state_root_inputs(inputs),
        missing_inputs=missing_inputs,
    )


def run_supervisor_goal_plan(*, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    inputs = normalize_supervisor_state_root_inputs(inputs)
    required_inputs = [SUPERVISOR_STATE_ROOT_INPUT, "cwd", "goal"]
    missing_inputs = _missing_inputs(required_inputs, inputs)
    if missing_inputs:
        raise ValueError("missing required capability inputs: " + ", ".join(missing_inputs))
    input_mapping = _validate_supervisor_goal_plan_inputs(
        inputs=inputs,
        missing_inputs=missing_inputs,
    )
    provider = resolve_summary_provider_from_env(agent_name="supervisor")
    goal_plan = plan_supervisor_goals(
        root=Path(input_mapping["cwd"]),
        codex_home=Path(input_mapping[SUPERVISOR_STATE_ROOT_INPUT]),
        provider=provider,
        user_goal=input_mapping["goal"],
        write=input_mapping["write"],
        limit=input_mapping["limit"],
        planning_trigger="capacity",
    )
    return {
        "kind": "capability_run_result",
        "capability_id": SUPERVISOR_GOAL_PLAN_CAPABILITY,
        "status": "completed",
        "runner_kind": "supervisor_goal_plan",
        "goal_plan": goal_plan,
    }


def _validate_supervisor_goal_plan_inputs(
    *,
    inputs: Mapping[str, Any] | None,
    missing_inputs: list[str],
) -> dict[str, Any]:
    input_mapping = inputs or {}
    for name in (SUPERVISOR_STATE_ROOT_INPUT, "cwd", "goal"):
        if name in missing_inputs:
            continue
        value = input_mapping.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")

    limit = input_mapping.get("limit", 3)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")

    write = input_mapping.get("write", False)
    if not isinstance(write, bool):
        raise ValueError("write must be a boolean")

    normalized = {
        key: value
        for key, value in input_mapping.items()
        if key != LEGACY_SUPERVISOR_STATE_ROOT_INPUT
    }
    normalized["limit"] = limit
    normalized["write"] = write
    return normalized


def _missing_inputs(required: list[str], inputs: Mapping[str, Any] | None) -> list[str]:
    return [
        name
        for name in required
        if inputs is None or name not in inputs or inputs.get(name) in (None, "")
    ]
