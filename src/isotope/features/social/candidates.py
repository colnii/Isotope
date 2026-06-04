"""Action candidates proposed by social agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .messages import (
    _omit_empty,
    _optional_nullable_string,
    _required_string_value,
    _string_tuple,
)
from .replies import SocialReplyAction


SUPPORTED_SOCIAL_ACTION_KINDS = {
    "silent",
    "internal_note",
    "respond",
    "interrupt",
    "call_capability",
    "write_memory",
    "request_operator_review",
}
SEND_ACTION_KINDS = {"respond", "interrupt"}


@dataclass(frozen=True)
class SocialActionCandidate:
    candidate_id: str
    agent_id: str
    kind: str
    reason: str
    confidence: float
    reply_action: SocialReplyAction | None = None
    capability_id: str | None = None
    memory_key: str | None = None
    state_locks: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _required_string_value(self.candidate_id, "candidate_id")
        _required_string_value(self.agent_id, "agent_id")
        if self.kind not in SUPPORTED_SOCIAL_ACTION_KINDS:
            raise ValueError("social action kind is not supported")
        _required_string_value(self.reason, "candidate reason")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            raise ValueError("candidate confidence must be between 0 and 1")
        if self.confidence < 0 or self.confidence > 1:
            raise ValueError("candidate confidence must be between 0 and 1")
        if self.is_send_action and not isinstance(self.reply_action, SocialReplyAction):
            raise ValueError("send candidates require reply_action")
        if not self.is_send_action and self.reply_action is not None:
            raise ValueError("non-send candidates must not include reply_action")
        _optional_nullable_string(self.capability_id, "capability_id")
        _optional_nullable_string(self.memory_key, "memory_key")
        _string_tuple(self.state_locks, "state_locks")
        if not isinstance(self.metadata, dict):
            raise ValueError("candidate metadata must be a dict")

    @property
    def is_send_action(self) -> bool:
        return self.kind in SEND_ACTION_KINDS

    def to_public_dict(self) -> dict[str, Any]:
        return _omit_empty(
            {
                "candidate_id": self.candidate_id,
                "agent_id": self.agent_id,
                "kind": self.kind,
                "reason": self.reason,
                "confidence": self.confidence,
                "reply_action": (
                    self.reply_action.to_public_dict()
                    if self.reply_action is not None
                    else None
                ),
                "capability_id": self.capability_id,
                "memory_key": self.memory_key,
                "state_locks": list(self.state_locks),
                "metadata": dict(self.metadata),
            }
        )
