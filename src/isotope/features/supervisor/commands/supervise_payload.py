"""Payload builders for supervise/loop command responses."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SuperviseBasePayload:
    payload: dict[str, Any]
    action_report: Any
    active_goals: list[dict[str, Any]]
    explicit_goal: str | None
    goal_replenishment: dict[str, Any] | None


def build_supervise_base_payload(
    args: Any,
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
    api: Any | None = None,
) -> SuperviseBasePayload:
    if api is None:
        from isotope.features.supervisor import runner as api

    action_report = api._action_report_for_workspace(args, report)
    state_snapshot = api.build_supervisor_state_snapshot(
        codex_home=Path(args.codex_home)
    )
    active_goals = api._active_goal_dicts(args, include_status=True)
    running_target_names = api._running_managed_target_names(report)
    goal_replenishment = api._maybe_replenish_active_goals(
        args,
        active_goals,
        running_target_names=running_target_names,
    )
    if (
        isinstance(goal_replenishment, dict)
        and goal_replenishment.get("status") == "ok"
        and goal_replenishment.get("written_count")
    ):
        state_snapshot = api.build_supervisor_state_snapshot(
            codex_home=Path(args.codex_home)
        )
        active_goals = api._active_goal_dicts(args, include_status=True)
    explicit_goal = api._explicit_goal_text(args)
    payload = api._advice_payload(
        action_report,
        target_name=args.name,
        include_all_managed=args.llm_action or args.llm_execute,
        allow_workspace_actions=api._loop_allows_workspace_actions(
            args,
            active_goals,
            explicit_goal,
        ),
        goal=api._goal_text(args),
        goal_workspace=api._goal_workspace(args),
        goal_target_name=api._goal_target_name(args),
        active_goals=None if explicit_goal else active_goals,
    )
    payload["workspace_scope"] = api._workspace_scope_payload(
        args,
        report,
        action_report,
    )
    payload["iteration"] = iteration
    payload["report"] = report.to_dict()
    payload["automation"] = api._automation_status(report)
    payload["auto_adopted"] = auto_adopted or []
    payload["auto_retried_workers"] = auto_retried_workers or []
    payload["active_goals"] = active_goals
    payload["state_snapshot"] = state_snapshot
    if goal_replenishment is not None:
        payload["goal_replenishment"] = goal_replenishment
    if goal_updates:
        payload["goal_updates"] = goal_updates
    if merge_promotions:
        payload["merge_promotions"] = merge_promotions
    if cleanup_archived:
        payload["cleanup_archived"] = cleanup_archived
    if cleanup_deleted_worktrees:
        payload["cleanup_deleted_worktrees"] = cleanup_deleted_worktrees
    payload["decision_timeout_alerts"] = decision_timeout_alerts or []
    return SuperviseBasePayload(
        payload=payload,
        action_report=action_report,
        active_goals=active_goals,
        explicit_goal=explicit_goal,
        goal_replenishment=goal_replenishment,
    )


def refresh_current_batch_after_execution(
    args: Any,
    payload: dict[str, Any],
    *,
    executed: dict[str, Any],
    active_goals: list[dict[str, Any]],
    worker_reviews: dict[str, Any] | None,
    api: Any | None = None,
) -> bool:
    if api is None:
        from isotope.features.supervisor import runner as api

    if not api._executed_action_forces_print(executed):
        return False
    default_limit = getattr(api, "DEFAULT_FANOUT_LIMIT", None)
    refreshed_report = api._scan_report(args)
    payload["current_batch"] = api._current_batch_payload(
        refreshed_report,
        active_goals=active_goals,
        worker_reviews=worker_reviews,
        dependency_limit=getattr(args, "max_fanout_launches", default_limit),
    )
    return True
