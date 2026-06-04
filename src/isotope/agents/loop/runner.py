"""Limited Agent loop goal runner."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable


Planner = Callable[[dict[str, Any]], dict[str, Any]]


def run_agent_loop_until_stop(
    api: Any,
    run_id: str,
    *,
    planner: Planner,
    max_ticks: int,
    budget_basis: str | None = None,
    user_pause: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run limited planner ticks until policy says the goal loop must stop."""
    if isinstance(max_ticks, bool) or not isinstance(max_ticks, int):
        raise ValueError("max_ticks must be a positive integer")
    if max_ticks <= 0:
        raise ValueError("max_ticks must be a positive integer")
    if not callable(planner):
        raise ValueError("planner must be callable")

    ticks: list[dict[str, Any]] = []
    final_policy: dict[str, Any] | None = None
    stop_reason: str | None = None
    status = "stopped"

    while True:
        tick_budget = _tick_budget(
            max_ticks=max_ticks,
            ticks_used=len(ticks),
            budget_basis=budget_basis,
        )
        policy = api.get_agent_loop_tick_policy(
            run_id,
            tick_budget=deepcopy(tick_budget),
            user_pause=deepcopy(user_pause),
        )
        if policy["should_continue"] is not True:
            final_policy = policy
            stop_reason = policy["must_stop_reason"]
            break

        control = api.get_agent_loop_control(run_id)
        planner_output = planner(
            {
                "run_id": run_id,
                "tick_index": len(ticks),
                "control": control,
                "tick_policy": policy,
            }
        )
        tick = api.run_agent_loop_tick(
            run_id,
            planner_output,
            tick_budget=deepcopy(tick_budget),
            user_pause=deepcopy(user_pause),
        )
        ticks.append(tick)
        final_policy = tick["after_policy"]
        stop_reason = tick["stop_reason"]
        if tick["tick_status"] != "executed" or final_policy["should_continue"] is not True:
            break

    return {
        "kind": "agent_loop_goal_run",
        "status": status,
        "run_id": run_id,
        "tick_count": len(ticks),
        "stop_reason": stop_reason,
        "final_policy": final_policy,
        "ticks": ticks,
        "safety": {
            "max_ticks": max_ticks,
            "limited": True,
            "real_llm_provider": False,
            "agent_conversation_interface": False,
        },
    }


def _tick_budget(
    *,
    max_ticks: int,
    ticks_used: int,
    budget_basis: str | None,
) -> dict[str, Any]:
    budget = {
        "max_ticks": max_ticks,
        "ticks_used": ticks_used,
    }
    if budget_basis is not None:
        if not isinstance(budget_basis, str) or not budget_basis:
            raise ValueError("budget_basis must be a non-empty string")
        budget["budget_basis"] = budget_basis
    return budget
