from __future__ import annotations

import pytest

from isotope.llm.provider import (
    DeepSeekChatProvider,
    OpenAICompatibleChatProvider,
    resolve_llm_chat_provider,
)


def test_deepseek_provider_uses_v4_flash_chat_completions_contract():
    captured: dict = {}

    def stub_transport(url, payload, headers, timeout):
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

    provider = DeepSeekChatProvider(api_key="test_secret", transport=stub_transport)

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
    def stub_transport(url, payload, headers, timeout):
        return {"choices": [{"message": {"content": ""}}]}

    provider = DeepSeekChatProvider(api_key="test_secret", transport=stub_transport)

    with pytest.raises(ValueError, match="empty model response"):
        provider.generate([{"role": "user", "content": "hello"}])


def test_openai_compatible_provider_uses_configured_chat_completions_contract():
    captured: dict = {}

    def stub_transport(url, payload, headers, timeout):
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
        transport=stub_transport,
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


def test_openai_compatible_provider_allows_user_image_url_content_blocks():
    captured: dict = {}

    def stub_transport(url, payload, headers, timeout):
        captured["payload"] = payload
        return {
            "id": "chatcmpl_test",
            "model": "vision-chat",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "saw image"},
                }
            ],
            "usage": {"total_tokens": 5},
        }

    provider = OpenAICompatibleChatProvider(
        provider="custom",
        api_key="test_secret",
        base_url="https://api.custom.example.com/v1",
        model="vision-chat",
        transport=stub_transport,
    )
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this screen."},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,ZmFrZS1pbWFnZS1ieXRlcw=="
                    },
                },
            ],
        }
    ]

    response = provider.generate(messages, max_tokens=64)

    assert captured["payload"]["messages"] == messages
    assert response.content == "saw image"


def test_openai_compatible_provider_rejects_invalid_image_url_content_blocks():
    provider = OpenAICompatibleChatProvider(
        provider="custom",
        api_key="test_secret",
        base_url="https://api.custom.example.com/v1",
        model="vision-chat",
        transport=lambda url, payload, headers, timeout: {},
    )

    with pytest.raises(ValueError, match="user content blocks"):
        provider.generate(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this screen."},
                        {
                            "type": "image_url",
                            "image_url": {"url": "https://example.com/image.png"},
                        },
                    ],
                }
            ]
        )


def test_openai_compatible_provider_streams_chat_completion_deltas():
    captured: dict = {}

    def stub_stream_transport(url, payload, headers, timeout):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        return iter(
            [
                {
                    "model": "custom-chat",
                    "choices": [{"delta": {"role": "assistant"}}],
                },
                {
                    "model": "custom-chat",
                    "choices": [{"delta": {"content": "Loop"}}],
                },
                {
                    "model": "custom-chat",
                    "choices": [{"delta": {"content": " 正常"}}],
                },
            ]
        )

    provider = OpenAICompatibleChatProvider(
        provider="custom",
        api_key="test_secret",
        base_url="https://api.custom.example.com/v1",
        model="custom-chat",
        stream_transport=stub_stream_transport,
    )

    chunks = list(provider.stream_generate([{"role": "user", "content": "hello"}], max_tokens=64))

    assert captured["url"] == "https://api.custom.example.com/v1/chat/completions"
    assert captured["payload"] == {
        "model": "custom-chat",
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0,
        "max_tokens": 64,
        "stream": True,
    }
    assert captured["headers"]["Authorization"] == "Bearer test_secret"
    assert captured["timeout"] == 60
    assert [chunk.content for chunk in chunks] == ["Loop", " 正常"]
    assert chunks[0].provider == "custom"
    assert chunks[0].model == "custom-chat"


def test_deepseek_provider_streams_with_thinking_disabled():
    captured: dict = {}

    def stub_stream_transport(url, payload, headers, timeout):
        captured["url"] = url
        captured["payload"] = payload
        return iter(
            [
                {
                    "model": "deepseek-v4-flash",
                    "choices": [{"delta": {"content": "正在"}}],
                },
                {
                    "model": "deepseek-v4-flash",
                    "choices": [{"delta": {"content": "回答"}}],
                },
            ]
        )

    provider = DeepSeekChatProvider(
        api_key="test_secret",
        stream_transport=stub_stream_transport,
    )

    chunks = list(provider.stream_generate([{"role": "user", "content": "hello"}], max_tokens=32))

    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert captured["payload"]["stream"] is True
    assert [chunk.content for chunk in chunks] == ["正在", "回答"]


