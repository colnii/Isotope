from __future__ import annotations

import pytest

from isotope.features.social import (
    SocialMessagePart,
    SocialReplyAction,
    SocialSendChunk,
    SocialSendFeedback,
    SocialSendPolicy,
    SocialTarget,
)


def test_reply_action_supports_text_and_sticker_parts() -> None:
    action = SocialReplyAction(
        action_id="reply_1",
        target=SocialTarget(platform="qq", chat_type="group", group_id="12345"),
        reply_to_message_id="qq_msg_1",
        parts=(
            SocialMessagePart(kind="text", text="收到"),
            SocialMessagePart(kind="sticker", media_ref="qq-image://ok"),
        ),
        send_policy=SocialSendPolicy(
            urgency="normal",
            allow_split=True,
            max_chunks=2,
            min_delay_ms=800,
            reason="text plus sticker reply",
        ),
    )

    payload = action.to_public_dict()
    assert payload["target"]["group_id"] == "12345"
    assert [part["kind"] for part in payload["parts"]] == ["text", "sticker"]
    assert payload["send_policy"]["max_chunks"] == 2


def test_reply_action_rejects_empty_parts() -> None:
    with pytest.raises(ValueError, match="reply action parts must not be empty"):
        SocialReplyAction(
            action_id="reply_empty",
            target=SocialTarget(platform="qq", chat_type="group", group_id="12345"),
            parts=(),
        )


def test_send_feedback_records_chunks_and_recent_messages() -> None:
    feedback = SocialSendFeedback(
        status="sent",
        sent_message_ids=("qq_sent_1", "qq_sent_2"),
        chunks=(
            SocialSendChunk(
                message_id="qq_sent_1",
                parts=(SocialMessagePart(kind="text", text="第一段"),),
                rendered_preview="第一段",
            ),
            SocialSendChunk(
                message_id="qq_sent_2",
                parts=(SocialMessagePart(kind="sticker", media_ref="qq-image://ok"),),
                rendered_preview="[sticker: qq-image://ok]",
            ),
        ),
        recent_messages_after_send=(
            {"message_id": "qq_sent_2", "sender": "bot", "preview": "[sticker]"},
        ),
    )

    payload = feedback.to_public_dict()
    assert payload["status"] == "sent"
    assert payload["sent_message_ids"] == ["qq_sent_1", "qq_sent_2"]
    assert payload["chunks"][1]["parts"][0]["kind"] == "sticker"
    assert payload["recent_messages_after_send"][0]["sender"] == "bot"


def test_send_feedback_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="send feedback status is not supported"):
        SocialSendFeedback(status="maybe")
