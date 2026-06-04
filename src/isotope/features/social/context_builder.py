"""Build inspectable social-agent context payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .character_card import CharacterCard
from .lorebook import Lorebook
from .messages import SocialMessage, _required_string_value


@dataclass(frozen=True)
class SocialContextBuilder:
    character_card: CharacterCard
    lorebook: Lorebook | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.character_card, CharacterCard):
            raise ValueError("character_card must be a CharacterCard")
        if self.lorebook is not None and not isinstance(self.lorebook, Lorebook):
            raise ValueError("lorebook must be a Lorebook")

    def build(
        self,
        *,
        group_id: str,
        message: SocialMessage,
        recent_messages: tuple[dict[str, Any], ...] = (),
        memory_previews: tuple[dict[str, Any], ...] = (),
        now: str | None = None,
    ) -> dict[str, Any]:
        clean_group_id = _required_string_value(group_id, "group_id")
        if not isinstance(message, SocialMessage):
            raise ValueError("message must be a SocialMessage")
        recent = _dict_tuple(recent_messages, "recent_messages")
        memory = _dict_tuple(memory_previews, "memory_previews")
        group_card = self.character_card.for_group(clean_group_id)
        selected = (
            self.lorebook.select_for_message(message, now=now)
            if self.lorebook is not None
            else ()
        )
        return {
            "kind": "social_context",
            "group_id": clean_group_id,
            "message": message.to_public_dict(),
            "character_card": group_card.to_dict(),
            "lorebook_entries": [entry.to_public_dict() for entry in selected],
            "recent_messages": [dict(item) for item in recent],
            "memory_previews": [dict(item) for item in memory],
        }


def _dict_tuple(value: object, field_name: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"{field_name} items must be dicts")
        result.append(dict(item))
    return tuple(result)
