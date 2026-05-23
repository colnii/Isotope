"""Read-only Supervisor state projection for dashboard and loop inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from isotope.features.notifications.flow import NotificationFlow, NotificationSummary
from isotope.memory.worker_event_channel import list_worker_events

from ..decision_requests import read_active_decision_requests
from ..goal_queue import (
    SupervisorGoal,
    read_active_supervisor_goals,
    read_latest_supervisor_goal_statuses,
)
from ..lane_state import LaneState, default_lane_state_path, read_lane_states


def build_supervisor_state_snapshot(
    *,
    codex_home: Path | str,
    decision_limit: int = 20,
    worker_event_limit: int = 20,
    notification_limit: int = 20,
    goal_limit: int = 20,
) -> dict[str, Any]:
    """Build a low-sensitive read model from existing Supervisor ledgers."""
    codex_home_path = Path(codex_home).expanduser()
    active_goals = _active_goal_payloads(codex_home_path, limit=goal_limit)
    active_decisions = [
        _decision_request_payload(request)
        for request in read_active_decision_requests(
            codex_home=codex_home_path,
            limit=decision_limit,
        )
    ]
    failed_lanes = _failed_lane_payloads(codex_home_path)
    worker_events = list_worker_events(
        root=codex_home_path,
        limit=worker_event_limit,
    )
    notifications = _notification_payload(
        codex_home_path,
        limit=notification_limit,
    )
    worker_event_summary = worker_events.get("summary", {})
    total_worker_events = (
        worker_event_summary.get("total", 0)
        if isinstance(worker_event_summary, dict)
        else 0
    )

    return {
        "status": "ok",
        "codex_home": str(codex_home_path),
        "summary": {
            "active_goals": len(active_goals),
            "goals_done": _goal_status_count(active_goals, "done"),
            "goals_blocked": _goal_status_count(active_goals, "blocked"),
            "goals_needs_user": _goal_status_count(active_goals, "needs_user"),
            "active_decisions": len(active_decisions),
            "failed_lanes": len(failed_lanes),
            "worker_events": total_worker_events,
            "notifications": notifications["total"],
            "unread_notifications": notifications["unread"],
        },
        "active_goals": active_goals,
        "active_decisions": active_decisions,
        "failed_lanes": failed_lanes,
        "recent_worker_events": list(worker_events.get("events") or []),
        "notifications": notifications,
    }


def _active_goal_payloads(codex_home: Path, *, limit: int) -> list[dict[str, Any]]:
    statuses = read_latest_supervisor_goal_statuses(codex_home=codex_home)
    return [
        _active_goal_payload(goal, latest_status=statuses.get(goal.goal_id))
        for goal in read_active_supervisor_goals(codex_home=codex_home, limit=limit)
    ]


def _active_goal_payload(
    goal: SupervisorGoal,
    *,
    latest_status: dict[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "goal_id": goal.goal_id,
        "created_at": goal.created_at,
        "cwd": goal.cwd,
        "goal": goal.goal,
        "target_name": goal.target_name,
        "depends_on": list(goal.depends_on),
        "stage": goal.stage,
        "scope": goal.scope,
        "merge_gate": goal.merge_gate,
    }
    if latest_status:
        payload.update(dict(latest_status))
    return payload


def _goal_status_count(goals: list[dict[str, Any]], status: str) -> int:
    return sum(1 for goal in goals if goal.get("last_status") == status)


def _decision_request_payload(request: Any) -> dict[str, Any]:
    return {
        "request_id": request.request_id,
        "session_id": request.session_id,
        "target_name": request.target_name,
        "goal_id": request.goal_id,
        "question": request.question,
        "reason": request.reason,
        "context_status": request.context_status,
        "created_at": request.created_at,
    }


def _failed_lane_payloads(codex_home: Path) -> list[dict[str, Any]]:
    states = read_lane_states(default_lane_state_path(codex_home))
    failed = [
        state
        for state in states.values()
        if state.last_status == "failed" and state.last_failure_reason
    ]
    return [_failed_lane_payload(state) for state in sorted(failed, key=lambda item: item.name)]


def _failed_lane_payload(state: LaneState) -> dict[str, Any]:
    return {
        "name": state.name,
        "last_failure_reason": state.last_failure_reason,
        "last_failure_exit_code": state.last_failure_exit_code,
        "last_failure_stderr_summary": state.last_failure_stderr_summary,
        "last_failure_record_id": state.last_failure_record_id,
        "last_failed_at": state.last_failed_at,
        "failure_count": state.failure_count,
        "worker_retry_count": state.worker_retry_count,
    }


def _notification_payload(codex_home: Path, *, limit: int) -> dict[str, Any]:
    notifications = NotificationFlow.in_process(codex_home).list_notifications()
    recent = notifications[:limit]
    unread_count = sum(1 for item in notifications if item.unread)
    return {
        "total": len(notifications),
        "unread": unread_count,
        "recent": [_notification_summary_payload(item) for item in recent],
    }


def _notification_summary_payload(summary: NotificationSummary) -> dict[str, Any]:
    payload = summary.to_dict()
    return {
        "notification_id": payload["notification_id"],
        "type": payload["type"],
        "title": payload["title"],
        "unread": payload["unread"],
        "created_at": payload["created_at"],
        "read_at": payload["read_at"],
        "source_ref": payload["source_ref"],
    }
