from __future__ import annotations

from isotope.features.social import (
    CharacterCard,
    MediaRef,
    SocialContextBuilder,
    SocialDecisionLoop,
    SocialDecisionRequest,
    SocialMessage,
    SocialMessagePart,
    SocialReplyDraft,
    SocialSendChunk,
    SocialSendFeedback,
    SocialSender,
    SocialTarget,
    StickerLibrary,
    StickerLibraryEntry,
)
from tests.unit.features.social.test_character_card import _card_dict


class RecordingReplyProvider:
    def __init__(self, text: str) -> None:
        self.text = text
        self.requests: list[SocialDecisionRequest] = []
        self.wake_reasons: list[str] = []

    def generate_reply(
        self,
        request: SocialDecisionRequest,
        *,
        wake_reason: str,
    ) -> SocialReplyDraft:
        self.requests.append(request)
        self.wake_reasons.append(wake_reason)
        return SocialReplyDraft(
            text=self.text,
            metadata={
                "provider": "recording",
                "saw_role": request.context["persona_instructions"]["role_name"],
                "saw_message": request.context["chat_context"]["current_message"]["text"],
            },
        )


def _card() -> CharacterCard:
    data = _card_dict()
    data["stickers"]["style_tags"] = ["review", "helpful"]
    data["stickers"]["emotion_map"]["positive"] = ["ship"]
    return CharacterCard.from_dict(data)


def _message(
    *,
    text: str,
    mentions: tuple[str, ...] = (),
) -> SocialMessage:
    parts = [SocialMessagePart(kind="text", text=text)]
    for user_id in mentions:
        parts.append(SocialMessagePart(kind="mention", text=f"@{user_id}", user_id=user_id))
    return SocialMessage(
        message_id="qq_decision_msg",
        platform="qq",
        adapter="napcat_onebot",
        chat_type="group",
        group_id="99999",
        sender=SocialSender(user_id="10001", display_name="小林"),
        timestamp="2026-06-04T08:00:00Z",
        text=text,
        mentions=mentions,
        parts=tuple(parts),
    )


def _context(message: SocialMessage) -> dict:
    return SocialContextBuilder(character_card=_card()).build(
        group_id="99999",
        message=message,
    )


def _target() -> SocialTarget:
    return SocialTarget(platform="qq", chat_type="group", group_id="99999")


def _library() -> StickerLibrary:
    return StickerLibrary(
        entries=(
            StickerLibraryEntry(
                sticker_id="ship-it",
                pack_id="engineering",
                media=MediaRef(
                    media_ref="qq-image://ship-it",
                    kind="sticker",
                    source="local_pack",
                ),
                tags=("ship", "review", "cheer"),
                meaning="代码通过时的轻松回应",
                allowed_groups=("99999",),
                source="engineering_pack",
            ),
        )
    )


def test_decision_loop_wakes_on_bot_mention() -> None:
    turn = SocialDecisionLoop().decide(
        SocialDecisionRequest(
            context=_context(_message(text="@bot 看看这个", mentions=("bot_qq",))),
            target=_target(),
            bot_user_id="bot_qq",
        )
    )

    assert [item.kind for item in turn.selected] == ["respond"]
    assert turn.selected[0].reason == "mention:bot_qq"
    assert turn.selected[0].reply_action is not None
    assert turn.selected[0].reply_action.parts[0].text == "我看到了，先按上下文处理。"


def test_decision_loop_uses_reply_provider_with_persona_and_chat_context() -> None:
    provider = RecordingReplyProvider("小林，我按工程猫的风格看完上下文了。")
    request = SocialDecisionRequest(
        context=_context(_message(text="@bot 看看这个", mentions=("bot_qq",))),
        target=_target(),
        bot_user_id="bot_qq",
    )

    turn = SocialDecisionLoop(reply_provider=provider).decide(request)

    assert provider.requests == [request]
    assert provider.wake_reasons == ["mention:bot_qq"]
    assert turn.selected[0].reply_action is not None
    assert turn.selected[0].reply_action.parts[0].text == "小林，我按工程猫的风格看完上下文了。"
    assert turn.selected[0].metadata["reply_provider"] == {
        "provider": "recording",
        "saw_role": "群聊工程猫",
        "saw_message": "@bot 看看这个",
    }


def test_decision_loop_wakes_on_keyword() -> None:
    turn = SocialDecisionLoop().decide(
        SocialDecisionRequest(
            context=_context(_message(text="测试咋跑")),
            target=_target(),
            bot_user_id="bot_qq",
            wake_keywords=("测试",),
        )
    )

    assert [item.kind for item in turn.selected] == ["respond"]
    assert turn.selected[0].reason == "keyword:测试"


