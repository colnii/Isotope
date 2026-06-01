from __future__ import annotations

import json
from typing import Any

import pytest

from isotope.llm.provider import (
    CodexCliLLMProvider,
    DeepSeekChatProvider,
    LLMFinalAnswerResponse,
    OpenAICompatibleChatProvider,
    resolve_llm_tool_call_provider,
)


class _FakeCompletedProcess:
    def __init__(self, *, stdout: str, stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class _RecordingCodexRunner:
    def __init__(self, agent_text: str, *, returncode: int = 0) -> None:
        self.agent_text = agent_text
        self.returncode = returncode
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": list(argv), "kwargs": dict(kwargs)})
        return _FakeCompletedProcess(
            stdout=json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": self.agent_text},
                }
            )
            + "\n",
            returncode=self.returncode,
        )


def _resolve_codex_executable(executable: str) -> str:
    assert executable == "codex"
    return "/opt/codex/bin/codex"


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


def test_openai_compatible_provider_streams_chat_completion_deltas():
    captured: dict = {}

    def fake_stream_transport(url, payload, headers, timeout):
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
        stream_transport=fake_stream_transport,
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

    def fake_stream_transport(url, payload, headers, timeout):
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
        stream_transport=fake_stream_transport,
    )

    chunks = list(provider.stream_generate([{"role": "user", "content": "hello"}], max_tokens=32))

    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert captured["payload"]["stream"] is True
    assert [chunk.content for chunk in chunks] == ["正在", "回答"]


def test_openai_compatible_provider_retries_length_limited_reasoning_without_thinking():
    captured_payloads: list[dict] = []

    def fake_transport(url, payload, headers, timeout):
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
        transport=fake_transport,
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


def test_codex_cli_provider_generates_from_agent_message(tmp_path):
    runner = _RecordingCodexRunner("Codex answer")
    provider = CodexCliLLMProvider(
        workspace_root=str(tmp_path),
        executable="codex",
        model="gpt-5-codex",
        timeout=11,
        process_runner=runner,
        executable_resolver=_resolve_codex_executable,
    )

    response = provider.generate(
        [
            {"role": "system", "content": "You answer briefly."},
            {"role": "user", "content": "hello"},
        ],
        max_tokens=77,
    )

    assert response.provider == "codex"
    assert response.model == "gpt-5-codex"
    assert response.content == "Codex answer"
    assert response.finish_reason == "stop"
    assert response.usage["max_tokens"] == 77
    assert runner.calls
    call = runner.calls[0]
    assert call["argv"][:2] == ["/opt/codex/bin/codex", "--ask-for-approval"]
    assert "--model" in call["argv"]
    assert "gpt-5-codex" in call["argv"]
    assert "--sandbox" in call["argv"]
    assert "read-only" in call["argv"]
    assert call["kwargs"]["timeout"] == 11
    assert call["kwargs"]["cwd"] == str(tmp_path.resolve())
    assert "Do not execute shell commands" in call["kwargs"]["input"]
    assert '"role": "user"' in call["kwargs"]["input"]


def test_codex_cli_provider_selects_required_tool_from_json_agent_message(tmp_path):
    runner = _RecordingCodexRunner(
        json.dumps(
            {
                "tool_call": {
                    "id": "call_codex",
                    "name": "codex_task",
                    "arguments": {"prompt": "inspect repo", "summary": "unit"},
                }
            }
        )
    )
    provider = CodexCliLLMProvider(
        workspace_root=str(tmp_path),
        executable="codex",
        timeout=9,
        process_runner=runner,
        executable_resolver=_resolve_codex_executable,
    )

    response = provider.select_tool(
        [{"role": "user", "content": "choose"}],
        tools=[
            {
                "name": "codex_task",
                "input_schema": {
                    "type": "object",
                    "properties": {"prompt": {"type": "string"}},
                },
            }
        ],
        max_tokens=33,
    )

    assert response.provider == "codex"
    assert response.finish_reason == "tool_calls"
    assert response.tool_call.call_id == "call_codex"
    assert response.tool_call.tool_name == "codex_task"
    assert response.tool_call.arguments == {"prompt": "inspect repo", "summary": "unit"}
    assert "Select exactly one offered tool" in runner.calls[0]["kwargs"]["input"]


def test_codex_cli_provider_select_chat_turn_can_return_final_answer(tmp_path):
    runner = _RecordingCodexRunner(
        json.dumps({"type": "final_answer", "content": "已经完成。"})
    )
    provider = CodexCliLLMProvider(
        workspace_root=str(tmp_path),
        executable="codex",
        timeout=9,
        process_runner=runner,
        executable_resolver=_resolve_codex_executable,
    )

    response = provider.select_chat_turn(
        [{"role": "user", "content": "answer"}],
        tools=[{"name": "codex_task", "input_schema": {"type": "object", "properties": {}}}],
        max_tokens=44,
    )

    assert isinstance(response, LLMFinalAnswerResponse)
    assert response.provider == "codex"
    assert response.content == "已经完成。"
    assert response.finish_reason == "stop"
    assert "Return either a final_answer or one tool_call" in runner.calls[0]["kwargs"]["input"]


def test_llm_provider_resolution_configures_codex_without_api_key(tmp_path):
    runner = _RecordingCodexRunner(
        json.dumps(
            {
                "tool_call": {
                    "id": "call_from_resolver",
                    "name": "codex_task",
                    "arguments": {"prompt": "ok", "summary": "unit"},
                }
            }
        )
    )

    resolution = resolve_llm_tool_call_provider(
        {
            "ISOTOPE_LLM_PROVIDER": "codex",
            "ISOTOPE_LLM_MODEL": "gpt-5-codex",
            "ISOTOPE_LLM_TIMEOUT_SECONDS": "13",
            "ISOTOPE_CODEX_WORKSPACE_ROOT": str(tmp_path),
        },
        codex_process_runner=runner,
        codex_executable_resolver=_resolve_codex_executable,
    )

    assert resolution.status == "configured"
    assert resolution.provider_name == "codex"
    assert resolution.provider is not None
    response = resolution.provider.select_tool(
        [{"role": "user", "content": "choose"}],
        tools=[{"name": "codex_task", "input_schema": {"type": "object", "properties": {}}}],
        max_tokens=55,
    )
    assert response.tool_call.call_id == "call_from_resolver"
    assert "--model" in runner.calls[0]["argv"]
    assert "gpt-5-codex" in runner.calls[0]["argv"]
