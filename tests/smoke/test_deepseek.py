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



def test_deepseek_tool_call_live_smoke_is_skipped_by_default(tmp_path):
    runner = RecordingProcessRunner(DeterministicCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    result = llm_live_smoke.run_deepseek_tool_call_live_smoke(app, run_id)

    assert result == {
        "status": "skipped",
        "reason_code": "deepseek_tool_call_live_smoke_unavailable",
        "provider": "deepseek",
        "tool_name": "codex_task",
    }
    assert _event_types(app, run_id) == before_events
    assert runner.calls == []



def test_deepseek_tool_call_live_smoke_reports_missing_key_without_side_effects(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    runner = RecordingProcessRunner(DeterministicCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    result = llm_live_smoke.run_deepseek_tool_call_live_smoke(
        app,
        run_id,
        config=llm_live_smoke.DeepSeekToolCallLiveSmokeConfig(enabled=True),
    )

    assert result == {
        "status": "missing_configuration",
        "reason_code": "deepseek_api_key_missing",
        "provider": "deepseek",
        "tool_name": "codex_task",
    }
    assert _event_types(app, run_id) == before_events
    assert runner.calls == []



def test_deepseek_tool_call_live_smoke_submits_pending_approval_with_deterministic_provider(tmp_path):
    runner = RecordingProcessRunner(DeterministicCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    provider = RecordingToolProvider(_provider_response())

    result = llm_live_smoke.run_deepseek_tool_call_live_smoke(
        app,
        run_id,
        config=llm_live_smoke.DeepSeekToolCallLiveSmokeConfig(enabled=True, max_tokens=64),
        provider=provider,
    )

    assert result["status"] == "completed"
    assert result["reason_code"] == "deepseek_tool_call_live_smoke_completed"
    assert result["provider"] == "deepseek"
    assert result["model"] == "deepseek-v4-flash"
    assert result["finish_reason"] == "tool_calls"
    assert result["tool_name"] == "codex_task"
    assert result["tool_result_status"] == "pending_user_approval"
    assert result["approval_id"].startswith("approval_")
    assert result["usage"] == {"prompt_tokens": 9, "completion_tokens": 5, "total_tokens": 14}
    assert [tool["name"] for tool in provider.calls[0]["tools"]] == ["codex_task"]
    assert provider.calls[0]["max_tokens"] == 64
    assert "approval.requested" in _event_types(app, run_id)
    assert runner.calls == []



def test_deepseek_tool_call_live_smoke_result_does_not_expose_prompt(tmp_path):
    runner = RecordingProcessRunner(DeterministicCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    provider = RecordingToolProvider(_provider_response("LIVE_SMOKE_PROMPT_SHOULD_NOT_LEAK"))

    result = llm_live_smoke.run_deepseek_tool_call_live_smoke(
        app,
        run_id,
        config=llm_live_smoke.DeepSeekToolCallLiveSmokeConfig(enabled=True),
        provider=provider,
    )

    assert "LIVE_SMOKE_PROMPT_SHOULD_NOT_LEAK" not in repr(result)
    assert runner.calls == []



def test_deepseek_tool_call_diagnosis_reports_ready_without_starting_codex(tmp_path):
    runner = RecordingProcessRunner(DeterministicCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    provider = RecordingToolProvider(_provider_response())

    result = llm_live_smoke.diagnose_deepseek_tool_call_live_smoke(
        app,
        run_id,
        config=llm_live_smoke.DeepSeekToolCallLiveSmokeConfig(enabled=True),
        provider=provider,
    )

    assert result["diagnosis"] == {
        "category": "ready",
        "provider_request_started": True,
        "approval_requested": True,
        "codex_started": False,
        "summary": "DeepSeek selected codex_task and Isotope stopped at approval",
        "next_step": "keep this as a dev-only readiness check until product route tests exist",
    }
    assert "LLM_LIVE_PROMPT_SHOULD_NOT_LEAK" not in repr(result)
    assert runner.calls == []



def test_deepseek_tool_call_diagnosis_reports_missing_key_without_side_effects(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    runner = RecordingProcessRunner(DeterministicCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    result = llm_live_smoke.diagnose_deepseek_tool_call_live_smoke(
        app,
        run_id,
        config=llm_live_smoke.DeepSeekToolCallLiveSmokeConfig(enabled=True),
    )

    assert result["diagnosis"] == {
        "category": "missing_configuration",
        "provider_request_started": False,
        "approval_requested": False,
        "codex_started": False,
        "summary": "DEEPSEEK_API_KEY is not configured",
        "next_step": "configure DeepSeek credentials before running the live provider smoke",
    }
    assert _event_types(app, run_id) == before_events
    assert runner.calls == []



def test_deepseek_tool_call_diagnosis_reports_provider_request_failure_without_secret_leak(
    tmp_path,
):
    runner = RecordingProcessRunner(DeterministicCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    provider = RecordingToolProvider(RuntimeError("network failed: SECRET_PROVIDER_TEXT"))

    result = llm_live_smoke.diagnose_deepseek_tool_call_live_smoke(
        app,
        run_id,
        config=llm_live_smoke.DeepSeekToolCallLiveSmokeConfig(enabled=True),
        provider=provider,
    )

    assert result["status"] == "failed"
    assert result["reason_code"] == "llm_provider_request_failed"
    assert result["diagnosis"]["category"] == "provider_request_failed"
    assert result["diagnosis"]["provider_request_started"] is True
    assert result["diagnosis"]["approval_requested"] is False
    assert result["diagnosis"]["codex_started"] is False
    assert "SECRET_PROVIDER_TEXT" not in repr(result)
    assert provider.calls
    assert runner.calls == []



def test_deepseek_tool_call_diagnosis_reports_invalid_provider_response(tmp_path):
    runner = RecordingProcessRunner(DeterministicCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    provider = RecordingToolProvider(ValueError("text response: SECRET_MODEL_TEXT"))

    result = llm_live_smoke.diagnose_deepseek_tool_call_live_smoke(
        app,
        run_id,
        config=llm_live_smoke.DeepSeekToolCallLiveSmokeConfig(enabled=True),
        provider=provider,
    )

    assert result["reason_code"] == "llm_tool_call_invalid_response"
    assert result["diagnosis"]["category"] == "provider_response_invalid"
    assert result["diagnosis"]["provider_request_started"] is True
    assert "SECRET_MODEL_TEXT" not in repr(result)
    assert runner.calls == []



def test_deepseek_tool_call_diagnosis_reports_unavailable_requested_tool(tmp_path):
    runner = RecordingProcessRunner(DeterministicCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    provider = RecordingToolProvider(_provider_response())

    result = llm_live_smoke.diagnose_deepseek_tool_call_live_smoke(
        app,
        run_id,
        config=llm_live_smoke.DeepSeekToolCallLiveSmokeConfig(
            enabled=True,
            tool_name="missing_tool",
        ),
        provider=provider,
    )

    assert result["reason_code"] == "llm_tool_unavailable"
    assert result["diagnosis"] == {
        "category": "tool_unavailable",
        "provider_request_started": False,
        "approval_requested": False,
        "codex_started": False,
        "summary": "the requested tool is absent from the model-facing catalog",
        "next_step": "wire the intended tool explicitly or keep the smoke limited to codex_task",
    }
    assert provider.calls == []
    assert runner.calls == []



def test_deepseek_tool_call_diagnosis_reports_provider_selected_unoffered_tool(tmp_path):
    runner = RecordingProcessRunner(DeterministicCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    provider = RecordingToolProvider(
        LLMToolCallResponse(
            provider="deepseek",
            model="deepseek-v4-flash",
            finish_reason="tool_calls",
            usage={"total_tokens": 11},
            tool_call=LLMToolCall(
                call_id="call_terminal_exec",
                tool_name="terminal_exec",
                arguments={"argv": ["python", "--version"]},
            ),
        )
    )

    result = llm_live_smoke.diagnose_deepseek_tool_call_live_smoke(
        app,
        run_id,
        config=llm_live_smoke.DeepSeekToolCallLiveSmokeConfig(enabled=True),
        provider=provider,
    )

    assert result["reason_code"] == "llm_provider_selected_unoffered_tool"
    assert result["diagnosis"] == {
        "category": "tool_unavailable",
        "provider_request_started": True,
        "approval_requested": False,
        "codex_started": False,
        "summary": "the provider selected a tool that was not offered in this smoke",
        "next_step": "tighten the provider response or include the intended tool in the smoke config",
    }
    assert runner.calls == []
