from __future__ import annotations

import pytest

from isotope.features.social import qq_runtime_commands
from isotope.features.social.participation_provider import LLMSocialParticipationProvider
from isotope.features.social.reply_provider import (
    DeterministicSocialReplyProvider,
    LLMSocialReplyProvider,
)
from isotope.llm.provider import LLMProviderResolution


class FakeChatProvider:
    provider = "unit-chat"
    model = "unit-model"

    def generate(self, messages: list[dict], *, max_tokens: int = 512):
        raise AssertionError("config wiring must not call generate")


def test_participation_provider_defaults_to_rules_without_llm(monkeypatch) -> None:
    def fail_if_called():
        raise AssertionError("default rules mode must not resolve LLM provider")

    monkeypatch.setattr(qq_runtime_commands, "resolve_llm_chat_provider", fail_if_called)

    loop = qq_runtime_commands.decision_loop_from_config({"runtime": {}})

    assert loop.participation_provider is None
    assert isinstance(loop.reply_provider, DeterministicSocialReplyProvider)


def test_participation_provider_llm_injects_llm_participation_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        qq_runtime_commands,
        "resolve_llm_chat_provider",
        lambda: LLMProviderResolution(
            status="configured",
            reason_code="llm_provider_configured",
            provider_name="unit-chat",
            provider=FakeChatProvider(),
        ),
    )

    loop = qq_runtime_commands.decision_loop_from_config(
        {"runtime": {"participation_provider": "llm"}}
    )

    assert isinstance(loop.participation_provider, LLMSocialParticipationProvider)
    assert isinstance(loop.reply_provider, DeterministicSocialReplyProvider)


def test_participation_provider_llm_can_share_config_with_llm_reply_provider(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        qq_runtime_commands,
        "resolve_llm_chat_provider",
        lambda: LLMProviderResolution(
            status="configured",
            reason_code="llm_provider_configured",
            provider_name="unit-chat",
            provider=FakeChatProvider(),
        ),
    )

    loop = qq_runtime_commands.decision_loop_from_config(
        {"runtime": {"participation_provider": "llm", "reply_provider": "llm"}}
    )

    assert isinstance(loop.participation_provider, LLMSocialParticipationProvider)
    assert isinstance(loop.reply_provider, LLMSocialReplyProvider)


def test_participation_provider_llm_requires_configured_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        qq_runtime_commands,
        "resolve_llm_chat_provider",
        lambda: LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_not_configured",
            provider_name="auto",
        ),
    )

    with pytest.raises(
        ValueError,
        match="LLM participation provider is not configured: llm_provider_not_configured",
    ):
        qq_runtime_commands.decision_loop_from_config(
            {"runtime": {"participation_provider": "llm"}}
        )


def test_participation_provider_rejects_invalid_config_value() -> None:
    with pytest.raises(
        ValueError,
        match="runtime.participation_provider must be rules or llm",
    ):
        qq_runtime_commands.decision_loop_from_config(
            {"runtime": {"participation_provider": "always"}}
        )
