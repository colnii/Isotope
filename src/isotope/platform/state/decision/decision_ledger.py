"""Reusable append-only decision request ledger."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DecisionRequest:
    request_id: str
    created_at: str
    session_id: str
    target_name: str | None
    question: str
    reason: str
    context_status: str | None
    gate: dict[str, Any]
    goal_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "event": "decision_request",
            "request_id": self.request_id,
            "created_at": self.created_at,
            "session_id": self.session_id,
            "target_name": self.target_name,
            "question": self.question,
            "reason": self.reason,
            "context_status": self.context_status,
            "gate": dict(self.gate),
        }
        if self.goal_id:
            payload["goal_id"] = self.goal_id
        return payload


class DecisionRequestLedger:
    """Append-only JSONL ledger for decision requests, answers, and archives."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).expanduser()

    def append_request(self, request: DecisionRequest) -> DecisionRequest:
        self._append(request.to_dict())
        return request

    def append_archive(
        self,
        *,
        request_id: str,
        now: Callable[[], datetime] | None = None,
    ) -> dict[str, Any]:
        request_id_text = _required_string(request_id, "request_id")
        event = {
            "event": "decision_archive",
            "request_id": request_id_text,
            "created_at": _ensure_aware_utc((now or _utc_now)()).isoformat(),
        }
        self._append(event)
        return event

    def append_answer(
        self,
        *,
        request: DecisionRequest,
        answer: str,
        now: Callable[[], datetime] | None = None,
    ) -> dict[str, Any]:
        answer_text = _required_string(answer, "answer")
        event = {
            "event": "decision_answer",
            "request_id": request.request_id,
            "created_at": _ensure_aware_utc((now or _utc_now)()).isoformat(),
            "session_id": request.session_id,
            "target_name": request.target_name,
            "question": request.question,
            "answer": answer_text,
            "reason": request.reason,
            "context_status": request.context_status,
            "gate": dict(request.gate),
        }
        if request.goal_id:
            event["goal_id"] = request.goal_id
        self._append(event)
        return event

    def append_event(self, event: dict[str, Any]) -> None:
        """Append a prebuilt ledger event for compatibility adapters."""
        self._append(dict(event))

    def read_active_requests(self, *, limit: int = 20) -> tuple[DecisionRequest, ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        latest: dict[tuple[str, str], DecisionRequest] = {}
        request_keys: dict[str, tuple[str, str]] = {}
        closed: set[str] = set()
        for raw in self._read_events():
            archived_id = _archive_request_id(raw)
            if archived_id is not None:
                closed.add(archived_id)
                if key := request_keys.get(archived_id):
                    latest.pop(key, None)
                continue
            answered_id = _answer_request_id(raw)
            if answered_id is not None:
                closed.add(answered_id)
                if key := request_keys.get(answered_id):
                    latest.pop(key, None)
                continue
            request = _request_from_dict(raw)
            if request is None or request.request_id in closed:
                continue
            key = (request.session_id, request.question)
            latest[key] = request
            request_keys[request.request_id] = key
        requests = sorted(
            latest.values(),
            key=lambda item: item.created_at,
            reverse=True,
        )
        return tuple(requests[:limit])

    def read_recent_answers(self, *, limit: int = 20) -> tuple[dict[str, Any], ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        answers = [
            answer
            for raw in self._read_events()
            if (answer := _answer_from_dict(raw)) is not None
        ]
        answers.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return tuple(answers[:limit])

    def active_request_for_identity(
        self,
        *,
        session_id: str,
        question: str,
    ) -> DecisionRequest | None:
        for request in self.read_active_requests(limit=1000):
            if request.session_id == session_id and request.question == question:
                return request
        return None

    def active_request_by_id(self, request_id: str) -> DecisionRequest:
        for request in self.read_active_requests(limit=1000):
            if request.request_id == request_id:
                return request
        raise ValueError(f"active decision request not found: {request_id}")

    def _append(self, event: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    def _read_events(self) -> tuple[dict[str, Any], ...]:
        if not self.path.is_file():
            return ()
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return ()
        events: list[dict[str, Any]] = []
        for line in lines:
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict):
                events.append(raw)
        return tuple(events)


def _archive_request_id(raw: dict[str, Any]) -> str | None:
    if raw.get("event") != "decision_archive":
        return None
    request_id = raw.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        return None
    return request_id


def _answer_request_id(raw: dict[str, Any]) -> str | None:
    if raw.get("event") != "decision_answer":
        return None
    request_id = raw.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        return None
    return request_id


def _answer_from_dict(raw: dict[str, Any]) -> dict[str, Any] | None:
    if raw.get("event") != "decision_answer":
        return None
    request_id = raw.get("request_id")
    created_at = raw.get("created_at")
    question = raw.get("question")
    answer = raw.get("answer")
    if not all(isinstance(value, str) and value for value in (
        request_id,
        created_at,
        question,
        answer,
    )):
        return None
    payload: dict[str, Any] = {
        "event": "decision_answer",
        "request_id": request_id,
        "created_at": created_at,
        "session_id": _optional_string(raw.get("session_id")),
        "target_name": _optional_string(raw.get("target_name")),
        "question": question,
        "answer": answer,
    }
    if reason := _optional_string(raw.get("reason")):
        payload["reason"] = reason
    if context_status := _optional_string(raw.get("context_status")):
        payload["context_status"] = context_status
    gate = raw.get("gate")
    if isinstance(gate, dict):
        payload["gate"] = dict(gate)
    if goal_id := _optional_string(raw.get("goal_id")):
        payload["goal_id"] = goal_id
    return payload


def _request_from_dict(raw: dict[str, Any]) -> DecisionRequest | None:
    if raw.get("event") != "decision_request":
        return None
    request_id = raw.get("request_id")
    created_at = raw.get("created_at")
    session_id = raw.get("session_id")
    question = raw.get("question")
    reason = raw.get("reason")
    if not all(isinstance(value, str) and value for value in (
        request_id,
        created_at,
        session_id,
        question,
        reason,
    )):
        return None
    gate = raw.get("gate")
    if not isinstance(gate, dict):
        gate = {}
    return DecisionRequest(
        request_id=request_id,
        created_at=created_at,
        session_id=session_id,
        target_name=_optional_string(raw.get("target_name")),
        question=question,
        reason=reason,
        context_status=_optional_string(raw.get("context_status")),
        gate=dict(gate),
        goal_id=_optional_string(raw.get("goal_id")),
    )


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
