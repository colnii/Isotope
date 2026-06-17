from __future__ import annotations

from isotope.llm.provider import (
    OpenAICompatibleChatProvider,
    OpenAICompatibleToolCallProvider,
    resolve_llm_tool_call_provider,
)


def test_minimax_chat_provider_disables_thinking_by_default():
    captured: dict[str, object] = {}

    def stub_transport(url, payload, headers, timeout):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        return {
            "model": "MiniMax-M3",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "OK"},
                }
            ],
        }

    provider = OpenAICompatibleChatProvider(
        provider="minimax",
        api_key="sk-test",
        base_url="https://api.minimaxi.com/v1",
        model="MiniMax-M3",
        transport=stub_transport,
    )

    response = provider.generate(
        [{"role": "user", "content": "Reply exactly OK."}],
        max_tokens=32,
    )

    assert captured["url"] == "https://api.minimaxi.com/v1/chat/completions"
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert captured["payload"]["model"] == "MiniMax-M3"
    assert captured["payload"]["max_tokens"] == 32
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert response.provider == "minimax"
    assert response.content == "OK"


def test_tool_call_resolution_can_select_minimax_pool_entry(tmp_path):
    pool_path = tmp_path / "pool.toml"
    pool_path.write_text(
        "\n".join(
            [
                "[[agents]]",
                'name = "supervisor"',
                "",
                "[[agents.providers]]",
                'provider = "minimax"',
                'base_url = "https://api.minimaxi.com/v1"',
                'model = "MiniMax-M3"',
                'max_tokens = 2048',
                'api_keys = ["env:YIFU_MINIMAX_CODER_API_KEY"]',
            ]
        ),
        encoding="utf-8",
    )

    resolution = resolve_llm_tool_call_provider(
        {
            "ISOTOPE_LLM_PROVIDER": "minimax",
            "ISOTOPE_LLM_POOL_TOML_FILES": str(pool_path),
            "YIFU_MINIMAX_CODER_API_KEY": "sk-test",
        }
    )

    assert resolution.status == "configured"
    assert resolution.reason_code == "llm_provider_configured"
    assert resolution.provider_name == "minimax"
    assert isinstance(resolution.provider, OpenAICompatibleToolCallProvider)
    assert resolution.provider.provider == "minimax"
    assert resolution.provider.base_url == "https://api.minimaxi.com/v1"
    assert resolution.provider.model == "MiniMax-M3"


def test_minimax_tool_call_provider_disables_thinking_by_default():
    captured: dict[str, object] = {}

    def stub_transport(url, payload, headers, timeout):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        return {
            "model": "MiniMax-M3",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "call_test",
                                "type": "function",
                                "function": {
                                    "name": "ping_tool",
                                    "arguments": '{"value":"OK"}',
                                },
                            }
                        ],
                    },
                }
            ],
        }

    provider = OpenAICompatibleToolCallProvider(
        provider="minimax",
        api_key="sk-test",
        base_url="https://api.minimaxi.com/v1",
        model="MiniMax-M3",
        transport=stub_transport,
    )

    response = provider.select_tool(
        [{"role": "user", "content": "Call ping_tool."}],
        tools=[
            {
                "name": "ping_tool",
                "input_schema": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                },
            }
        ],
        max_tokens=64,
    )

    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert captured["payload"]["tool_choice"] == "required"
    assert response.tool_call.tool_name == "ping_tool"
    assert response.tool_call.arguments == {"value": "OK"}
