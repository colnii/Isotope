"""Contracts for Supervisor long tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


TASK_STATUSES = {
    "queued",
    "running",
    "paused",
    "stopping",
    "stopped",
    "completed",
    "failed",
    "blocked",
}
CONTROL_STATES = {"run", "pause", "resume", "stop"}
RAW_LONG_TASK_FIELDS = {
    "api_key",
    "artifact_content",
    "full_content",
    "full_text",
    "messages",
    "model_prompt",
    "model_request",
    "model_response",
    "prompt",
    "raw_artifact_content",
    "raw_content",
    "raw_prompt",
    "raw_provider_response",
    "raw_response",
    "secret",
    "stderr",
    "stdin",
    "stdout",
    "token",
}


@dataclass(frozen=True)
class LongTaskRecord:
    task_id: str
    run_id: str
    session_id: str
    goal: str
    status: str
    created_at: str
    updated_at: str
    last_event_id: str = ""
    last_checkpoint_event_id: str = ""
    heartbeat: dict[str, Any] = field(default_factory=dict)
    control_state: str = "run"
    summary: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.task_id, "task_id")
        _require_text(self.run_id, "run_id")
        _require_text(self.session_id, "session_id")
        _require_text(self.goal, "goal")
        _require_choice(self.status, TASK_STATUSES, "status")
        _require_text(self.created_at, "created_at")
        _require_text(self.updated_at, "updated_at")
        _require_optional_text(self.last_event_id, "last_event_id")
        _require_optional_text(
            self.last_checkpoint_event_id,
            "last_checkpoint_event_id",
        )
        _require_choice(self.control_state, CONTROL_STATES, "control_state")
        if not isinstance(self.heartbeat, dict):
            raise ValueError("heartbeat must be a dict")
        if not isinstance(self.summary, dict):
            raise ValueError("summary must be a dict")
        reject_raw_long_task_payload(self.heartbeat)
        reject_raw_long_task_payload(self.summary)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "goal": self.goal,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_event_id": self.last_event_id,
            "last_checkpoint_event_id": self.last_checkpoint_event_id,
            "heartbeat": _copy_public_payload(self.heartbeat),
            "control_state": self.control_state,
            "summary": _copy_public_payload(self.summary),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LongTaskRecord":
        return cls(
            task_id=_dict_text(payload, "task_id"),
            run_id=_dict_text(payload, "run_id"),
            session_id=_dict_text(payload, "session_id"),
            goal=_dict_text(payload, "goal"),
            status=_dict_text(payload, "status"),
            created_at=_dict_text(payload, "created_at"),
            updated_at=_dict_text(payload, "updated_at"),
            last_event_id=str(payload.get("last_event_id") or ""),
            last_checkpoint_event_id=str(
                payload.get("last_checkpoint_event_id") or ""
            ),
            heartbeat=_dict_payload(payload.get("heartbeat")),
            control_state=str(payload.get("control_state") or "run"),
            summary=_dict_payload(payload.get("summary")),
        )


@dataclass(frozen=True)
class LongTaskControlRecord:
    task_id: str
    control: str
    reason: str
    created_at: str

    def __post_init__(self) -> None:
        _require_text(self.task_id, "task_id")
        _require_choice(self.control, CONTROL_STATES, "control")
        _require_text(self.reason, "reason")
        _require_text(self.created_at, "created_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "control": self.control,
            "reason": self.reason,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LongTaskControlRecord":
        return cls(
            task_id=_dict_text(payload, "task_id"),
            control=_dict_text(payload, "control"),
            reason=_dict_text(payload, "reason"),
            created_at=_dict_text(payload, "created_at"),
        )


def reject_raw_long_task_payload(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = RAW_LONG_TASK_FIELDS.intersection(value)
        if forbidden:
            raise ValueError("raw long-task payload fields are not allowed")
        for nested in value.values():
            reject_raw_long_task_payload(nested)
    elif isinstance(value, list):
        for nested in value:
            reject_raw_long_task_payload(nested)


def _copy_public_payload(value: Any) -> Any:
    reject_raw_long_task_payload(value)
    if isinstance(value, dict):
        return {str(key): _copy_public_payload(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [_copy_public_payload(nested) for nested in value]
    return value


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_optional_text(value: object, field_name: str) -> None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")


def _require_choice(value: object, choices: set[str], field_name: str) -> str:
    if value not in choices:
        raise ValueError(f"{field_name} must be one of {sorted(choices)}")
    return str(value)


def _dict_text(payload: dict[str, Any], field_name: str) -> str:
    return _require_text(payload.get(field_name), field_name)


def _dict_payload(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("payload value must be a dict")
    reject_raw_long_task_payload(value)
    return dict(value)
