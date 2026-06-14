from __future__ import annotations

import pytest

from isotope.features.social import (
    SocialOperationsController,
    qq_runtime_commands,
)
from isotope.features.social.participation_provider import LLMSocialParticipationProvider
from isotope.features.social.reply_provider import (
    DeterministicSocialReplyProvider,
    LLMSocialReplyProvider,
)
from isotope.integrations.qq import FakeOneBotClient, OneBotAdapter
from isotope.llm.provider import LLMProviderResolution
from tests.unit.features.social.test_character_card import _card_dict


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


def test_participation_and_reply_provider_can_resolve_mimo_from_pool(
    tmp_path,
    monkeypatch,
) -> None:
    pool_path = tmp_path / "llm-pool.toml"
    pool_path.write_text(
        "\n".join(
            [
                "[[agents]]",
                'name = "supervisor"',
                "",
                "[[agents.providers]]",
                'provider = "mimo"',
                'base_url = "https://token-plan-cn.xiaomimimo.com/v1"',
                'model = "mimo-v2.5-pro"',
                'api_keys = ["tp-test-key"]',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ISOTOPE_LLM_PROVIDER", "mimo")
    monkeypatch.setenv("ISOTOPE_LLM_POOL_TOML_FILES", str(pool_path))

    loop = qq_runtime_commands.decision_loop_from_config(
        {"runtime": {"participation_provider": "llm", "reply_provider": "llm"}}
    )

    assert isinstance(loop.participation_provider, LLMSocialParticipationProvider)
    assert isinstance(loop.reply_provider, LLMSocialReplyProvider)
    assert loop.participation_provider.chat_provider.provider == "mimo"
    assert loop.reply_provider.chat_provider.provider == "mimo"
    assert loop.reply_provider.chat_provider.model == "mimo-v2.5-pro"


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


def test_runtime_config_parses_social_capability_intent() -> None:
    config = qq_runtime_commands.runtime_config_from_config(
        {
            "bot_user_id": "bot_qq",
            "runtime": {
                "capability": {
                    "enabled": True,
                    "capability_id": "supervisor.request_context",
                    "trigger_keywords": ["capacity"],
                    "input_defaults": {"cwd": "/repo", "state_root": "/state"},
                    "query_input_key": "query",
                    "approval_keywords": ["批准"],
                }
            },
        }
    )

    assert config.capability.enabled is True
    assert config.capability.capability_id == "supervisor.request_context"
    assert config.capability.trigger_keywords == ("capacity",)
    assert config.capability.input_defaults == {"cwd": "/repo", "state_root": "/state"}
    assert config.capability.query_input_key == "query"
    assert config.capability.approval_keywords == ("批准",)


def test_runtime_from_adapter_wires_capability_bridge_when_enabled() -> None:
    runtime = qq_runtime_commands.runtime_from_adapter(
        config={
            "bot_user_id": "bot_qq",
            "role_card": _card_dict(),
            "runtime": {
                "capability": {
                    "enabled": True,
                    "capability_id": "supervisor.request_context",
                    "trigger_keywords": ["capacity"],
                    "input_defaults": {"cwd": "/repo", "state_root": "/state"},
                    "approval_keywords": ["批准"],
                    "approval_required": True,
                }
            },
        },
        operations=SocialOperationsController(),
        adapter=OneBotAdapter(client=FakeOneBotClient()),
    )

    assert runtime.config.capability.enabled is True
    assert runtime.capability_bridge is not None
    assert (
        runtime.capability_bridge.policy.approval_required_capabilities
        == ("supervisor.request_context",)
    )
