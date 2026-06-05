"""Pure fanout planning helpers for agent scheduler goals."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any, Iterable

from .dependency_graph import (
    DependencyGraphError,
    build_dependency_graph_from_goal_records,
    build_node_states_from_goal_records,
    resolve_ready_nodes,
)
from .dependency_batches import build_dependency_batch_plan
from .fanout_status import (
    ATTENTION_STATUSES,
    FANOUT_STATUS_VALUES,
    build_fanout_status_summary,
)
from .goal_queue import filter_fanout_candidate_goals


DEFAULT_FANOUT_LIMIT = 3
REVIEW_NOTE = "fanout 输出可执行 launch spec；runner 按调度入口执行并记录结果。"


def build_fanout_launch_plan(
    goal_plan: dict[str, Any],
    *,
    cwd: str | None = None,
    limit: int = DEFAULT_FANOUT_LIMIT,
    running_target_names: Iterable[str] = (),
    requires_human_review: bool = True,
) -> dict[str, Any]:
    """Convert goal-plan parallel recommendations into reviewable launch specs."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    candidates = _candidate_by_target_name(goal_plan)
    dependency_state = _resolved_dependency_state(candidates.values())
    running_names = {
        _normalize_target_name(name)
        for name in running_target_names
        if isinstance(name, str) and name.strip()
    }
    default_cwd = _optional_string(cwd) or _optional_string(goal_plan.get("root"))
    launch_specs: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    seen_targets: set[str] = set()

    for recommendation in _parallel_recommendations(goal_plan):
        batch = _optional_string(recommendation.get("batch"))
        reason = _optional_string(recommendation.get("reason")) or (
            "goal plan 建议并行启动。"
        )
        for raw_target in _target_names(recommendation):
            target_name = _normalize_target_name(raw_target)
            skip_base = _skip_base(target_name=target_name, batch=batch)
            if target_name in seen_targets:
                skipped.append({**skip_base, "reason": "duplicate_target"})
                continue
            seen_targets.add(target_name)
            candidate = candidates.get(target_name)
            if candidate is None:
                skipped.append({**skip_base, "reason": "candidate_not_found"})
                continue
            if target_name in running_names:
                skipped.append({**skip_base, "reason": "worker_already_running"})
                continue
            dependency_skip = _dependency_skip(
                candidate,
                dependency_state=dependency_state,
            )
            if dependency_skip is not None:
                skipped.append({**skip_base, **dependency_skip})
                continue
            if len(running_names) + len(launch_specs) >= limit:
                reason = (
                    "global_running_limit_reached"
                    if running_names
                    else "fanout_limit_reached"
                )
                skipped.append({**skip_base, "reason": reason})
                continue
            launch_cwd = _optional_string(candidate.get("cwd")) or default_cwd
            if not launch_cwd:
                skipped.append({**skip_base, "reason": "cwd_missing"})
                continue
            goal = _optional_string(candidate.get("goal"))
            if not goal:
                skipped.append({**skip_base, "reason": "goal_missing"})
                continue
            spec = {
                "kind": "launch_session",
                "target_name": target_name,
                "cwd": launch_cwd,
                "prompt": goal,
                "reason": reason,
                "batch": batch,
                "source": "parallel_recommendations",
                "candidate_reason": _optional_string(candidate.get("reason")),
                "review": {
                    "requires_human_review": requires_human_review,
                    "note": REVIEW_NOTE,
                },
            }
            dependency_graph = _launch_dependency_graph(candidate)
            if dependency_graph:
                spec["dependency_graph"] = dependency_graph
            launch_specs.append(spec)

    return {
        "status": "ok",
        "summary": {
            "launchable": len(launch_specs),
            "skipped": len(skipped),
            "limit": limit,
        },
        "launch_specs": launch_specs,
        "skipped": skipped,
        "safety": {
            "auto_launch": False,
            "note": REVIEW_NOTE,
        },
    }


def build_active_goals_fanout_launch_plan(
    active_goals: list[dict[str, Any]],
    *,
    limit: int = DEFAULT_FANOUT_LIMIT,
    running_target_names: Iterable[str] = (),
    requires_human_review: bool = False,
) -> dict[str, Any] | None:
    fanout_goals = filter_fanout_candidate_goals(active_goals)
    dependency_batch = build_dependency_batch_plan(
        active_goals,
        limit=limit,
        running_target_names=running_target_names,
    )
    targets = [
        target_name
        for goal in fanout_goals
        for target_name in (goal.get("target_name"),)
        if isinstance(target_name, str) and target_name
    ]
    if len(targets) < 2:
        return None
    plan = build_fanout_launch_plan(
        {
            "goals": active_goals,
            "parallel_recommendations": [
                {
                    "batch": "active_goals",
                    "targets": targets,
                    "reason": "多个 active goals 可并行启动受控 worker。",
                }
            ],
        },
        limit=limit,
        running_target_names=running_target_names,
        requires_human_review=requires_human_review,
    )
    plan["dependency_batch"] = dependency_batch
    return plan


def build_replenished_goal_plan_fanout_launch_plan(
    goal_replenishment: Mapping[str, Any] | None,
    *,
    limit: int = DEFAULT_FANOUT_LIMIT,
    running_target_names: Iterable[str] = (),
    requires_human_review: bool = False,
) -> dict[str, Any] | None:
    if not isinstance(goal_replenishment, Mapping):
        return None
    if goal_replenishment.get("status") != "ok":
        return None
    recommendations = goal_replenishment.get("parallel_recommendations")
    if not isinstance(recommendations, list) or not recommendations:
        return None
    written_goals = goal_replenishment.get("written_goals")
    if not isinstance(written_goals, list) or not written_goals:
        return None
    return build_fanout_launch_plan(
        {
            "goals": written_goals,
            "parallel_recommendations": recommendations,
        },
        limit=limit,
        running_target_names=running_target_names,
        requires_human_review=requires_human_review,
    )


