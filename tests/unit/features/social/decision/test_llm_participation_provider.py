from __future__ import annotations

from isotope.features.social.participation_provider import (
    LLMParticipationDecision,
    LLMSocialParticipationProvider,
    participation_decision_from_content,
)
from tests.unit.features.social.test_social_reply_provider import (
    RecordingChatProvider,
    _request,
)


def test_participation_decision_parses_respond() -> None:
    decision = participation_decision_from_content(
        '{"action":"respond","reason":"topic fit","confidence":0.73,"text":"可以，我补一句。"}'
    )

    assert decision == LLMParticipationDecision(
        action="respond",
        reason="topic fit",
        confidence=0.73,
        text="可以，我补一句。",
    )


def test_participation_decision_parses_silent() -> None:
    decision = participation_decision_from_content(
        '{"action":"silent","reason":"用户只是记录状态","confidence":0.64}'
    )

    assert decision.action == "silent"
    assert decision.reason == "用户只是记录状态"
    assert decision.confidence == 0.64
    assert decision.text is None


def test_participation_decision_rejects_respond_without_text() -> None:
    try:
        participation_decision_from_content(
            '{"action":"respond","reason":"topic fit","confidence":0.73}'
        )
    except ValueError as exc:
        assert "respond decisions require text" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_llm_participation_provider_builds_prompt_and_metadata() -> None:
    chat_provider = RecordingChatProvider(
        '{"action":"respond","reason":"topic fit","confidence":0.73,"text":"可以，我补一句。"}'
    )

    decision = LLMSocialParticipationProvider(chat_provider=chat_provider).decide(
        _request(),
        wake_signals=("mention:bot_qq",),
    )

    assert decision.action == "respond"
    assert decision.reason == "topic fit"
    assert decision.confidence == 0.73
    assert decision.text == "可以，我补一句。"
    assert decision.metadata == {
        "provider": "unit-chat",
        "model": "unit-model",
        "usage": {"total_tokens": 12},
    }
    assert chat_provider.calls[0]["max_tokens"] == 256
    messages = chat_provider.calls[0]["messages"]
    assert messages[0]["role"] == "system"
    assert "QQ group chatbot participation decider" in messages[0]["content"]
    assert "required_json_shape" in messages[1]["content"]
    assert "wake_signals" in messages[1]["content"]
