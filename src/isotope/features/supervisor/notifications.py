"""Supervisor event bridge for low-sensitive notifications."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from isotope.features.notifications.flow import NotificationFlow, NotificationSummary


def notify_goal_status_written(
    *,
    codex_home: Path | str,
    goal_id: str,
    status: str,
    target_name: str | None = None,
) -> NotificationSummary | None:
    source_ref = _low_sensitive_source_ref(
        ref_type="supervisor_goal_status",
        goal_id=goal_id,
        status=status,
    )
    return _try_create_notification(
        codex_home=codex_home,
        notification_type="supervisor_goal_status",
        title=f"Supervisor goal status: {status}",
        source_ref=source_ref,
    )


def notify_decision_request_written(
    *,
    codex_home: Path | str,
    request_id: str,
    target_name: str | None = None,
    goal_id: str | None = None,
) -> NotificationSummary | None:
    source_ref = _low_sensitive_source_ref(
        ref_type="supervisor_decision_request",
        goal_id=goal_id,
        request_id=request_id,
    )
    return _try_create_notification(
        codex_home=codex_home,
        notification_type="supervisor_decision_request",
        title="Supervisor decision request",
        source_ref=source_ref,
    )


def _low_sensitive_source_ref(**fields: str | None) -> dict[str, Any]:
    return {
        key: value
        for key, value in fields.items()
        if isinstance(value, str) and value.strip()
    }


def _try_create_notification(
    *,
    codex_home: Path | str,
    notification_type: str,
    title: str,
    source_ref: dict[str, Any],
) -> NotificationSummary | None:
    try:
        return NotificationFlow.in_process(codex_home).create_notification(
            notification_type=notification_type,
            title=title,
            source_ref=source_ref,
        )
    except (OSError, ValueError):
        return None