def build_paused_active_goals_fanout_plan(
    active_goals: list[dict[str, Any]],
    *,
    limit: int = DEFAULT_FANOUT_LIMIT,
) -> dict[str, Any]:
    blocked_targets = {
        target_name
        for goal in active_goals
        for target_name in (goal.get("target_name"),)
        if goal.get("last_status") in {"blocked", "needs_user"}
        and isinstance(target_name, str)
        and target_name
    }
    skipped = [
        {
            "target_name": target_name,
            "reason": "fanout_paused_for_attention",
            "batch": "active_goals",
        }
        for goal in active_goals
        for target_name in (goal.get("target_name"),)
        if isinstance(target_name, str)
        and target_name
        and target_name not in blocked_targets
    ]
    return {
        "status": "paused",
        "summary": {
            "launchable": 0,
            "skipped": len(skipped),
            "limit": limit,
        },
        "launch_specs": [],
        "skipped": skipped,
        "safety": {
            "auto_launch": False,
            "note": "fanout 已暂停，等待 blocked/needs_user worker 处理。",
        },
    }


def _candidate_by_target_name(goal_plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for raw in _candidate_items(goal_plan):
        if not isinstance(raw, dict):
            continue
        target_name = _optional_string(raw.get("target_name"))
        if not target_name:
            continue
        normalized = _normalize_target_name(target_name)
        candidates.setdefault(normalized, raw)
    return candidates


def _resolved_dependency_state(
    candidates: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    candidate_list = list(candidates)
    try:
        graph = build_dependency_graph_from_goal_records(candidate_list)
        states = build_node_states_from_goal_records(candidate_list)
        ready_nodes = resolve_ready_nodes(graph, states=states)
    except DependencyGraphError as exc:
        return {
            "status": "invalid",
            "reason": str(exc),
            "ready_target_names": set(),
            "states": {},
        }
    return {
        "status": "ok",
        "reason": None,
        "ready_target_names": {
            _normalize_target_name(node.node_id)
            for node in ready_nodes
        },
        "states": states,
    }


def _dependency_skip(
    candidate: Mapping[str, Any],
    *,
    dependency_state: Mapping[str, Any],
) -> dict[str, str] | None:
    if dependency_state.get("status") != "ok":
        reason = _optional_string(dependency_state.get("reason")) or "invalid graph"
        return {
            "reason": "dependency_graph_invalid",
            "dependency": reason,
        }
    target_name = _optional_string(candidate.get("target_name"))
    if target_name is None:
        return None
    ready_targets = dependency_state.get("ready_target_names")
    if not isinstance(ready_targets, set):
        return None
    if _normalize_target_name(target_name) in ready_targets:
        return None
    states = dependency_state.get("states")
    if not isinstance(states, Mapping):
        states = {}
    for dependency in _goal_dependencies(candidate):
        if not _dependency_ready(dependency, states=states):
            return {
                "reason": "dependency_unmet",
                "dependency": dependency,
            }
    stage = _optional_string(candidate.get("stage"))
    if stage is not None:
        return {
            "reason": "dependency_unmet",
            "dependency": stage,
        }
    return {
        "reason": "dependency_unmet",
        "dependency": _normalize_target_name(target_name),
    }


def _dependency_ready(dependency: str, *, states: Mapping[str, Any]) -> bool:
    state = states.get(dependency) or states.get(_normalize_target_name(dependency))
    if state is None:
        return False
    return (
        getattr(state, "status", None) == "done"
        and getattr(state, "merged", False)
        and getattr(state, "verified", False)
    )


def _goal_status(candidate: Mapping[str, Any]) -> str | None:
    for key in ("last_status", "status", "supervisor_status"):
        status = _optional_string(candidate.get(key))
        if status is not None:
            return status.lower()
    return None


def _goal_dependencies(candidate: Mapping[str, Any]) -> list[str]:
    return [
        _normalize_target_name(item)
        for item in _string_list(candidate.get("depends_on"))
    ]


def _launch_dependency_graph(candidate: Mapping[str, Any]) -> dict[str, Any]:
    graph: dict[str, Any] = {}
    depends_on = _goal_dependencies(candidate)
    if depends_on:
        graph["depends_on"] = depends_on
    stage = _optional_string(candidate.get("stage"))
    if stage is not None:
        graph["stage"] = stage
    scope = _optional_string(candidate.get("scope"))
    if scope is not None:
        graph["scope"] = scope
    merge_gate = _optional_string(candidate.get("merge_gate"))
    if merge_gate is not None:
        graph["merge_gate"] = merge_gate
    return graph


def _candidate_items(goal_plan: dict[str, Any]) -> list[Any]:
    items: list[Any] = []
    for key in ("candidates", "written_goals", "goals"):
        value = goal_plan.get(key)
        if isinstance(value, list):
            items.extend(value)
    return items


def _parallel_recommendations(goal_plan: dict[str, Any]) -> list[dict[str, Any]]:
    value = goal_plan.get("parallel_recommendations")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _target_names(recommendation: dict[str, Any]) -> list[str]:
    value = recommendation.get("targets")
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        text = _optional_string(item)
        if text:
            names.append(text)
    return names


def _skip_base(*, target_name: str, batch: str | None) -> dict[str, str]:
    base = {"target_name": target_name}
    if batch:
        base["batch"] = batch
    return base


def _normalize_target_name(value: str) -> str:
    text = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    text = re.sub(r"-+", "-", text)
    return text[:80] or "supervisor-goal"


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = _optional_string(item)
        if text is not None:
            items.append(text)
    return items
