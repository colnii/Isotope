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



def test_llm_terminal_tool_smoke_cli_runs_deterministic_provider_without_codex(tmp_path, capsys):
    exit_code = llm_live_smoke.main(
        [
            "terminal-tool",
            "--deterministic-provider",
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
    assert "TERMINAL_TOOL_CLI_DETERMINISTIC_STDOUT_SHOULD_NOT_LEAK" not in rendered
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
        "next_step": "use this as a dev-only readiness_check before application-layer terminal wiring",
    }
    assert result["readiness_check"] == {
        "ready": True,
        "gate": "passed",
        "category": "ready",
        "status": "completed",
        "reason_code": "llm_terminal_tool_live_smoke_completed",
        "summary": "provider selected terminal_exec and Isotope completed the terminal action",
        "next_step": "use this as a dev-only readiness_check before application-layer terminal wiring",
    }
    rendered = repr(result)
    assert "TERMINAL_DIAG_STDOUT_SHOULD_NOT_LEAK" not in rendered
    assert "codex_task" not in rendered



def test_llm_terminal_tool_smoke_cli_can_print_diagnosis(tmp_path, capsys):
    exit_code = llm_live_smoke.main(
        [
            "terminal-tool",
            "--deterministic-provider",
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
    assert payload["result"]["readiness_check"]["ready"] is True
    assert "TERMINAL_TOOL_CLI_DETERMINISTIC_STDOUT_SHOULD_NOT_LEAK" not in repr(payload)



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
            "readiness_check": {
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
    assert result["readiness_check"]["ready"] is False
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
    assert result["readiness_check"]["ready"] is False
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
    assert result["readiness_check"]["ready"] is False
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
    assert result["readiness_check"]["ready"] is False
    assert "action.started" in _event_types(app, run_id)
    assert "action.failed" in _event_types(app, run_id)
    assert "stdout" not in repr(result).lower()
