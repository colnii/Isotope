"""Agent-loop tick policy demo scenarios."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .runtime.in_process import InProcessServer


def _run_agent_loop_tick_policy_trace(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    api = InProcessServer(root)

    session = api.create_session()
    run = api.create_run(session["session_id"], goal="agent loop tick policy trace")
    run_id = run["run_id"]

    ready_policy = api.get_agent_loop_tick_policy(run_id)
    user_pause_policy = api.get_agent_loop_tick_policy(
        run_id,
        user_pause={
            "user_paused": True,
            "pause_basis": "demo:operator_pause",
        },
    )
    budget_policy = api.get_agent_loop_tick_policy(
        run_id,
        tick_budget={
            "max_ticks": 2,
            "ticks_used": 2,
            "budget_basis": "demo:max_ticks",
        },
    )

    pending = api.run_agent_loop_step(
        run_id,
        {
            "step": "submit_approval_gated_action",
            "intent": {
                "action": "call_tool",
                "tool": "write_artifact_tool",
                "text": "agent loop tick policy trace final artifact",
            },
        },
    )
    approval_policy = api.get_agent_loop_tick_policy(run_id)
    approval_id = pending["action_result"]["approval_id"]
    api.run_agent_loop_step(
        run_id,
        {
            "step": "resolve_approval",
            "approval_id": approval_id,
            "resolution": {
                "resolution": "approved",
                "reason": "tick policy trace demo",
                "resolver": "developer_demo",
            },
        },
    )
    completed_policy = api.get_agent_loop_tick_policy(run_id)

    tick_policies = [
        _policy_case("ready_continue", ready_policy),
        _policy_case("user_pause", user_pause_policy),
        _policy_case("budget_exhausted", budget_policy),
        _policy_case("awaiting_approval", approval_policy),
        _policy_case("completed", completed_policy),
    ]
    ready_continue_ok = ready_policy["should_continue"] is True
    user_pause_stop_reason = user_pause_policy["must_stop_reason"]
    budget_stop_reason = budget_policy["must_stop_reason"]
    approval_stop_reason = approval_policy["must_stop_reason"]
    completed_stop_reason = completed_policy["must_stop_reason"]
    app_friction: list[dict[str, Any]] = []
    tick_policy_trace_ok = (
        ready_continue_ok
        and user_pause_stop_reason == "user_paused"
        and budget_stop_reason == "tick_budget_exhausted"
        and approval_stop_reason == "awaiting_approval"
        and completed_stop_reason == "completed"
        and app_friction == []
    )

    return {
        "scenario": "agent-loop-tick-policy-trace",
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": api.get_run_state(run_id).status,
        "transport": "in_process",
        "tick_policy_trace_ok": tick_policy_trace_ok,
        "tick_policies": tick_policies,
        "ready_continue_ok": ready_continue_ok,
        "user_pause_stop_reason": user_pause_stop_reason,
        "budget_stop_reason": budget_stop_reason,
        "approval_stop_reason": approval_stop_reason,
        "completed_stop_reason": completed_stop_reason,
        "app_friction": app_friction,
        "app_friction_count": len(app_friction),
        "model_status": "not_used",
        "scheduler_status": "not_used",
        "provider_status": "not_used",
        "network_listener_status": "not_used",
        "filesystem_mutation_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
        "next_development_step": (
            "Use this readable tick-policy trace as the handoff before wiring any "
            "Supervisor path to agent-loop-driven execution."
        ),
    }


def _policy_case(case_id: str, policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "phase": policy["phase"],
        "should_continue": policy["should_continue"],
        "must_stop_reason": policy["must_stop_reason"],
        "requires_human": policy["requires_human"],
        "max_next_tick_kind": policy["max_next_tick_kind"],
        "next_actions": list(policy["next_actions"]),
        "blocked_reason_codes": list(policy["blocked_reason_codes"]),
    }
