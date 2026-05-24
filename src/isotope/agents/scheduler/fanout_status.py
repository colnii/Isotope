"""Fanout batch status summary helpers for agent scheduler goals."""

from __future__ import annotations

from typing import Any, Iterable


ATTENTION_STATUSES = {"blocked", "needs_user"}
FANOUT_STATUS_VALUES = ("done", "blocked", "needs_user", "running", "pending")


def build_fanout_status_summary(
    *,
    active_goals: Iterable[dict[str, Any]],
    goal_updates: Iterable[dict[str, Any]] = (),
    running_target_names: Iterable[str] = (),
) -> dict[str, Any]:
    """Project active goals and status updates into a fanout batch state."""
    running_names = {
        name for name in running_target_names if isinstance(name, str) and name
    }
    items = _fanout_status_items(
        active_goals=active_goals,
        goal_updates=goal_updates,
        running_target_names=running_names,
    )
    counts = {status: 0 for status in FANOUT_STATUS_VALUES}
    for item in items:
        status = item["status"]
        if status in counts:
            counts[status] += 1
    summary = {
        "total": len(items),
        "done": counts["done"],
        "blocked": counts["blocked"],
        "needs_user": counts["needs_user"],
        "running": counts["running"],
        "pending": counts["pending"],
    }
    attention = [
        item for item in items if item.get("status") in ATTENTION_STATUSES
    ]
    if attention:
        return {
            "status": "paused",
            "summary": summary,
            "message": f"fanout paused: {len(attention)} workers need attention.",
            "attention": attention,
            "requires_user_attention": True,
        }
    if items and summary["done"] == summary["total"]:
        return {
            "status": "completed",
            "summary": summary,
            "message": f"fanout batch completed: {summary['done']} workers done.",
            "results": items,
            "requires_user_attention": False,
        }
    if items:
        return {
            "status": "running",
            "summary": summary,
            "message": "fanout batch still has running or pending workers.",
            "results": items,
            "requires_user_attention": False,
        }
    return {
        "status": "idle",
        "summary": summary,
        "message": "no fanout batch targets.",
        "results": [],
        "requires_user_attention": False,
    }


def _fanout_status_items(
    *,
    active_goals: Iterable[dict[str, Any]],
    goal_updates: Iterable[dict[str, Any]],
    running_target_names: set[str],
) -> list[dict[str, Any]]:
    items_by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for goal in active_goals:
        item = _fanout_item_from_goal(goal, running_target_names=running_target_names)
        if item is None:
            continue
        key = _fanout_item_key(item)
        if key not in items_by_key:
            order.append(key)
        items_by_key[key] = item
    for update in goal_updates:
        item = _fanout_item_from_update(update)
        if item is None:
            continue
        key = _fanout_item_key(item)
        if key not in items_by_key:
            order.append(key)
        items_by_key[key] = {**items_by_key.get(key, {}), **item}
    return [items_by_key[key] for key in order]


def _fanout_item_from_goal(
    goal: dict[str, Any],
    *,
    running_target_names: set[str],
) -> dict[str, Any] | None:
    goal_id = _optional_string(goal.get("goal_id"))
    target_name = _optional_string(goal.get("target_name"))
    if not goal_id and not target_name:
        return None
    status = _optional_string(goal.get("last_status"))
    if status not in {"done", "blocked", "needs_user"}:
        status = "running" if target_name in running_target_names else "pending"
    item = {
        "goal_id": goal_id,
        "target_name": target_name,
        "status": status,
        "summary": _optional_string(goal.get("last_summary")),
        "next": _optional_string(goal.get("last_next")),
    }
    return {key: value for key, value in item.items() if value is not None}


def _fanout_item_from_update(update: dict[str, Any]) -> dict[str, Any] | None:
    goal_id = _optional_string(update.get("goal_id"))
    target_name = _optional_string(update.get("target_name"))
    status = _optional_string(update.get("status"))
    if status not in {"done", "blocked", "needs_user"}:
        return None
    item = {
        "goal_id": goal_id,
        "target_name": target_name,
        "status": status,
        "summary": _optional_string(update.get("summary")),
        "next": _optional_string(update.get("next")),
    }
    return {key: value for key, value in item.items() if value is not None}


def _fanout_item_key(item: dict[str, Any]) -> str:
    goal_id = item.get("goal_id")
    if isinstance(goal_id, str) and goal_id:
        return f"goal:{goal_id}"
    target_name = item.get("target_name")
    if isinstance(target_name, str) and target_name:
        return f"target:{target_name}"
    return "unknown"


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()
