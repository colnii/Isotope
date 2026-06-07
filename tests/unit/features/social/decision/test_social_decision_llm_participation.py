from __future__ import annotations

from isotope.features.social import SocialDecisionLoop, SocialDecisionRequest
from isotope.features.social.participation_provider import LLMParticipationDecision
from tests.unit.features.social.test_social_decision_loop import (
    _context,
    _message,
    _target,
)


class FakeParticipationProvider:
    def __init__(self, decision: LLMParticipationDecision):
        self.decision = decision
        self.requests: list[SocialDecisionRequest] = []
        self.wake_signals: list[tuple[str, ...]] = []

    def decide(
        self,
        request: SocialDecisionRequest,
        *,
        wake_signals: tuple[str, ...],
    ) -> LLMParticipationDecision:
        self.requests.append(request)
        self.wake_signals.append(wake_signals)
        return self.decision


class FailingParticipationProvider:
    def decide(
        self,
        request: SocialDecisionRequest,
        *,
        wake_signals: tuple[str, ...],
    ) -> LLMParticipationDecision:
        raise ValueError("bad model output")


def test_default_decision_loop_keeps_rule_based_silence_for_ordinary_message() -> None:
    turn = SocialDecisionLoop().decide(
        _request(text="这里是一条普通群聊记录", dry_run=False)
    )

    assert [item.kind for item in turn.selected] == ["silent"]
    assert turn.selected[0].reason == "no_wake_reason"


def test_llm_participation_can_respond_to_ordinary_message_without_wake_rule() -> None:
    provider = FakeParticipationProvider(
        LLMParticipationDecision(
            action="respond",
            reason="topic is active",
            confidence=0.82,
            text="我补一句上下文。",
            metadata={
                "provider": "unit-chat",
                "model": "unit-model",
                "usage": {"total_tokens": 21},
            },
        )
    )
    request = _request(text="这里是一条普通群聊记录", dry_run=False)

    turn = SocialDecisionLoop(participation_provider=provider).decide(request)

    assert provider.requests == [request]
    assert provider.wake_signals == [()]
    assert [item.kind for item in turn.selected] == ["respond"]
    selected = turn.selected[0]
    assert selected.reason == "topic is active"
    assert selected.confidence == 0.82
    assert selected.reply_action is not None
    assert selected.reply_action.parts[0].text == "我补一句上下文。"
    assert selected.metadata["participation_provider"]["provider"] == "unit-chat"


def test_llm_participation_dry_run_records_reply_without_selecting_send() -> None:
    provider = FakeParticipationProvider(
        LLMParticipationDecision(
            action="respond",
            reason="useful context",
            confidence=0.77,
            text="我会这样回。",
            metadata={"provider": "unit-chat"},
        )
    )

    turn = SocialDecisionLoop(participation_provider=provider).decide(
        _request(text="普通消息也可以判断是否参与", dry_run=True)
    )

    assert [item.kind for item in turn.proposed] == ["respond"]
    assert turn.selected == ()
    assert turn.rejected == {"reply_text": "dry_run:not selected for sending"}
    assert turn.proposed[0].reply_action is not None
    assert turn.proposed[0].reply_action.parts[0].text == "我会这样回。"


def test_llm_participation_provider_error_degrades_to_silent_candidate() -> None:
    turn = SocialDecisionLoop(participation_provider=FailingParticipationProvider()).decide(
        _request(text="普通消息", dry_run=False)
    )

    assert [item.kind for item in turn.selected] == ["silent"]
    assert turn.selected[0].reason == "participation_provider_error"
    assert turn.selected[0].metadata == {
        "participation_provider": {
            "provider_error": "bad model output",
            "wake_signals": [],
        }
    }


def _request(*, text: str, dry_run: bool) -> SocialDecisionRequest:
    return SocialDecisionRequest(
        context=_context(_message(text=text)),
        target=_target(),
        bot_user_id="bot_qq",
        dry_run=dry_run,
    )
