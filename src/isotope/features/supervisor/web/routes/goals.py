"""Goal route helpers for the supervisor web API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...planner.goal_queue import record_supervisor_goal


def write_goal_plan_candidates(
    *,
    codex_home: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    candidates = goal_plan_candidates(payload)
    written = [
        record_supervisor_goal(
            codex_home=codex_home,
            cwd=Path.cwd(),
            goal=candidate["goal"],
            target_name=candidate.get("target_name"),
        ).to_dict()
        for candidate in candidates
    ]
    return {
        "status": "ok",
        "mode": "write",
        "root": str(Path.cwd()),
        "user_goal": _optional_string(payload.get("goal")),
        "planning_trigger": "web",
        "sources": [],
        "candidates": candidates,
        "written_goals": written,
        "plan_summary": _optional_string(payload.get("plan_summary")),
        "phases": payload.get("phases") if isinstance(payload.get("phases"), list) else [],
        "parallel_recommendations": payload.get("parallel_recommendations")
        if isinstance(payload.get("parallel_recommendations"), list)
        else [],
        "stop_conditions": payload.get("stop_conditions")
        if isinstance(payload.get("stop_conditions"), list)
        else [],
        "acceptance_conditions": payload.get("acceptance_conditions")
        if isinstance(payload.get("acceptance_conditions"), list)
        else [],
    }


def goal_plan_candidates(payload: dict[str, Any]) -> list[dict[str, str]]:
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise ValueError("candidates must not be empty")
    candidates: list[dict[str, str]] = []
    for raw in raw_candidates:
        if not isinstance(raw, dict):
            continue
        goal = _optional_string(raw.get("goal"))
        if goal is None:
            continue
        target_name = _optional_string(raw.get("target_name"))
        reason = _optional_string(raw.get("reason"))
        item = {"goal": goal}
        if target_name is not None:
            item["target_name"] = target_name
        if reason is not None:
            item["reason"] = reason
        candidates.append(item)
    if not candidates:
        raise ValueError("candidates must contain usable goals")
    return candidates


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()
