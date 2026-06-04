"""Platform-neutral incoming social message shapes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SUPPORTED_MESSAGE_PART_KINDS = {
    "text",
    "mention",
    "reply",
    "qq_face",
    "image",
    "sticker",
    "file",
    "voice",
    "video",
    "link",
    "raw",
}
SUPPORTED_CHAT_TYPES = {"group", "private"}


@dataclass(frozen=True)
class SocialSender:
    user_id: str
    display_name: str
    roles: tuple[str, ...] = ()
    is_bot: bool = False

    def __post_init__(self) -> None:
        _required_string_value(self.user_id, "sender.user_id")
        _required_string_value(self.display_name, "sender.display_name")
        _string_tuple(self.roles, "sender.roles")
        if not isinstance(self.is_bot, bool):
            raise ValueError("sender.is_bot must be a bool")

    def to_public_dict(self) -> dict[str, Any]:
        return _omit_empty(
            {
                "user_id": self.user_id.strip(),
                "display_name": self.display_name.strip(),
                "roles": list(self.roles),
                "is_bot": self.is_bot,
            }
        )


@dataclass(frozen=True)
class SocialReplyRef:
    message_id: str
    sender_id: str
    text_preview: str = ""

    def __post_init__(self) -> None:
        _required_string_value(self.message_id, "reply_to.message_id")
        _required_string_value(self.sender_id, "reply_to.sender_id")
        _optional_string_value(self.text_preview, "reply_to.text_preview")

    def to_public_dict(self) -> dict[str, Any]:
        return _omit_empty(
            {
                "message_id": self.message_id.strip(),
                "sender_id": self.sender_id.strip(),
                "text_preview": self.text_preview.strip(),
            }
        )


@dataclass(frozen=True)
class SocialMessagePart:
    kind: str
    text: str = ""
    user_id: str | None = None
    media_ref: str | None = None
    platform_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in SUPPORTED_MESSAGE_PART_KINDS:
            raise ValueError("message part kind is not supported")
        _optional_string_value(self.text, "message_part.text")
        _optional_nullable_string(self.user_id, "message_part.user_id")
        _optional_nullable_string(self.media_ref, "message_part.media_ref")
        if not isinstance(self.platform_data, dict):
            raise ValueError("message_part.platform_data must be a dict")

    @property
    def has_content(self) -> bool:
        return bool(
            self.text.strip()
            or self.user_id
            or self.media_ref
            or self.platform_data
            or self.kind in {"qq_face", "raw"}
        )

    def to_public_dict(self) -> dict[str, Any]:
        return _omit_empty(
            {
                "kind": self.kind,
                "text": self.text,
                "user_id": self.user_id,
                "media_ref": self.media_ref,
                "platform_data": dict(self.platform_data),
            }
        )


@dataclass(frozen=True)
class SocialMessage:
    message_id: str
    platform: str
    adapter: str
    chat_type: str
    group_id: str | None
    sender: SocialSender
    timestamp: str
    text: str
    parts: tuple[SocialMessagePart, ...]
    mentions: tuple[str, ...] = ()
    reply_to: SocialReplyRef | None = None
    raw_event_ref: str | None = None

    def __post_init__(self) -> None:
        _required_string_value(self.message_id, "message_id")
        _required_string_value(self.platform, "platform")
        _required_string_value(self.adapter, "adapter")
        if self.chat_type not in SUPPORTED_CHAT_TYPES:
            raise ValueError("chat_type must be group or private")
        if self.chat_type == "group":
            _required_string_value(self.group_id, "group_id")
        else:
            _optional_nullable_string(self.group_id, "group_id")
        if not isinstance(self.sender, SocialSender):
            raise ValueError("sender must be a SocialSender")
        _required_string_value(self.timestamp, "timestamp")
        _optional_string_value(self.text, "text")
        if not isinstance(self.parts, tuple):
            raise ValueError("parts must be a tuple")
        if not self.parts:
            raise ValueError("parts must not be empty")
        for part in self.parts:
            if not isinstance(part, SocialMessagePart):
                raise ValueError("parts items must be SocialMessagePart")
        _string_tuple(self.mentions, "mentions")
        if self.reply_to is not None and not isinstance(self.reply_to, SocialReplyRef):
            raise ValueError("reply_to must be a SocialReplyRef")
        _optional_nullable_string(self.raw_event_ref, "raw_event_ref")

    @property
    def has_content(self) -> bool:
        return bool(self.text.strip() or any(part.has_content for part in self.parts))

    @property
    def text_content(self) -> str:
        return self.text

    @property
    def part_kinds(self) -> tuple[str, ...]:
        return tuple(part.kind for part in self.parts)

    def to_public_dict(self) -> dict[str, Any]:
        return _omit_empty(
            {
                "message_id": self.message_id.strip(),
                "platform": self.platform.strip(),
                "adapter": self.adapter.strip(),
                "chat_type": self.chat_type,
                "group_id": self.group_id.strip() if self.group_id else None,
                "sender": self.sender.to_public_dict(),
                "timestamp": self.timestamp.strip(),
                "text": self.text,
                "mentions": list(self.mentions),
                "reply_to": (
                    self.reply_to.to_public_dict() if self.reply_to is not None else None
                ),
                "parts": [part.to_public_dict() for part in self.parts],
                "raw_event_ref": self.raw_event_ref.strip() if self.raw_event_ref else None,
            }
        )


def _required_string_value(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_string_value(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value.strip()


def _optional_nullable_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string when provided")
    return value.strip()


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} items must be non-empty strings")
    return tuple(item.strip() for item in value)


def _omit_empty(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item not in (None, [], {}, ())
    }
