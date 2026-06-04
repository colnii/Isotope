from __future__ import annotations

from isotope.features.social import (
    CharacterCard,
    SocialGroupPolicy,
    SocialOperationsConfig,
    SocialOperationsController,
    SocialRuntime,
    SocialRuntimeConfig,
)
from isotope.integrations.qq import FakeOneBotClient, OneBotAdapter
from tests.unit.features.social.test_character_card import _card_dict


def _event(message_id: int = 123, *, group_id: int = 99999) -> dict:
    return {
        "message_id": message_id,
        "message_type": "group",
        "group_id": group_id,
        "user_id": 10001,
        "sender": {"nickname": "小林", "role": "member"},
        "time": 1780560000,
        "message": [
            {"type": "at", "data": {"qq": "bot_qq"}},
            {"type": "text", "data": {"text": " 看看这个 PR"}},
        ],
        "raw_message": "[CQ:at,qq=bot_qq] 看看这个 PR",
    }


def _card() -> CharacterCard:
    return CharacterCard.from_dict(_card_dict())


def _operations(*, paused_groups: tuple[str, ...] = ()) -> SocialOperationsController:
    return SocialOperationsController(
        config=SocialOperationsConfig(
            group_policy=SocialGroupPolicy(
                allowed_groups=("99999",),
                blocked_groups=("300",),
                operator_user_ids=("op",),
                paused_groups=paused_groups,
            )
        )
    )


def _runtime(
    *,
    client: FakeOneBotClient,
    dry_run: bool,
    operations: SocialOperationsController | None = None,
) -> SocialRuntime:
    return SocialRuntime(
        adapter=OneBotAdapter(client=client),
        character_card=_card(),
        operations=operations or _operations(),
        config=SocialRuntimeConfig(
            bot_user_id="bot_qq",
            dry_run=dry_run,
        ),
    )


def test_social_runtime_dry_run_records_decision_without_sending() -> None:
    client = FakeOneBotClient()
    client.queue_event(_event())
    runtime = _runtime(client=client, dry_run=True)

    turn = runtime.process_next()

    assert turn is not None
    assert turn.policy.allowed is True
    assert turn.decision is not None
    assert [item.kind for item in turn.decision.proposed] == ["respond"]
    assert turn.decision.selected == ()
    assert turn.send_feedback == ()
    assert client.sent_group_messages == []
    assert [entry.kind for entry in runtime.operations.audit_log.entries_for_group("99999")] == [
        "decision"
    ]


def test_social_runtime_send_mode_sends_and_records_feedback() -> None:
    client = FakeOneBotClient()
    client.queue_event(_event())
    runtime = _runtime(client=client, dry_run=False)

    turn = runtime.process_next()

    assert turn is not None
    assert turn.policy.allowed is True
    assert turn.send_feedback[0].status == "sent"
    assert client.sent_group_messages[0]["group_id"] == "99999"
    assert [entry.kind for entry in runtime.operations.audit_log.entries_for_group("99999")] == [
        "decision",
        "send",
    ]


def test_social_runtime_blocked_group_returns_policy_without_decision() -> None:
    client = FakeOneBotClient()
    client.queue_event(_event(group_id=300))
    runtime = _runtime(client=client, dry_run=False)

    turn = runtime.process_next()

    assert turn is not None
    assert turn.policy.allowed is False
    assert turn.policy.reason == "group_blocked:300"
    assert turn.decision is None
    assert turn.send_feedback == ()
    assert client.sent_group_messages == []


def test_social_runtime_paused_group_returns_policy_without_decision() -> None:
    client = FakeOneBotClient()
    client.queue_event(_event())
    runtime = _runtime(
        client=client,
        dry_run=False,
        operations=_operations(paused_groups=("99999",)),
    )

    turn = runtime.process_next()

    assert turn is not None
    assert turn.policy.allowed is False
    assert turn.policy.reason == "group_paused:99999"
    assert turn.decision is None
    assert turn.send_feedback == ()


def test_social_runtime_records_failed_send_feedback() -> None:
    client = FakeOneBotClient(fail_send=True)
    client.queue_event(_event())
    runtime = _runtime(client=client, dry_run=False)

    turn = runtime.process_next()

    assert turn is not None
    assert turn.send_feedback[0].status == "failed"
    assert turn.send_feedback[0].platform_error == "OneBot send failed"
    assert runtime.operations.audit_log.entries_for_group("99999")[1].payload["status"] == "failed"


def test_social_runtime_carries_send_feedback_into_next_decision() -> None:
    client = FakeOneBotClient()
    client.queue_event(_event(123))
    client.queue_event(_event(124))
    runtime = _runtime(client=client, dry_run=False)

    first = runtime.process_next()
    second = runtime.process_next()

    assert first is not None
    assert first.send_feedback[0].status == "sent"
    assert second is not None
    assert second.decision is not None
    assert [item.kind for item in second.decision.selected] == ["silent"]
    assert second.decision.selected[0].reason == "recent_send_feedback:sent"
    assert len(client.sent_group_messages) == 1


def test_social_runtime_returns_none_when_no_event_is_available() -> None:
    runtime = _runtime(client=FakeOneBotClient(), dry_run=True)

    assert runtime.process_next() is None
