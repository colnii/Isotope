from __future__ import annotations

import json
import os
import shutil
from typing import Any

import pytest

import isotope.integrations.codex.server as codex_server
import isotope.demo.live_smoke.llm_live_smoke as llm_live_smoke
from isotope.interfaces.http import (
    create_codex_cli_http_app,
    create_http_app,
    create_llm_product_chat_http_app,
)
import isotope.llm.provider as llm_provider
from isotope.llm.provider import LLMToolCall, LLMToolCallResponse


class DeterministicCompletedProcess:
    def __init__(self, *, stdout: str = "") -> None:
        self.returncode = 0
        self.stdout = stdout
        self.stderr = ""


class RecordingProcessRunner:
    def __init__(self, result: DeterministicCompletedProcess) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": list(argv), "kwargs": dict(kwargs)})
        return self.result


class RecordingToolProvider:
    provider = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(self, response: LLMToolCallResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def select_tool(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]],
        max_tokens: int = 512,
    ) -> LLMToolCallResponse:
        self.calls.append(
            {
                "messages": list(messages),
                "tools": list(tools),
                "max_tokens": max_tokens,
            }
        )
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class SequencedChatProvider:
    provider = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def select_chat_turn(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]],
        max_tokens: int = 512,
    ):
        self.calls.append({"messages": list(messages), "tools": list(tools), "max_tokens": max_tokens})
        assert self.responses
        return self.responses.pop(0)


def _codex_http_app(tmp_path, runner: RecordingProcessRunner):
    return create_codex_cli_http_app(
        tmp_path,
        config=codex_server.CodexCliServerConfig(
            workspace_root=str(tmp_path / "workspace"),
            executable="/opt/codex/bin/codex",
            timeout_seconds=17,
            max_output_bytes=4096,
        ),
        process_runner=runner,
    )


def _product_chat_http_app(tmp_path, runner: RecordingProcessRunner, provider: Any):
    return create_llm_product_chat_http_app(
        tmp_path,
        config=codex_server.CodexCliServerConfig(
            workspace_root=str(tmp_path / "workspace"),
            executable="/opt/codex/bin/codex",
            timeout_seconds=17,
            max_output_bytes=4096,
        ),
        provider=provider,
        process_runner=runner,
    )


def _create_run(app) -> str:
    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="live model chooses a tool")
    return run["run_id"]


def _event_types(app, run_id: str) -> list[str]:
    return [event.event_type for event in app.server.get_events(run_id)]


def _provider_response(
    prompt: str = "LLM_LIVE_PROMPT_SHOULD_NOT_LEAK",
    *,
    call_id: str = "call_live_smoke",
    summary: str = "live smoke selected Codex task",
) -> LLMToolCallResponse:
    return LLMToolCallResponse(
        provider="deepseek",
        model="deepseek-v4-flash",
        finish_reason="tool_calls",
        usage={"prompt_tokens": 9, "completion_tokens": 5, "total_tokens": 14},
        tool_call=LLMToolCall(
            call_id=call_id,
            tool_name="codex_task",
            arguments={
                "prompt": prompt,
                "summary": summary,
            },
        ),
    )


def _final_answer_response(content: str) -> llm_provider.LLMFinalAnswerResponse:
    return llm_provider.LLMFinalAnswerResponse(
        provider="deepseek",
        model="deepseek-v4-flash",
        finish_reason="stop",
        usage={"prompt_tokens": 13, "completion_tokens": 5, "total_tokens": 18},
        content=content,
    )


def _raw_tool_call_completion() -> dict[str, Any]:
    return {
        "model": "deepseek-unit",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "tool_calls": [
                        {
                            "id": "call_unified_env",
                            "type": "function",
                            "function": {
                                "name": "codex_task",
                                "arguments": '{"prompt":"ok","summary":"unit"}',
                            },
                        }
                    ]
                },
            }
        ],
        "usage": {"total_tokens": 12},
    }



