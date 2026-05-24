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


def _run_agent_loop_tick_driver_trace(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    api = InProcessServer(root)

    session = api.create_session()
    run = api.create_run(session["session_id"], goal="agent loop tick driver trace")
    run_id = run["run_id"]

    before_control = api.get_agent_loop_control(run_id)
    executed_result = api.run_agent_loop_tick(
        run_id,
        _planner_output(
            before_control,
            step="call_capability",
            request={"capability_id": "artifact.review"},
        ),
        tick_budget={
            "max_ticks": 2,
            "ticks_used": 0,
            "budget_basis": "demo:tick_driver",
        },
    )
    budget_before_events = list(api.get_events(run_id))
    budget_stopped = api.run_agent_loop_tick(
        run_id,
        None,
        tick_budget={
            "max_ticks": 2,
            "ticks_used": 2,
            "budget_basis": "demo:max_ticks",
        },
    )
    budget_event_delta = len(api.get_events(run_id)) - len(budget_before_events)
    pause_before_events = list(api.get_events(run_id))
    user_pause_stopped = api.run_agent_loop_tick(
        run_id,
        None,
        user_pause={
            "user_paused": True,
            "pause_basis": "demo:operator_pause",
        },
    )
    pause_event_delta = len(api.get_events(run_id)) - len(pause_before_events)

    executed_tick = _executed_tick_summary(executed_result)
    stopped_ticks = [
        _stopped_tick_case("budget_exhausted", budget_stopped, budget_event_delta),
        _stopped_tick_case("user_pause", user_pause_stopped, pause_event_delta),
    ]
    app_friction: list[dict[str, Any]] = []
    tick_driver_trace_ok = (
        executed_tick["tick_status"] == "executed"
        and executed_tick["selected_step"] == "call_capability"
        and executed_tick["before_policy"]["phase"] == "ready"
        and executed_tick["after_policy"]["phase"] == "ready"
        and executed_tick["after_policy"]["tick_budget"]["ticks_used"] == 1
        and stopped_ticks[0]["stop_reason"] == "tick_budget_exhausted"
        and stopped_ticks[0]["event_delta"] == 0
        and stopped_ticks[1]["stop_reason"] == "user_paused"
        and stopped_ticks[1]["event_delta"] == 0
        and app_friction == []
    )

    return {
        "scenario": "agent-loop-tick-driver-trace",
        "session_id": session["session_id"],
        "run_id": run_id,
        "run_status": api.get_run_state(run_id).status,
        "transport": "in_process",
        "tick_driver_trace_ok": tick_driver_trace_ok,
        "executed_tick": executed_tick,
        "stopped_ticks": stopped_ticks,
        "app_friction": app_friction,
        "app_friction_count": len(app_friction),
        "model_status": "not_used",
        "scheduler_status": "not_used",
        "provider_status": "not_used",
        "network_listener_status": "not_used",
        "filesystem_mutation_status": "not_used",
        "memory_status": "boundary_only",
        "memory_query_status": "not_enabled",
        "replay_status": "not_applicable",
        "checkpoint_status": "not_applicable",
        "next_development_step": (
            "Use this readable tick-driver trace before wiring a Supervisor "
            "handoff into agent-loop-driven execution."
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


def _planner_output(
    control: dict[str, Any],
    *,
    step: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    return {
        "planner_run_id": "planner_run_tick_driver_demo",
        "basis": {
            "run_id": control["run_id"],
            "last_event_id": control["last_event_id"],
        },
        "decision": {
            "step": step,
            "request": request,
        },
    }


def _executed_tick_summary(result: dict[str, Any]) -> dict[str, Any]:
    planner_result = result["planner_result"]
    step_result = planner_result["step_result"]
    action_result = step_result["action_result"]
    return {
        "tick_status": result["tick_status"],
        "selected_step": planner_result["selected_step"],
        "step_status": step_result["status"],
        "before_policy": _policy_summary(result["before_policy"]),
        "after_policy": _policy_summary(result["after_policy"]),
        "artifact_ref": dict(action_result["artifact_ref"]),
        "artifact_summary": action_result["artifact_summary"],
    }


def _stopped_tick_case(
    case_id: str,
    result: dict[str, Any],
    event_delta: int,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "tick_status": result["tick_status"],
        "stop_reason": result["stop_reason"],
        "before_policy": _policy_summary(result["before_policy"]),
        "after_policy": _policy_summary(result["after_policy"]),
        "event_delta": event_delta,
    }


def _policy_summary(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "phase": policy["phase"],
        "should_continue": policy["should_continue"],
        "must_stop_reason": policy["must_stop_reason"],
        "requires_human": policy["requires_human"],
        "max_next_tick_kind": policy["max_next_tick_kind"],
        "tick_budget": policy["tick_budget"],
        "user_pause": policy["user_pause"],
    }
