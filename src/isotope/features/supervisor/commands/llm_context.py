"""LLM planner context payload helpers for Supervisor loop commands."""

from __future__ import annotations

from typing import Any


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
