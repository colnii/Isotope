from __future__ import annotations

from isotope.features.social import (
    CharacterCard,
    Lorebook,
    LorebookEntry,
    MediaRef,
    SocialActionCandidate,
    SocialArbiter,
    SocialGroupPolicy,
    SocialInformationReport,
    SocialMessagePart,
    SocialOperationsConfig,
    SocialOperationsController,
    SocialReplyAction,
    SocialSendChunk,
    SocialSendFeedback,
    SocialTarget,
    StickerLibrary,
    StickerLibraryEntry,
)
from tests.unit.features.social.test_character_card import _card_dict


def _controller() -> SocialOperationsController:
    return SocialOperationsController(
        config=SocialOperationsConfig(
            group_policy=SocialGroupPolicy(
                allowed_groups=("100", "200"),
                blocked_groups=("300",),
                operator_user_ids=("op",),
            )
        )
    )


def _card() -> CharacterCard:
    return CharacterCard.from_dict(_card_dict())


def _decision():
    action = SocialReplyAction(
        action_id="reply",
        target=SocialTarget(platform="qq", chat_type="group", group_id="100"),
        parts=(SocialMessagePart(kind="text", text="收到"),),
    )
    return SocialArbiter().choose(
        (
            SocialActionCandidate(
                candidate_id="reply",
                agent_id="agent",
                kind="respond",
                reason="mention:bot",
                confidence=0.8,
                reply_action=action,
            ),
        )
    )


def _send_feedback() -> SocialSendFeedback:
    return SocialSendFeedback(
        status="sent",
        sent_message_ids=("sent1",),
        chunks=(
            SocialSendChunk(
                message_id="sent1",
                parts=(SocialMessagePart(kind="text", text="收到"),),
                rendered_preview="收到",
            ),
        ),
    )


def _lorebook() -> Lorebook:
    return Lorebook(
        entries=(
            LorebookEntry(
                entry_id="rules",
                title="群规则",
                content="先问清楚验证命令。",
                keywords=("测试",),
            ),
        )
    )


def _stickers() -> StickerLibrary:
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
                tags=("ship", "review"),
                meaning="通过时使用",
                source="engineering_pack",
            ),
        )
    )


def test_operations_group_policy_and_pause_are_group_scoped() -> None:
    controller = _controller()

    assert controller.can_process_group("100").allowed is True
    assert controller.can_process_group("300").reason == "group_blocked:300"
    assert controller.can_process_group("999").reason == "group_not_allowed:999"

    controller.pause_group("100", operator_user_id="op")

    assert controller.can_process_group("100").reason == "group_paused:100"
    assert controller.can_process_group("200").allowed is True

    controller.resume_group("100", operator_user_id="op")

    assert controller.can_process_group("100").allowed is True


def test_operations_rejects_non_operator_controls() -> None:
    controller = _controller()

    assert controller.pause_group("100", operator_user_id="user") == {
        "ok": False,
        "reason": "operator_required:user",
    }
    assert controller.can_process_group("100").allowed is True


def test_operations_logs_decision_send_and_capability_by_group() -> None:
    controller = _controller()
    arbiter_result = _decision()
    controller.record_decision("100", arbiter_result)
    controller.record_send("100", _send_feedback())
    controller.record_capability(
        "100",
        SocialInformationReport(
            status="completed",
            capability_id="research.search",
            target="research.search",
            reason="capability_completed",
            content="找到 3 个结果。",
        ),
    )

    entries = controller.audit_log.entries_for_group("100")

    assert [entry.kind for entry in entries] == ["decision", "send", "capability"]
    assert entries[0].payload["selected"][0]["reason"] == "mention:bot"
    assert entries[1].payload["status"] == "sent"
    assert entries[2].payload["content"] == "找到 3 个结果。"


def test_operations_inspects_role_lorebook_and_stickers() -> None:
    controller = _controller()

    role = controller.inspect_role(_card())
    lorebook = controller.inspect_lorebook(_lorebook())
    stickers = controller.inspect_stickers(_stickers())

    assert role["identity"]["name"] == "群聊工程猫"
    assert lorebook["entries"][0]["entry_id"] == "rules"
    assert stickers["entries"][0]["sticker_id"] == "ship-it"


def test_operations_health_check_reports_counts_and_adapter_state() -> None:
    controller = _controller()
    controller.pause_group("100", operator_user_id="op")
    controller.record_send("100", _send_feedback())

    health = controller.health_check(
        adapter_states=(
            {"adapter": "onebot", "connected": True, "pending_events": 0},
        )
    )

    assert health["status"] == "ok"
    assert health["paused_groups"] == ["100"]
    assert health["audit_counts"] == {"send": 1}
    assert health["adapter_states"][0]["adapter"] == "onebot"
