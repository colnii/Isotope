"""Supervisor worker event summary schema for public state snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


WORKER_EVENT_PAYLOAD_KEYS = {
    "branch",
    "goal_id",
    "record_id",
    "run_id",
    "session_id",
    "status",
    "target_name",
    "worker",
    "worker_id",
    "worker_name",
}


@dataclass(frozen=True)
class SupervisorWorkerEventSummary:
    """Public worker event payload for Supervisor read models."""

    record_id: str
    channel: str
    event_type: str
    from_worker: str
    to_worker: str | None
    message: str
    payload: dict[str, Any]
    created_at: str
    summary: str
    quality: str

    def __post_init__(self) -> None:
        _required_text(self.record_id, "record_id")
        _required_text(self.channel, "channel")
        _required_text(self.event_type, "event_type")
        _required_text(self.from_worker, "from_worker")
        _optional_text(self.to_worker, "to_worker")
        _required_text(self.message, "message")
        if not isinstance(self.payload, dict):
            raise TypeError("payload must be a dict")
        _required_text(self.created_at, "created_at")
        _required_text(self.summary, "summary")
        _required_text(self.quality, "quality")

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SupervisorWorkerEventSummary":
        return cls(
            record_id=payload.get("record_id"),
            channel=payload.get("channel"),
            event_type=payload.get("event_type"),
            from_worker=payload.get("from_worker"),
            to_worker=payload.get("to_worker"),
            message=payload.get("message"),
            payload=payload.get("payload"),
            created_at=payload.get("created_at"),
            summary=payload.get("summary"),
            quality=payload.get("quality"),
        )

    def to_state_payload(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "channel": self.channel,
            "event_type": self.event_type,
            "from_worker": self.from_worker,
            "to_worker": self.to_worker,
            "message": self.message,
            "payload": filter_worker_event_payload(self.payload),
            "created_at": self.created_at,
            "summary": self.summary,
            "quality": self.quality,
        }


def filter_worker_event_payload(payload: Any) -> dict[str, Any]:
    """Return stable public worker event payload keys for snapshots."""
    if not isinstance(payload, dict):
        return {}
    return {
        key: value
        for key, value in payload.items()
        if key in WORKER_EVENT_PAYLOAD_KEYS
        and isinstance(value, str | bool | int | float)
    }


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value
