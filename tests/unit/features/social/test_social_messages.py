from __future__ import annotations

import pytest

from isotope.features.social import (
    SocialMessage,
    SocialMessagePart,
    SocialReplyRef,
    SocialSender,
)


def test_social_message_accepts_sticker_only_group_message() -> None:
    message = SocialMessage(
        message_id="qq_msg_1",
        platform="qq",
        adapter="napcat_onebot",
        chat_type="group",
        group_id="12345",
        sender=SocialSender(
            user_id="10001",
            display_name="小林",
            roles=("member",),
            is_bot=False,
        ),
        timestamp="2026-06-04T08:00:00Z",
        text="",
        parts=(
            SocialMessagePart(
                kind="sticker",
                media_ref="qq-image://abc",
                platform_data={"file_id": "abc"},
            ),
        ),
        raw_event_ref="event://qq/qq_msg_1",
    )

    assert message.has_content is True
    assert message.text_content == ""
    assert message.part_kinds == ("sticker",)
    assert message.to_public_dict()["parts"][0]["kind"] == "sticker"


def test_social_message_keeps_text_part_for_plain_text() -> None:
    message = SocialMessage(
        message_id="qq_msg_2",
        platform="qq",
        adapter="napcat_onebot",
        chat_type="group",
        group_id="12345",
        sender=SocialSender(user_id="10001", display_name="小林"),
        timestamp="2026-06-04T08:00:00Z",
        text="你好",
        parts=(SocialMessagePart(kind="text", text="你好"),),
    )

    assert message.has_content is True
    assert message.text_content == "你好"
    assert message.to_public_dict()["parts"] == [{"kind": "text", "text": "你好"}]


def test_social_message_supports_mentions_and_reply_reference() -> None:
    message = SocialMessage(
        message_id="qq_msg_3",
        platform="qq",
        adapter="napcat_onebot",
        chat_type="group",
        group_id="12345",
        sender=SocialSender(user_id="10001", display_name="小林"),
        timestamp="2026-06-04T08:00:00Z",
        text="@bot 看看这个",
        mentions=("bot_qq",),
        reply_to=SocialReplyRef(
            message_id="qq_msg_parent",
            sender_id="10002",
            text_preview="上一条内容",
        ),
        parts=(
            SocialMessagePart(kind="mention", user_id="bot_qq", text="@bot"),
            SocialMessagePart(kind="text", text=" 看看这个"),
        ),
    )

    payload = message.to_public_dict()
    assert payload["mentions"] == ["bot_qq"]
    assert payload["reply_to"]["message_id"] == "qq_msg_parent"
    assert payload["parts"][0]["kind"] == "mention"


def test_social_message_rejects_missing_required_fields() -> None:
    with pytest.raises(ValueError, match="message_id must be a non-empty string"):
        SocialMessage(
            message_id=" ",
            platform="qq",
            adapter="napcat_onebot",
            chat_type="group",
            group_id="12345",
            sender=SocialSender(user_id="10001", display_name="小林"),
            timestamp="2026-06-04T08:00:00Z",
            text="hello",
            parts=(SocialMessagePart(kind="text", text="hello"),),
        )


def test_social_message_rejects_unknown_part_kind() -> None:
    with pytest.raises(ValueError, match="message part kind is not supported"):
        SocialMessagePart(kind="unknown", text="hello")
