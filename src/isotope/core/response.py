"""Product-level response shapes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CoreTurnResponse:
    status: str
    run_id: str
    run_status: str
    artifact_ref: dict[str, Any]
    artifact_summary: str
    event_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "run_id": self.run_id,
            "run_status": self.run_status,
            "artifact_ref": dict(self.artifact_ref),
            "artifact_summary": self.artifact_summary,
            "event_count": self.event_count,
        }


@dataclass(frozen=True)
class CoreTurn:
    text: str
    response: CoreTurnResponse

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "response": self.response.to_dict(),
        }


@dataclass(frozen=True)
class CoreConversationState:
    conversation_id: str
    session_id: str
    run_id: str
    goal: str
    run_ids: tuple[str, ...]
    turns: tuple[CoreTurn, ...]

    @property
    def latest_response(self) -> CoreTurnResponse | None:
        if not self.turns:
            return None
        return self.turns[-1].response

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "goal": self.goal,
            "run_ids": list(self.run_ids),
            "turns": [turn.to_dict() for turn in self.turns],
            "latest_response": self.latest_response.to_dict()
            if self.latest_response is not None
            else None,
        }
