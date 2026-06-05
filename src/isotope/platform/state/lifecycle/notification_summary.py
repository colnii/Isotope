"""Supervisor notification summary schema for public state snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


NOTIFICATION_SOURCE_REF_KEYS = {
    "ref_type",
    "goal_id",
    "request_id",
    "run_id",
    "session_id",
    "notification_id",
    "status",
    "target_name",
    "timeout_seconds",
}


@dataclass(frozen=True)
class SupervisorNotificationSummary:
    """Public notification payload for Supervisor read models."""

    notification_id: str
    notification_type: str
    title: str
    unread: bool
    created_at: str
    read_at: str | None = None
    source_ref: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        _required_text(self.notification_id, "notification_id")
        _required_text(self.notification_type, "notification_type")
        _required_text(self.title, "title")
        if not isinstance(self.unread, bool):
            raise TypeError("unread must be a bool")
        _required_text(self.created_at, "created_at")
        _optional_text(self.read_at, "read_at")
        if self.source_ref is not None and not isinstance(self.source_ref, dict):
            raise TypeError("source_ref must be a dict")

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SupervisorNotificationSummary":
        return cls(
            notification_id=payload.get("notification_id"),
            notification_type=payload.get("type"),
            title=payload.get("title"),
            unread=payload.get("unread"),
            created_at=payload.get("created_at"),
            read_at=payload.get("read_at"),
            source_ref=payload.get("source_ref"),
        )

    def to_state_payload(self) -> dict[str, Any]:
        return {
            "notification_id": self.notification_id,
            "type": self.notification_type,
            "title": self.title,
            "unread": self.unread,
            "created_at": self.created_at,
            "read_at": self.read_at,
            "source_ref": filter_notification_source_ref(self.source_ref),
        }


def filter_notification_source_ref(source_ref: Any) -> dict[str, Any]:
    """Return the stable public source reference used by state snapshots."""
    if not isinstance(source_ref, dict):
        return {}
    return {
        key: value
        for key, value in source_ref.items()
        if key in NOTIFICATION_SOURCE_REF_KEYS and isinstance(value, str | bool | int | float)
    }


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value
