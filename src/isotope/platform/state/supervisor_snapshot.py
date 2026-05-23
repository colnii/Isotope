"""Low-sensitive Supervisor state snapshot schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SupervisorStateSnapshot:
    """Structured read model for Supervisor state projection adapters."""

    codex_home: str
    summary: dict[str, int]
    active_goals: list[dict[str, Any]] = field(default_factory=list)
    active_decisions: list[dict[str, Any]] = field(default_factory=list)
    failed_lanes: list[dict[str, Any]] = field(default_factory=list)
    recent_worker_events: list[dict[str, Any]] = field(default_factory=list)
    notifications: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"

    def __post_init__(self) -> None:
        _required_text(self.status, "status")
        _required_text(self.codex_home, "codex_home")
        _dict_of_ints(self.summary, "summary")
        _list_of_dicts(self.active_goals, "active_goals")
        _list_of_dicts(self.active_decisions, "active_decisions")
        _list_of_dicts(self.failed_lanes, "failed_lanes")
        _list_of_dicts(self.recent_worker_events, "recent_worker_events")
        if not isinstance(self.notifications, dict):
            raise TypeError("notifications must be a dict")

    @classmethod
    def empty(cls, *, codex_home: Path | str) -> SupervisorStateSnapshot:
        return cls(
            codex_home=str(Path(codex_home).expanduser()),
            summary={
                "active_goals": 0,
                "goals_done": 0,
                "goals_blocked": 0,
                "goals_needs_user": 0,
                "active_decisions": 0,
                "failed_lanes": 0,
                "worker_events": 0,
                "notifications": 0,
                "unread_notifications": 0,
            },
            notifications={"total": 0, "unread": 0, "recent": []},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "codex_home": self.codex_home,
            "summary": dict(self.summary),
            "active_goals": [dict(item) for item in self.active_goals],
            "active_decisions": [dict(item) for item in self.active_decisions],
            "failed_lanes": [dict(item) for item in self.failed_lanes],
            "recent_worker_events": [dict(item) for item in self.recent_worker_events],
            "notifications": dict(self.notifications),
        }


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _dict_of_ints(value: Any, field_name: str) -> None:
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be a dict")
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{field_name} keys must be non-empty strings")
        if not isinstance(item, int):
            raise TypeError(f"{field_name} values must be integers")


def _list_of_dicts(value: Any, field_name: str) -> None:
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be a list")
    for item in value:
        if not isinstance(item, dict):
            raise TypeError(f"{field_name} entries must be dicts")
