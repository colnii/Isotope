"""Supervisor adapter for persistent decision requests."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from isotope.platform.state.decision_ledger import DecisionRequest, DecisionRequestLedger

from ..state.lane_state import clear_lane_decision_timeout, record_lane_decision_timeout
from ..notifications.notifications import (
    notify_decision_answer_written,
    notify_decision_request_timeout,
    notify_decision_request_written,
)


DEFAULT_DECISION_TIMEOUT_SECONDS = 3600


def default_decision_requests_path(codex_home: Path | str) -> Path:
    return Path(codex_home).expanduser() / "supervisor" / "decision_requests.jsonl"


def record_decision_request(
    *,
    codex_home: Path | str,
    action: dict[str, Any],
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
    now: Callable[[], datetime] | None = None,
) -> DecisionRequest:
    goal_id = _optional_string(action.get("goal_id"))
    raw_session_id = action.get("session_id")
    session_id = (
        f"goal:{goal_id}"
        if goal_id and (not isinstance(raw_session_id, str) or not raw_session_id.strip())
        else _required_string(raw_session_id, "session_id")
    )
    question = _required_string(action.get("question"), "question")
    reason = _required_string(action.get("reason"), "reason")
    target_name = _optional_string(action.get("target_name"))
    context_status = _optional_string(action.get("context_status"))
    gate = action.get("gate")
    if not isinstance(gate, dict):
        gate = {
            "codex_requested_decision": action.get("codex_requested_decision"),
            "instructions_exhausted": action.get("instructions_exhausted"),
            "context_status": context_status,
        }

    ledger = _decision_ledger(codex_home)
    existing = ledger.active_request_for_identity(
        session_id=session_id,
        question=question,
    )
    if existing is not None:
        return existing

    request = DecisionRequest(
        request_id="decision-" + uuid.uuid4().hex[:12],
        created_at=_ensure_aware_utc((now or _utc_now)()).isoformat(),
        session_id=session_id,
        target_name=target_name,
        question=question,
        reason=reason,
        context_status=context_status,
        gate=dict(gate),
        goal_id=goal_id,
    )
    ledger.append_request(request)
    notify_decision_request_written(
        codex_home=codex_home,
        request_id=request.request_id,
        target_name=request.target_name,
        goal_id=request.goal_id,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
    )
    return request


def archive_decision_request(
    *,
    codex_home: Path | str,
    request_id: str,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    request_id_text = _required_string(request_id, "request_id")
    ledger = _decision_ledger(codex_home)
    request = ledger.active_request_by_id(request_id_text)
    event = ledger.append_archive(request_id=request_id_text, now=now or _utc_now)
    clear_lane_decision_timeout(
        codex_home=codex_home,
        name=_decision_lane_name(request),
        request_id=request.request_id,
    )
    return event


def record_decision_answer(
    *,
    codex_home: Path | str,
    request_id: str,
    answer: str,
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    request_id_text = _required_string(request_id, "request_id")
    ledger = _decision_ledger(codex_home)
    request = ledger.active_request_by_id(request_id_text)
    event = ledger.append_answer(
        request=request,
        answer=_required_string(answer, "answer"),
        now=now or _utc_now,
    )
    clear_lane_decision_timeout(
        codex_home=codex_home,
        name=_decision_lane_name(request),
        request_id=request.request_id,
    )
    notify_decision_answer_written(
        request_id=request.request_id,
        goal_id=request.goal_id,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
    )
    return event


def mark_stale_decision_request_timeouts(
    *,
    codex_home: Path | str,
    timeout_seconds: int = DEFAULT_DECISION_TIMEOUT_SECONDS,
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
    now: Callable[[], datetime] | None = None,
) -> list[dict[str, Any]]:
    if timeout_seconds <= 0:
        return []
    current = _ensure_aware_utc((now or _utc_now)())
    alerts: list[dict[str, Any]] = []
    for request in read_active_decision_requests(codex_home=codex_home, limit=1000):
        created_at = _parse_timestamp(request.created_at)
        if created_at is None:
            continue
        age_seconds = max(0, int((current - created_at).total_seconds()))
        if age_seconds < timeout_seconds:
            continue
        lane_name = _decision_lane_name(request)
        _state, first_alert = record_lane_decision_timeout(
            codex_home=codex_home,
            name=lane_name,
            request_id=request.request_id,
            timeout_seconds=timeout_seconds,
            now=current,
        )
        if not first_alert:
            continue
        alert = {
            "request_id": request.request_id,
            "goal_id": request.goal_id,
            "target_name": request.target_name,
            "lane_name": lane_name,
            "timeout_seconds": timeout_seconds,
        }
        alerts.append(alert)
        notify_decision_request_timeout(
            codex_home=codex_home,
            request_id=request.request_id,
            target_name=request.target_name,
            goal_id=request.goal_id,
            timeout_seconds=timeout_seconds,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
        )
    return alerts


def append_decision_request(path: Path | str, request: DecisionRequest) -> None:
    DecisionRequestLedger(path).append_request(request)


def append_decision_archive(path: Path | str, event: dict[str, Any]) -> None:
    DecisionRequestLedger(path).append_event(event)


def append_decision_answer(path: Path | str, event: dict[str, Any]) -> None:
    DecisionRequestLedger(path).append_event(event)


def read_active_decision_requests(
    *,
    codex_home: Path | str,
    limit: int = 20,
) -> tuple[DecisionRequest, ...]:
    return _decision_ledger(codex_home).read_active_requests(limit=limit)


def read_recent_decision_answers(
    *,
    codex_home: Path | str,
    limit: int = 20,
) -> tuple[dict[str, Any], ...]:
    return _decision_ledger(codex_home).read_recent_answers(limit=limit)


def _decision_ledger(codex_home: Path | str) -> DecisionRequestLedger:
    return DecisionRequestLedger(default_decision_requests_path(codex_home))


def _active_request_by_id(
    *,
    codex_home: Path | str,
    request_id: str,
) -> DecisionRequest:
    return _decision_ledger(codex_home).active_request_by_id(request_id)


def _decision_lane_name(request: DecisionRequest) -> str:
    return request.target_name or request.session_id


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return _ensure_aware_utc(parsed)


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must not be empty")
    return value.strip()


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
