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



def test_llm_product_chat_live_smoke_is_skipped_by_default_without_side_effects(tmp_path):
    runner = RecordingProcessRunner(DeterministicCompletedProcess(stdout='{"event":"task_complete"}\n'))
    provider = SequencedChatProvider([])
    app = _product_chat_http_app(tmp_path, runner, provider)
    before_sessions = list(app.server._sessions)

    result = llm_live_smoke.run_llm_product_chat_live_smoke(app)

    assert result == {
        "status": "skipped",
        "reason_code": "llm_product_chat_live_smoke_unavailable",
        "provider": "auto",
        "case_count": 0,
        "cases": [],
    }
    assert list(app.server._sessions) == before_sessions
    assert provider.calls == []
    assert runner.calls == []



def test_llm_product_chat_live_smoke_covers_final_tool_pause_and_resume_without_leaks(tmp_path):
    runner = RecordingProcessRunner(
        DeterministicCompletedProcess(stdout='{"event":"task_complete","secret":"PRODUCT_SMOKE_STDOUT_SHOULD_NOT_LEAK"}\n')
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
        DeterministicCompletedProcess(stdout='{"event":"task_complete","secret":"PRODUCT_DIAG_STDOUT_SHOULD_NOT_LEAK"}\n')
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
        "next_step": "use this as a dev-only readiness_check before application-layer product chat wiring",
    }
    assert result["readiness_check"] == {
        "ready": True,
        "gate": "passed",
        "category": "ready",
        "status": "completed",
        "reason_code": "llm_product_chat_live_smoke_completed",
        "summary": "product-chat smoke completed direct answer, approval pause, and resume final answer",
        "next_step": "use this as a dev-only readiness_check before application-layer product chat wiring",
    }
    assert len(provider.calls) == 3
    assert len(runner.calls) == 1
    rendered = repr(result)
    assert "PRODUCT_DIAG_TOOL_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "PRODUCT_DIAG_STDOUT_SHOULD_NOT_LEAK" not in rendered



def test_llm_product_chat_smoke_cli_runs_deterministic_provider_without_network(tmp_path, capsys):
    exit_code = llm_live_smoke.main(
        [
            "product-chat",
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
    assert payload["command"] == "llm_product_chat_live_smoke"
    assert payload["codex_runner"] == "deterministic_test"
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
    assert "PRODUCT_CHAT_CLI_DETERMINISTIC_PROMPT_SHOULD_NOT_LEAK" not in rendered
    assert "PRODUCT_CHAT_CLI_DETERMINISTIC_STDOUT_SHOULD_NOT_LEAK" not in rendered



def test_llm_product_chat_smoke_cli_deterministic_provider_does_not_require_codex_executable(
    tmp_path,
    capsys,
):
    exit_code = llm_live_smoke.main(
        [
            "product-chat",
            "--deterministic-provider",
            "--json",
            "--root",
            str(tmp_path),
            "--codex-executable",
            "__missing_codex_for_deterministic_product_chat__",
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
    assert payload["result"]["status"] == "completed"
    assert payload["result"]["diagnosis"]["category"] == "ready"
    assert payload["result"]["readiness_check"]["ready"] is True
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
        "codex_runner": "deterministic_test",
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
        "codex_runner": "deterministic_test",
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
            "readiness_check": {
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
