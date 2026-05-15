"""Product-level task state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .response import CoreConversationState


@dataclass(frozen=True)
class CoreTask:
    task_id: str
    conversation_id: str
    goal: str


@dataclass(frozen=True)
class CoreTaskState:
    task_id: str
    conversation: CoreConversationState
    status: str

    @property
    def goal(self) -> str:
        return self.conversation.goal

    @property
    def result_summary(self) -> str | None:
        if self.conversation.latest_response is None:
            return None
        return self.conversation.latest_response.artifact_summary

    @property
    def result_ref(self) -> dict[str, Any] | None:
        if self.conversation.latest_response is None:
            return None
        return dict(self.conversation.latest_response.artifact_ref)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status,
            "conversation": self.conversation.to_dict(),
            "result_summary": self.result_summary,
            "result_ref": self.result_ref,
        }
