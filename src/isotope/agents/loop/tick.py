"""Agent loop one-tick driver."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def run_agent_loop_tick(
    api: Any,
    run_id: str,
    planner_output: dict[str, Any] | None,
    *,
    tick_budget: dict[str, Any] | None = None,
    user_pause: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run at most one planner-selected step, honoring app-owned tick controls."""
    before_policy = api.get_agent_loop_tick_policy(
        run_id,
        tick_budget=deepcopy(tick_budget),
        user_pause=deepcopy(user_pause),
    )
    if before_policy["should_continue"] is not True:
        return {
            "tick_status": "stopped",
            "stop_reason": before_policy["must_stop_reason"],
            "before_policy": before_policy,
            "planner_result": None,
            "after_policy": before_policy,
        }
    if not isinstance(planner_output, dict):
        raise ValueError("planner_output must be a dict when tick should continue")

    planner_result = api.run_agent_loop_planner_step(run_id, planner_output)
    after_policy = api.get_agent_loop_tick_policy(
        run_id,
        tick_budget=_advance_tick_budget(tick_budget),
        user_pause=deepcopy(user_pause),
    )
    return {
        "tick_status": "executed",
        "stop_reason": after_policy["must_stop_reason"],
        "before_policy": before_policy,
        "planner_result": planner_result,
        "after_policy": after_policy,
    }


def _advance_tick_budget(
    tick_budget: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if tick_budget is None:
        return None
    advanced = deepcopy(tick_budget)
    ticks_used = advanced.get("ticks_used", 0)
    if isinstance(ticks_used, bool) or not isinstance(ticks_used, int):
        return advanced
    advanced["ticks_used"] = ticks_used + 1
    return advanced