def test_llm_provider_resolution_accepts_unified_env_without_deepseek_key():
    calls: list[dict[str, Any]] = []

    def transport(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int):
        calls.append({"url": url, "payload": payload, "headers": headers, "timeout": timeout})
        return _raw_tool_call_completion()

    resolution = llm_provider.resolve_llm_tool_call_provider(
        {
            "ISOTOPE_LLM_PROVIDER": "deepseek",
            "ISOTOPE_LLM_API_KEY": "UNIFIED_SECRET_SHOULD_NOT_LEAK",
            "ISOTOPE_LLM_MODEL": "deepseek-unit",
            "ISOTOPE_LLM_BASE_URL": "https://unit.deepseek.invalid",
            "ISOTOPE_LLM_TIMEOUT_SECONDS": "9",
        },
        transport=transport,
    )

    assert resolution.status == "configured"
    assert resolution.reason_code == "llm_provider_configured"
    assert resolution.provider_name == "deepseek"
    assert resolution.provider is not None
    response = resolution.provider.select_tool(
        [{"role": "user", "content": "choose a tool"}],
        tools=[{"name": "codex_task", "input_schema": {"type": "object", "properties": {}}}],
        max_tokens=33,
    )

    assert response.tool_call.call_id == "call_unified_env"
    assert calls[0]["url"] == "https://unit.deepseek.invalid/chat/completions"
    assert calls[0]["payload"]["model"] == "deepseek-unit"
    assert calls[0]["payload"]["max_tokens"] == 33
    assert calls[0]["headers"]["Authorization"] == "Bearer UNIFIED_SECRET_SHOULD_NOT_LEAK"
    assert calls[0]["timeout"] == 9
    assert "UNIFIED_SECRET_SHOULD_NOT_LEAK" not in repr(resolution)



def test_llm_provider_resolution_reports_unsupported_provider_without_secret_leak():
    resolution = llm_provider.resolve_llm_tool_call_provider(
        {
            "ISOTOPE_LLM_PROVIDER": "anthropic",
            "ISOTOPE_LLM_API_KEY": "UNSUPPORTED_SECRET_SHOULD_NOT_LEAK",
        }
    )

    assert resolution.status == "missing_configuration"
    assert resolution.reason_code == "llm_provider_unsupported"
    assert resolution.provider_name == "anthropic"
    assert resolution.provider is None
    assert "UNSUPPORTED_SECRET_SHOULD_NOT_LEAK" not in repr(resolution)


def test_llm_provider_resolution_accepts_mimo_multimodal_tool_calls():
    calls: list[dict[str, Any]] = []

    def transport(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int):
        calls.append({"url": url, "payload": payload, "headers": headers, "timeout": timeout})
        return {
            "model": "mimo-v2.5",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_mimo_screen",
                                "type": "function",
                                "function": {
                                    "name": "screen_control",
                                    "arguments": (
                                        '{"target_selector":{"kind":"window","selector":{"app":"notepad.exe"}},'
                                        '"execution_mode":"execute","actions":[{"type":"restore_window"}]}'
                                    ),
                                },
                            }
                        ]
                    },
                }
            ],
            "usage": {"total_tokens": 28},
        }

    resolution = llm_provider.resolve_llm_tool_call_provider(
        {
            "ISOTOPE_LLM_PROVIDER": "mimo",
            "ISOTOPE_LLM_API_KEY": "MIMO_SECRET_SHOULD_NOT_LEAK",
            "ISOTOPE_LLM_BASE_URL": "https://token-plan-cn.xiaomimimo.com/v1",
            "ISOTOPE_LLM_TIMEOUT_SECONDS": "11",
        },
        transport=transport,
    )

    assert resolution.status == "configured"
    assert resolution.reason_code == "llm_provider_configured"
    assert resolution.provider_name == "mimo"
    assert resolution.provider is not None
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Use screen_control for the shown window."},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,ZmFrZS1pbWFnZS1ieXRlcw=="
                    },
                },
            ],
        }
    ]
    response = resolution.provider.select_tool(
        messages,
        tools=[{"name": "screen_control", "input_schema": {"type": "object", "properties": {}}}],
        max_tokens=44,
    )

    assert response.provider == "mimo"
    assert response.tool_call.tool_name == "screen_control"
    assert calls[0]["url"] == "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
    assert calls[0]["payload"]["messages"] == messages
    assert calls[0]["payload"]["model"] == "mimo-v2.5"
    assert calls[0]["payload"]["max_tokens"] == 44
    assert "thinking" not in calls[0]["payload"]
    assert calls[0]["headers"]["Authorization"] == "Bearer MIMO_SECRET_SHOULD_NOT_LEAK"
    assert "api-key" not in calls[0]["headers"]
    assert calls[0]["timeout"] == 11
    assert "MIMO_SECRET_SHOULD_NOT_LEAK" not in repr(resolution)


def test_llm_tool_call_live_smoke_reports_unified_missing_configuration_without_side_effects(tmp_path):
    runner = RecordingProcessRunner(DeterministicCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    result = llm_live_smoke.run_llm_tool_call_live_smoke(
        app,
        run_id,
        config=llm_live_smoke.LLMToolCallLiveSmokeConfig(enabled=True),
        environ={},
    )

    assert result == {
        "status": "missing_configuration",
        "reason_code": "llm_provider_not_configured",
        "provider": "auto",
        "tool_name": "codex_task",
    }
    assert "DEEPSEEK_API_KEY" not in repr(result)
    assert _event_types(app, run_id) == before_events
    assert runner.calls == []
