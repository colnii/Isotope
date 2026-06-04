"""Platform-neutral send feedback shapes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .messages import (
    SocialMessagePart,
    _omit_empty,
    _optional_nullable_string,
    _required_string_value,
    _string_tuple,
)


SUPPORTED_SEND_STATUSES = {"sent", "partial", "failed"}


@dataclass(frozen=True)
class SocialSendChunk:
    message_id: str
    parts: tuple[SocialMessagePart, ...]
    rendered_preview: str

    def __post_init__(self) -> None:
        _required_string_value(self.message_id, "send chunk message_id")
        if not isinstance(self.parts, tuple):
            raise ValueError("send chunk parts must be a tuple")
        if not self.parts:
            raise ValueError("send chunk parts must not be empty")
        for part in self.parts:
            if not isinstance(part, SocialMessagePart):
                raise ValueError("send chunk parts items must be SocialMessagePart")
        _required_string_value(self.rendered_preview, "send chunk rendered_preview")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id.strip(),
            "parts": [part.to_public_dict() for part in self.parts],
            "rendered_preview": self.rendered_preview.strip(),
        }


@dataclass(frozen=True)
class SocialSendFeedback:
    status: str
    sent_message_ids: tuple[str, ...] = ()
    chunks: tuple[SocialSendChunk, ...] = ()
    recent_messages_after_send: tuple[dict[str, Any], ...] = ()
    platform_error: str | None = None

    def __post_init__(self) -> None:
        if self.status not in SUPPORTED_SEND_STATUSES:
            raise ValueError("send feedback status is not supported")
        _string_tuple(self.sent_message_ids, "sent_message_ids")
        if not isinstance(self.chunks, tuple):
            raise ValueError("send feedback chunks must be a tuple")
        for chunk in self.chunks:
            if not isinstance(chunk, SocialSendChunk):
                raise ValueError("send feedback chunks items must be SocialSendChunk")
        if not isinstance(self.recent_messages_after_send, tuple):
            raise ValueError("recent_messages_after_send must be a tuple")
        for item in self.recent_messages_after_send:
            if not isinstance(item, dict):
                raise ValueError("recent_messages_after_send items must be dicts")
        _optional_nullable_string(self.platform_error, "platform_error")

    def to_public_dict(self) -> dict[str, Any]:
        return _omit_empty(
            {
                "status": self.status,
                "sent_message_ids": list(self.sent_message_ids),
                "chunks": [chunk.to_public_dict() for chunk in self.chunks],
                "recent_messages_after_send": [
                    dict(item) for item in self.recent_messages_after_send
                ],
                "platform_error": self.platform_error,
            }
        )
