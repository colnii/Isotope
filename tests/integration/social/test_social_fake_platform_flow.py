from __future__ import annotations

from isotope.features.social import (
    CharacterCard,
    MediaRef,
    SocialFakePlatform,
    SocialFakePlatformHarness,
    SocialMessage,
    SocialMessagePart,
    SocialSender,
    StickerLibrary,
    StickerLibraryEntry,
)
from tests.unit.features.social.test_character_card import _card_dict


def _card() -> CharacterCard:
    data = _card_dict()
    data["stickers"]["style_tags"] = ["review", "helpful"]
    data["stickers"]["emotion_map"]["positive"] = ["ship"]
    return CharacterCard.from_dict(data)


def _message(
    *,
    text: str,
    group_id: str = "99999",
    mentions: tuple[str, ...] = (),
    parts: tuple[SocialMessagePart, ...] | None = None,
) -> SocialMessage:
    message_parts = parts or (SocialMessagePart(kind="text", text=text),)
    return SocialMessage(
        message_id="qq_fake_msg",
        platform="qq",
        adapter="fake",
        chat_type="group",
        group_id=group_id,
        sender=SocialSender(user_id="10001", display_name="小林"),
        timestamp="2026-06-04T08:00:00Z",
        text=text,
        mentions=mentions,
        parts=message_parts,
    )


def _sticker_library() -> StickerLibrary:
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


def test_fake_platform_processes_multipart_group_message_and_sends_text_reply() -> None:
    platform = SocialFakePlatform(platform="qq", group_id="99999", bot_user_id="bot_qq")
    platform.emit_message(
        _message(
            text="@bot 看看这个 PR",
            mentions=("bot_qq",),
            parts=(
                SocialMessagePart(kind="mention", text="@bot", user_id="bot_qq"),
                SocialMessagePart(kind="text", text=" 看看这个 PR"),
                SocialMessagePart(kind="image", media_ref="qq-image://diagram"),
            ),
        )
    )

    turn = SocialFakePlatformHarness(
        platform=platform,
        character_card=_card(),
    ).process_next()

    assert turn.message.message_id == "qq_fake_msg"
    assert turn.decision.selected[0].kind == "respond"
    assert platform.outgoing_actions[0].parts[0].kind == "text"
    assert turn.send_feedback[0].sent_message_ids == ("fake_sent_1",)


def test_fake_platform_sends_sticker_reply_when_role_and_group_allow_it() -> None:
    platform = SocialFakePlatform(platform="qq", group_id="99999", bot_user_id="bot_qq")
    platform.emit_message(_message(text="@bot 这 PR 过了", mentions=("bot_qq",)))

    turn = SocialFakePlatformHarness(
        platform=platform,
        character_card=_card(),
        sticker_library=_sticker_library(),
    ).process_next(
        sticker_emotion="positive",
        sticker_scene_tags=("review",),
        allow_sticker_only=True,
    )

    assert turn.decision.selected[0].candidate_id == "reply_sticker"
    assert platform.outgoing_actions[0].parts[0].kind == "sticker"
    assert platform.outgoing_actions[0].parts[0].media_ref == "qq-image://ship-it"


def test_fake_platform_dry_run_records_no_outgoing_action() -> None:
    platform = SocialFakePlatform(platform="qq", group_id="99999", bot_user_id="bot_qq")
    platform.emit_message(_message(text="@bot 看看这个", mentions=("bot_qq",)))

    turn = SocialFakePlatformHarness(
        platform=platform,
        character_card=_card(),
    ).process_next(dry_run=True)

    assert [item.kind for item in turn.decision.proposed] == ["respond"]
    assert turn.decision.selected == ()
    assert platform.outgoing_actions == ()
    assert turn.send_feedback == ()
