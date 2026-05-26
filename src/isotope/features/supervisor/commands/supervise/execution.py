"""Execution dispatch for supervise/loop command payloads."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def append_supervise_execution(
    args: Any,
    payload: dict[str, Any],
    report: Any,
    *,
    action_report: Any,
    active_goals: list[dict[str, Any]],
    goal_replenishment: dict[str, Any] | None,
    worker_reviews: dict[str, Any] | None,
    fanout_status: dict[str, Any] | None,
    fanout_paused: bool,
    worker_role_guard: dict[str, Any] | None,
    merge_dispatch: dict[str, Any] | None,
    fanout_plan: dict[str, Any] | None,
    precomputed_auto_action: dict[str, Any] | None = None,
    precomputed_executed: dict[str, Any] | None = None,
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    if args.llm_execute:
        return _append_supervise_llm_execution(
            args,
            payload,
            action_report,
            active_goals=active_goals,
            goal_replenishment=goal_replenishment,
            worker_reviews=worker_reviews,
            fanout_status=fanout_status,
            fanout_paused=fanout_paused,
            worker_role_guard=worker_role_guard,
            merge_dispatch=merge_dispatch,
            fanout_plan=fanout_plan,
            api=api,
        )
    if args.auto_execute:
        return _append_supervise_auto_execution(
            args,
            payload,
            action_report,
            precomputed_auto_action=precomputed_auto_action,
            precomputed_executed=precomputed_executed,
            api=api,
        )
    if args.execute:
        payload["executed"] = api._execute_advice(args, report, payload)
        return payload["executed"]
    return None


def _append_supervise_llm_execution(
    args: Any,
    payload: dict[str, Any],
    action_report: Any,
    *,
    active_goals: list[dict[str, Any]],
    goal_replenishment: dict[str, Any] | None,
    worker_reviews: dict[str, Any] | None,
    fanout_status: dict[str, Any] | None,
    fanout_paused: bool,
    worker_role_guard: dict[str, Any] | None,
    merge_dispatch: dict[str, Any] | None,
    fanout_plan: dict[str, Any] | None,
    api: Any,
) -> dict[str, Any] | None:
    if fanout_paused:
        payload["executed"] = api._fanout_paused_executed(fanout_status)
    elif fanout_plan is not None:
        payload["executed"] = api._execute_fanout_launch_actions(
            args,
            fanout_plan,
            report=action_report,
            payload=payload,
        )
        payload["fanout_log"] = api._fanout_log_payload(
            fanout_plan,
            goal_replenishment=goal_replenishment,
            executed=payload["executed"],
        )
        if api._fanout_execution_launched_workers(payload["executed"]):
            api._refresh_current_batch_after_execution(
                args,
                payload,
                executed=payload["executed"],
                active_goals=active_goals,
                worker_reviews=worker_reviews,
            )
    elif worker_role_guard is not None:
        payload["executed"] = api._recursive_worker_role_guard_executed(
            worker_role_guard
        )
    elif merge_dispatch is not None:
        payload["executed"] = _merge_dispatch_executed(
            args,
            action_report,
            payload,
            merge_dispatch,
            api=api,
        )
        api._refresh_current_batch_after_execution(
            args,
            payload,
            executed=payload["executed"],
            active_goals=active_goals,
            worker_reviews=worker_reviews,
        )
    else:
        payload["executed"] = api._execute_llm_action(args, action_report, payload)
        api._maybe_replan_after_context_request(args, action_report, payload)
    return payload.get("executed")


def _merge_dispatch_executed(
    args: Any,
    action_report: Any,
    payload: dict[str, Any],
    merge_dispatch: dict[str, Any],
    *,
    api: Any,
) -> dict[str, Any]:
    if merge_dispatch.get("status") == "worker_already_running":
        return api._merge_dispatch_already_running_executed(merge_dispatch)
    if not getattr(args, "merge_dispatch_execute", False):
        return api._merge_dispatch_planned_executed(merge_dispatch)
    return api._mark_merge_dispatch_execution(
        api._execute_failure_guarded_action(
            args,
            report=action_report,
            payload=payload,
            action=merge_dispatch["launch_spec"],
            event_type="merge_dispatch_failed",
            execute=lambda: api._execute_launch_action(
                args,
                merge_dispatch["launch_spec"],
            ),
        )
    )


def _append_supervise_auto_execution(
    args: Any,
    payload: dict[str, Any],
    action_report: Any,
    *,
    precomputed_auto_action: dict[str, Any] | None,
    precomputed_executed: dict[str, Any] | None,
    api: Any,
) -> dict[str, Any] | None:
    auto_action = precomputed_auto_action or api._auto_execute_action(
        action_report,
        target_name=args.name,
        codex_home=Path(args.codex_home),
        prompt_cooldown_seconds=args.prompt_cooldown,
        max_continue_count=args.max_continue_count,
        max_run_minutes=args.max_run_minutes,
    )
    payload["auto_action"] = auto_action
    payload["executed"] = precomputed_executed or api._execute_auto_action(
        args,
        action_report,
        auto_action,
    )
    return payload["executed"]
