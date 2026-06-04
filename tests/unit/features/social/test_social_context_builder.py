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
