"""Supervisor event bridge for low-sensitive notifications."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from pathlib import Path
from typing import Any
import urllib.request

from isotope.features.notifications.flow import NotificationFlow, NotificationSummary

LOGGER = logging.getLogger(__name__)
WEBHOOK_TIMEOUT_SECONDS = 5


def notify_goal_status_written(
    *,
    codex_home: Path | str,
    goal_id: str,
    status: str,
    target_name: str | None = None,
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
) -> NotificationSummary | None:
    source_ref = _low_sensitive_source_ref(
        ref_type="supervisor_goal_status",
        goal_id=goal_id,
        status=status,
    )
    summary = _try_create_notification(
        codex_home=codex_home,
        notification_type="supervisor_goal_status",
        title=f"Supervisor goal status: {status}",
        source_ref=source_ref,
    )
    dispatch_supervisor_webhook(
        event_type="supervisor_goal_status",
        source_ref=source_ref,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
    )
    return summary


def notify_decision_request_written(
    *,
    codex_home: Path | str,
    request_id: str,
    target_name: str | None = None,
    goal_id: str | None = None,
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
) -> NotificationSummary | None:
    source_ref = _low_sensitive_source_ref(
        ref_type="supervisor_decision_request",
        goal_id=goal_id,
        request_id=request_id,
    )
    summary = _try_create_notification(
        codex_home=codex_home,
        notification_type="supervisor_decision_request",
        title="Supervisor decision request",
        source_ref=source_ref,
    )
    dispatch_supervisor_webhook(
        event_type="supervisor_decision_request",
        source_ref=source_ref,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
    )
    return summary


def notify_decision_answer_written(
    *,
    request_id: str,
    goal_id: str | None = None,
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
) -> None:
    source_ref = _low_sensitive_source_ref(
        ref_type="supervisor_decision_answer",
        goal_id=goal_id,
        request_id=request_id,
    )
    dispatch_supervisor_webhook(
        event_type="supervisor_decision_answer",
        source_ref=source_ref,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
    )


def notify_decision_request_timeout(
    *,
    codex_home: Path | str,
    request_id: str,
    target_name: str | None = None,
    goal_id: str | None = None,
    timeout_seconds: int,
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
) -> NotificationSummary | None:
    source_ref = _low_sensitive_source_ref(
        ref_type="supervisor_decision_timeout",
        goal_id=goal_id,
        request_id=request_id,
        target_name=target_name,
        timeout_seconds=str(timeout_seconds),
    )
    summary = _try_create_notification(
        codex_home=codex_home,
        notification_type="supervisor_decision_timeout",
        title="Supervisor decision request timeout",
        source_ref=source_ref,
    )
    dispatch_supervisor_webhook(
        event_type="supervisor_decision_timeout",
        source_ref=source_ref,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
    )
    return summary


def notify_worker_integration_review_passed(
    *,
    record_id: str,
    group: str,
    status: str = "done",
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
) -> None:
    source_ref = _low_sensitive_source_ref(
        ref_type="supervisor_worker_integration_review",
        record_id=record_id,
        status=status,
        group=group,
    )
    dispatch_supervisor_webhook(
        event_type="supervisor_worker_integration_review",
        source_ref=source_ref,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
    )


def dispatch_supervisor_webhook(
    *,
    event_type: str,
    source_ref: dict[str, Any],
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
) -> bool:
    url = webhook_url.strip() if isinstance(webhook_url, str) else ""
    if not url:
        return False
    payload = {
        "event_type": event_type,
        "source_ref": _low_sensitive_source_ref(**source_ref),
    }
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Isotope-Event": event_type,
    }
    secret = webhook_secret.strip() if isinstance(webhook_secret, str) else ""
    if secret:
        digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers["X-Isotope-Signature"] = f"sha256={digest}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=WEBHOOK_TIMEOUT_SECONDS) as response:
            response.read()
    except Exception as exc:  # noqa: BLE001 - external webhook failures must not break ledgers.
        LOGGER.warning("supervisor webhook POST failed: %s", exc)
        return False
    return True


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
