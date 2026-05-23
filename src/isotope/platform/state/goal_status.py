"""Supervisor goal status read-model schema."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


GOAL_STATUS_VALUES = {"done", "blocked", "needs_user"}


@dataclass(frozen=True)
class SupervisorGoalStatus:
    """Low-sensitive status payload for an active Supervisor goal."""

    goal_id: str
    status: str
    created_at: str
    target_name: str | None = None
    session_id: str | None = None
    summary: str | None = None
    next_step: str | None = None

    def __post_init__(self) -> None:
        _required_text(self.goal_id, "goal_id")
        status = _required_text(self.status, "status")
        _required_text(self.created_at, "created_at")
        if status not in GOAL_STATUS_VALUES:
            supported = ", ".join(sorted(GOAL_STATUS_VALUES))
            raise ValueError(f"status must be one of: {supported}")
        for field_name in ("target_name", "session_id", "summary", "next_step"):
            value = getattr(self, field_name)
            if value is not None:
                _required_text(value, field_name)

    @classmethod
    def from_event(cls, event: dict[str, Any]) -> SupervisorGoalStatus | None:
        goal_id = event.get("goal_id")
        status = event.get("status")
        created_at = event.get("created_at")
        if not all(isinstance(value, str) and value for value in (goal_id, status, created_at)):
            return None
        try:
            return cls(
                goal_id=goal_id,
                status=status,
                created_at=created_at,
                target_name=_optional_text(event.get("target_name")),
                session_id=_optional_text(event.get("session_id")),
                summary=_optional_text(event.get("summary")),
                next_step=_optional_text(event.get("next")),
            )
        except ValueError:
            return None

    def to_latest_payload(self) -> dict[str, Any]:
        item: dict[str, Any] = {
            "goal_id": self.goal_id,
            "last_status": self.status,
            "last_status_at": self.created_at,
        }
        for value, key in (
            (self.target_name, "last_target_name"),
            (self.session_id, "last_session_id"),
            (self.summary, "last_summary"),
            (self.next_step, "last_next"),
        ):
            if value is not None:
                item[key] = value
        return item


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
