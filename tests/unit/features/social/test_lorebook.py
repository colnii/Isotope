from __future__ import annotations

from isotope.features.social import (
    Lorebook,
    LorebookEntry,
    SocialMessage,
    SocialMessagePart,
    SocialSender,
)


def _message(
    *,
    text: str,
    sender_id: str = "10001",
    parts=None,
) -> SocialMessage:
    return SocialMessage(
        message_id="qq_msg_lore",
        platform="qq",
        adapter="napcat_onebot",
        chat_type="group",
        group_id="12345",
        sender=SocialSender(user_id=sender_id, display_name="小林"),
        timestamp="2026-06-04T08:00:00Z",
        text=text,
        parts=tuple(parts or (SocialMessagePart(kind="text", text=text),)),
    )


def test_lorebook_selects_keyword_regex_user_and_part_kind_triggers() -> None:
    lorebook = Lorebook(
        entries=(
            LorebookEntry(
                entry_id="rule_tests",
                title="测试规则",
                content="聊测试时要问清楚验证命令。",
                keywords=("测试",),
                priority=20,
            ),
            LorebookEntry(
                entry_id="regex_pr",
                title="PR 规则",
                content="提到 PR 编号时要检查链接。",
                regex=(r"PR #\d+",),
                priority=30,
            ),
            LorebookEntry(
                entry_id="user_lumber",
                title="用户偏好",
                content="这个用户讨厌空泛安全话术。",
                users=("10001",),
                priority=10,
            ),
            LorebookEntry(
                entry_id="sticker_norm",
                title="表情包规则",
                content="表情包消息可以用短文字回应。",
                message_part_kinds=("sticker",),
                priority=40,
            ),
        )
    )

    selected = lorebook.select_for_message(
        _message(
            text="PR #12 的测试咋样",
            parts=(SocialMessagePart(kind="sticker", media_ref="qq-image://ok"),),
        )
    )

    assert [item.entry.entry_id for item in selected] == [
        "sticker_norm",
        "regex_pr",
        "rule_tests",
        "user_lumber",
    ]
    assert "message_part_kind:sticker" in selected[0].reasons
    assert "regex:PR #\\d+" in selected[1].reasons


def test_lorebook_skips_expired_entries() -> None:
    lorebook = Lorebook(
        entries=(
            LorebookEntry(
                entry_id="old",
                title="旧规则",
                content="过期规则不进入上下文。",
                keywords=("测试",),
                expires_at="2026-06-03T00:00:00Z",
            ),
        )
    )

    assert lorebook.select_for_message(
        _message(text="测试"),
        now="2026-06-04T00:00:00Z",
    ) == ()
