"""Agent-loop tick policy demo scenarios."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ...runtime.in_process import InProcessServer


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
        "memory_status": "active",
        "memory_query_status": "unavailable",
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

    executed_tick = _executed_tick_result(executed_result)
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
        "memory_status": "active",
        "memory_query_status": "unavailable",
        "replay_status": "not_applicable",
        "checkpoint_status": "not_applicable",
        "next_development_step": (
            "Use this readable tick-driver trace before wiring a Supervisor "
            "handoff into agent-loop-driven execution."
        ),
    }


def _run_supervisor_capacity_handoff_trace(root: Path) -> dict[str, Any]:
    from ...features.supervisor.commands.handlers.capacity import build_supervisor_capacity_plan

    root.mkdir(parents=True, exist_ok=True)
    plan = build_supervisor_capacity_plan(
        goal="Supervisor capacity handoff trace",
        provider=_FixtureCapacityProvider(),
        state_root=root / "supervisor-capacity-handoff-state",
        execute_agent_loop=True,
    )
    agent_loop = plan["agent_loop"]
    raw_tick_result = agent_loop["tick_result"]
    planner_result = raw_tick_result["planner_result"]
    step_result = planner_result["step_result"]
    action_result = step_result["action_result"]
    persisted_policy = agent_loop["tick_policy_after"]
    tick_result = {
        "tick_status": raw_tick_result["tick_status"],
        "planner_status": planner_result["planner_status"],
        "selected_step": planner_result["selected_step"],
        "step_status": step_result["status"],
        "artifact_ref": dict(action_result["artifact_ref"]),
        "artifact_summary": action_result["artifact_summary"],
        "capability_run_status": action_result["capability_run"]["status"],
        "before_policy": _policy_summary(raw_tick_result["before_policy"]),
        "after_policy": _policy_summary(raw_tick_result["after_policy"]),
    }
    capacity_decision = plan["supervisor_decision"]
    supervisor_action = {
        "kind": "call_capacity",
        "capacity_id": capacity_decision["capacity_id"],
    }
    app_friction: list[dict[str, Any]] = []
    capacity_handoff_trace_ok = (
        plan["status"] == "ok"
        and capacity_decision["next_action"] == "call_capacity"
        and capacity_decision["can_execute_agent_loop"] is True
        and agent_loop["planner_output"]["selected_step"] == "call_capability"
        and tick_result["tick_status"] == "executed"
        and tick_result["planner_status"] == "accepted"
        and tick_result["selected_step"] == "call_capability"
        and tick_result["step_status"] == "completed"
        and tick_result["after_policy"]["must_stop_reason"] == "tick_budget_exhausted"
        and persisted_policy["phase"] == "ready"
        and persisted_policy["must_stop_reason"] is None
        and app_friction == []
    )
    return {
        "scenario": "supervisor-capacity-handoff-trace",
        "session_id": agent_loop["session_id"],
        "run_id": agent_loop["run_id"],
        "run_status": "running",
        "transport": "in_process",
        "capacity_handoff_trace_ok": capacity_handoff_trace_ok,
        "supervisor_action": supervisor_action,
        "capacity_decision": {
            "kind": capacity_decision["kind"],
            "next_action": capacity_decision["next_action"],
            "capacity_id": capacity_decision["capacity_id"],
            "can_execute_agent_loop": capacity_decision["can_execute_agent_loop"],
            "reason": capacity_decision["reason"],
        },
        "planner_output": dict(agent_loop["planner_output"]),
        "tick_result": tick_result,
        "persisted_run_policy": _policy_summary(persisted_policy),
        "handoff": dict(agent_loop["handoff"]),
        "app_friction": app_friction,
        "app_friction_count": len(app_friction),
        "model_status": "not_used",
        "scheduler_status": "not_used",
        "provider_status": "fixture_only",
        "network_listener_status": "not_used",
        "memory_status": "active",
        "memory_query_status": "unavailable",
        "replay_status": "not_applicable",
        "checkpoint_status": "not_applicable",
        "next_development_step": (
            "Use this Supervisor capacity handoff trace as the readable proof "
            "before adding broader CLI smoke coverage."
        ),
    }


def _run_supervisor_capacity_dashboard_smoke(root: Path) -> dict[str, Any]:
    from ...features.supervisor.commands.handlers.capacity import (
        build_supervisor_capacity_plan,
        capacity_call_specs,
        execute_capacity_action,
    )
    from ...features.supervisor.web import build_dashboard_web_payload
    from ...platform.state.memory_store import FileMemoryStore

    root.mkdir(parents=True, exist_ok=True)
    goal = "Supervisor capacity dashboard smoke"
    plan = build_supervisor_capacity_plan(
        goal=goal,
        provider=_FixtureCapacityProvider(),
        state_root=root / "capacity-dashboard-state",
        execute_agent_loop=False,
    )
    capacity_decision = plan["supervisor_decision"]
    action = {
        "kind": "call_capacity",
        "capacity_id": capacity_decision["capacity_id"],
        "reason": capacity_decision["reason"],
    }
    action_payload = {
        "capacity_decisions": [capacity_decision],
        "capacity_call_specs": capacity_call_specs(plan, goal=goal),
    }
    executed = execute_capacity_action(
        SimpleNamespace(codex_home=str(root), name="capa"),
        action,
        action_payload,
    )
    records = [
        record
        for record in FileMemoryStore(root).list_records(scope="run")
        if record.content.get("kind") == "capacity_call"
    ]
    memory_record = records[-1]
    dashboard_payload = build_dashboard_web_payload(
        _EmptyDashboardReport(),
        codex_home=root,
        workspace_cwd=root,
        state_snapshot=_empty_state_snapshot(),
    )
    workers = {
        worker["name"]: worker
        for worker in dashboard_payload["multi_worker"]["workers"]
    }
    dashboard_recent = workers["capa"]["recent_capacity_result"]
    execution_summary = dict(executed["agent_loop_result"])
    memory_summary = dict(memory_record.content["agent_loop_result"])
    dashboard_summary = dict(dashboard_recent["agent_loop_result"])
    app_friction: list[dict[str, Any]] = []
    capacity_dashboard_smoke_ok = (
        executed["kind"] == "call_capacity"
        and memory_record.content["capacity_id"] == "artifact.review"
        and dashboard_recent["capacity_id"] == "artifact.review"
        and execution_summary == memory_summary == dashboard_summary
        and dashboard_payload["multi_worker"]["summary"]["capacity_calls_total"] == 1
        and app_friction == []
    )
    return {
        "scenario": "supervisor-capacity-dashboard-smoke",
        "transport": "in_process",
        "capacity_dashboard_smoke_ok": capacity_dashboard_smoke_ok,
        "executed": {
            "kind": executed["kind"],
            "capacity_id": executed["capacity_id"],
            "agent_loop_result": execution_summary,
        },
        "memory_record": {
            "record_id": memory_record.memory_id,
            "capacity_id": memory_record.content["capacity_id"],
            "agent_loop_result": memory_summary,
        },
        "dashboard_recent_capacity_result": dashboard_recent,
        "dashboard_capacity_calls_total": dashboard_payload["multi_worker"]["summary"][
            "capacity_calls_total"
        ],
        "app_friction": app_friction,
        "app_friction_count": len(app_friction),
        "model_status": "not_used",
        "scheduler_status": "not_used",
        "provider_status": "fixture_only",
        "network_listener_status": "not_used",
        "memory_status": "capacity_record_persisted",
        "next_development_step": (
            "Use the supervised_execution read model before wiring capacity "
            "summaries to live scheduling or real provider loops."
        ),
    }


class _EmptyDashboardReport:
    generated_at = "2026-05-27T00:00:00Z"
    sessions: list[Any] = []

    class recommendation:
        @staticmethod
        def to_dict() -> dict[str, Any]:
            return {
                "label": "No action",
                "action": "monitor",
                "priority": "low",
                "target_session_id": None,
            }


def _empty_state_snapshot() -> dict[str, Any]:
    return {
        "status": "ok",
        "kind": "supervisor_state_snapshot",
        "schema_version": 1,
        "summary": {
            "active_goals": 0,
            "goals_done": 0,
            "goals_blocked": 0,
            "goals_needs_user": 0,
            "active_decisions": 0,
            "failed_lanes": 0,
            "worker_events": 0,
            "notifications": 0,
            "unread_notifications": 0,
        },
        "active_goals": [],
        "active_decisions": [],
        "failed_lanes": [],
        "recent_worker_events": [],
        "notifications": {"total": 0, "unread": 0, "recent": []},
    }


class _FixtureCapacityProvider:
    provider = "fixture"
    model = "capacity-handoff-demo"

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> Any:
        from ...llm.provider import LLMResponse

        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=(
                '{"capacity_id":"artifact.review","arguments":{},'
                '"confidence":0.91,"rationale":"low risk review"}'
            ),
            finish_reason="stop",
            usage={"prompt_tokens": 0, "completion_tokens": 0},
            raw={},
        )


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


def _executed_tick_result(result: dict[str, Any]) -> dict[str, Any]:
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
