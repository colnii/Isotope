"""Fanout planning helpers for Supervisor goal-plan recommendations."""

from __future__ import annotations

import re
from typing import Any, Iterable


DEFAULT_FANOUT_LIMIT = 3
REVIEW_NOTE = "fanout 只生成受控 launch spec；runner 执行时仍需通过 launch gate。"


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
            if len(launch_specs) >= limit:
                skipped.append({**skip_base, "reason": "fanout_limit_reached"})
                continue
            launch_cwd = _optional_string(candidate.get("cwd")) or default_cwd
            if not launch_cwd:
                skipped.append({**skip_base, "reason": "cwd_missing"})
                continue
            goal = _optional_string(candidate.get("goal"))
            if not goal:
                skipped.append({**skip_base, "reason": "goal_missing"})
                continue
            launch_specs.append(
                {
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
            )

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
