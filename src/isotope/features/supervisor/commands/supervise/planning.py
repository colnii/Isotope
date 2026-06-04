"""Planning payload assembly for supervise/loop commands."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from isotope.features.supervisor.lifecycle import (
    build_worker_lifecycle_decision,
    build_worker_lifecycle_execution_plan,
)


@dataclass
class SupervisePlanningPayload:
    fanout_status: dict[str, Any] | None
    fanout_paused: bool
    worker_role_guard: dict[str, Any] | None
    merge_dispatch: dict[str, Any] | None
    fanout_plan: dict[str, Any] | None
    lifecycle_execution: dict[str, Any] | None


def append_supervise_planning_payload(
    args: Any,
    payload: dict[str, Any],
    report: Any,
    *,
    active_goals: list[dict[str, Any]],
    goal_updates: list[dict[str, Any]] | None,
    goal_replenishment: dict[str, Any] | None,
    worker_reviews: dict[str, Any] | None,
    api: Any | None = None,
) -> SupervisePlanningPayload:
    if api is None:
        from isotope.features.supervisor import runner as api

    payload["current_batch"] = api._current_batch_payload(
        report,
        active_goals=active_goals,
        worker_reviews=worker_reviews,
        dependency_limit=getattr(args, "max_fanout_launches", api.DEFAULT_FANOUT_LIMIT),
    )
    fanout_status = api._fanout_status_payload(
        report,
        active_goals=api._fanout_candidate_active_goals(active_goals),
        goal_updates=goal_updates or [],
    )
    if fanout_status is not None:
        payload["fanout_status"] = fanout_status
    fanout_paused = (
        isinstance(fanout_status, dict)
        and fanout_status.get("status") == "paused"
        and not api._goal_replenishment_wrote_goals(goal_replenishment)
    )
    worker_role_guard = api._recursive_worker_role_guard_payload(args)
    allows_llm = args.llm_action or args.llm_execute
    merge_dispatch = (
        api._integration_merge_dispatch_payload(args)
        if not fanout_paused and worker_role_guard is None and allows_llm
        else None
    )
    fanout_plan = (
        None
        if merge_dispatch is not None
        else (
            api._paused_active_goals_fanout_plan(args, active_goals)
            if fanout_paused
            else api._replenished_goal_plan_fanout_launch_plan(
                args,
                report,
                goal_replenishment,
            )
            or api._active_goals_fanout_launch_plan(args, report, active_goals)
        )
    )
    if fanout_plan is not None and allows_llm:
        payload["fanout_plan"] = fanout_plan
        payload["fanout_log"] = api._fanout_log_payload(
            fanout_plan,
            goal_replenishment=goal_replenishment,
        )
    if merge_dispatch is not None:
        payload["merge_dispatch"] = merge_dispatch
    lifecycle_can_consume_cleanup = (
        allows_llm
        and not fanout_paused
        and worker_role_guard is None
        and fanout_plan is None
    )
    cleanup_candidates = (
        api._cleanup_candidate_dicts(Path(args.codex_home))
        if lifecycle_can_consume_cleanup
        else None
    )
    delete_worktree_candidates = (
        api._delete_worktree_candidate_payloads(args)
        if lifecycle_can_consume_cleanup
        else None
    )
    integration_review = (
        merge_dispatch.get("integration_review")
        if isinstance(merge_dispatch, dict)
        else None
    )
    if lifecycle_can_consume_cleanup and integration_review is None:
        integration_review = api.collect_integration_reviews(
            codex_home=Path(args.codex_home),
            base_ref="main",
            include_unfinished=False,
            run_test_gate=False,
            run_candidate_validation=False,
        )
    lifecycle_decision = build_worker_lifecycle_decision(
        worker_reviews=worker_reviews,
        integration_review=integration_review,
        merge_dispatch=merge_dispatch,
        cleanup_candidates=cleanup_candidates,
        cleanup_archived=(
            payload.get("cleanup_archived")
            if isinstance(payload.get("cleanup_archived"), list)
            else None
        ),
        cleanup_deleted_worktrees=(
            payload.get("cleanup_deleted_worktrees")
            if isinstance(payload.get("cleanup_deleted_worktrees"), list)
            else None
        ),
    )
    payload["worker_lifecycle_decision"] = lifecycle_decision
    lifecycle_execution_plan = build_worker_lifecycle_execution_plan(
        worker_lifecycle_decision=lifecycle_decision,
        merge_dispatch=merge_dispatch,
        cleanup_candidates=cleanup_candidates,
        delete_worktree_candidates=delete_worktree_candidates,
    )
    lifecycle_execution = (
        lifecycle_execution_plan.to_dict()
        if lifecycle_execution_plan is not None
        else None
    )
    if lifecycle_execution is not None:
        payload["worker_lifecycle_execution"] = lifecycle_execution
    if (
        fanout_plan is None
        and merge_dispatch is None
        and not fanout_paused
        and worker_role_guard is None
        and allows_llm
    ):
        merge_dispatch = api._integration_merge_dispatch_payload(args)
        if merge_dispatch is not None:
            payload["merge_dispatch"] = merge_dispatch
            lifecycle_execution_plan = build_worker_lifecycle_execution_plan(
                worker_lifecycle_decision=lifecycle_decision,
                merge_dispatch=merge_dispatch,
                cleanup_candidates=cleanup_candidates,
                delete_worktree_candidates=delete_worktree_candidates,
            )
            lifecycle_execution = (
                lifecycle_execution_plan.to_dict()
                if lifecycle_execution_plan is not None
                else None
            )
            if lifecycle_execution is not None:
                payload["worker_lifecycle_execution"] = lifecycle_execution
    return SupervisePlanningPayload(
        fanout_status=fanout_status,
        fanout_paused=fanout_paused,
        worker_role_guard=worker_role_guard,
        merge_dispatch=merge_dispatch,
        fanout_plan=fanout_plan,
        lifecycle_execution=lifecycle_execution,
    )
