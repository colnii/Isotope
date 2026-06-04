"""Role-card driven personality configuration for social agents."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .messages import _omit_empty, _required_string_value


CHARACTER_CARD_SCHEMA_VERSION = "isotope.character_card_plus.v1"


@dataclass(frozen=True)
class CharacterIdentity:
    name: str
    aliases: tuple[str, ...] = ()
    avatar_ref: str = ""
    description: str = ""
    creator_notes: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CharacterIdentity":
        _require_dict(data, "identity")
        return cls(
            name=_required_mapping_string(data, "name", "identity.name"),
            aliases=_string_tuple_from_mapping(data, "aliases", "identity.aliases"),
            avatar_ref=_optional_mapping_string(data, "avatar_ref", "identity.avatar_ref"),
            description=_optional_mapping_string(data, "description", "identity.description"),
            creator_notes=_optional_mapping_string(
                data,
                "creator_notes",
                "identity.creator_notes",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return _omit_empty(
            {
                "name": self.name,
                "aliases": list(self.aliases),
                "avatar_ref": self.avatar_ref,
                "description": self.description,
                "creator_notes": self.creator_notes,
            }
        )


@dataclass(frozen=True)
class CharacterVoice:
    speaking_style: str
    tone: str = ""
    vocabulary: tuple[str, ...] = ()
    example_messages: tuple[str, ...] = ()
    forbidden_style: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CharacterVoice":
        _require_dict(data, "voice")
        return cls(
            speaking_style=_required_mapping_string(
                data,
                "speaking_style",
                "voice.speaking_style",
            ),
            tone=_optional_mapping_string(data, "tone", "voice.tone"),
            vocabulary=_string_tuple_from_mapping(data, "vocabulary", "voice.vocabulary"),
            example_messages=_string_tuple_from_mapping(
                data,
                "example_messages",
                "voice.example_messages",
            ),
            forbidden_style=_optional_mapping_string(
                data,
                "forbidden_style",
                "voice.forbidden_style",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return _omit_empty(
            {
                "speaking_style": self.speaking_style,
                "tone": self.tone,
                "vocabulary": list(self.vocabulary),
                "example_messages": list(self.example_messages),
                "forbidden_style": self.forbidden_style,
            }
        )


@dataclass(frozen=True)
class SocialBehavior:
    talkativeness: float = 0.5
    interruption_style: str = ""
    mention_policy: str = ""
    lurk_policy: str = ""
    disagreement_style: str = ""
    relationship_policy: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SocialBehavior":
        _require_dict(data, "social_behavior")
        return cls(
            talkativeness=_ratio_from_mapping(
                data,
                "talkativeness",
                "social_behavior.talkativeness",
                default=0.5,
            ),
            interruption_style=_optional_mapping_string(
                data,
                "interruption_style",
                "social_behavior.interruption_style",
            ),
            mention_policy=_optional_mapping_string(
                data,
                "mention_policy",
                "social_behavior.mention_policy",
            ),
            lurk_policy=_optional_mapping_string(data, "lurk_policy", "social_behavior.lurk_policy"),
            disagreement_style=_optional_mapping_string(
                data,
                "disagreement_style",
                "social_behavior.disagreement_style",
            ),
            relationship_policy=_optional_mapping_string(
                data,
                "relationship_policy",
                "social_behavior.relationship_policy",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return _omit_empty(
            {
                "talkativeness": self.talkativeness,
                "interruption_style": self.interruption_style,
                "mention_policy": self.mention_policy,
                "lurk_policy": self.lurk_policy,
                "disagreement_style": self.disagreement_style,
                "relationship_policy": self.relationship_policy,
            }
        )


@dataclass(frozen=True)
class StickerPreferences:
    enabled: bool = True
    favorite_packs: tuple[str, ...] = ()
    style_tags: tuple[str, ...] = ()
    emotion_map: dict[str, tuple[str, ...]] | None = None
    use_frequency: float = 0.0
    allow_sticker_only_reply: bool = False
    avoid_tags: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StickerPreferences":
        _require_dict(data, "stickers")
        return cls(
            enabled=_bool_from_mapping(data, "enabled", "stickers.enabled", default=True),
            favorite_packs=_string_tuple_from_mapping(
                data,
                "favorite_packs",
                "stickers.favorite_packs",
            ),
            style_tags=_string_tuple_from_mapping(data, "style_tags", "stickers.style_tags"),
            emotion_map=_emotion_map_from_mapping(data, "emotion_map", "stickers.emotion_map"),
            use_frequency=_ratio_from_mapping(
                data,
                "use_frequency",
                "stickers.use_frequency",
                default=0.0,
            ),
            allow_sticker_only_reply=_bool_from_mapping(
                data,
                "allow_sticker_only_reply",
                "stickers.allow_sticker_only_reply",
                default=False,
            ),
            avoid_tags=_string_tuple_from_mapping(data, "avoid_tags", "stickers.avoid_tags"),
        )

    def to_dict(self) -> dict[str, Any]:
        emotion_map = self.emotion_map or {}
        return _omit_empty(
            {
                "enabled": self.enabled,
                "favorite_packs": list(self.favorite_packs),
                "style_tags": list(self.style_tags),
                "emotion_map": {
                    key: list(value)
                    for key, value in emotion_map.items()
                },
                "use_frequency": self.use_frequency,
                "allow_sticker_only_reply": self.allow_sticker_only_reply,
                "avoid_tags": list(self.avoid_tags),
            }
        )


@dataclass(frozen=True)
class ToolPolicy:
    allowed_capabilities: tuple[str, ...] = ()
    tool_use_style: str = ""
    after_tool_result_behavior: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolPolicy":
        _require_dict(data, "tools")
        return cls(
            allowed_capabilities=_string_tuple_from_mapping(
                data,
                "allowed_capabilities",
                "tools.allowed_capabilities",
            ),
            tool_use_style=_optional_mapping_string(data, "tool_use_style", "tools.tool_use_style"),
            after_tool_result_behavior=_optional_mapping_string(
                data,
                "after_tool_result_behavior",
                "tools.after_tool_result_behavior",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return _omit_empty(
            {
                "allowed_capabilities": list(self.allowed_capabilities),
                "tool_use_style": self.tool_use_style,
                "after_tool_result_behavior": self.after_tool_result_behavior,
            }
        )


@dataclass(frozen=True)
class MemoryPolicy:
    remember: tuple[str, ...] = ()
    do_not_remember: tuple[str, ...] = ()
    review_policy: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryPolicy":
        _require_dict(data, "memory")
        return cls(
            remember=_string_tuple_from_mapping(data, "remember", "memory.remember"),
            do_not_remember=_string_tuple_from_mapping(
                data,
                "do_not_remember",
                "memory.do_not_remember",
            ),
            review_policy=_optional_mapping_string(data, "review_policy", "memory.review_policy"),
        )

    def to_dict(self) -> dict[str, Any]:
        return _omit_empty(
            {
                "remember": list(self.remember),
                "do_not_remember": list(self.do_not_remember),
                "review_policy": self.review_policy,
            }
        )


@dataclass(frozen=True)
class CharacterCard:
    schema_version: str
    identity: CharacterIdentity
    voice: CharacterVoice
    social_behavior: SocialBehavior
    stickers: StickerPreferences
    tools: ToolPolicy
    memory: MemoryPolicy
    group_overrides: dict[str, dict[str, Any]]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CharacterCard":
        _require_dict(data, "character card")
        schema_version = _required_mapping_string(data, "schema_version", "schema_version")
        if schema_version != CHARACTER_CARD_SCHEMA_VERSION:
            raise ValueError("schema_version is not supported")
        groups = data.get("groups", {})
        if not isinstance(groups, dict):
            raise ValueError("groups must be a dict")
        overrides = groups.get("overrides", {})
        if not isinstance(overrides, dict):
            raise ValueError("groups.overrides must be a dict")
        return cls(
            schema_version=schema_version,
            identity=CharacterIdentity.from_dict(_required_dict_field(data, "identity")),
            voice=CharacterVoice.from_dict(_required_dict_field(data, "voice")),
            social_behavior=SocialBehavior.from_dict(
                _optional_dict_field(data, "social_behavior")
            ),
            stickers=StickerPreferences.from_dict(_optional_dict_field(data, "stickers")),
            tools=ToolPolicy.from_dict(_optional_dict_field(data, "tools")),
            memory=MemoryPolicy.from_dict(_optional_dict_field(data, "memory")),
            group_overrides={
                _required_string_value(str(group_id), "groups.overrides key"): _copy_dict(
                    override,
                    "groups.overrides value",
                )
                for group_id, override in overrides.items()
            },
        )

    def for_group(self, group_id: str) -> "CharacterCard":
        clean_group_id = _required_string_value(group_id, "group_id")
        override = self.group_overrides.get(clean_group_id)
        if not override:
            return self
        merged = _deep_merge_dicts(self.to_dict(), override)
        return CharacterCard.from_dict(merged)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "identity": self.identity.to_dict(),
            "voice": self.voice.to_dict(),
            "social_behavior": self.social_behavior.to_dict(),
            "stickers": self.stickers.to_dict(),
            "tools": self.tools.to_dict(),
            "memory": self.memory.to_dict(),
            "groups": {"overrides": deepcopy(self.group_overrides)},
        }


def _require_dict(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dict")
    return value


def _required_dict_field(data: dict[str, Any], field_name: str) -> dict[str, Any]:
    value = data.get(field_name)
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dict")
    return value


def _optional_dict_field(data: dict[str, Any], field_name: str) -> dict[str, Any]:
    value = data.get(field_name, {})
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dict")
    return value


def _copy_dict(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dict")
    return deepcopy(value)


def _required_mapping_string(data: dict[str, Any], key: str, field_name: str) -> str:
    return _required_string_value(data.get(key), field_name)


def _optional_mapping_string(data: dict[str, Any], key: str, field_name: str) -> str:
    value = data.get(key, "")
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value.strip()


def _string_tuple_from_mapping(data: dict[str, Any], key: str, field_name: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} items must be non-empty strings")
        result.append(item.strip())
    return tuple(result)


def _bool_from_mapping(data: dict[str, Any], key: str, field_name: str, *, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a bool")
    return value


def _ratio_from_mapping(
    data: dict[str, Any],
    key: str,
    field_name: str,
    *,
    default: float,
) -> float:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be between 0 and 1")
    ratio = float(value)
    if ratio < 0 or ratio > 1:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return ratio


def _emotion_map_from_mapping(
    data: dict[str, Any],
    key: str,
    field_name: str,
) -> dict[str, tuple[str, ...]]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dict")
    result: dict[str, tuple[str, ...]] = {}
    for emotion, tags in value.items():
        if not isinstance(emotion, str) or not emotion.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        if not isinstance(tags, list):
            raise ValueError(f"{field_name}.{emotion} must be a list")
        clean_tags: list[str] = []
        for tag in tags:
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError(f"{field_name}.{emotion} items must be non-empty strings")
            clean_tags.append(tag.strip())
        result[emotion.strip()] = tuple(clean_tags)
    return result


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if (
            isinstance(value, dict)
            and isinstance(result.get(key), dict)
        ):
            result[key] = _deep_merge_dicts(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result
