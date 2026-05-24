"""Failure ledger helpers for Supervisor LLM/action guardrails."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from isotope.features.supervisor.failure_ledger import (
    FailureLedger,
    default_failure_ledger_path,
)


def record_failure_event(
    args: Any,
    *,
    event_type: str,
    report: Any | None = None,
    payload: dict[str, Any] | None = None,
    action: dict[str, Any] | None = None,
    error_summary: str,
) -> dict[str, Any]:
    ledger = FailureLedger(default_failure_ledger_path(Path(args.codex_home)))
    lane_name = failure_lane_name(args, report=report, payload=payload, action=action)
    goal_id = failure_goal_id(payload=payload, action=action, lane_name=lane_name)
    return ledger.record_failure(
        event_type=event_type,
        lane_name=lane_name,
        goal_id=goal_id,
        error_summary=error_summary,
    )


def failure_retry_exhausted(
    args: Any,
    event: dict[str, Any],
    *,
    api: Any | None = None,
) -> bool:
    if api is None:
        from isotope.features.supervisor import runner as api

    retry_count = event.get("retry_count")
    max_retries = getattr(args, "max_failure_retries", api.DEFAULT_MAX_FAILURE_RETRIES)
    return isinstance(retry_count, int) and retry_count > max_retries


def failure_decision_request_action(
    *,
    event: dict[str, Any],
    question: str,
    reason: str,
) -> dict[str, Any]:
    event_type = str(event.get("event_type") or "supervisor_failure")
    lane_name = event.get("lane_name")
    lane_text = lane_name if isinstance(lane_name, str) and lane_name else "global"
    goal_id = event.get("goal_id")
    return {
        "kind": "ask_user",
        "session_id": f"failure:{event_type}:{lane_text}",
        "target_name": lane_name if isinstance(lane_name, str) else None,
        **({"goal_id": goal_id} if isinstance(goal_id, str) and goal_id else {}),
        "question": question,
        "reason": reason,
        "context_status": "conflict",
        "codex_requested_decision": True,
        "instructions_exhausted": True,
        "command_suggestion": None,
        "failure_event": event,
    }


def failure_lane_name(
    args: Any,
    *,
    report: Any | None = None,
    payload: dict[str, Any] | None = None,
    action: dict[str, Any] | None = None,
) -> str | None:
    for value in (
        action.get("target_name") if isinstance(action, dict) else None,
        getattr(args, "name", None),
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    if report is not None:
        for session in getattr(report, "sessions", []):
            name = getattr(session, "managed_name", None)
            if isinstance(name, str) and name:
                return name
    if isinstance(payload, dict):
        for goal in payload.get("active_goals") or []:
            if isinstance(goal, dict):
                name = goal.get("target_name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
    return None


def failure_goal_id(
    *,
    payload: dict[str, Any] | None = None,
    action: dict[str, Any] | None = None,
    lane_name: str | None = None,
) -> str | None:
    if isinstance(action, dict):
        goal_id = action.get("goal_id")
        if isinstance(goal_id, str) and goal_id.strip():
            return goal_id.strip()
    if isinstance(payload, dict):
        for goal in payload.get("active_goals") or []:
            if not isinstance(goal, dict):
                continue
            goal_id = goal.get("goal_id")
            target_name = goal.get("target_name")
            if not isinstance(goal_id, str) or not goal_id.strip():
                continue
            if lane_name is None or target_name == lane_name:
                return goal_id.strip()
    return None
