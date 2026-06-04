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
        lorebook_entries = [entry.to_public_dict() for entry in selected]
        message_payload = message.to_public_dict()
        recent_payload = [dict(item) for item in recent]
        memory_payload = [dict(item) for item in memory]
        return {
            "kind": "social_context",
            "group_id": clean_group_id,
            "message": message_payload,
            "character_card": group_card.to_dict(),
            "persona_instructions": _persona_instructions(
                group_card,
                group_id=clean_group_id,
                group_override_applied=clean_group_id in self.character_card.group_overrides,
            ),
            "chat_context": {
                "current_message": message_payload,
                "recent_messages": recent_payload,
                "memory_previews": memory_payload,
                "lorebook_entries": lorebook_entries,
            },
            "lorebook_entries": lorebook_entries,
            "recent_messages": recent_payload,
            "memory_previews": memory_payload,
        }


def _persona_instructions(
    character_card: CharacterCard,
    *,
    group_id: str,
    group_override_applied: bool,
) -> dict[str, Any]:
    card = character_card.to_dict()
    identity = card["identity"]
    return {
        "role_name": identity["name"],
        "aliases": list(identity.get("aliases", [])),
        "description": identity.get("description", ""),
        "voice": dict(card["voice"]),
        "social_behavior": dict(card["social_behavior"]),
        "stickers": dict(card["stickers"]),
        "tools": dict(card["tools"]),
        "memory": dict(card["memory"]),
        "group_id": group_id,
        "group_override_applied": group_override_applied,
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
