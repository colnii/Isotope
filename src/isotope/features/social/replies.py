"""Platform-neutral outgoing social reply actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .messages import (
    SUPPORTED_CHAT_TYPES,
    SocialMessagePart,
    _omit_empty,
    _optional_nullable_string,
    _required_string_value,
)


SUPPORTED_SEND_URGENCIES = {"normal", "interrupt", "delayed"}


@dataclass(frozen=True)
class SocialTarget:
    platform: str
    chat_type: str
    group_id: str | None = None
    user_id: str | None = None

    def __post_init__(self) -> None:
        _required_string_value(self.platform, "target.platform")
        if self.chat_type not in SUPPORTED_CHAT_TYPES:
            raise ValueError("target.chat_type must be group or private")
        if self.chat_type == "group":
            _required_string_value(self.group_id, "target.group_id")
            _optional_nullable_string(self.user_id, "target.user_id")
        else:
            _required_string_value(self.user_id, "target.user_id")
            _optional_nullable_string(self.group_id, "target.group_id")

    def to_public_dict(self) -> dict[str, Any]:
        return _omit_empty(
            {
                "platform": self.platform.strip(),
                "chat_type": self.chat_type,
                "group_id": self.group_id.strip() if self.group_id else None,
                "user_id": self.user_id.strip() if self.user_id else None,
            }
        )


@dataclass(frozen=True)
class SocialSendPolicy:
    urgency: str = "normal"
    allow_split: bool = True
    max_chunks: int = 1
    min_delay_ms: int = 0
    reason: str = ""

    def __post_init__(self) -> None:
        if self.urgency not in SUPPORTED_SEND_URGENCIES:
            raise ValueError("send policy urgency is not supported")
        if not isinstance(self.allow_split, bool):
            raise ValueError("send policy allow_split must be a bool")
        if isinstance(self.max_chunks, bool) or not isinstance(self.max_chunks, int):
            raise ValueError("send policy max_chunks must be a positive integer")
        if self.max_chunks <= 0:
            raise ValueError("send policy max_chunks must be a positive integer")
        if isinstance(self.min_delay_ms, bool) or not isinstance(self.min_delay_ms, int):
            raise ValueError("send policy min_delay_ms must be a non-negative integer")
        if self.min_delay_ms < 0:
            raise ValueError("send policy min_delay_ms must be a non-negative integer")
        if not isinstance(self.reason, str):
            raise ValueError("send policy reason must be a string")

    def to_public_dict(self) -> dict[str, Any]:
        return _omit_empty(
            {
                "urgency": self.urgency,
                "allow_split": self.allow_split,
                "max_chunks": self.max_chunks,
                "min_delay_ms": self.min_delay_ms,
                "reason": self.reason.strip(),
            }
        )


@dataclass(frozen=True)
class SocialReplyAction:
    action_id: str
    target: SocialTarget
    parts: tuple[SocialMessagePart, ...]
    reply_to_message_id: str | None = None
    send_policy: SocialSendPolicy = SocialSendPolicy()

    def __post_init__(self) -> None:
        _required_string_value(self.action_id, "action_id")
        if not isinstance(self.target, SocialTarget):
            raise ValueError("reply action target must be a SocialTarget")
        if not isinstance(self.parts, tuple):
            raise ValueError("reply action parts must be a tuple")
        if not self.parts:
            raise ValueError("reply action parts must not be empty")
        for part in self.parts:
            if not isinstance(part, SocialMessagePart):
                raise ValueError("reply action parts items must be SocialMessagePart")
        _optional_nullable_string(self.reply_to_message_id, "reply_to_message_id")
        if not isinstance(self.send_policy, SocialSendPolicy):
            raise ValueError("reply action send_policy must be a SocialSendPolicy")

    def to_public_dict(self) -> dict[str, Any]:
        return _omit_empty(
            {
                "action_id": self.action_id.strip(),
                "target": self.target.to_public_dict(),
                "reply_to_message_id": (
                    self.reply_to_message_id.strip() if self.reply_to_message_id else None
                ),
                "parts": [part.to_public_dict() for part in self.parts],
                "send_policy": self.send_policy.to_public_dict(),
            }
        )
