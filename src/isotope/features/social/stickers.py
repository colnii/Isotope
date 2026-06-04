"""Sticker library selection for social-agent replies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .character_card import StickerPreferences
from .media_refs import MediaRef
from .messages import (
    SocialMessagePart,
    _omit_empty,
    _optional_string_value,
    _required_string_value,
    _string_tuple,
)
from .replies import SocialReplyAction, SocialTarget


@dataclass(frozen=True)
class StickerLibraryEntry:
    sticker_id: str
    pack_id: str
    media: MediaRef
    tags: tuple[str, ...]
    meaning: str
    allowed_groups: tuple[str, ...] = ()
    blocked_groups: tuple[str, ...] = ()
    source: str = ""

    def __post_init__(self) -> None:
        _required_string_value(self.sticker_id, "sticker_id")
        _required_string_value(self.pack_id, "sticker pack_id")
        if not isinstance(self.media, MediaRef):
            raise ValueError("sticker media must be a MediaRef")
        if self.media.kind != "sticker":
            raise ValueError("sticker media kind must be sticker")
        _string_tuple(self.tags, "sticker tags")
        _required_string_value(self.meaning, "sticker meaning")
        _string_tuple(self.allowed_groups, "sticker allowed_groups")
        _string_tuple(self.blocked_groups, "sticker blocked_groups")
        _optional_string_value(self.source, "sticker source")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StickerLibraryEntry":
        if not isinstance(data, dict):
            raise ValueError("sticker entry must be a dict")
        return cls(
            sticker_id=_required_string_value(data.get("sticker_id"), "sticker_id"),
            pack_id=_required_string_value(data.get("pack_id"), "sticker pack_id"),
            media=MediaRef.from_dict(_required_dict_field(data, "media")),
            tags=_string_tuple_from_list(data.get("tags", []), "sticker tags"),
            meaning=_required_string_value(data.get("meaning"), "sticker meaning"),
            allowed_groups=_string_tuple_from_list(
                data.get("allowed_groups", []),
                "sticker allowed_groups",
            ),
            blocked_groups=_string_tuple_from_list(
                data.get("blocked_groups", []),
                "sticker blocked_groups",
            ),
            source=_optional_string_from_mapping(data, "source", "sticker source"),
        )

    def to_public_dict(self) -> dict[str, Any]:
        return _omit_empty(
            {
                "sticker_id": self.sticker_id,
                "pack_id": self.pack_id,
                "media": self.media.to_public_dict(),
                "tags": list(self.tags),
                "meaning": self.meaning,
                "allowed_groups": list(self.allowed_groups),
                "blocked_groups": list(self.blocked_groups),
                "source": self.source,
            }
        )


@dataclass(frozen=True)
class StickerSelectionRequest:
    group_id: str
    emotion: str
    scene_tags: tuple[str, ...]
    character_stickers: StickerPreferences
    allow_sticker_only: bool = False

    def __post_init__(self) -> None:
        _required_string_value(self.group_id, "group_id")
        _required_string_value(self.emotion, "sticker emotion")
        _string_tuple(self.scene_tags, "sticker scene_tags")
        if not isinstance(self.character_stickers, StickerPreferences):
            raise ValueError("character_stickers must be StickerPreferences")
        if not isinstance(self.allow_sticker_only, bool):
            raise ValueError("allow_sticker_only must be a bool")


@dataclass(frozen=True)
class StickerSelectionResult:
    entry: StickerLibraryEntry
    reasons: tuple[str, ...]
    allow_sticker_only: bool

    def __post_init__(self) -> None:
        if not isinstance(self.entry, StickerLibraryEntry):
            raise ValueError("sticker selection entry must be StickerLibraryEntry")
        _string_tuple(self.reasons, "sticker selection reasons")
        if not isinstance(self.allow_sticker_only, bool):
            raise ValueError("allow_sticker_only must be a bool")

    def to_reply_action(
        self,
        *,
        action_id: str,
        target: SocialTarget,
        reply_to_message_id: str | None = None,
    ) -> SocialReplyAction:
        if not self.allow_sticker_only:
            raise ValueError("sticker-only replies are not allowed")
        return SocialReplyAction(
            action_id=action_id,
            target=target,
            reply_to_message_id=reply_to_message_id,
            parts=(
                SocialMessagePart(
                    kind="sticker",
                    media_ref=self.entry.media.media_ref,
                    platform_data={
                        "sticker_id": self.entry.sticker_id,
                        "pack_id": self.entry.pack_id,
                        "reasons": list(self.reasons),
                    },
                ),
            ),
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "entry": self.entry.to_public_dict(),
            "reasons": list(self.reasons),
            "allow_sticker_only": self.allow_sticker_only,
        }


@dataclass(frozen=True)
class StickerLibrary:
    entries: tuple[StickerLibraryEntry, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple):
            raise ValueError("sticker library entries must be a tuple")
        for entry in self.entries:
            if not isinstance(entry, StickerLibraryEntry):
                raise ValueError("sticker library entries items must be StickerLibraryEntry")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StickerLibrary":
        if not isinstance(data, dict):
            raise ValueError("sticker library must be a dict")
        entries = data.get("entries")
        if not isinstance(entries, list):
            raise ValueError("sticker library entries must be a list")
        return cls(entries=tuple(StickerLibraryEntry.from_dict(item) for item in entries))

    def select(
        self,
        request: StickerSelectionRequest,
    ) -> StickerSelectionResult | None:
        if not isinstance(request, StickerSelectionRequest):
            raise ValueError("request must be a StickerSelectionRequest")
        if not request.character_stickers.enabled:
            return None
        candidates: list[tuple[int, StickerLibraryEntry, tuple[str, ...]]] = []
        for entry in self.entries:
            if _is_blocked(entry, request):
                continue
            score, reasons = _score_entry(entry, request)
            if score > 0 and _has_request_match(reasons):
                candidates.append((score, entry, tuple(reasons)))
        if not candidates:
            return None
        _, entry, reasons = sorted(
            candidates,
            key=lambda item: (-item[0], item[1].sticker_id),
        )[0]
        return StickerSelectionResult(
            entry=entry,
            reasons=reasons,
            allow_sticker_only=(
                request.allow_sticker_only
                and request.character_stickers.allow_sticker_only_reply
            ),
        )


def _is_blocked(
    entry: StickerLibraryEntry,
    request: StickerSelectionRequest,
) -> bool:
    if request.group_id in entry.blocked_groups:
        return True
    if entry.allowed_groups and request.group_id not in entry.allowed_groups:
        return True
    entry_tags = set(entry.tags)
    return any(tag in entry_tags for tag in request.character_stickers.avoid_tags)


def _score_entry(
    entry: StickerLibraryEntry,
    request: StickerSelectionRequest,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    entry_tags = set(entry.tags)
    for tag in _emotion_tags(request):
        if tag in entry_tags:
            score += 4
            reasons.append(f"emotion_tag:{tag}")
    for tag in request.scene_tags:
        if tag in entry_tags:
            score += 3
            reasons.append(f"scene_tag:{tag}")
    if entry.pack_id in request.character_stickers.favorite_packs:
        score += 2
        reasons.append(f"favorite_pack:{entry.pack_id}")
    for tag in request.character_stickers.style_tags:
        if tag in entry_tags:
            score += 1
            reasons.append(f"style_tag:{tag}")
    return score, reasons


def _has_request_match(reasons: list[str]) -> bool:
    return any(
        reason.startswith("emotion_tag:") or reason.startswith("scene_tag:")
        for reason in reasons
    )


def _emotion_tags(request: StickerSelectionRequest) -> tuple[str, ...]:
    emotion_map = request.character_stickers.emotion_map or {}
    mapped = emotion_map.get(request.emotion)
    if mapped:
        return mapped
    return (request.emotion,)


def _required_dict_field(data: dict[str, Any], field_name: str) -> dict[str, Any]:
    value = data.get(field_name)
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dict")
    return value


def _optional_string_from_mapping(
    data: dict[str, Any],
    key: str,
    field_name: str,
) -> str:
    value = data.get(key, "")
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value.strip()


def _string_tuple_from_list(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} items must be non-empty strings")
        result.append(item.strip())
    return tuple(result)
