from __future__ import annotations

from isotope.features.social import (
    CharacterCard,
    Lorebook,
    LorebookEntry,
    SocialContextBuilder,
    SocialMessage,
    SocialMessagePart,
    SocialSender,
)
from tests.unit.features.social.test_character_card import _card_dict


def test_social_context_builder_combines_card_lorebook_recent_messages_and_memory() -> None:
    card = CharacterCard.from_dict(_card_dict())
    lorebook = Lorebook(
        entries=(
            LorebookEntry(
                entry_id="rule_tests",
                title="测试规则",
                content="聊测试时要问清楚验证命令。",
                keywords=("测试",),
                priority=20,
            ),
        )
    )
    message = SocialMessage(
        message_id="qq_msg_context",
        platform="qq",
        adapter="napcat_onebot",
        chat_type="group",
        group_id="12345",
        sender=SocialSender(user_id="10001", display_name="小林"),
        timestamp="2026-06-04T08:00:00Z",
        text="测试咋跑",
        parts=(SocialMessagePart(kind="text", text="测试咋跑"),),
    )

    payload = SocialContextBuilder(
        character_card=card,
        lorebook=lorebook,
    ).build(
        group_id="12345",
        message=message,
        recent_messages=(
            {"message_id": "prev", "preview": "前文"},
        ),
        memory_previews=(
            {"memory_id": "mem_1", "summary": "用户偏好直接答案"},
        ),
    )

    assert payload["character_card"]["social_behavior"]["talkativeness"] == 0.2
    assert payload["lorebook_entries"][0]["entry_id"] == "rule_tests"
    assert payload["lorebook_entries"][0]["reasons"] == ["keyword:测试"]
    assert payload["recent_messages"][0]["message_id"] == "prev"
    assert payload["memory_previews"][0]["memory_id"] == "mem_1"
    assert payload["persona_instructions"] == {
        "role_name": "群聊工程猫",
        "aliases": ["bot", "工程猫"],
        "description": "一个长期待在群里的工程助手角色。",
        "voice": {
            "speaking_style": "直接、简洁、带一点吐槽",
            "tone": "calm",
            "vocabulary": ["repo", "测试", "表情包"],
            "example_messages": ["我先看上下文，再决定要不要插话。"],
            "forbidden_style": "不要像客服机器人。",
        },
        "social_behavior": {
            "talkativeness": 0.2,
            "interruption_style": "only_when_useful",
            "mention_policy": "always_consider",
            "lurk_policy": "watch_and_wait",
            "disagreement_style": "explain_reason",
            "relationship_policy": "remember_stable_preferences",
        },
        "stickers": {
            "enabled": False,
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
        "group_id": "12345",
        "group_override_applied": True,
    }
    assert payload["persona_instructions"]["voice"]["example_messages"] == [
        "我先看上下文，再决定要不要插话。"
    ]
    assert payload["chat_context"]["current_message"]["message_id"] == "qq_msg_context"
    assert payload["chat_context"]["current_message"]["sender"]["display_name"] == "小林"
    assert payload["chat_context"]["recent_messages"][0]["preview"] == "前文"
    assert payload["chat_context"]["memory_previews"][0]["summary"] == "用户偏好直接答案"
    assert payload["chat_context"]["lorebook_entries"][0]["title"] == "测试规则"
