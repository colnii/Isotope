from __future__ import annotations

from isotope.features.social.participation_provider import (
    LLMParticipationDecision,
    participation_decision_from_content,
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
