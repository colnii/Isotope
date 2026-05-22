"""Dependency-graph batch planning for scheduler goals."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .dependency_graph import (
    DependencyGraphError,
    NodeState,
    build_dependency_graph_from_goal_records,
    build_node_states_from_goal_records,
    resolve_ready_nodes,
)


ATTENTION_STATUSES = {"blocked", "needs_user"}


def build_dependency_batch_plan(
    goals: Iterable[Mapping[str, Any]],
    *,
    limit: int,
    running_target_names: Iterable[str] = (),
) -> dict[str, Any]:
    """Project goal records into the next dependency-aware runnable batch."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    goal_list = [dict(goal) for goal in goals]
    running_names = {
        name for name in running_target_names if isinstance(name, str) and name
    }
    try:
        graph = build_dependency_graph_from_goal_records(goal_list)
        states = build_node_states_from_goal_records(goal_list)
        ready_ids = {node.node_id for node in resolve_ready_nodes(graph, states=states)}
    except DependencyGraphError as exc:
        return _invalid_graph_plan(goal_list, limit=limit, detail=str(exc))

    attention_goals = _attention_goals(goal_list)
    running_goals = _running_goals(goal_list, running_names=running_names)
    available_slots = max(limit - len(running_names), 0)

    ready_goals: list[dict[str, Any]] = []
    blocked_goals: list[dict[str, Any]] = []
    for goal in goal_list:
        target_name = _goal_node_id(goal)
        if target_name is None or _is_terminal_or_attention(goal):
            continue
        if target_name in running_names:
            continue
        if target_name in ready_ids:
            if len(ready_goals) < available_slots:
                ready_goals.append(_goal_ref(goal))
            else:
                blocked_goals.append(
                    {
                        "target_name": target_name,
                        "reason": "global_running_limit_reached",
                    }
                )
            continue
        blocked_goals.append(
            _blocked_goal(goal, states=states)
        )

    status = _batch_status(
        ready_goals=ready_goals,
        blocked_goals=blocked_goals,
        attention_goals=attention_goals,
    )
    return {
        "status": status,
        "summary": {
            "ready": len(ready_goals),
            "blocked": len(blocked_goals),
            "running": len(running_goals),
            "attention": len(attention_goals),
            "limit": limit,
        },
        "ready_goals": ready_goals,
        "blocked_goals": blocked_goals,
        "running_goals": running_goals,
        "attention_goals": attention_goals,
    }


def _invalid_graph_plan(
    goals: list[dict[str, Any]],
    *,
    limit: int,
    detail: str,
) -> dict[str, Any]:
    blocked = [
        {
            "target_name": target_name,
            "reason": "dependency_graph_invalid",
            "detail": detail,
        }
        for goal in goals
        for target_name in (_goal_node_id(goal),)
        if target_name is not None
    ]
    return {
        "status": "blocked",
        "summary": {
            "ready": 0,
            "blocked": len(blocked),
            "running": 0,
            "attention": 0,
            "limit": limit,
        },
        "ready_goals": [],
        "blocked_goals": blocked,
        "running_goals": [],
        "attention_goals": [],
    }


def _blocked_goal(
    goal: Mapping[str, Any],
    *,
    states: Mapping[str, NodeState],
) -> dict[str, str]:
    target_name = _goal_node_id(goal) or "unknown"
    for dependency in _string_list(goal.get("depends_on")):
        state = states.get(dependency)
        if state is not None and state.status in ATTENTION_STATUSES:
            return {
                "target_name": target_name,
                "reason": "dependency_attention",
                "dependency": dependency,
            }
        if state is None or state.status != "done" or not state.merged or not state.verified:
            return {
                "target_name": target_name,
                "reason": "dependency_unmet",
                "dependency": dependency,
            }
    return {
        "target_name": target_name,
        "reason": "dependency_unmet",
        "dependency": _optional_string(goal.get("stage")) or target_name,
    }


def _attention_goals(goals: list[dict[str, Any]]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for goal in goals:
        status = _goal_status(goal)
        target_name = _goal_node_id(goal)
        if status in ATTENTION_STATUSES and target_name is not None:
            items.append({"target_name": target_name, "status": status})
    return items


def _running_goals(
    goals: list[dict[str, Any]],
    *,
    running_names: set[str],
) -> list[dict[str, str]]:
    return [
        {"target_name": target_name, "status": "running"}
        for goal in goals
        for target_name in (_goal_node_id(goal),)
        if target_name in running_names
    ]


def _batch_status(
    *,
    ready_goals: list[dict[str, Any]],
    blocked_goals: list[dict[str, Any]],
    attention_goals: list[dict[str, Any]],
) -> str:
    if attention_goals:
        return "paused"
    if ready_goals:
        return "ready"
    if blocked_goals:
        return "blocked"
    return "idle"


def _goal_ref(goal: Mapping[str, Any]) -> dict[str, Any]:
    item = {"target_name": _goal_node_id(goal)}
    for key in ("goal_id", "stage", "scope", "cwd", "goal"):
        value = goal.get(key)
        if value:
            item[key] = value
    return item


def _is_terminal_or_attention(goal: Mapping[str, Any]) -> bool:
    return _goal_status(goal) in {"done", "blocked", "needs_user", "failed"}


def _goal_status(goal: Mapping[str, Any]) -> str:
    for key in ("last_status", "status", "supervisor_status"):
        value = goal.get(key)
        if isinstance(value, str) and value:
            return value.lower()
    return "pending"


def _goal_node_id(goal: Mapping[str, Any]) -> str | None:
    for key in ("target_name", "goal_id", "id"):
        value = _optional_string(goal.get(key))
        if value is not None:
            return value
    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
