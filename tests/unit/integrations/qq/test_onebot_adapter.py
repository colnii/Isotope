from __future__ import annotations

from isotope.features.social import (
    SocialMessagePart,
    SocialReplyAction,
    SocialTarget,
)
from isotope.integrations.qq import FakeOneBotClient, OneBotAdapter


def _group_event() -> dict:
    return {
        "message_id": 123,
        "message_type": "group",
        "group_id": 99999,
        "user_id": 10001,
        "sender": {"nickname": "小林", "role": "member"},
        "time": 1780560000,
        "message": [
            {"type": "reply", "data": {"id": "122"}},
            {"type": "at", "data": {"qq": "bot_qq"}},
            {"type": "text", "data": {"text": " 看看这个"}},
            {"type": "face", "data": {"id": "14"}},
            {
                "type": "image",
                "data": {"file": "diagram.png", "url": "qq-image://diagram"},
            },
            {"type": "file", "data": {"file": "report.zip", "url": "qq-file://report"}},
        ],
        "raw_message": "[CQ:at,qq=bot_qq] 看看这个",
    }


def test_onebot_adapter_maps_group_segments_to_social_message_parts() -> None:
    message = OneBotAdapter(client=FakeOneBotClient()).normalize_event(_group_event())

    assert message is not None
    assert message.message_id == "123"
    assert message.chat_type == "group"
    assert message.group_id == "99999"
    assert message.sender.user_id == "10001"
    assert message.mentions == ("bot_qq",)
    assert message.text == "看看这个"
    assert [part.kind for part in message.parts] == [
        "reply",
        "mention",
        "text",
        "qq_face",
        "image",
        "file",
    ]
    assert message.parts[3].platform_data == {"face_id": "14"}
    assert message.parts[4].media_ref == "qq-image://diagram"
    assert message.parts[5].media_ref == "qq-file://report"


def test_onebot_adapter_ignores_duplicate_message_ids() -> None:
    adapter = OneBotAdapter(client=FakeOneBotClient())

    assert adapter.normalize_event(_group_event()) is not None
    assert adapter.normalize_event(_group_event()) is None


def test_onebot_adapter_maps_mixed_reply_action_to_segments() -> None:
    client = FakeOneBotClient()
    adapter = OneBotAdapter(client=client)
    action = SocialReplyAction(
        action_id="reply",
        target=SocialTarget(platform="qq", chat_type="group", group_id="99999"),
        reply_to_message_id="123",
        parts=(
            SocialMessagePart(kind="mention", text="@小林", user_id="10001"),
            SocialMessagePart(kind="text", text=" 收到"),
            SocialMessagePart(kind="qq_face", platform_data={"face_id": "14"}),
            SocialMessagePart(kind="sticker", media_ref="qq-image://ship-it"),
        ),
    )

    feedback = adapter.send_action(action)

    assert feedback.status == "sent"
    assert client.sent_group_messages[0]["group_id"] == "99999"
    assert client.sent_group_messages[0]["message"] == [
        {"type": "reply", "data": {"id": "123"}},
        {"type": "at", "data": {"qq": "10001"}},
        {"type": "text", "data": {"text": " 收到"}},
        {"type": "face", "data": {"id": "14"}},
        {"type": "image", "data": {"file": "qq-image://ship-it", "sub_type": "sticker"}},
    ]


def test_onebot_adapter_returns_failed_feedback_on_platform_error() -> None:
    adapter = OneBotAdapter(client=FakeOneBotClient(fail_send=True))
    action = SocialReplyAction(
        action_id="reply",
        target=SocialTarget(platform="qq", chat_type="group", group_id="99999"),
        parts=(SocialMessagePart(kind="text", text="收到"),),
    )

    feedback = adapter.send_action(action)

    assert feedback.status == "failed"
    assert feedback.platform_error == "OneBot send failed"
