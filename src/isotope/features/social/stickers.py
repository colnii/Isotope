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
from .send_feedback import SocialSendFeedback


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
    recent_send_feedback: tuple[SocialSendFeedback, ...] = ()

    def __post_init__(self) -> None:
        _required_string_value(self.group_id, "group_id")
        _required_string_value(self.emotion, "sticker emotion")
        _string_tuple(self.scene_tags, "sticker scene_tags")
        if not isinstance(self.character_stickers, StickerPreferences):
            raise ValueError("character_stickers must be StickerPreferences")
        if not isinstance(self.allow_sticker_only, bool):
            raise ValueError("allow_sticker_only must be a bool")
        if not isinstance(self.recent_send_feedback, tuple):
            raise ValueError("recent_send_feedback must be a tuple")
        for item in self.recent_send_feedback:
            if not isinstance(item, SocialSendFeedback):
                raise ValueError("recent_send_feedback items must be SocialSendFeedback")


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
class StickerSelectionOutcome:
    selected: StickerSelectionResult | None
    blocked_reasons: tuple[str, ...] = ()
    recent_sticker_ids: tuple[str, ...] = ()
    emotion: str = ""
    scene_tags: tuple[str, ...] = ()
    candidate_count: int = 0

    def __post_init__(self) -> None:
        if self.selected is not None and not isinstance(
            self.selected,
            StickerSelectionResult,
        ):
            raise ValueError("sticker outcome selected must be StickerSelectionResult")
        _string_tuple(self.blocked_reasons, "sticker blocked_reasons")
        _string_tuple(self.recent_sticker_ids, "sticker recent_sticker_ids")
        _optional_string_value(self.emotion, "sticker outcome emotion")
        _string_tuple(self.scene_tags, "sticker outcome scene_tags")
        if isinstance(self.candidate_count, bool) or not isinstance(
            self.candidate_count,
            int,
        ):
            raise ValueError("sticker outcome candidate_count must be an integer")
        if self.candidate_count < 0:
            raise ValueError("sticker outcome candidate_count must be 0 or greater")

    def to_public_dict(self) -> dict[str, Any]:
        return _omit_empty(
            {
                "selected": self.selected is not None,
                "selection": (
                    self.selected.to_public_dict()
                    if self.selected is not None
                    else None
                ),
                "blocked_reasons": list(self.blocked_reasons),
                "recent_sticker_ids": list(self.recent_sticker_ids),
                "emotion": self.emotion,
                "scene_tags": list(self.scene_tags),
                "candidate_count": self.candidate_count,
            }
        )


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
        return self.select_with_explanation(request).selected

    def select_with_explanation(
        self,
        request: StickerSelectionRequest,
    ) -> StickerSelectionOutcome:
        if not isinstance(request, StickerSelectionRequest):
            raise ValueError("request must be a StickerSelectionRequest")
        recent_sticker_ids = recent_successful_sticker_ids(request.recent_send_feedback)
        if not request.character_stickers.enabled:
            return _outcome(
                request,
                blocked_reasons=("stickers_disabled",),
                recent_sticker_ids=recent_sticker_ids,
            )
        if request.character_stickers.use_frequency <= 0:
            return _outcome(
                request,
                blocked_reasons=("use_frequency_zero",),
                recent_sticker_ids=recent_sticker_ids,
            )
        if recent_sticker_ids:
            return _outcome(
                request,
                blocked_reasons=("recent_sticker_feedback",),
                recent_sticker_ids=recent_sticker_ids,
            )
        candidates: list[tuple[int, StickerLibraryEntry, tuple[str, ...]]] = []
        for entry in self.entries:
            if _is_blocked(entry, request):
                continue
            if entry.sticker_id in recent_sticker_ids:
                continue
            score, reasons = _score_entry(entry, request)
            if score > 0 and _has_request_match(reasons):
                candidates.append((score, entry, tuple(reasons)))
        if not candidates:
            return _outcome(
                request,
                blocked_reasons=("no_matching_sticker",),
                recent_sticker_ids=recent_sticker_ids,
            )
        _, entry, reasons = sorted(
            candidates,
            key=lambda item: (-item[0], item[1].sticker_id),
        )[0]
        return _outcome(
            request,
            selected=StickerSelectionResult(
                entry=entry,
                reasons=reasons,
                allow_sticker_only=(
                    request.allow_sticker_only
                    and request.character_stickers.allow_sticker_only_reply
                ),
            ),
            recent_sticker_ids=recent_sticker_ids,
            candidate_count=len(candidates),
        )


def recent_successful_sticker_ids(
    feedback_items: tuple[SocialSendFeedback, ...],
) -> tuple[str, ...]:
    if not isinstance(feedback_items, tuple):
        raise ValueError("feedback_items must be a tuple")
    sticker_ids: list[str] = []
    for feedback in feedback_items:
        if not isinstance(feedback, SocialSendFeedback):
            raise ValueError("feedback_items items must be SocialSendFeedback")
        if feedback.status not in {"sent", "partial"} or not feedback.sent_message_ids:
            continue
        for chunk in feedback.chunks:
            for part in chunk.parts:
                if part.kind != "sticker":
                    continue
                _append_unique_sticker_id(sticker_ids, part.platform_data.get("sticker_id"))
                if not sticker_ids:
                    _append_unique_sticker_id(sticker_ids, part.media_ref)
    return tuple(sticker_ids)


def _outcome(
    request: StickerSelectionRequest,
    *,
    selected: StickerSelectionResult | None = None,
    blocked_reasons: tuple[str, ...] = (),
    recent_sticker_ids: tuple[str, ...] = (),
    candidate_count: int = 0,
) -> StickerSelectionOutcome:
    return StickerSelectionOutcome(
        selected=selected,
        blocked_reasons=blocked_reasons,
        recent_sticker_ids=recent_sticker_ids,
        emotion=request.emotion,
        scene_tags=request.scene_tags,
        candidate_count=candidate_count,
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


def _append_unique_sticker_id(target: list[str], value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        return
    sticker_id = value.strip()
    if sticker_id not in target:
        target.append(sticker_id)
