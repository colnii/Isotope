from __future__ import annotations

from pathlib import Path

import pytest

from isotope.features.social import CharacterCard, load_character_card


def _card_dict() -> dict:
    return {
        "schema_version": "isotope.character_card_plus.v1",
        "identity": {
            "name": "群聊工程猫",
            "aliases": ["bot", "工程猫"],
            "avatar_ref": "asset://avatars/engineer-cat.png",
            "description": "一个长期待在群里的工程助手角色。",
        },
        "voice": {
            "speaking_style": "直接、简洁、带一点吐槽",
            "tone": "calm",
            "vocabulary": ["repo", "测试", "表情包"],
            "example_messages": ["我先看上下文，再决定要不要插话。"],
            "forbidden_style": "不要像客服机器人。",
        },
        "social_behavior": {
            "talkativeness": 0.45,
            "interruption_style": "only_when_useful",
            "mention_policy": "always_consider",
            "lurk_policy": "watch_and_wait",
            "disagreement_style": "explain_reason",
            "relationship_policy": "remember_stable_preferences",
        },
        "stickers": {
            "enabled": True,
            "favorite_packs": ["engineering"],
            "style_tags": ["dry", "helpful"],
            "emotion_map": {"ack": ["ok"], "confused": ["question"]},
            "use_frequency": 0.35,
            "allow_sticker_only_reply": True,
            "avoid_tags": ["spammy"],
        },
        "tools": {
            "allowed_capabilities": ["research.search", "supervisor.request_context"],
            "tool_use_style": "use_when_it_improves_answer",
            "after_tool_result_behavior": "answer_with_sources",
        },
        "memory": {
            "remember": ["group rules", "stable preferences"],
            "do_not_remember": ["one-off jokes"],
            "review_policy": "operator_review_for_reviewable_social_facts",
        },
        "groups": {
            "overrides": {
                "12345": {
                    "social_behavior": {"talkativeness": 0.2},
                    "stickers": {"enabled": False},
                }
            }
        },
    }


def test_character_card_loads_complete_role_card() -> None:
    card = CharacterCard.from_dict(_card_dict())

    assert card.identity.name == "群聊工程猫"
    assert card.voice.speaking_style == "直接、简洁、带一点吐槽"
    assert card.social_behavior.talkativeness == 0.45
    assert card.stickers.enabled is True
    assert card.stickers.favorite_packs == ("engineering",)
    assert card.tools.allowed_capabilities == (
        "research.search",
        "supervisor.request_context",
    )
    assert card.to_dict()["schema_version"] == "isotope.character_card_plus.v1"


def test_character_card_applies_group_override_without_mutating_base() -> None:
    card = CharacterCard.from_dict(_card_dict())
    group_card = card.for_group("12345")

    assert group_card.social_behavior.talkativeness == 0.2
    assert group_card.stickers.enabled is False
    assert card.social_behavior.talkativeness == 0.45
    assert card.stickers.enabled is True


def test_character_card_rejects_missing_identity_name() -> None:
    data = _card_dict()
    data["identity"]["name"] = " "

    with pytest.raises(ValueError, match="identity.name must be a non-empty string"):
        CharacterCard.from_dict(data)


def test_character_card_rejects_invalid_sticker_frequency() -> None:
    data = _card_dict()
    data["stickers"]["use_frequency"] = 1.2

    with pytest.raises(ValueError, match="stickers.use_frequency must be between 0 and 1"):
        CharacterCard.from_dict(data)


def test_character_card_rejects_unknown_schema_version() -> None:
    data = _card_dict()
    data["schema_version"] = "unknown"

    with pytest.raises(ValueError, match="schema_version is not supported"):
        CharacterCard.from_dict(data)


def test_load_character_card_reads_json_fixture() -> None:
    fixture = (
        Path(__file__).parents[3]
        / "fixtures"
        / "social"
        / "character_cards"
        / "qq_helper.json"
    )

    card = load_character_card(fixture)

    assert card.identity.name == "群聊工程猫"
    assert card.stickers.enabled is True
