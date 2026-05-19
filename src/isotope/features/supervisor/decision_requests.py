"""Persistent decision requests for Codex Supervisor."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


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


def default_decision_requests_path(codex_home: Path | str) -> Path:
    return Path(codex_home).expanduser() / "supervisor" / "decision_requests.jsonl"


def record_decision_request(
    *,
    codex_home: Path | str,
    action: dict[str, Any],
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
    append_decision_request(default_decision_requests_path(codex_home), request)
    return request


def archive_decision_request(
    *,
    codex_home: Path | str,
    request_id: str,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    request_id_text = _required_string(request_id, "request_id")
    active = {
        request.request_id
        for request in read_active_decision_requests(codex_home=codex_home, limit=1000)
    }
    if request_id_text not in active:
        raise ValueError(f"active decision request not found: {request_id_text}")
    event = {
        "event": "decision_archive",
        "request_id": request_id_text,
        "created_at": _ensure_aware_utc((now or _utc_now)()).isoformat(),
    }
    append_decision_archive(default_decision_requests_path(codex_home), event)
    return event


def record_decision_answer(
    *,
    codex_home: Path | str,
    request_id: str,
    answer: str,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    request_id_text = _required_string(request_id, "request_id")
    answer_text = _required_string(answer, "answer")
    request = _active_request_by_id(codex_home=codex_home, request_id=request_id_text)
    event = {
        "event": "decision_answer",
        "request_id": request.request_id,
        "created_at": _ensure_aware_utc((now or _utc_now)()).isoformat(),
        "session_id": request.session_id,
        "target_name": request.target_name,
        "question": request.question,
        "answer": answer_text,
    }
    if request.goal_id:
        event["goal_id"] = request.goal_id
    append_decision_answer(default_decision_requests_path(codex_home), event)
    return event


def append_decision_request(path: Path | str, request: DecisionRequest) -> None:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(request.to_dict(), ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def append_decision_archive(path: Path | str, event: dict[str, Any]) -> None:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def append_decision_answer(path: Path | str, event: dict[str, Any]) -> None:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def read_active_decision_requests(
    *,
    codex_home: Path | str,
    limit: int = 20,
) -> tuple[DecisionRequest, ...]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    path = default_decision_requests_path(codex_home)
    if not path.is_file():
        return ()
    latest: dict[tuple[str, str], DecisionRequest] = {}
    request_keys: dict[str, tuple[str, str]] = {}
    closed: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    for line in lines:
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
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
        if request is None:
            continue
        if request.request_id in closed:
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


def read_recent_decision_answers(
    *,
    codex_home: Path | str,
    limit: int = 20,
) -> tuple[dict[str, Any], ...]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    path = default_decision_requests_path(codex_home)
    if not path.is_file():
        return ()
    answers: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    for line in lines:
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        answer = _answer_from_dict(raw) if isinstance(raw, dict) else None
        if answer is not None:
            answers.append(answer)
    answers.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return tuple(answers[:limit])


def _active_request_by_id(
    *,
    codex_home: Path | str,
    request_id: str,
) -> DecisionRequest:
    for request in read_active_decision_requests(codex_home=codex_home, limit=1000):
        if request.request_id == request_id:
            return request
    raise ValueError(f"active decision request not found: {request_id}")


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
