"""Goal lifecycle synchronization for the Supervisor loop."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..planner.goal_queue import (
    archive_supervisor_goal,
    read_active_supervisor_goals,
    record_supervisor_goal_status,
)
from ..merge.merge_dispatch import DEFAULT_TARGET_NAME as MERGE_DISPATCH_TARGET_NAME

def sync_goal_lifecycle(
    args: argparse.Namespace,
    report: Any,
) -> list[dict[str, Any]]:
    active_goals = {
        goal.target_name: goal
        for goal in read_active_supervisor_goals(
            codex_home=Path(args.codex_home),
            limit=1000,
        )
    }
    if not active_goals:
        return []
    updates: list[dict[str, Any]] = []
    for session in report.sessions:
        target_name = getattr(session, "managed_name", None)
        if not isinstance(target_name, str) or not target_name:
            continue
        status = goal_status_from_session(session)
        if status is None:
            continue
        if target_name == MERGE_DISPATCH_TARGET_NAME and status == "done":
            continue
        goal = active_goals.pop(target_name, None)
        if goal is None:
            continue
        update = record_goal_status_from_session(
            args,
            goal_id=goal.goal_id,
            target_name=target_name,
            session=session,
            status=status,
        )
        updates.append(update)
    return updates


def non_empty_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def goal_status_from_session(session: Any) -> str | None:
    status = getattr(session, "supervisor_status", None)
    if not isinstance(status, str):
        return None
    normalized = status.lower()
    if normalized not in {"done", "blocked", "needs_user"}:
        return None
    return normalized


def record_goal_status_from_session(
    args: argparse.Namespace,
    *,
    goal_id: str,
    target_name: str,
    session: Any,
    status: str,
) -> dict[str, Any]:
    summary = getattr(session, "supervisor_summary", None)
    next_step = getattr(session, "supervisor_next", None)
    session_id = getattr(session, "session_id", None)
    event = record_supervisor_goal_status(
        codex_home=Path(args.codex_home),
        goal_id=goal_id,
        status=status,
        target_name=target_name,
        session_id=session_id if isinstance(session_id, str) else None,
        summary=summary if isinstance(summary, str) else None,
        next_step=next_step if isinstance(next_step, str) else None,
        webhook_url=args.webhook_url,
        webhook_secret=args.webhook_secret,
    )
    update: dict[str, Any] = {
        "goal_id": goal_id,
        "target_name": target_name,
        "session_id": session_id,
        "status": status,
    }
    if isinstance(summary, str) and summary:
        update["summary"] = summary
    if isinstance(next_step, str) and next_step:
        update["next"] = next_step
    if event is None:
        update["skipped"] = True
        update["reason"] = "duplicate goal status"
    else:
        update["event"] = event
    if status == "done":
        update["archived"] = archive_supervisor_goal(
            codex_home=Path(args.codex_home),
            goal_id=goal_id,
            status=status,
            target_name=target_name,
            session_id=session_id if isinstance(session_id, str) else None,
            summary=summary if isinstance(summary, str) else None,
            next_step=next_step if isinstance(next_step, str) else None,
        )
    return update

__all__ = (
    "goal_status_from_session",
    "non_empty_text",
    "record_goal_status_from_session",
    "sync_goal_lifecycle",
)
