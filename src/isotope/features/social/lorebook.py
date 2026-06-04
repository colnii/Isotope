"""Group lorebook entries and trigger selection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .messages import (
    SocialMessage,
    _omit_empty,
    _optional_nullable_string,
    _required_string_value,
    _string_tuple,
)


@dataclass(frozen=True)
class LorebookEntry:
    entry_id: str
    title: str
    content: str
    keywords: tuple[str, ...] = ()
    regex: tuple[str, ...] = ()
    users: tuple[str, ...] = ()
    message_part_kinds: tuple[str, ...] = ()
    priority: int = 0
    position: str = "after_recent_context"
    expires_at: str | None = None

    def __post_init__(self) -> None:
        _required_string_value(self.entry_id, "lorebook entry_id")
        _required_string_value(self.title, "lorebook title")
        _required_string_value(self.content, "lorebook content")
        _string_tuple(self.keywords, "lorebook keywords")
        _string_tuple(self.regex, "lorebook regex")
        _string_tuple(self.users, "lorebook users")
        _string_tuple(self.message_part_kinds, "lorebook message_part_kinds")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise ValueError("lorebook priority must be an integer")
        _required_string_value(self.position, "lorebook position")
        _optional_nullable_string(self.expires_at, "lorebook expires_at")
        for pattern in self.regex:
            re.compile(pattern)

    def to_public_dict(self) -> dict[str, Any]:
        return _omit_empty(
            {
                "entry_id": self.entry_id,
                "title": self.title,
                "content": self.content,
                "keywords": list(self.keywords),
                "regex": list(self.regex),
                "users": list(self.users),
                "message_part_kinds": list(self.message_part_kinds),
                "priority": self.priority,
                "position": self.position,
                "expires_at": self.expires_at,
            }
        )


@dataclass(frozen=True)
class SelectedLorebookEntry:
    entry: LorebookEntry
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.entry, LorebookEntry):
            raise ValueError("selected lorebook entry must contain a LorebookEntry")
        _string_tuple(self.reasons, "selected lorebook reasons")

    def to_public_dict(self) -> dict[str, Any]:
        payload = self.entry.to_public_dict()
        payload["reasons"] = list(self.reasons)
        return payload


@dataclass(frozen=True)
class Lorebook:
    entries: tuple[LorebookEntry, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple):
            raise ValueError("lorebook entries must be a tuple")
        for entry in self.entries:
            if not isinstance(entry, LorebookEntry):
                raise ValueError("lorebook entries items must be LorebookEntry")

    def select_for_message(
        self,
        message: SocialMessage,
        *,
        now: str | None = None,
    ) -> tuple[SelectedLorebookEntry, ...]:
        if not isinstance(message, SocialMessage):
            raise ValueError("message must be a SocialMessage")
        selected: list[SelectedLorebookEntry] = []
        now_datetime = _parse_datetime(now) if now is not None else None
        for entry in self.entries:
            if _is_expired(entry, now_datetime):
                continue
            reasons = _match_entry(entry, message)
            if reasons:
                selected.append(SelectedLorebookEntry(entry=entry, reasons=tuple(reasons)))
        return tuple(
            sorted(
                selected,
                key=lambda item: (-item.entry.priority, item.entry.entry_id),
            )
        )


def _match_entry(entry: LorebookEntry, message: SocialMessage) -> list[str]:
    reasons: list[str] = []
    text = message.text_content
    for keyword in entry.keywords:
        if keyword in text:
            reasons.append(f"keyword:{keyword}")
    for pattern in entry.regex:
        if re.search(pattern, text):
            reasons.append(f"regex:{pattern}")
    if message.sender.user_id in entry.users:
        reasons.append(f"user:{message.sender.user_id}")
    message_kinds = set(message.part_kinds)
    for kind in entry.message_part_kinds:
        if kind in message_kinds:
            reasons.append(f"message_part_kind:{kind}")
    return reasons


def _is_expired(entry: LorebookEntry, now: datetime | None) -> bool:
    if entry.expires_at is None or now is None:
        return False
    return _parse_datetime(entry.expires_at) <= now


def _parse_datetime(value: str) -> datetime:
    text = _required_string_value(value, "datetime")
    normalized = text.removesuffix("Z") + "+00:00" if text.endswith("Z") else text
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
