"""Supervisor decision request schema for public state snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SupervisorDecisionRequest:
    """Active decision request payload used by Supervisor read models."""

    request_id: str
    session_id: str
    target_name: str | None
    goal_id: str | None
    question: str
    reason: str
    context_status: str | None
    created_at: str

    def __post_init__(self) -> None:
        _required_text(self.request_id, "request_id")
        _required_text(self.session_id, "session_id")
        _optional_text(self.target_name, "target_name")
        _optional_text(self.goal_id, "goal_id")
        _required_text(self.question, "question")
        _required_text(self.reason, "reason")
        _optional_text(self.context_status, "context_status")
        _required_text(self.created_at, "created_at")

    @classmethod
    def from_ledger_request(cls, request: Any) -> "SupervisorDecisionRequest":
        return cls(
            request_id=request.request_id,
            session_id=request.session_id,
            target_name=request.target_name,
            goal_id=request.goal_id,
            question=request.question,
            reason=request.reason,
            context_status=request.context_status,
            created_at=request.created_at,
        )

    def to_state_payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "target_name": self.target_name,
            "goal_id": self.goal_id,
            "question": self.question,
            "reason": self.reason,
            "context_status": self.context_status,
            "created_at": self.created_at,
        }


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value
