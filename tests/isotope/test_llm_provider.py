from __future__ import annotations

import pytest

from isotope.llm.provider import DeepSeekChatProvider, OpenAICompatibleChatProvider


def test_deepseek_provider_uses_v4_flash_chat_completions_contract():
    captured: dict = {}

    def fake_transport(url, payload, headers, timeout):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        return {
            "id": "chatcmpl_test",
            "model": "deepseek-v4-flash",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "review result"},
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        }

    provider = DeepSeekChatProvider(api_key="test_secret", transport=fake_transport)

    response = provider.generate(
        [
            {"role": "system", "content": "You review artifacts."},
            {"role": "user", "content": "Please review this note."},
        ],
        max_tokens=128,
    )

    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["payload"]["model"] == "deepseek-v4-flash"
    assert captured["payload"]["messages"][1]["role"] == "user"
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert captured["payload"]["temperature"] == 0
    assert captured["payload"]["stream"] is False
    assert captured["headers"]["Authorization"] == "Bearer test_secret"
    assert captured["timeout"] == 60
    assert response.provider == "deepseek"
    assert response.model == "deepseek-v4-flash"
    assert response.content == "review result"
    assert response.finish_reason == "stop"
    assert response.usage["total_tokens"] == 5


def test_deepseek_provider_requires_api_key_without_echoing_key_value():
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        DeepSeekChatProvider(api_key="")


def test_deepseek_provider_rejects_malformed_response():
    def fake_transport(url, payload, headers, timeout):
        return {"choices": [{"message": {"content": ""}}]}

    provider = DeepSeekChatProvider(api_key="test_secret", transport=fake_transport)

    with pytest.raises(ValueError, match="empty model response"):
        provider.generate([{"role": "user", "content": "hello"}])


def test_openai_compatible_provider_uses_configured_chat_completions_contract():
    captured: dict = {}

    def fake_transport(url, payload, headers, timeout):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        return {
            "id": "chatcmpl_test",
            "model": "custom-chat",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "summary result"},
                }
            ],
            "usage": {"total_tokens": 5},
        }

    provider = OpenAICompatibleChatProvider(
        provider="custom",
        api_key="test_secret",
        base_url="https://api.custom.example.com/v1",
        model="custom-chat",
        transport=fake_transport,
    )

    response = provider.generate([{"role": "user", "content": "hello"}], max_tokens=64)

    assert captured["url"] == "https://api.custom.example.com/v1/chat/completions"
    assert captured["payload"] == {
        "model": "custom-chat",
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0,
        "max_tokens": 64,
        "stream": False,
    }
    assert captured["headers"]["Authorization"] == "Bearer test_secret"
    assert captured["timeout"] == 60
    assert response.provider == "custom"
    assert response.content == "summary result"


def test_openai_compatible_provider_rejects_empty_configuration():
    with pytest.raises(ValueError, match="api_key"):
        OpenAICompatibleChatProvider(
            provider="custom",
            api_key="",
            base_url="https://api.custom.example.com",
            model="custom-chat",
        )