def test_openai_compatible_provider_retries_length_limited_reasoning_without_thinking():
    captured_payloads: list[dict] = []

    def stub_transport(url, payload, headers, timeout):
        captured_payloads.append(payload)
        if len(captured_payloads) == 1:
            return {
                "id": "chatcmpl_reasoning_only",
                "model": "reasoning-chat",
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "reasoning_content": "模型把输出额度用在思考过程。",
                        },
                    }
                ],
                "usage": {"completion_tokens": 512, "total_tokens": 900},
            }
        return {
            "id": "chatcmpl_retry",
            "model": "reasoning-chat",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": '{"kind":"monitor"}'},
                }
            ],
            "usage": {"completion_tokens": 12, "total_tokens": 300},
        }

    provider = OpenAICompatibleChatProvider(
        provider="custom",
        api_key="test_secret",
        base_url="https://api.custom.example.com/v1",
        model="reasoning-chat",
        transport=stub_transport,
    )

    response = provider.generate([{"role": "user", "content": "hello"}], max_tokens=512)

    assert response.content == '{"kind":"monitor"}'
    assert len(captured_payloads) == 2
    assert "thinking" not in captured_payloads[0]
    assert captured_payloads[1]["thinking"] == {"type": "disabled"}


def test_openai_compatible_provider_rejects_empty_configuration():
    with pytest.raises(ValueError, match="api_key"):
        OpenAICompatibleChatProvider(
            provider="custom",
            api_key="",
            base_url="https://api.custom.example.com",
            model="custom-chat",
        )


def test_resolve_chat_provider_can_select_openai_compatible_pool_entry_by_provider(
    tmp_path,
):
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

    resolution = resolve_llm_chat_provider(
        {
            "ISOTOPE_LLM_PROVIDER": "mimo",
            "ISOTOPE_LLM_POOL_TOML_FILES": str(pool_path),
        }
    )

    assert resolution.status == "configured"
    assert resolution.reason_code == "llm_provider_configured"
    assert resolution.provider_name == "mimo"
    assert isinstance(resolution.provider, OpenAICompatibleChatProvider)
    assert resolution.provider.provider == "mimo"
    assert resolution.provider.model == "mimo-v2.5-pro"
    assert resolution.provider.base_url == "https://token-plan-cn.xiaomimimo.com/v1"


def test_resolve_chat_provider_reports_unsupported_when_pool_provider_is_missing(
    tmp_path,
):
    pool_path = tmp_path / "llm-pool.toml"
    pool_path.write_text(
        "\n".join(
            [
                "[[agents]]",
                'name = "supervisor"',
                "",
                "[[agents.providers]]",
                'provider = "other"',
                'base_url = "https://api.other.example.com/v1"',
                'model = "other-chat"',
                'api_keys = ["other-test-key"]',
            ]
        ),
        encoding="utf-8",
    )

    resolution = resolve_llm_chat_provider(
        {
            "ISOTOPE_LLM_PROVIDER": "mimo",
            "ISOTOPE_LLM_POOL_TOML_FILES": str(pool_path),
        }
    )

    assert resolution.status == "missing_configuration"
    assert resolution.reason_code == "llm_provider_unsupported"
    assert resolution.provider_name == "mimo"
    assert resolution.provider is None


def test_resolve_chat_provider_accepts_supervisor_pool_toml_env_alias(tmp_path):
    pool_path = tmp_path / "supervisor-pool.toml"
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

    resolution = resolve_llm_chat_provider(
        {
            "ISOTOPE_LLM_PROVIDER": "mimo",
            "SUPERVISOR_LLM_POOL_TOML_FILES": str(pool_path),
        }
    )

    assert resolution.status == "configured"
    assert resolution.provider_name == "mimo"
    assert isinstance(resolution.provider, OpenAICompatibleChatProvider)
