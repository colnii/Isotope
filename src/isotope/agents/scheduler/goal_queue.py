"""Pure goal-queue scheduling helpers."""

from __future__ import annotations

from typing import Any, Iterable, Mapping


GOAL_QUEUE_VIEW_GROUPS = ("pending", "running", "blocked", "needs_user", "done_recent")


def build_supervisor_goal_queue_view(
    active_goals: Iterable[Mapping[str, Any]],
    *,
    running_target_names: Iterable[str] = (),
) -> dict[str, list[dict[str, Any]]]:
    running_names = {name for name in running_target_names if name}
    grouped: dict[str, list[dict[str, Any]]] = {
        group: [] for group in GOAL_QUEUE_VIEW_GROUPS
    }
    for goal in active_goals:
        state = _goal_queue_state(goal, running_target_names=running_names)
        item = dict(goal)
        item["queue_status"] = state
        if state == "running" and not item.get("worker_status"):
            item["worker_status"] = "running"
        grouped[state].append(item)
    for group, items in grouped.items():
        reverse = group == "done_recent"
        items.sort(key=_goal_queue_sort_key, reverse=reverse)
    return grouped


def filter_replenishment_counted_goals(
    active_goals: Iterable[Mapping[str, Any]],
    *,
    running_target_names: Iterable[str] = (),
) -> list[dict[str, Any]]:
    running_names = {name for name in running_target_names if name}
    counted: list[dict[str, Any]] = []
    for goal in active_goals:
        if active_goal_is_deferred(goal):
            continue
        target_name = goal.get("target_name")
        if isinstance(target_name, str) and target_name in running_names:
            continue
        counted.append(dict(goal))
    return counted


def filter_fanout_candidate_goals(
    active_goals: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [dict(goal) for goal in active_goals if not active_goal_is_deferred(goal)]


def active_goal_is_deferred(goal: Mapping[str, Any]) -> bool:
    for key in ("last_status", "status", "supervisor_status"):
        status = goal.get(key)
        if isinstance(status, str) and status.lower() in {
            "blocked",
            "done",
            "needs_user",
        }:
            return True
    return False


def _goal_queue_state(
    goal: Mapping[str, Any],
    *,
    running_target_names: set[str],
) -> str:
    last_status = goal.get("last_status")
    if last_status == "done":
        return "done_recent"
    if last_status in {"blocked", "needs_user"}:
        return str(last_status)
    target_name = goal.get("target_name")
    if isinstance(target_name, str) and target_name in running_target_names:
        return "running"
    return "pending"


def _goal_queue_sort_key(goal: Mapping[str, Any]) -> str:
    status_at = goal.get("last_status_at")
    if isinstance(status_at, str) and status_at:
        return status_at
    created_at = goal.get("created_at")
    if isinstance(created_at, str) and created_at:
        return created_at
    return ""
