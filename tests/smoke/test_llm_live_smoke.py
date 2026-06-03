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


class FakeCompletedProcess:
    def __init__(self, *, stdout: str = "") -> None:
        self.returncode = 0
        self.stdout = stdout
        self.stderr = ""


class RecordingProcessRunner:
    def __init__(self, result: FakeCompletedProcess) -> None:
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


def test_llm_tool_call_live_smoke_reports_unified_missing_configuration_without_side_effects(tmp_path):
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
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


def test_llm_terminal_tool_live_smoke_offers_only_terminal_exec_and_runs_without_codex(tmp_path):
    app = create_http_app(tmp_path)
    run_id = _create_run(app)
    provider = RecordingToolProvider(
        LLMToolCallResponse(
            provider="deepseek",
            model="deepseek-v4-flash",
            finish_reason="tool_calls",
            usage={"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
            tool_call=LLMToolCall(
                call_id="call_terminal_live_smoke",
                tool_name="terminal_exec",
                arguments={
                    "argv": ["printf", "TERMINAL_LIVE_STDOUT_SHOULD_NOT_LEAK"],
                    "summary": "terminal tool live smoke",
                },
            ),
        )
    )

    result = llm_live_smoke.run_llm_terminal_tool_live_smoke(
        app,
        run_id,
        config=llm_live_smoke.LLMTerminalToolLiveSmokeConfig(enabled=True, max_tokens=64),
        provider=provider,
    )

    assert result["status"] == "completed"
    assert result["reason_code"] == "llm_terminal_tool_live_smoke_completed"
    assert result["provider"] == "deepseek"
    assert result["model"] == "deepseek-v4-flash"
    assert result["tool_name"] == "terminal_exec"
    assert result["provider_tool_call_id"] == "call_terminal_live_smoke"
    assert result["tool_result_status"] == "completed"
    assert result["artifact_ref_present"] is True
    assert result["codex_call_count"] == 0
    assert [tool["name"] for tool in provider.calls[0]["tools"]] == ["terminal_exec"]
    assert provider.calls[0]["max_tokens"] == 64
    assert "approval.requested" not in _event_types(app, run_id)
    assert "run.completed" in _event_types(app, run_id)
    rendered = repr(result)
    assert "TERMINAL_LIVE_STDOUT_SHOULD_NOT_LEAK" not in rendered
    assert "codex_task" not in rendered
    assert "Codex" not in rendered


def test_llm_terminal_tool_smoke_cli_runs_fake_provider_without_codex(tmp_path, capsys):
    exit_code = llm_live_smoke.main(
        [
            "terminal-tool",
            "--fake-provider",
            "--json",
            "--root",
            str(tmp_path),
            "--max-tokens",
            "64",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["command"] == "llm_terminal_tool_live_smoke"
    assert payload["provider_call_count"] == 1
    assert payload["codex_call_count"] == 0
    assert payload["result"]["status"] == "completed"
    assert payload["result"]["reason_code"] == "llm_terminal_tool_live_smoke_completed"
    assert payload["result"]["tool_name"] == "terminal_exec"
    assert payload["result"]["tool_result_status"] == "completed"
    rendered = repr(payload)
    assert "TERMINAL_TOOL_CLI_FAKE_STDOUT_SHOULD_NOT_LEAK" not in rendered
    assert "codex_task" not in rendered


def test_llm_terminal_tool_smoke_cli_reports_missing_provider_without_side_effects(tmp_path, capsys):
    exit_code = llm_live_smoke.main(
        [
            "terminal-tool",
            "--json",
            "--root",
            str(tmp_path),
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert captured.err == ""
    assert payload == {
        "codex_call_count": 0,
        "command": "llm_terminal_tool_live_smoke",
        "provider_call_count": 0,
        "result": {
            "provider": "auto",
            "reason_code": "llm_provider_not_configured",
            "status": "missing_configuration",
            "tool_name": "terminal_exec",
        },
    }
    assert not (tmp_path / "runs").exists()


def test_llm_terminal_tool_diagnosis_reports_ready_without_leaks(tmp_path):
    app = create_http_app(tmp_path)
    run_id = _create_run(app)
    provider = RecordingToolProvider(
        LLMToolCallResponse(
            provider="deepseek",
            model="deepseek-v4-flash",
            finish_reason="tool_calls",
            usage={"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
            tool_call=LLMToolCall(
                call_id="call_terminal_diag_ready",
                tool_name="terminal_exec",
                arguments={
                    "argv": ["printf", "TERMINAL_DIAG_STDOUT_SHOULD_NOT_LEAK"],
                    "summary": "terminal tool diagnosis",
                },
            ),
        )
    )

    result = llm_live_smoke.diagnose_llm_terminal_tool_live_smoke(
        app,
        run_id,
        config=llm_live_smoke.LLMTerminalToolLiveSmokeConfig(enabled=True, max_tokens=64),
        provider=provider,
    )

    assert result["status"] == "completed"
    assert result["tool_name"] == "terminal_exec"
    assert result["tool_result_status"] == "completed"
    assert result["diagnosis"] == {
        "category": "ready",
        "provider_request_started": True,
        "terminal_tool_selected": True,
        "terminal_executed": True,
        "terminal_completed": True,
        "codex_started": False,
        "summary": "provider selected terminal_exec and Isotope completed the terminal action",
        "next_step": "use this as a dev-only preflight before application-layer terminal wiring",
    }
    assert result["preflight"] == {
        "ready": True,
        "gate": "passed",
        "category": "ready",
        "status": "completed",
        "reason_code": "llm_terminal_tool_live_smoke_completed",
        "summary": "provider selected terminal_exec and Isotope completed the terminal action",
        "next_step": "use this as a dev-only preflight before application-layer terminal wiring",
    }
    rendered = repr(result)
    assert "TERMINAL_DIAG_STDOUT_SHOULD_NOT_LEAK" not in rendered
    assert "codex_task" not in rendered


def test_llm_terminal_tool_smoke_cli_can_print_diagnosis(tmp_path, capsys):
    exit_code = llm_live_smoke.main(
        [
            "terminal-tool",
            "--fake-provider",
            "--diagnose",
            "--json",
            "--root",
            str(tmp_path),
            "--max-tokens",
            "64",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["command"] == "llm_terminal_tool_live_smoke"
    assert payload["provider_call_count"] == 1
    assert payload["codex_call_count"] == 0
    assert payload["result"]["status"] == "completed"
    assert payload["result"]["diagnosis"]["category"] == "ready"
    assert payload["result"]["preflight"]["ready"] is True
    assert "TERMINAL_TOOL_CLI_FAKE_STDOUT_SHOULD_NOT_LEAK" not in repr(payload)


def test_llm_terminal_tool_smoke_cli_diagnoses_missing_provider_without_side_effects(tmp_path, capsys):
    exit_code = llm_live_smoke.main(
        [
            "terminal-tool",
            "--diagnose",
            "--json",
            "--root",
            str(tmp_path),
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert captured.err == ""
    assert payload == {
        "codex_call_count": 0,
        "command": "llm_terminal_tool_live_smoke",
        "provider_call_count": 0,
        "result": {
            "diagnosis": {
                "category": "missing_configuration",
                "codex_started": False,
                "next_step": "configure ISOTOPE_LLM_PROVIDER and provider credentials before running terminal-tool smoke",
                "provider_request_started": False,
                "summary": "LLM provider is not configured",
                "terminal_completed": False,
                "terminal_executed": False,
                "terminal_tool_selected": False,
            },
            "preflight": {
                "category": "missing_configuration",
                "gate": "blocked",
                "next_step": "configure ISOTOPE_LLM_PROVIDER and provider credentials before running terminal-tool smoke",
                "ready": False,
                "reason_code": "llm_provider_not_configured",
                "status": "missing_configuration",
                "summary": "LLM provider is not configured",
            },
            "provider": "auto",
            "reason_code": "llm_provider_not_configured",
            "status": "missing_configuration",
            "tool_name": "terminal_exec",
        },
    }
    assert not (tmp_path / "runs").exists()


def test_llm_terminal_tool_diagnosis_reports_unoffered_tool_without_action_side_effects(tmp_path):
    app = create_http_app(tmp_path)
    run_id = _create_run(app)
    provider = RecordingToolProvider(_provider_response(call_id="call_terminal_diag_codex"))

    result = llm_live_smoke.diagnose_llm_terminal_tool_live_smoke(
        app,
        run_id,
        config=llm_live_smoke.LLMTerminalToolLiveSmokeConfig(enabled=True),
        provider=provider,
    )

    assert result["status"] == "failed"
    assert result["reason_code"] == "llm_provider_selected_unoffered_tool"
    assert result["diagnosis"]["category"] == "provider_selected_unoffered_tool"
    assert result["diagnosis"]["provider_request_started"] is True
    assert result["diagnosis"]["terminal_tool_selected"] is False
    assert result["diagnosis"]["terminal_executed"] is False
    assert result["preflight"]["ready"] is False
    assert "action.started" not in _event_types(app, run_id)
    assert "codex_task" not in repr(result)


def test_llm_terminal_tool_diagnosis_reports_invalid_terminal_arguments_without_action_side_effects(tmp_path):
    app = create_http_app(tmp_path)
    run_id = _create_run(app)
    provider = RecordingToolProvider(
        LLMToolCallResponse(
            provider="deepseek",
            model="deepseek-v4-flash",
            finish_reason="tool_calls",
            usage={"total_tokens": 11},
            tool_call=LLMToolCall(
                call_id="call_terminal_diag_invalid_argv",
                tool_name="terminal_exec",
                arguments={"argv": ["/bin/echo", "nope"], "summary": "invalid argv"},
            ),
        )
    )

    result = llm_live_smoke.diagnose_llm_terminal_tool_live_smoke(
        app,
        run_id,
        config=llm_live_smoke.LLMTerminalToolLiveSmokeConfig(enabled=True),
        provider=provider,
    )

    assert result["status"] == "failed"
    assert result["reason_code"] == "invalid_model_tool_call"
    assert result["diagnosis"]["category"] == "provider_tool_arguments_invalid"
    assert result["diagnosis"]["terminal_tool_selected"] is True
    assert result["diagnosis"]["terminal_executed"] is False
    assert result["preflight"]["ready"] is False
    assert "action.started" not in _event_types(app, run_id)
    assert "/bin/echo" not in repr(result)


def test_llm_terminal_tool_diagnosis_reports_pending_approval_without_execution(tmp_path):
    app = create_http_app(tmp_path)
    run_id = _create_run(app)
    provider = RecordingToolProvider(
        LLMToolCallResponse(
            provider="deepseek",
            model="deepseek-v4-flash",
            finish_reason="tool_calls",
            usage={"total_tokens": 11},
            tool_call=LLMToolCall(
                call_id="call_terminal_diag_policy_denied",
                tool_name="terminal_exec",
                arguments={
                    "argv": ["bash", "-lc", "PENDING_APPROVAL_STDOUT_SHOULD_NOT_LEAK"],
                    "summary": "terminal approval request",
                },
            ),
        )
    )

    result = llm_live_smoke.diagnose_llm_terminal_tool_live_smoke(
        app,
        run_id,
        config=llm_live_smoke.LLMTerminalToolLiveSmokeConfig(enabled=True),
        provider=provider,
    )

    assert result["status"] == "completed"
    assert result["tool_result_status"] == "pending_user_approval"
    assert result["diagnosis"]["category"] == "terminal_approval_required"
    assert result["diagnosis"]["terminal_tool_selected"] is True
    assert result["diagnosis"]["terminal_executed"] is False
    assert result["preflight"]["ready"] is False
    assert "action.started" not in _event_types(app, run_id)
    assert "approval.requested" in _event_types(app, run_id)
    assert "PENDING_APPROVAL_STDOUT_SHOULD_NOT_LEAK" not in repr(result)


def test_llm_terminal_tool_diagnosis_reports_terminal_execution_failure_without_output_leak(tmp_path):
    app = create_http_app(tmp_path)
    run_id = _create_run(app)
    provider = RecordingToolProvider(
        LLMToolCallResponse(
            provider="deepseek",
            model="deepseek-v4-flash",
            finish_reason="tool_calls",
            usage={"total_tokens": 11},
            tool_call=LLMToolCall(
                call_id="call_terminal_diag_failed_command",
                tool_name="terminal_exec",
                arguments={"argv": ["false"], "summary": "terminal failure"},
            ),
        )
    )

    result = llm_live_smoke.diagnose_llm_terminal_tool_live_smoke(
        app,
        run_id,
        config=llm_live_smoke.LLMTerminalToolLiveSmokeConfig(enabled=True),
        provider=provider,
    )

    assert result["status"] == "completed"
    assert result["tool_result_status"] == "failed"
    assert result["terminal_error_reason_code"] == "terminal_exit_nonzero"
    assert result["diagnosis"]["category"] == "terminal_execution_failed"
    assert result["diagnosis"]["terminal_tool_selected"] is True
    assert result["diagnosis"]["terminal_executed"] is True
    assert result["diagnosis"]["terminal_completed"] is False
    assert result["preflight"]["ready"] is False
    assert "action.started" in _event_types(app, run_id)
    assert "action.failed" in _event_types(app, run_id)
    assert "stdout" not in repr(result).lower()


def test_llm_product_chat_live_smoke_is_skipped_by_default_without_side_effects(tmp_path):
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
    provider = SequencedChatProvider([])
    app = _product_chat_http_app(tmp_path, runner, provider)
    before_sessions = list(app.server._sessions)

    result = llm_live_smoke.run_llm_product_chat_live_smoke(app)

    assert result == {
        "status": "skipped",
        "reason_code": "llm_product_chat_live_smoke_not_enabled",
        "provider": "auto",
        "case_count": 0,
        "cases": [],
    }
    assert list(app.server._sessions) == before_sessions
    assert provider.calls == []
    assert runner.calls == []


def test_llm_product_chat_live_smoke_covers_final_tool_pause_and_resume_without_leaks(tmp_path):
    runner = RecordingProcessRunner(
        FakeCompletedProcess(stdout='{"event":"task_complete","secret":"PRODUCT_SMOKE_STDOUT_SHOULD_NOT_LEAK"}\n')
    )
    provider = SequencedChatProvider(
        [
            _final_answer_response("Direct product smoke answer."),
            _provider_response(
                "PRODUCT_SMOKE_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_product_smoke_tool",
                summary="product chat smoke tool call",
            ),
            _final_answer_response("Final product smoke answer."),
        ]
    )
    app = _product_chat_http_app(tmp_path, runner, provider)

    result = llm_live_smoke.run_llm_product_chat_live_smoke(
        app,
        config=llm_live_smoke.LLMProductChatLiveSmokeConfig(enabled=True, max_tokens=64),
    )

    assert result["status"] == "completed"
    assert result["reason_code"] == "llm_product_chat_live_smoke_completed"
    assert result["provider"] == "deepseek"
    assert result["model"] == "deepseek-v4-flash"
    assert result["case_count"] == 4
    assert result["cases"] == [
        {
            "case": "direct_final_answer",
            "http_status": 200,
            "status": "completed",
            "provider_status": "final_answer",
            "turn_kind": "initial",
            "artifact_ref_present": True,
            "assistant_message_present": True,
            "run_state_status": "completed",
        },
        {
            "case": "tool_choice_pending_approval",
            "http_status": 202,
            "status": "pending_user_approval",
            "provider_status": "tool_call_selected",
            "turn_kind": "initial",
            "tool_name": "codex_task",
            "requires_approval": True,
            "approval_id_present": True,
            "run_state_status": "pending_user_approval",
        },
        {
            "case": "approval_resolution",
            "http_status": 200,
            "status": "running",
            "artifact_ref_present": True,
            "run_state_status": "running",
        },
        {
            "case": "resume_final_answer",
            "http_status": 200,
            "status": "completed",
            "provider_status": "final_answer",
            "turn_kind": "tool_result_followup",
            "assistant_message_present": True,
            "tool_result_artifact_ref_present": True,
            "run_state_status": "completed",
        },
    ]
    assert len(provider.calls) == 3
    assert all(call["max_tokens"] == 64 for call in provider.calls)
    assert len(runner.calls) == 1
    rendered = repr(result)
    assert "PRODUCT_SMOKE_TOOL_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "PRODUCT_SMOKE_STDOUT_SHOULD_NOT_LEAK" not in rendered
    assert "ISOTOPE_LLM_PRODUCT_CHAT_SMOKE" not in rendered


def test_llm_product_chat_diagnosis_reports_ready_without_leaks(tmp_path):
    runner = RecordingProcessRunner(
        FakeCompletedProcess(stdout='{"event":"task_complete","secret":"PRODUCT_DIAG_STDOUT_SHOULD_NOT_LEAK"}\n')
    )
    provider = SequencedChatProvider(
        [
            _final_answer_response("Direct product diagnostic answer."),
            _provider_response(
                "PRODUCT_DIAG_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_product_diag_tool",
                summary="product chat diagnostic tool call",
            ),
            _final_answer_response("Final product diagnostic answer."),
        ]
    )
    app = _product_chat_http_app(tmp_path, runner, provider)

    result = llm_live_smoke.diagnose_llm_product_chat_live_smoke(
        app,
        config=llm_live_smoke.LLMProductChatLiveSmokeConfig(enabled=True, max_tokens=64),
    )

    assert result["status"] == "completed"
    assert result["diagnosis"] == {
        "category": "ready",
        "provider_request_started": True,
        "direct_answer_completed": True,
        "approval_requested": True,
        "approval_resolved": True,
        "resume_completed": True,
        "summary": "product-chat smoke completed direct answer, approval pause, and resume final answer",
        "next_step": "use this as a dev-only preflight before application-layer product chat wiring",
    }
    assert result["preflight"] == {
        "ready": True,
        "gate": "passed",
        "category": "ready",
        "status": "completed",
        "reason_code": "llm_product_chat_live_smoke_completed",
        "summary": "product-chat smoke completed direct answer, approval pause, and resume final answer",
        "next_step": "use this as a dev-only preflight before application-layer product chat wiring",
    }
    assert len(provider.calls) == 3
    assert len(runner.calls) == 1
    rendered = repr(result)
    assert "PRODUCT_DIAG_TOOL_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "PRODUCT_DIAG_STDOUT_SHOULD_NOT_LEAK" not in rendered


def test_llm_product_chat_smoke_cli_runs_fake_provider_without_network(tmp_path, capsys):
    exit_code = llm_live_smoke.main(
        [
            "product-chat",
            "--fake-provider",
            "--json",
            "--root",
            str(tmp_path),
            "--max-tokens",
            "64",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["command"] == "llm_product_chat_live_smoke"
    assert payload["codex_runner"] == "fake"
    assert payload["runner_call_count"] == 1
    assert payload["result"]["status"] == "completed"
    assert payload["result"]["reason_code"] == "llm_product_chat_live_smoke_completed"
    assert payload["result"]["provider"] == "deepseek"
    assert payload["result"]["case_count"] == 4
    assert [case["case"] for case in payload["result"]["cases"]] == [
        "direct_final_answer",
        "tool_choice_pending_approval",
        "approval_resolution",
        "resume_final_answer",
    ]
    rendered = repr(payload)
    assert "PRODUCT_CHAT_CLI_FAKE_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "PRODUCT_CHAT_CLI_FAKE_STDOUT_SHOULD_NOT_LEAK" not in rendered


def test_llm_product_chat_smoke_cli_fake_provider_does_not_require_codex_executable(
    tmp_path,
    capsys,
):
    exit_code = llm_live_smoke.main(
        [
            "product-chat",
            "--fake-provider",
            "--json",
            "--root",
            str(tmp_path),
            "--codex-executable",
            "__missing_codex_for_fake_product_chat__",
            "--max-tokens",
            "64",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["result"]["status"] == "completed"
    assert payload["runner_call_count"] == 1


def test_llm_product_chat_smoke_cli_can_print_diagnosis(tmp_path, capsys):
    exit_code = llm_live_smoke.main(
        [
            "product-chat",
            "--fake-provider",
            "--diagnose",
            "--json",
            "--root",
            str(tmp_path),
            "--max-tokens",
            "64",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["result"]["status"] == "completed"
    assert payload["result"]["diagnosis"]["category"] == "ready"
    assert payload["result"]["preflight"]["ready"] is True
    assert payload["result"]["diagnosis"]["approval_resolved"] is True
    assert payload["runner_call_count"] == 1


def test_llm_product_chat_smoke_cli_reports_missing_provider_without_side_effects(tmp_path, capsys):
    exit_code = llm_live_smoke.main(
        [
            "product-chat",
            "--json",
            "--root",
            str(tmp_path),
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert captured.err == ""
    assert payload == {
        "codex_runner": "fake",
        "command": "llm_product_chat_live_smoke",
        "result": {
            "case_count": 0,
            "cases": [],
            "provider": "auto",
            "reason_code": "llm_provider_not_configured",
            "status": "missing_configuration",
        },
        "runner_call_count": 0,
    }
    assert not (tmp_path / "runs").exists()


def test_llm_product_chat_smoke_cli_missing_provider_does_not_require_codex_executable(
    tmp_path,
    capsys,
):
    exit_code = llm_live_smoke.main(
        [
            "product-chat",
            "--json",
            "--root",
            str(tmp_path),
            "--codex-executable",
            "__missing_codex_for_missing_product_chat__",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert captured.err == ""
    assert payload["result"]["status"] == "missing_configuration"
    assert payload["runner_call_count"] == 0
    assert not (tmp_path / "runs").exists()


def test_llm_product_chat_smoke_cli_diagnoses_missing_provider_without_side_effects(tmp_path, capsys):
    exit_code = llm_live_smoke.main(
        [
            "product-chat",
            "--diagnose",
            "--json",
            "--root",
            str(tmp_path),
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert captured.err == ""
    assert payload == {
        "codex_runner": "fake",
        "command": "llm_product_chat_live_smoke",
        "result": {
            "case_count": 0,
            "cases": [],
            "diagnosis": {
                "approval_requested": False,
                "approval_resolved": False,
                "category": "missing_configuration",
                "direct_answer_completed": False,
                "next_step": "configure ISOTOPE_LLM_PROVIDER and provider credentials before running product-chat smoke",
                "provider_request_started": False,
                "resume_completed": False,
                "summary": "LLM provider is not configured",
            },
            "preflight": {
                "category": "missing_configuration",
                "gate": "blocked",
                "next_step": "configure ISOTOPE_LLM_PROVIDER and provider credentials before running product-chat smoke",
                "ready": False,
                "reason_code": "llm_provider_not_configured",
                "status": "missing_configuration",
                "summary": "LLM provider is not configured",
            },
            "provider": "auto",
            "reason_code": "llm_provider_not_configured",
            "status": "missing_configuration",
        },
        "runner_call_count": 0,
    }
    assert not (tmp_path / "runs").exists()


def test_llm_product_chat_entry_cli_rejects_empty_message_without_preflight_side_effects(
    tmp_path,
    capsys,
):
    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--message",
            "   ",
            "--json",
            "--root",
            str(tmp_path),
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert captured.err == ""
    assert payload == {
        "codex_runner": "fake",
        "command": "llm_product_chat_app_entry",
        "entry": {
            "error_code": "invalid_request",
            "http_status": 400,
            "reason_code": "llm_product_chat_user_message_required",
            "status": "bad_request",
        },
        "preflight": {
            "category": "invalid_request",
            "gate": "blocked",
            "next_step": "pass a non-empty --message value",
            "ready": False,
            "reason_code": "llm_product_chat_user_message_required",
            "status": "bad_request",
            "summary": "user message is required",
        },
        "runner_call_count": 0,
    }
    assert not (tmp_path / "runs").exists()


def test_llm_product_chat_entry_cli_blocks_when_preflight_is_not_ready_without_side_effects(
    tmp_path,
    capsys,
):
    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--message",
            "ENTRY_CLI_BLOCKED_MESSAGE_SHOULD_NOT_LEAK",
            "--json",
            "--root",
            str(tmp_path),
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert captured.err == ""
    assert payload["command"] == "llm_product_chat_app_entry"
    assert payload["codex_runner"] == "fake"
    assert payload["runner_call_count"] == 0
    assert payload["preflight"]["ready"] is False
    assert payload["preflight"]["category"] == "missing_configuration"
    assert payload["entry"] == {
        "explanation": {
            "next_step": "configure ISOTOPE_LLM_PROVIDER and provider credentials before running product-chat smoke",
            "summary": "LLM provider is not configured",
        },
        "http_status": 412,
        "preflight_category": "missing_configuration",
        "reason_code": "llm_product_chat_preflight_blocked",
        "status": "blocked_by_preflight",
    }
    assert "ENTRY_CLI_BLOCKED_MESSAGE_SHOULD_NOT_LEAK" not in repr(payload)
    assert not (tmp_path / "runs").exists()


def test_llm_product_chat_entry_cli_runs_fake_provider_after_ready_preflight(
    tmp_path,
    capsys,
):
    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--message",
            "ENTRY_CLI_READY_MESSAGE_SHOULD_NOT_LEAK",
            "--json",
            "--root",
            str(tmp_path),
            "--max-tokens",
            "64",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["command"] == "llm_product_chat_app_entry"
    assert payload["codex_runner"] == "fake"
    assert payload["runner_call_count"] == 1
    assert payload["preflight"]["ready"] is True
    assert payload["preflight"]["category"] == "ready"
    assert payload["entry"] == {
        "artifact_ref_present": True,
        "assistant_message_present": True,
        "http_status": 200,
        "provider": "deepseek",
        "provider_status": "final_answer",
        "requires_approval": False,
        "run_state_status": "completed",
        "status": "completed",
        "turn_kind": "initial",
    }
    rendered = repr(payload)
    assert "ENTRY_CLI_READY_MESSAGE_SHOULD_NOT_LEAK" not in rendered
    assert "PRODUCT_CHAT_ENTRY_CLI_FINAL_ANSWER_SHOULD_NOT_LEAK" not in rendered
    assert "PRODUCT_CHAT_CLI_FAKE_STDOUT_SHOULD_NOT_LEAK" not in rendered


def test_llm_product_chat_entry_cli_fake_provider_does_not_require_codex_executable(
    tmp_path,
    capsys,
):
    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--message",
            "ENTRY_CLI_MISSING_CODEX_MESSAGE_SHOULD_NOT_LEAK",
            "--json",
            "--root",
            str(tmp_path),
            "--codex-executable",
            "__missing_codex_for_fake_product_chat_entry__",
            "--max-tokens",
            "64",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["preflight"]["ready"] is True
    assert payload["entry"]["status"] == "completed"
    assert payload["runner_call_count"] == 1
    assert "ENTRY_CLI_MISSING_CODEX_MESSAGE_SHOULD_NOT_LEAK" not in repr(payload)


def test_llm_product_chat_entry_cli_pending_json_reports_safe_approval_next_step(
    tmp_path,
    capsys,
    monkeypatch,
):
    provider = SequencedChatProvider(
        [
            _final_answer_response("ENTRY_CLI_PREFLIGHT_DIRECT_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_CLI_PREFLIGHT_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_cli_preflight",
                summary="entry cli preflight task",
            ),
            _final_answer_response("ENTRY_CLI_PREFLIGHT_RESUME_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_CLI_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_cli_pending",
                summary="entry cli pending task",
            ),
        ]
    )
    monkeypatch.setattr(llm_live_smoke, "_fake_product_chat_entry_provider", lambda: provider)

    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--message",
            "ENTRY_CLI_PENDING_MESSAGE_SHOULD_NOT_LEAK",
            "--json",
            "--root",
            str(tmp_path),
            "--max-tokens",
            "64",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["entry"] == {
        "approval_id_present": True,
        "http_status": 202,
        "next_step": "resolve the pending approval before expecting tool execution or a final answer",
        "provider": "deepseek",
        "provider_status": "tool_call_selected",
        "requires_approval": True,
        "run_state_status": "pending_user_approval",
        "status": "pending_user_approval",
        "tool_name": "codex_task",
        "turn_kind": "initial",
    }
    rendered = repr(payload)
    assert "ENTRY_CLI_PENDING_MESSAGE_SHOULD_NOT_LEAK" not in rendered
    assert "ENTRY_CLI_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK" not in rendered


def test_llm_product_chat_entry_cli_fake_entry_pending_flag_writes_resume_state(
    tmp_path,
    capsys,
):
    state_file = tmp_path / "entry-state.json"

    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--fake-entry-pending",
            "--message",
            "ENTRY_CLI_FLAG_PENDING_MESSAGE_SHOULD_NOT_LEAK",
            "--json",
            "--root",
            str(tmp_path),
            "--state-file",
            str(state_file),
            "--max-tokens",
            "64",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert captured.err == ""
    assert payload["entry"]["status"] == "pending_user_approval"
    assert payload["pending_state"] == {
        "next_step": "resume with product-chat-entry --resume-state using this saved state file",
        "resume_ready": True,
        "saved": True,
    }
    assert state["llm_result"]["approval_id"] == state["approval_id"]
    rendered = repr(payload) + repr(state)
    assert "ENTRY_CLI_FLAG_PENDING_MESSAGE_SHOULD_NOT_LEAK" not in rendered
    assert "PRODUCT_CHAT_ENTRY_CLI_PENDING_PROMPT_SHOULD_NOT_LEAK" not in rendered


def test_llm_product_chat_entry_cli_state_file_directory_reports_safe_save_error(
    tmp_path,
    capsys,
):
    state_dir = tmp_path / "entry-state-dir"
    state_dir.mkdir()

    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--fake-entry-pending",
            "--message",
            "ENTRY_CLI_STATE_SAVE_MESSAGE_SHOULD_NOT_LEAK",
            "--json",
            "--root",
            str(tmp_path),
            "--state-file",
            str(state_dir),
            "--max-tokens",
            "64",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert captured.err == ""
    assert payload == {
        "codex_runner": "fake",
        "command": "llm_product_chat_app_entry",
        "error": {
            "category": "validation",
            "code": "product_chat_entry_state_save_failed",
            "http_status": 400,
            "next_step": "choose a writable --state-file path and rerun product-chat-entry",
            "reason": "not_file",
            "retryable": False,
            "summary": "The local resume state could not be saved.",
        },
        "runner_call_count": 0,
        "status": "failed",
    }
    rendered = repr(payload)
    assert str(state_dir) not in rendered
    assert "ENTRY_CLI_STATE_SAVE_MESSAGE_SHOULD_NOT_LEAK" not in rendered


def test_llm_product_chat_entry_cli_state_file_unwritable_parent_reports_safe_save_error(
    tmp_path,
    capsys,
):
    blocked_parent = tmp_path / "blocked-parent"
    blocked_parent.mkdir()
    state_file = blocked_parent / "child" / "entry-state.json"
    os.chmod(blocked_parent, 0o500)
    try:
        exit_code = llm_live_smoke.main(
            [
                "product-chat-entry",
                "--fake-provider",
                "--fake-entry-pending",
                "--message",
                "ENTRY_CLI_STATE_SAVE_PARENT_MESSAGE_SHOULD_NOT_LEAK",
                "--json",
                "--root",
                str(tmp_path),
                "--state-file",
                str(state_file),
                "--max-tokens",
                "64",
            ],
            environ={},
        )
    finally:
        os.chmod(blocked_parent, 0o700)

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert captured.err == ""
    assert payload == {
        "codex_runner": "fake",
        "command": "llm_product_chat_app_entry",
        "error": {
            "category": "validation",
            "code": "product_chat_entry_state_save_failed",
            "http_status": 400,
            "next_step": "choose a writable --state-file path and rerun product-chat-entry",
            "reason": "unwritable",
            "retryable": False,
            "summary": "The local resume state could not be saved.",
        },
        "runner_call_count": 0,
        "status": "failed",
    }
    rendered = repr(payload)
    assert str(state_file) not in rendered
    assert "ENTRY_CLI_STATE_SAVE_PARENT_MESSAGE_SHOULD_NOT_LEAK" not in rendered


def test_llm_product_chat_entry_cli_state_file_parent_not_directory_reports_safe_save_error(
    tmp_path,
    capsys,
):
    blocked_parent = tmp_path / "blocked-parent"
    blocked_parent.write_text("not a directory", encoding="utf-8")
    state_file = blocked_parent / "entry-state.json"

    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--fake-entry-pending",
            "--message",
            "ENTRY_CLI_STATE_PARENT_FILE_MESSAGE_SHOULD_NOT_LEAK",
            "--json",
            "--root",
            str(tmp_path),
            "--state-file",
            str(state_file),
            "--max-tokens",
            "64",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert captured.err == ""
    assert payload == {
        "codex_runner": "fake",
        "command": "llm_product_chat_app_entry",
        "error": {
            "category": "validation",
            "code": "product_chat_entry_state_save_failed",
            "http_status": 400,
            "next_step": "choose a --state-file path whose parent is a directory, then rerun product-chat-entry",
            "reason": "parent_not_directory",
            "retryable": False,
            "summary": "The local resume state could not be saved.",
        },
        "runner_call_count": 0,
        "status": "failed",
    }
    rendered = repr(payload)
    assert str(state_file) not in rendered
    assert "ENTRY_CLI_STATE_PARENT_FILE_MESSAGE_SHOULD_NOT_LEAK" not in rendered


def test_llm_product_chat_entry_cli_fake_entry_pending_requires_fake_provider(
    tmp_path,
    capsys,
):
    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-entry-pending",
            "--message",
            "ENTRY_CLI_FLAG_REQUIRES_FAKE_PROVIDER_SHOULD_NOT_LEAK",
            "--json",
            "--root",
            str(tmp_path),
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert captured.err == ""
    assert payload == {
        "codex_runner": "fake",
        "command": "llm_product_chat_app_entry",
        "entry": {
            "error_code": "invalid_request",
            "http_status": 400,
            "reason_code": "llm_product_chat_fake_entry_pending_requires_fake_provider",
            "status": "bad_request",
        },
        "preflight": {
            "category": "invalid_request",
            "gate": "blocked",
            "next_step": "pass --fake-provider with --fake-entry-pending, or remove --fake-entry-pending",
            "ready": False,
            "reason_code": "llm_product_chat_fake_entry_pending_requires_fake_provider",
            "status": "bad_request",
            "summary": "--fake-entry-pending only applies to the fake provider",
        },
        "runner_call_count": 0,
    }
    assert "ENTRY_CLI_FLAG_REQUIRES_FAKE_PROVIDER_SHOULD_NOT_LEAK" not in repr(payload)


def test_llm_product_chat_entry_cli_root_file_reports_safe_error_without_preflight_side_effects(
    tmp_path,
    capsys,
):
    root_file = tmp_path / "not-a-root-dir"
    root_file.write_text("ROOT_FILE_CONTENT_SHOULD_NOT_LEAK", encoding="utf-8")

    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--message",
            "ENTRY_ROOT_FILE_MESSAGE_SHOULD_NOT_LEAK",
            "--json",
            "--root",
            str(root_file),
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert captured.err == ""
    assert payload == {
        "codex_runner": "fake",
        "command": "llm_product_chat_app_entry",
        "error": {
            "category": "validation",
            "code": "product_chat_entry_root_invalid",
            "http_status": 400,
            "next_step": "choose a command root that is a writable directory, then rerun product-chat-entry",
            "reason": "not_directory",
            "retryable": False,
            "summary": "The command root is not a usable directory.",
        },
        "runner_call_count": 0,
        "status": "failed",
    }
    rendered = repr(payload)
    assert str(root_file) not in rendered
    assert "ROOT_FILE_CONTENT_SHOULD_NOT_LEAK" not in rendered
    assert "ENTRY_ROOT_FILE_MESSAGE_SHOULD_NOT_LEAK" not in rendered


def test_llm_product_chat_entry_cli_resume_state_rejects_new_entry_flags_without_leaks(
    tmp_path,
    capsys,
):
    state_file = tmp_path / "entry-state.json"

    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--resume-state",
            str(state_file),
            "--message",
            "ENTRY_CLI_RESUME_CONFLICT_MESSAGE_SHOULD_NOT_LEAK",
            "--state-file",
            str(tmp_path / "other-state.json"),
            "--fake-entry-pending",
            "--json",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert captured.err == ""
    assert payload == {
        "codex_runner": "fake",
        "command": "llm_product_chat_app_entry_resume",
        "entry": {
            "error_code": "invalid_request",
            "http_status": 400,
            "reason_code": "llm_product_chat_resume_state_conflicting_flags",
            "status": "bad_request",
        },
        "preflight": {
            "category": "invalid_request",
            "gate": "blocked",
            "next_step": "use --resume-state by itself, or start a new product-chat-entry request",
            "ready": False,
            "reason_code": "llm_product_chat_resume_state_conflicting_flags",
            "status": "bad_request",
            "summary": "--resume-state cannot be combined with new-entry flags",
        },
        "runner_call_count": 0,
    }
    assert "ENTRY_CLI_RESUME_CONFLICT_MESSAGE_SHOULD_NOT_LEAK" not in repr(payload)


def test_llm_product_chat_entry_cli_pending_plain_output_reports_approval_next_step(
    tmp_path,
    capsys,
    monkeypatch,
):
    provider = SequencedChatProvider(
        [
            _final_answer_response("ENTRY_CLI_PLAIN_PREFLIGHT_DIRECT_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_CLI_PLAIN_PREFLIGHT_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_cli_plain_preflight",
                summary="entry cli plain preflight task",
            ),
            _final_answer_response("ENTRY_CLI_PLAIN_PREFLIGHT_RESUME_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_CLI_PLAIN_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_cli_plain_pending",
                summary="entry cli plain pending task",
            ),
        ]
    )
    monkeypatch.setattr(llm_live_smoke, "_fake_product_chat_entry_provider", lambda: provider)

    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--message",
            "ENTRY_CLI_PENDING_PLAIN_MESSAGE_SHOULD_NOT_LEAK",
            "--root",
            str(tmp_path),
            "--max-tokens",
            "64",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert "entry_status: pending_user_approval" in captured.out
    assert "entry_requires_approval: true" in captured.out
    assert "approval_id_present: true" in captured.out
    assert (
        "entry_next_step: resolve the pending approval before expecting tool execution or a final answer"
        in captured.out
    )
    assert (
        "pending_state_next_step: rerun product-chat-entry with --state-file to save a resumable pending state"
        in captured.out
    )
    assert "ENTRY_CLI_PENDING_PLAIN_MESSAGE_SHOULD_NOT_LEAK" not in captured.out
    assert "ENTRY_CLI_PLAIN_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK" not in captured.out


def test_llm_product_chat_entry_cli_pending_json_writes_resume_state_without_leaks(
    tmp_path,
    capsys,
    monkeypatch,
):
    provider = SequencedChatProvider(
        [
            _final_answer_response("ENTRY_STATE_PREFLIGHT_DIRECT_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_STATE_PREFLIGHT_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_state_preflight",
                summary="entry state preflight task",
            ),
            _final_answer_response("ENTRY_STATE_PREFLIGHT_RESUME_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_STATE_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_state_pending",
                summary="entry state pending task",
            ),
        ]
    )
    monkeypatch.setattr(llm_live_smoke, "_fake_product_chat_entry_provider", lambda: provider)
    state_file = tmp_path / "entry-state.json"

    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--message",
            "ENTRY_STATE_MESSAGE_SHOULD_NOT_LEAK",
            "--json",
            "--root",
            str(tmp_path),
            "--state-file",
            str(state_file),
            "--max-tokens",
            "64",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["pending_state"] == {
        "next_step": "resume with product-chat-entry --resume-state using this saved state file",
        "resume_ready": True,
        "saved": True,
    }
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["schema_version"] == "product_chat_entry_state_v1"
    assert state["root"] == str(tmp_path)
    assert state["run_id"].startswith("run_")
    assert state["approval_id"].startswith("approval_")
    assert state["llm_result"]["approval_id"] == state["approval_id"]
    assert state["preflight"]["ready"] is True
    rendered_payload = repr(payload)
    rendered_state = repr(state)
    assert state["approval_id"] not in rendered_payload
    assert "ENTRY_STATE_MESSAGE_SHOULD_NOT_LEAK" not in rendered_payload
    assert "ENTRY_STATE_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK" not in rendered_payload
    assert "ENTRY_STATE_MESSAGE_SHOULD_NOT_LEAK" not in rendered_state
    assert "ENTRY_STATE_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK" not in rendered_state


def test_llm_product_chat_entry_cli_resume_state_approves_and_returns_final_answer_without_leaks(
    tmp_path,
    capsys,
    monkeypatch,
):
    first_provider = SequencedChatProvider(
        [
            _final_answer_response("ENTRY_RESUME_PREFLIGHT_DIRECT_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_RESUME_PREFLIGHT_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_resume_preflight",
                summary="entry resume preflight task",
            ),
            _final_answer_response("ENTRY_RESUME_PREFLIGHT_RESUME_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_RESUME_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_resume_pending",
                summary="entry resume pending task",
            ),
        ]
    )
    monkeypatch.setattr(llm_live_smoke, "_fake_product_chat_entry_provider", lambda: first_provider)
    state_file = tmp_path / "entry-resume-state.json"
    first_exit = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--message",
            "ENTRY_RESUME_MESSAGE_SHOULD_NOT_LEAK",
            "--json",
            "--root",
            str(tmp_path),
            "--state-file",
            str(state_file),
            "--max-tokens",
            "64",
        ],
        environ={},
    )
    first_output = capsys.readouterr()
    first_payload = json.loads(first_output.out)
    approval_id = json.loads(state_file.read_text(encoding="utf-8"))["approval_id"]
    assert first_exit == 0
    assert first_payload["entry"]["status"] == "pending_user_approval"

    resume_provider = SequencedChatProvider(
        [_final_answer_response("ENTRY_RESUME_FINAL_ANSWER_SHOULD_NOT_LEAK")]
    )
    monkeypatch.setattr(llm_live_smoke, "_fake_product_chat_entry_provider", lambda: resume_provider)

    resume_exit = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--resume-state",
            str(state_file),
            "--json",
            "--max-tokens",
            "64",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert resume_exit == 0
    assert captured.err == ""
    assert payload["command"] == "llm_product_chat_app_entry_resume"
    assert payload["approval"] == {
        "artifact_ref_present": True,
        "status": "running",
        "tool_execution_status": "completed",
    }
    assert payload["entry"] == {
        "artifact_ref_present": True,
        "assistant_message_present": True,
        "http_status": 200,
        "previous_provider_tool_call_id": "call_entry_resume_pending",
        "provider": "deepseek",
        "provider_status": "final_answer",
        "requires_approval": False,
        "run_state_status": "completed",
        "status": "completed",
        "tool_result_artifact_ref_present": True,
        "tool_result_status": "completed",
        "turn_kind": "tool_result_followup",
    }
    updated_state = json.loads(state_file.read_text(encoding="utf-8"))
    assert updated_state["resume"]["status"] == "completed"
    assert updated_state["resume"]["approval_resolved"] is True
    rendered = repr(payload)
    assert approval_id not in rendered
    assert "ENTRY_RESUME_MESSAGE_SHOULD_NOT_LEAK" not in rendered
    assert "ENTRY_RESUME_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "ENTRY_RESUME_FINAL_ANSWER_SHOULD_NOT_LEAK" not in rendered


def test_llm_product_chat_entry_cli_resume_state_reports_already_resolved_approval(
    tmp_path,
    capsys,
    monkeypatch,
):
    state_file = tmp_path / "entry-approval-resolved-state.json"
    first_exit = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--fake-entry-pending",
            "--message",
            "ENTRY_APPROVAL_RESOLVED_MESSAGE_SHOULD_NOT_LEAK",
            "--json",
            "--root",
            str(tmp_path),
            "--state-file",
            str(state_file),
            "--max-tokens",
            "64",
        ],
        environ={},
    )
    capsys.readouterr()
    assert first_exit == 0

    monkeypatch.setattr(
        llm_live_smoke,
        "_mark_product_chat_entry_state_resumed",
        lambda *args, **kwargs: None,
    )
    first_resume_exit = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--resume-state",
            str(state_file),
            "--json",
            "--max-tokens",
            "64",
        ],
        environ={},
    )
    capsys.readouterr()
    assert first_resume_exit == 0

    second_resume_exit = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--resume-state",
            str(state_file),
            "--json",
            "--max-tokens",
            "64",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert second_resume_exit == 2
    assert captured.err == ""
    assert payload == {
        "codex_runner": "fake",
        "command": "llm_product_chat_app_entry_resume",
        "error": {
            "category": "conflict",
            "code": "product_chat_entry_approval_already_resolved",
            "http_status": 409,
            "next_step": "inspect the completed run, or create a fresh pending state",
            "reason": "approval_already_resolved",
            "retryable": False,
            "summary": "The saved approval has already been resolved.",
        },
        "runner_call_count": 0,
        "status": "failed",
    }
    rendered = repr(payload)
    assert "ENTRY_APPROVAL_RESOLVED_MESSAGE_SHOULD_NOT_LEAK" not in rendered
    assert str(state_file) not in rendered


def test_llm_product_chat_entry_cli_resume_state_reports_unwritable_mark_without_path_leak(
    tmp_path,
    capsys,
):
    state_file = tmp_path / "entry-resume-readonly-state.json"
    first_exit = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--fake-entry-pending",
            "--message",
            "ENTRY_RESUME_MARK_MESSAGE_SHOULD_NOT_LEAK",
            "--json",
            "--root",
            str(tmp_path),
            "--state-file",
            str(state_file),
            "--max-tokens",
            "64",
        ],
        environ={},
    )
    capsys.readouterr()
    assert first_exit == 0

    os.chmod(state_file, 0o400)
    try:
        resume_exit = llm_live_smoke.main(
            [
                "product-chat-entry",
                "--fake-provider",
                "--resume-state",
                str(state_file),
                "--json",
                "--max-tokens",
                "64",
            ],
            environ={},
        )
    finally:
        os.chmod(state_file, 0o600)

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert resume_exit == 2
    assert captured.err == ""
    assert payload == {
        "codex_runner": "fake",
        "command": "llm_product_chat_app_entry_resume",
        "error": {
            "category": "validation",
            "code": "product_chat_entry_state_mark_failed",
            "http_status": 400,
            "next_step": "do not reuse this state file; inspect the completed run or create a fresh pending state",
            "reason": "unwritable",
            "retryable": False,
            "summary": "The resume completed, but the local state file could not be marked as used.",
        },
        "runner_call_count": 1,
        "status": "failed",
    }
    rendered = repr(payload)
    assert str(state_file) not in rendered
    assert "ENTRY_RESUME_MARK_MESSAGE_SHOULD_NOT_LEAK" not in rendered


def test_llm_product_chat_entry_cli_resume_state_rejects_wrong_root_without_path_leak(
    tmp_path,
    capsys,
):
    state_file = tmp_path / "entry-root-state.json"
    saved_root = tmp_path / "saved-root"
    wrong_root = tmp_path / "wrong-root"

    first_exit = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--fake-entry-pending",
            "--message",
            "ENTRY_ROOT_MISMATCH_MESSAGE_SHOULD_NOT_LEAK",
            "--json",
            "--root",
            str(saved_root),
            "--state-file",
            str(state_file),
            "--max-tokens",
            "64",
        ],
        environ={},
    )
    capsys.readouterr()
    assert first_exit == 0

    resume_exit = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--resume-state",
            str(state_file),
            "--root",
            str(wrong_root),
            "--json",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert resume_exit == 2
    assert captured.err == ""
    assert payload == {
        "codex_runner": "fake",
        "command": "llm_product_chat_app_entry_resume",
        "error": {
            "category": "validation",
            "code": "product_chat_entry_root_mismatch",
            "http_status": 400,
            "next_step": "omit --root or use the root recorded in the resume state",
            "reason": "root_mismatch",
            "retryable": False,
            "summary": "The provided root does not match the local resume state.",
        },
        "runner_call_count": 0,
        "status": "failed",
    }
    rendered = repr(payload)
    assert str(saved_root) not in rendered
    assert str(wrong_root) not in rendered
    assert "ENTRY_ROOT_MISMATCH_MESSAGE_SHOULD_NOT_LEAK" not in rendered


def test_llm_product_chat_entry_cli_resume_state_root_file_reports_safe_error(
    tmp_path,
    capsys,
):
    state_file = tmp_path / "entry-root-file-state.json"
    saved_root = tmp_path / "saved-root"

    first_exit = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--fake-entry-pending",
            "--message",
            "ENTRY_RESUME_ROOT_FILE_MESSAGE_SHOULD_NOT_LEAK",
            "--json",
            "--root",
            str(saved_root),
            "--state-file",
            str(state_file),
            "--max-tokens",
            "64",
        ],
        environ={},
    )
    capsys.readouterr()
    assert first_exit == 0
    shutil.rmtree(saved_root)
    saved_root.write_text("ROOT_FILE_CONTENT_SHOULD_NOT_LEAK", encoding="utf-8")

    resume_exit = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--resume-state",
            str(state_file),
            "--json",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert resume_exit == 2
    assert captured.err == ""
    assert payload == {
        "codex_runner": "fake",
        "command": "llm_product_chat_app_entry_resume",
        "error": {
            "category": "validation",
            "code": "product_chat_entry_root_invalid",
            "http_status": 400,
            "next_step": "choose a command root that is a writable directory, then rerun product-chat-entry",
            "reason": "not_directory",
            "retryable": False,
            "summary": "The command root is not a usable directory.",
        },
        "runner_call_count": 0,
        "status": "failed",
    }
    rendered = repr(payload)
    assert str(saved_root) not in rendered
    assert "ROOT_FILE_CONTENT_SHOULD_NOT_LEAK" not in rendered
    assert "ENTRY_RESUME_ROOT_FILE_MESSAGE_SHOULD_NOT_LEAK" not in rendered


def test_llm_product_chat_entry_cli_resume_state_reports_missing_file_without_path_leak(
    tmp_path,
    capsys,
):
    state_file = tmp_path / "missing-entry-state.json"

    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--resume-state",
            str(state_file),
            "--json",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert captured.err == ""
    assert payload == {
        "codex_runner": "fake",
        "command": "llm_product_chat_app_entry_resume",
        "error": {
            "category": "not_found",
            "code": "product_chat_entry_state_missing",
            "http_status": 404,
            "next_step": "check the --resume-state path, or create a fresh pending state with product-chat-entry --state-file",
            "reason": "missing",
            "retryable": False,
            "summary": "The local resume state file was not found.",
        },
        "runner_call_count": 0,
        "status": "failed",
    }
    assert str(state_file) not in repr(payload)


def test_llm_product_chat_entry_cli_resume_state_reports_malformed_json_without_leaks(
    tmp_path,
    capsys,
):
    state_file = tmp_path / "entry-malformed-state.json"
    state_file.write_text("ENTRY_MALFORMED_STATE_CONTENT_SHOULD_NOT_LEAK", encoding="utf-8")

    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--resume-state",
            str(state_file),
            "--json",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert captured.err == ""
    assert payload == {
        "codex_runner": "fake",
        "command": "llm_product_chat_app_entry_resume",
        "error": {
            "category": "validation",
            "code": "product_chat_entry_state_invalid",
            "http_status": 400,
            "next_step": "create a fresh pending state with product-chat-entry --state-file before resuming",
            "reason": "invalid",
            "retryable": False,
            "summary": "The local resume state file is invalid.",
        },
        "runner_call_count": 0,
        "status": "failed",
    }
    assert "ENTRY_MALFORMED_STATE_CONTENT_SHOULD_NOT_LEAK" not in repr(payload)


def test_llm_product_chat_entry_cli_resume_state_reports_directory_path_without_path_leak(
    tmp_path,
    capsys,
):
    state_dir = tmp_path / "entry-state-dir"
    state_dir.mkdir()

    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--resume-state",
            str(state_dir),
            "--json",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert captured.err == ""
    assert payload == {
        "codex_runner": "fake",
        "command": "llm_product_chat_app_entry_resume",
        "error": {
            "category": "validation",
            "code": "product_chat_entry_state_invalid",
            "http_status": 400,
            "next_step": "create a fresh pending state with product-chat-entry --state-file before resuming",
            "reason": "not_file",
            "retryable": False,
            "summary": "The local resume state file is invalid.",
        },
        "runner_call_count": 0,
        "status": "failed",
    }
    assert str(state_dir) not in repr(payload)


def test_llm_product_chat_entry_cli_resume_state_reports_unreadable_file_without_path_leak(
    tmp_path,
    capsys,
):
    state_file = tmp_path / "entry-unreadable-state.json"
    state_file.write_text("{}", encoding="utf-8")
    os.chmod(state_file, 0)
    try:
        exit_code = llm_live_smoke.main(
            [
                "product-chat-entry",
                "--fake-provider",
                "--resume-state",
                str(state_file),
                "--json",
            ],
            environ={},
        )
    finally:
        os.chmod(state_file, 0o600)

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert captured.err == ""
    assert payload == {
        "codex_runner": "fake",
        "command": "llm_product_chat_app_entry_resume",
        "error": {
            "category": "validation",
            "code": "product_chat_entry_state_invalid",
            "http_status": 400,
            "next_step": "create a fresh pending state with product-chat-entry --state-file before resuming",
            "reason": "unreadable",
            "retryable": False,
            "summary": "The local resume state file is invalid.",
        },
        "runner_call_count": 0,
        "status": "failed",
    }
    assert str(state_file) not in repr(payload)


def test_llm_product_chat_entry_cli_resume_state_reports_mismatched_state_json(
    tmp_path,
    capsys,
    monkeypatch,
):
    provider = SequencedChatProvider(
        [
            _final_answer_response("ENTRY_MISMATCH_PREFLIGHT_DIRECT_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_MISMATCH_PREFLIGHT_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_mismatch_preflight",
            ),
            _final_answer_response("ENTRY_MISMATCH_PREFLIGHT_RESUME_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_MISMATCH_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_mismatch_pending",
            ),
        ]
    )
    monkeypatch.setattr(llm_live_smoke, "_fake_product_chat_entry_provider", lambda: provider)
    state_file = tmp_path / "entry-mismatch-state.json"
    first_exit = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--message",
            "ENTRY_MISMATCH_MESSAGE_SHOULD_NOT_LEAK",
            "--json",
            "--root",
            str(tmp_path),
            "--state-file",
            str(state_file),
        ],
        environ={},
    )
    capsys.readouterr()
    assert first_exit == 0
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["approval_id"] = "approval_mismatch_should_not_leak"
    state_file.write_text(json.dumps(state), encoding="utf-8")

    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--resume-state",
            str(state_file),
            "--json",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert captured.err == ""
    assert payload == {
        "codex_runner": "fake",
        "command": "llm_product_chat_app_entry_resume",
        "error": {
            "category": "validation",
            "code": "product_chat_entry_state_invalid",
            "http_status": 400,
            "next_step": "create a fresh pending state with product-chat-entry --state-file before resuming",
            "reason": "llm_result_mismatch",
            "retryable": False,
            "summary": "The local resume state file is invalid.",
        },
        "runner_call_count": 0,
        "status": "failed",
    }
    rendered = repr(payload)
    assert "approval_mismatch_should_not_leak" not in rendered
    assert "ENTRY_MISMATCH_MESSAGE_SHOULD_NOT_LEAK" not in rendered
    assert "ENTRY_MISMATCH_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK" not in rendered


def test_llm_product_chat_entry_cli_resume_state_reports_already_resumed_json(
    tmp_path,
    capsys,
    monkeypatch,
):
    provider = SequencedChatProvider(
        [
            _final_answer_response("ENTRY_ALREADY_PREFLIGHT_DIRECT_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_ALREADY_PREFLIGHT_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_already_preflight",
            ),
            _final_answer_response("ENTRY_ALREADY_PREFLIGHT_RESUME_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_ALREADY_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_already_pending",
            ),
        ]
    )
    monkeypatch.setattr(llm_live_smoke, "_fake_product_chat_entry_provider", lambda: provider)
    state_file = tmp_path / "entry-already-state.json"
    first_exit = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--message",
            "ENTRY_ALREADY_MESSAGE_SHOULD_NOT_LEAK",
            "--json",
            "--root",
            str(tmp_path),
            "--state-file",
            str(state_file),
        ],
        environ={},
    )
    capsys.readouterr()
    assert first_exit == 0
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["resume"] = {"approval_resolved": True, "status": "completed"}
    state_file.write_text(json.dumps(state), encoding="utf-8")

    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--resume-state",
            str(state_file),
            "--json",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert captured.err == ""
    assert payload["status"] == "failed"
    assert payload["error"] == {
        "category": "conflict",
        "code": "product_chat_entry_state_already_resumed",
        "http_status": 409,
        "next_step": "start a new product-chat-entry request instead of reusing this state file",
        "reason": "completed",
        "retryable": False,
        "summary": "The local resume state has already been used.",
    }
    assert payload["runner_call_count"] == 0
    rendered = repr(payload)
    assert "ENTRY_ALREADY_MESSAGE_SHOULD_NOT_LEAK" not in rendered
    assert "ENTRY_ALREADY_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK" not in rendered


def test_llm_product_chat_entry_cli_resume_state_plain_reports_missing_approval_context(
    tmp_path,
    capsys,
    monkeypatch,
):
    provider = SequencedChatProvider(
        [
            _final_answer_response("ENTRY_MISSING_PREFLIGHT_DIRECT_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_MISSING_PREFLIGHT_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_missing_preflight",
            ),
            _final_answer_response("ENTRY_MISSING_PREFLIGHT_RESUME_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_MISSING_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_missing_pending",
            ),
        ]
    )
    monkeypatch.setattr(llm_live_smoke, "_fake_product_chat_entry_provider", lambda: provider)
    state_file = tmp_path / "entry-missing-state.json"
    first_exit = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--message",
            "ENTRY_MISSING_MESSAGE_SHOULD_NOT_LEAK",
            "--json",
            "--root",
            str(tmp_path / "source"),
            "--state-file",
            str(state_file),
        ],
        environ={},
    )
    capsys.readouterr()
    assert first_exit == 0
    shutil.rmtree(tmp_path / "source")

    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--resume-state",
            str(state_file),
        ],
        environ={},
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err == ""
    assert "command: llm_product_chat_app_entry_resume" in captured.out
    assert "status: failed" in captured.out
    assert "error_code: product_chat_entry_approval_unavailable" in captured.out
    assert "error_reason: unknown_approval" in captured.out
    assert "error_summary: The saved approval is not available in this command root." in captured.out
    assert (
        "error_next_step: use the original root/state file, or create a fresh pending state"
        in captured.out
    )
    assert "runner_call_count: 0" in captured.out
    assert "ENTRY_MISSING_MESSAGE_SHOULD_NOT_LEAK" not in captured.out
    assert "ENTRY_MISSING_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK" not in captured.out


def test_llm_product_chat_entry_cli_plain_output_is_low_sensitive(tmp_path, capsys):
    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--fake-provider",
            "--message",
            "ENTRY_CLI_PLAIN_MESSAGE_SHOULD_NOT_LEAK",
            "--root",
            str(tmp_path),
            "--max-tokens",
            "64",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert "command: llm_product_chat_app_entry" in captured.out
    assert "preflight_ready: true" in captured.out
    assert "entry_status: completed" in captured.out
    assert "assistant_message_present: true" in captured.out
    assert "ENTRY_CLI_PLAIN_MESSAGE_SHOULD_NOT_LEAK" not in captured.out
    assert "PRODUCT_CHAT_ENTRY_CLI_FINAL_ANSWER_SHOULD_NOT_LEAK" not in captured.out


def test_deepseek_tool_call_live_smoke_is_skipped_by_default(tmp_path):
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    result = llm_live_smoke.run_deepseek_tool_call_live_smoke(app, run_id)

    assert result == {
        "status": "skipped",
        "reason_code": "deepseek_tool_call_live_smoke_not_enabled",
        "provider": "deepseek",
        "tool_name": "codex_task",
    }
    assert _event_types(app, run_id) == before_events
    assert runner.calls == []


def test_deepseek_tool_call_live_smoke_reports_missing_key_without_side_effects(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
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


def test_deepseek_tool_call_live_smoke_submits_pending_approval_with_fake_provider(tmp_path):
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
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
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
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
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
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
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
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
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
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
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
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
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
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

    assert result["reason_code"] == "llm_tool_not_enabled"
    assert result["diagnosis"] == {
        "category": "tool_not_enabled",
        "provider_request_started": False,
        "approval_requested": False,
        "codex_started": False,
        "summary": "the requested tool is not enabled in the model-facing catalog",
        "next_step": "wire the intended tool explicitly or keep the smoke limited to codex_task",
    }
    assert provider.calls == []
    assert runner.calls == []


def test_deepseek_tool_call_diagnosis_reports_provider_selected_unoffered_tool(tmp_path):
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
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
        "category": "tool_not_enabled",
        "provider_request_started": True,
        "approval_requested": False,
        "codex_started": False,
        "summary": "the provider selected a tool that was not offered in this smoke",
        "next_step": "tighten the provider response or include the intended tool in the smoke config",
    }
    assert runner.calls == []


@pytest.mark.skipif(
    os.environ.get("ISOTOPE_RUN_LIVE_LLM_SMOKE") != "1"
    or llm_provider.resolve_llm_tool_call_provider().status != "configured",
    reason="live LLM provider smoke is opt-in and requires unified provider configuration",
)
def test_live_llm_tool_call_smoke_reaches_provider_without_starting_codex(tmp_path):
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)

    result = llm_live_smoke.run_llm_tool_call_live_smoke(
        app,
        run_id,
        config=llm_live_smoke.LLMToolCallLiveSmokeConfig(enabled=True, max_tokens=128),
    )

    assert result["status"] in {"completed", "failed", "missing_configuration"}
    assert "DEEPSEEK_API_KEY" not in repr(result)
    assert llm_live_smoke.DEFAULT_DEEPSEEK_LIVE_SMOKE_PROMPT not in repr(result)
    assert runner.calls == []
    if result["status"] == "completed":
        assert result["tool_name"] == "codex_task"
        assert result["tool_result_status"] == "pending_user_approval"
        assert "approval.requested" in _event_types(app, run_id)


@pytest.mark.skipif(
    os.environ.get("ISOTOPE_RUN_LIVE_LLM_TERMINAL_SMOKE") != "1"
    or llm_provider.resolve_llm_tool_call_provider().status != "configured",
    reason="live LLM terminal tool smoke is opt-in and requires unified provider configuration",
)
def test_live_llm_terminal_tool_smoke_reaches_provider_and_runs_terminal_only(tmp_path):
    app = create_http_app(tmp_path)
    run_id = _create_run(app)

    result = llm_live_smoke.run_llm_terminal_tool_live_smoke(
        app,
        run_id,
        config=llm_live_smoke.LLMTerminalToolLiveSmokeConfig(enabled=True, max_tokens=128),
    )

    assert result["status"] in {"completed", "failed", "missing_configuration"}
    assert "DEEPSEEK_API_KEY" not in repr(result)
    assert llm_live_smoke.DEFAULT_LLM_TERMINAL_TOOL_SMOKE_PROMPT not in repr(result)
    assert "codex_task" not in repr(result)
    if result["status"] == "completed":
        assert result["tool_name"] == "terminal_exec"
        assert result["tool_result_status"] == "completed"
        assert "approval.requested" not in _event_types(app, run_id)
        assert "run.completed" in _event_types(app, run_id)