def test_decision_loop_wakes_autonomously_when_score_allows() -> None:
    turn = SocialDecisionLoop().decide(
        SocialDecisionRequest(
            context=_context(_message(text="大家在聊 PR")),
            target=_target(),
            bot_user_id="bot_qq",
            autonomy_score=0.1,
        )
    )

    assert [item.kind for item in turn.selected] == ["respond"]
    assert turn.selected[0].reason == "autonomous:0.1<=0.45"


def test_decision_loop_stays_silent_without_wake_reason() -> None:
    turn = SocialDecisionLoop().decide(
        SocialDecisionRequest(
            context=_context(_message(text="普通闲聊")),
            target=_target(),
            bot_user_id="bot_qq",
            autonomy_score=0.9,
        )
    )

    assert [item.kind for item in turn.selected] == ["silent"]
    assert turn.selected[0].reason == "no_wake_reason"


def test_decision_loop_send_feedback_suppresses_immediate_repeat() -> None:
    turn = SocialDecisionLoop().decide(
        SocialDecisionRequest(
            context=_context(_message(text="@bot 再说一句", mentions=("bot_qq",))),
            target=_target(),
            bot_user_id="bot_qq",
            recent_send_feedback=(
                SocialSendFeedback(
                    status="sent",
                    sent_message_ids=("sent1",),
                    chunks=(
                        SocialSendChunk(
                            message_id="sent1",
                            parts=(SocialMessagePart(kind="text", text="刚回过了。"),),
                            rendered_preview="刚回过了。",
                        ),
                    ),
                ),
            ),
        )
    )

    assert [item.kind for item in turn.selected] == ["silent"]
    assert turn.selected[0].reason == "recent_send_feedback:sent"


def test_decision_loop_falls_back_to_text_after_recent_sticker_send() -> None:
    provider = RecordingReplyProvider("这次我用文字说，避免表情包刷屏。")

    turn = SocialDecisionLoop(reply_provider=provider).decide(
        SocialDecisionRequest(
            context=_context(_message(text="@bot 这 PR 过了", mentions=("bot_qq",))),
            target=_target(),
            bot_user_id="bot_qq",
            sticker_library=_library(),
            sticker_emotion="positive",
            sticker_scene_tags=("review",),
            allow_sticker_only=True,
            recent_send_feedback=(
                SocialSendFeedback(
                    status="sent",
                    sent_message_ids=("sent_sticker",),
                    chunks=(
                        SocialSendChunk(
                            message_id="sent_sticker",
                            parts=(
                                SocialMessagePart(
                                    kind="sticker",
                                    media_ref="qq-image://ship-it",
                                    platform_data={"sticker_id": "ship-it"},
                                ),
                            ),
                            rendered_preview="[sticker: qq-image://ship-it]",
                        ),
                    ),
                ),
            ),
        )
    )

    assert [item.kind for item in turn.selected] == ["respond"]
    assert turn.selected[0].candidate_id == "reply_text"
    assert turn.selected[0].reply_action is not None
    assert turn.selected[0].reply_action.parts[0].kind == "text"
    assert turn.selected[0].reply_action.parts[0].text == "这次我用文字说，避免表情包刷屏。"


def test_decision_loop_dry_run_returns_proposals_without_selecting_send() -> None:
    turn = SocialDecisionLoop().decide(
        SocialDecisionRequest(
            context=_context(_message(text="@bot 看看这个", mentions=("bot_qq",))),
            target=_target(),
            bot_user_id="bot_qq",
            dry_run=True,
        )
    )

    assert [item.kind for item in turn.proposed] == ["respond"]
    assert turn.selected == ()
    assert turn.rejected == {"reply_text": "dry_run:not selected for sending"}


def test_decision_loop_can_propose_sticker_only_reply() -> None:
    turn = SocialDecisionLoop().decide(
        SocialDecisionRequest(
            context=_context(_message(text="@bot 这 PR 过了", mentions=("bot_qq",))),
            target=_target(),
            bot_user_id="bot_qq",
            sticker_library=_library(),
            sticker_emotion="positive",
            sticker_scene_tags=("review",),
            allow_sticker_only=True,
        )
    )

    assert [item.kind for item in turn.selected] == ["respond"]
    assert turn.selected[0].candidate_id == "reply_sticker"
    assert turn.selected[0].reply_action is not None
    assert turn.selected[0].reply_action.parts[0].kind == "sticker"
    assert turn.selected[0].reply_action.parts[0].media_ref == "qq-image://ship-it"
