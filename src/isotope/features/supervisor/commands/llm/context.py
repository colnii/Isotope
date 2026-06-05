"""LLM planner context payload helpers for Supervisor loop commands."""

from __future__ import annotations

from typing import Any

from isotope.features.supervisor.commands.supervisor_action import (
    set_supervisor_action_payload,
    set_supervisor_followup_action_payload,
    supervisor_followup_action_from_payload,
)


def planner_context_payload(
    args: Any,
    report: Any,
    *,
    action_report: Any | None = None,
    active_goals: list[dict[str, Any]],
    explicit_goal: str | None,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    context_report = action_report if action_report is not None else report
    payload = {
        "recent_context_results": api._recent_context_results(args, context_report),
        "recent_decision_answers": api._decision_answer_dicts(args),
    }
    capacity_payload = api._loop_capacity_decision_payload(
        args,
        active_goals=active_goals,
        explicit_goal=explicit_goal,
    )
    if capacity_payload is not None:
        payload["capacity_decisions"] = capacity_payload["capacity_decisions"]
        payload["capacity_call_specs"] = capacity_payload["capacity_call_specs"]
        payload["capacity_decision_status"] = {
            key: value
            for key, value in capacity_payload.items()
            if key not in {"capacity_decisions", "capacity_call_specs"}
        }
    payload["worker_reviews"] = api._worker_review_context(args)
    payload["delete_worktree_candidates"] = api._delete_worktree_candidate_payloads(args)
    return payload


def maybe_replan_after_context_request(
    args: Any,
    report: Any,
    payload: dict[str, Any],
    *,
    api: Any | None = None,
) -> bool:
    if api is None:
        from isotope.features.supervisor import runner as api

    executed = payload.get("executed")
    context_result = _executed_request_context_result(executed)
    if context_result is None:
        return False
    if isinstance(executed, dict) and executed.get("skipped"):
        return False
    if isinstance(context_result, dict):
        recent = list(payload.get("recent_context_results") or [])
        recent.append(context_result)
        payload["recent_context_results"] = recent[-3:]
    followup_action = api._decide_action_with_llm(
        args,
        report,
        payload,
    )
    set_supervisor_followup_action_payload(payload, followup_action)
    followup_payload = {
        **payload,
    }
    set_supervisor_action_payload(
        followup_payload,
        supervisor_followup_action_from_payload(payload),
    )
    payload["followup_executed"] = api._execute_llm_action(
        args,
        report,
        followup_payload,
    )
    return True


def _executed_request_context_result(executed: Any) -> dict[str, Any] | None:
    if not isinstance(executed, dict):
        return None
    if executed.get("kind") == "request_context":
        context_result = executed.get("context")
        return context_result if isinstance(context_result, dict) else None
    if (
        executed.get("kind") != "call_capacity"
        or executed.get("capacity_id") != "supervisor.codex_operation"
        or executed.get("operation") != "request_context"
    ):
        return None
    agent_loop = executed.get("agent_loop")
    if not isinstance(agent_loop, dict):
        return None
    step_result = agent_loop.get("step_result")
    if not isinstance(step_result, dict):
        return None
    action_result = step_result.get("action_result")
    if not isinstance(action_result, dict):
        return None
    capability_run = action_result.get("capability_run")
    if not isinstance(capability_run, dict):
        return None
    operation_result = capability_run.get("operation_result")
    if not isinstance(operation_result, dict):
        return None
    context_result = operation_result.get("context_result")
    return context_result if isinstance(context_result, dict) else None
