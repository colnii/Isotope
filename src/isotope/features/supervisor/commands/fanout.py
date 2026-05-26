"""Fanout orchestration helpers for Supervisor command execution."""

from __future__ import annotations

import argparse
from typing import Any

from isotope.agents.scheduler.goal_queue import filter_fanout_candidate_goals
from isotope.features.supervisor.state.fanout import (
    build_active_goals_fanout_launch_plan,
    build_fanout_status_summary,
    build_paused_active_goals_fanout_plan,
    build_replenished_goal_plan_fanout_launch_plan,
)


def fanout_candidate_active_goals(
    active_goals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return filter_fanout_candidate_goals(active_goals)


def active_goals_fanout_launch_plan(
    args: argparse.Namespace,
    report: Any,
    active_goals: list[dict[str, Any]],
    *,
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    if getattr(args, "command", None) != "loop":
        return None
    if getattr(args, "name", None):
        return None
    return build_active_goals_fanout_launch_plan(
        active_goals,
        limit=getattr(args, "max_fanout_launches", api.DEFAULT_FANOUT_LIMIT),
        running_target_names=api._running_managed_target_names(report),
    )


def goal_replenishment_wrote_goals(
    goal_replenishment: dict[str, Any] | None,
) -> bool:
    return (
        isinstance(goal_replenishment, dict)
        and goal_replenishment.get("status") == "ok"
        and int_value(goal_replenishment.get("written_count")) > 0
    )


def replenished_goal_plan_fanout_launch_plan(
    args: argparse.Namespace,
    report: Any,
    goal_replenishment: dict[str, Any] | None,
    *,
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    if getattr(args, "command", None) != "loop":
        return None
    if getattr(args, "name", None):
        return None
    return build_replenished_goal_plan_fanout_launch_plan(
        goal_replenishment,
        limit=getattr(args, "max_fanout_launches", api.DEFAULT_FANOUT_LIMIT),
        running_target_names=api._running_managed_target_names(report),
    )


def fanout_status_payload(
    report: Any,
    *,
    active_goals: list[dict[str, Any]],
    goal_updates: list[dict[str, Any]],
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    payload = build_fanout_status_summary(
        active_goals=active_goals,
        goal_updates=goal_updates,
        running_target_names=api._running_managed_target_names(report),
    )
    summary = payload.get("summary")
    if not isinstance(summary, dict) or summary.get("total", 0) < 2:
        return None
    if payload.get("status") == "idle":
        return None
    return payload


def paused_active_goals_fanout_plan(
    args: argparse.Namespace,
    active_goals: list[dict[str, Any]],
    *,
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    if getattr(args, "command", None) != "loop":
        return None
    if getattr(args, "name", None):
        return None
    return build_paused_active_goals_fanout_plan(
        active_goals,
        limit=getattr(args, "max_fanout_launches", api.DEFAULT_FANOUT_LIMIT),
    )


def fanout_llm_action(fanout_plan: dict[str, Any]) -> dict[str, Any]:
    launchable = fanout_plan.get("summary", {}).get("launchable", 0)
    if launchable:
        reason = "多个 active goals 可并行启动受控 worker。"
    else:
        reason = "多个 active goals 已被 running worker 或 fanout gate 跳过。"
    return {
        "kind": "fanout_launch_sessions",
        "target_name": None,
        "reason": reason,
        "command_suggestion": None,
    }


def fanout_paused_action(fanout_status: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "monitor",
        "target_name": None,
        "reason": fanout_status.get("message")
        or "fanout 已暂停，等待用户处理 blocked/needs_user worker。",
        "command_suggestion": None,
    }


def fanout_paused_executed(fanout_status: dict[str, Any]) -> dict[str, Any]:
    action = fanout_paused_action(fanout_status)
    return {
        "kind": "monitor",
        "skipped": True,
        "reason": action["reason"],
    }


def fanout_log_payload(
    fanout_plan: dict[str, Any],
    *,
    goal_replenishment: dict[str, Any] | None = None,
    executed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan_summary = fanout_plan.get("summary") if isinstance(fanout_plan, dict) else {}
    if not isinstance(plan_summary, dict):
        plan_summary = {}
    log = {
        "status": "executed" if executed is not None else "planned",
        "trigger": fanout_trigger(goal_replenishment),
        "planned_launches": int_value(plan_summary.get("launchable")),
        "planned_skips": int_value(plan_summary.get("skipped")),
        "limit": int_value(plan_summary.get("limit")),
    }
    if executed is not None:
        executed_summary = executed.get("summary")
        if not isinstance(executed_summary, dict):
            executed_summary = {}
        log["executed_launches"] = int_value(executed_summary.get("launched"))
        log["executed_skips"] = int_value(executed_summary.get("skipped"))
    return log


def fanout_trigger(goal_replenishment: dict[str, Any] | None) -> str:
    if (
        isinstance(goal_replenishment, dict)
        and goal_replenishment.get("trigger") == "low_water"
        and goal_replenishment.get("status") == "ok"
        and int_value(goal_replenishment.get("written_count")) > 0
    ):
        return "low_water"
    return "active_goals"


def int_value(value: object) -> int:
    return value if isinstance(value, int) else 0


def execute_fanout_launch_actions(
    args: argparse.Namespace,
    fanout_plan: dict[str, Any],
    *,
    report: Any | None = None,
    payload: dict[str, Any] | None = None,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    results: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen_target_names: set[str] = set()
    for launch_spec in fanout_plan.get("launch_specs") or []:
        if not isinstance(launch_spec, dict):
            continue
        target_name = api._optional_text(launch_spec.get("target_name"))
        if target_name is not None:
            if target_name in seen_target_names:
                skipped.append(
                    {
                        "kind": "launch_session",
                        "skipped": True,
                        "reason": "duplicate_fanout_target",
                        "target_name": target_name,
                    }
                )
                continue
            seen_target_names.add(target_name)
        result = api._execute_failure_guarded_action(
            args,
            report=report,
            payload=payload or {},
            action=launch_spec,
            event_type="worker_launch_failed",
            execute=lambda launch_spec=launch_spec: api._execute_launch_action(
                args,
                launch_spec,
            ),
        )
        if result.get("skipped"):
            skipped.append(result)
        else:
            results.append(result)
    return {
        "kind": "fanout_launch_sessions",
        "summary": {
            "launched": len(results),
            "skipped": len(skipped),
            "limit": fanout_plan.get("summary", {}).get("limit"),
        },
        "results": results,
        "skipped": skipped,
    }


def fanout_execution_launched_workers(executed: dict[str, Any]) -> bool:
    summary = executed.get("summary")
    return isinstance(summary, dict) and bool(summary.get("launched"))
