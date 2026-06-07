"""Payload assembly pipeline for supervise/loop."""

from __future__ import annotations

import argparse
from typing import Any

def _runner_api(api: Any | None) -> Any:
    if api is not None:
        return api
    from isotope.features.supervisor import runner

    return runner


def supervise_payload(
    args: argparse.Namespace,
    report: Any,
    *,
    iteration: int,
    auto_adopted: list[dict[str, str]] | None = None,
    auto_retried_workers: list[dict[str, Any]] | None = None,
    goal_updates: list[dict[str, Any]] | None = None,
    merge_promotions: list[dict[str, Any]] | None = None,
    cleanup_archived: list[dict[str, Any]] | None = None,
    cleanup_deleted_worktrees: list[dict[str, Any]] | None = None,
    decision_timeout_alerts: list[dict[str, Any]] | None = None,
    precomputed_auto_action: dict[str, Any] | None = None,
    precomputed_executed: dict[str, Any] | None = None,
    api: Any | None = None,
) -> dict[str, Any]:
    api = _runner_api(api)
    base = api._build_supervise_base_payload(
        args,
        report,
        iteration=iteration,
        auto_adopted=auto_adopted,
        auto_retried_workers=auto_retried_workers,
        goal_updates=goal_updates,
        merge_promotions=merge_promotions,
        cleanup_archived=cleanup_archived,
        cleanup_deleted_worktrees=cleanup_deleted_worktrees,
        decision_timeout_alerts=decision_timeout_alerts,
    )
    payload = base.payload
    action_report = base.action_report
    active_goals = base.active_goals
    explicit_goal = base.explicit_goal
    goal_replenishment = base.goal_replenishment
    worker_reviews: dict[str, Any] | None = None
    if args.llm_action or args.llm_execute:
        llm_context = api._planner_context_payload(
            args,
            report,
            action_report=action_report,
            active_goals=active_goals,
            explicit_goal=explicit_goal,
        )
        payload.update(llm_context)
        worker_reviews = llm_context["worker_reviews"]
    planning = api._append_supervise_planning_payload(
        args,
        payload,
        report,
        active_goals=active_goals,
        goal_updates=goal_updates,
        goal_replenishment=goal_replenishment,
        worker_reviews=worker_reviews,
    )
    fanout_status = planning.fanout_status
    fanout_paused = planning.fanout_paused
    worker_role_guard = planning.worker_role_guard
    merge_dispatch = planning.merge_dispatch
    fanout_plan = planning.fanout_plan
    lifecycle_execution = planning.lifecycle_execution
    if args.llm_summary:
        payload["llm_summary"] = api._summarize_with_llm(report)
    api._append_supervise_supervisor_action(
        args,
        payload,
        action_report,
        active_goals=active_goals,
        explicit_goal=explicit_goal,
        fanout_status=fanout_status,
        fanout_paused=fanout_paused,
        worker_role_guard=worker_role_guard,
        merge_dispatch=merge_dispatch,
        fanout_plan=fanout_plan,
        lifecycle_execution=lifecycle_execution,
    )
    api._append_supervise_execution(
        args,
        payload,
        report,
        action_report=action_report,
        active_goals=active_goals,
        goal_replenishment=goal_replenishment,
        worker_reviews=worker_reviews,
        fanout_status=fanout_status,
        fanout_paused=fanout_paused,
        worker_role_guard=worker_role_guard,
        merge_dispatch=merge_dispatch,
        fanout_plan=fanout_plan,
        lifecycle_execution=lifecycle_execution,
        precomputed_auto_action=precomputed_auto_action,
        precomputed_executed=precomputed_executed,
    )
    api._append_supervise_final_payload(args, payload)
    return payload

__all__ = ("supervise_payload",)
