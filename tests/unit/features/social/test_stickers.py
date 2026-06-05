from __future__ import annotations

import json
from pathlib import Path

import pytest

from isotope.features.social import (
    CharacterCard,
    MediaRef,
    SocialMessagePart,
    SocialSendChunk,
    SocialSendFeedback,
    SocialTarget,
    StickerLibrary,
    StickerLibraryEntry,
    StickerSelectionRequest,
)
from tests.unit.features.social.test_character_card import _card_dict


def _card(*, sticker_frequency: float = 0.35) -> CharacterCard:
    data = _card_dict()
    data["stickers"]["style_tags"] = ["review", "helpful"]
    data["stickers"]["emotion_map"]["positive"] = ["ship"]
    data["stickers"]["use_frequency"] = sticker_frequency
    return CharacterCard.from_dict(data)


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
                allowed_groups=("12345",),
                source="engineering_pack",
            ),
            StickerLibraryEntry(
                sticker_id="calm-down",
                pack_id="engineering",
                media=MediaRef(
                    media_ref="qq-image://calm-down",
                    kind="sticker",
                    source="local_pack",
                ),
                tags=("calm", "review"),
                meaning="提醒先别急，按步骤排查",
                blocked_groups=("12345",),
                source="engineering_pack",
            ),
            StickerLibraryEntry(
                sticker_id="coffee",
                pack_id="casual",
                media=MediaRef(
                    media_ref="qq-image://coffee",
                    kind="sticker",
                    source="local_pack",
                ),
                tags=("coffee", "casual"),
                meaning="闲聊时的咖啡表情",
                source="casual_pack",
            ),
        )
    )


def test_sticker_library_selects_by_emotion_scene_and_role_preferences() -> None:
    selected = _library().select(
        StickerSelectionRequest(
            group_id="12345",
            emotion="positive",
            scene_tags=("review",),
            character_stickers=_card().stickers,
        )
    )

    assert selected is not None
    assert selected.entry.sticker_id == "ship-it"
    assert selected.reasons == (
        "emotion_tag:ship",
        "scene_tag:review",
        "favorite_pack:engineering",
        "style_tag:review",
    )


def test_sticker_library_respects_zero_use_frequency() -> None:
    selected = _library().select(
        StickerSelectionRequest(
            group_id="12345",
            emotion="positive",
            scene_tags=("review",),
            character_stickers=_card(sticker_frequency=0.0).stickers,
        )
    )

    assert selected is None


def test_sticker_library_explains_zero_use_frequency() -> None:
    outcome = _library().select_with_explanation(
        StickerSelectionRequest(
            group_id="12345",
            emotion="positive",
            scene_tags=("review",),
            character_stickers=_card(sticker_frequency=0.0).stickers,
        )
    )

    assert outcome.selected is None
    assert outcome.blocked_reasons == ("use_frequency_zero",)
    assert outcome.to_public_dict()["blocked_reasons"] == ["use_frequency_zero"]


def test_sticker_library_does_not_repeat_recent_successful_sticker() -> None:
    selected = _library().select(
        StickerSelectionRequest(
            group_id="12345",
            emotion="positive",
            scene_tags=("review",),
            character_stickers=_card().stickers,
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

    assert selected is None


def test_sticker_library_rejects_blocked_group() -> None:
    selected = _library().select(
        StickerSelectionRequest(
            group_id="12345",
            emotion="calm",
            scene_tags=("calm",),
            character_stickers=_card().stickers,
        )
    )

    assert selected is None


def test_sticker_library_can_load_json_fixture() -> None:
    payload = json.loads(
        Path("tests/fixtures/social/stickers/engineering.json").read_text(
            encoding="utf-8"
        )
    )

    library = StickerLibrary.from_dict(payload)

    assert library.entries[0].sticker_id == "ship-it"
    assert library.entries[0].media.media_ref == "qq-image://ship-it"


def test_sticker_only_reply_action_is_valid_when_allowed() -> None:
    selected = _library().select(
        StickerSelectionRequest(
            group_id="12345",
            emotion="positive",
            scene_tags=("review",),
            character_stickers=_card().stickers,
            allow_sticker_only=True,
        )
    )
    assert selected is not None

    action = selected.to_reply_action(
        action_id="reply_sticker",
        target=SocialTarget(platform="qq", chat_type="group", group_id="12345"),
    )

    assert action.parts[0].kind == "sticker"
    assert action.parts[0].media_ref == "qq-image://ship-it"


def test_sticker_only_reply_requires_role_and_request_permission() -> None:
    selected = _library().select(
        StickerSelectionRequest(
            group_id="12345",
            emotion="positive",
            scene_tags=("review",),
            character_stickers=_card().stickers,
            allow_sticker_only=False,
        )
    )
    assert selected is not None

    with pytest.raises(ValueError, match="sticker-only replies are not allowed"):
        selected.to_reply_action(
            action_id="reply_sticker",
            target=SocialTarget(platform="qq", chat_type="group", group_id="12345"),
        )
