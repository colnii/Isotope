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



def test_llm_product_chat_entry_cli_rejects_empty_message_without_readiness_check_side_effects(
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
        "codex_runner": "deterministic_test",
        "command": "llm_product_chat_app_entry",
        "entry": {
            "error_code": "invalid_request",
            "http_status": 400,
            "reason_code": "llm_product_chat_user_message_required",
            "status": "bad_request",
        },
        "readiness_check": {
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



def test_llm_product_chat_entry_cli_blocks_when_readiness_check_is_not_ready_without_side_effects(
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
    assert payload["codex_runner"] == "deterministic_test"
    assert payload["runner_call_count"] == 0
    assert payload["readiness_check"]["ready"] is False
    assert payload["readiness_check"]["category"] == "missing_configuration"
    assert payload["entry"] == {
        "explanation": {
            "next_step": "configure ISOTOPE_LLM_PROVIDER and provider credentials before running product-chat smoke",
            "summary": "LLM provider is not configured",
        },
        "http_status": 412,
        "readiness_check_category": "missing_configuration",
        "reason_code": "llm_product_chat_readiness_check_blocked",
        "status": "blocked_by_readiness_check",
    }
    assert "ENTRY_CLI_BLOCKED_MESSAGE_SHOULD_NOT_LEAK" not in repr(payload)
    assert not (tmp_path / "runs").exists()



def test_llm_product_chat_entry_cli_runs_deterministic_provider_after_ready_readiness_check(
    tmp_path,
    capsys,
):
    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--deterministic-provider",
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
    assert payload["codex_runner"] == "deterministic_test"
    assert payload["runner_call_count"] == 1
    assert payload["readiness_check"]["ready"] is True
    assert payload["readiness_check"]["category"] == "ready"
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
    assert "PRODUCT_CHAT_CLI_DETERMINISTIC_STDOUT_SHOULD_NOT_LEAK" not in rendered



def test_llm_product_chat_entry_cli_deterministic_provider_does_not_require_codex_executable(
    tmp_path,
    capsys,
):
    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--deterministic-provider",
            "--message",
            "ENTRY_CLI_MISSING_CODEX_MESSAGE_SHOULD_NOT_LEAK",
            "--json",
            "--root",
            str(tmp_path),
            "--codex-executable",
            "__missing_codex_for_deterministic_product_chat_entry__",
            "--max-tokens",
            "64",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["readiness_check"]["ready"] is True
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
            _final_answer_response("ENTRY_CLI_READINESS_CHECK_DIRECT_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_CLI_READINESS_CHECK_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_cli_readiness_check",
                summary="entry cli readiness_check task",
            ),
            _final_answer_response("ENTRY_CLI_READINESS_CHECK_RESUME_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_CLI_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_cli_pending",
                summary="entry cli pending task",
            ),
        ]
    )
    monkeypatch.setattr(llm_live_smoke, "_deterministic_product_chat_entry_provider", lambda: provider)

    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--deterministic-provider",
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



def test_llm_product_chat_entry_cli_deterministic_entry_pending_flag_writes_resume_state(
    tmp_path,
    capsys,
):
    state_file = tmp_path / "entry-state.json"

    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--deterministic-provider",
            "--deterministic-entry-pending",
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
            "--deterministic-provider",
            "--deterministic-entry-pending",
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
        "codex_runner": "deterministic_test",
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
                "--deterministic-provider",
                "--deterministic-entry-pending",
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
        "codex_runner": "deterministic_test",
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
            "--deterministic-provider",
            "--deterministic-entry-pending",
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
        "codex_runner": "deterministic_test",
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



def test_llm_product_chat_entry_cli_deterministic_entry_pending_requires_deterministic_provider(
    tmp_path,
    capsys,
):
    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--deterministic-entry-pending",
            "--message",
            "ENTRY_CLI_FLAG_REQUIRES_DETERMINISTIC_PROVIDER_SHOULD_NOT_LEAK",
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
        "command": "llm_product_chat_app_entry",
        "entry": {
            "error_code": "invalid_request",
            "http_status": 400,
            "reason_code": "llm_product_chat_deterministic_entry_pending_requires_deterministic_provider",
            "status": "bad_request",
        },
        "readiness_check": {
            "category": "invalid_request",
            "gate": "blocked",
            "next_step": "pass --deterministic-provider with --deterministic-entry-pending, or remove --deterministic-entry-pending",
            "ready": False,
            "reason_code": "llm_product_chat_deterministic_entry_pending_requires_deterministic_provider",
            "status": "bad_request",
            "summary": "--deterministic-entry-pending only applies to the deterministic test provider",
        },
        "runner_call_count": 0,
    }
    assert "ENTRY_CLI_FLAG_REQUIRES_DETERMINISTIC_PROVIDER_SHOULD_NOT_LEAK" not in repr(payload)



def test_llm_product_chat_entry_cli_root_file_reports_safe_error_without_readiness_check_side_effects(
    tmp_path,
    capsys,
):
    root_file = tmp_path / "not-a-root-dir"
    root_file.write_text("ROOT_FILE_CONTENT_SHOULD_NOT_LEAK", encoding="utf-8")

    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--deterministic-provider",
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
        "codex_runner": "deterministic_test",
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
            "--deterministic-entry-pending",
            "--json",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert captured.err == ""
    assert payload == {
        "codex_runner": "deterministic_test",
        "command": "llm_product_chat_app_entry_resume",
        "entry": {
            "error_code": "invalid_request",
            "http_status": 400,
            "reason_code": "llm_product_chat_resume_state_conflicting_flags",
            "status": "bad_request",
        },
        "readiness_check": {
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
            _final_answer_response("ENTRY_CLI_PLAIN_READINESS_CHECK_DIRECT_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_CLI_PLAIN_READINESS_CHECK_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_cli_plain_readiness_check",
                summary="entry cli plain readiness_check task",
            ),
            _final_answer_response("ENTRY_CLI_PLAIN_READINESS_CHECK_RESUME_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_CLI_PLAIN_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_cli_plain_pending",
                summary="entry cli plain pending task",
            ),
        ]
    )
    monkeypatch.setattr(llm_live_smoke, "_deterministic_product_chat_entry_provider", lambda: provider)

    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--deterministic-provider",
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
            _final_answer_response("ENTRY_STATE_READINESS_CHECK_DIRECT_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_STATE_READINESS_CHECK_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_state_readiness_check",
                summary="entry state readiness_check task",
            ),
            _final_answer_response("ENTRY_STATE_READINESS_CHECK_RESUME_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_STATE_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_state_pending",
                summary="entry state pending task",
            ),
        ]
    )
    monkeypatch.setattr(llm_live_smoke, "_deterministic_product_chat_entry_provider", lambda: provider)
    state_file = tmp_path / "entry-state.json"

    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--deterministic-provider",
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
    assert state["readiness_check"]["ready"] is True
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
            _final_answer_response("ENTRY_RESUME_READINESS_CHECK_DIRECT_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_RESUME_READINESS_CHECK_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_resume_readiness_check",
                summary="entry resume readiness_check task",
            ),
            _final_answer_response("ENTRY_RESUME_READINESS_CHECK_RESUME_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_RESUME_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_resume_pending",
                summary="entry resume pending task",
            ),
        ]
    )
    monkeypatch.setattr(llm_live_smoke, "_deterministic_product_chat_entry_provider", lambda: first_provider)
    state_file = tmp_path / "entry-resume-state.json"
    first_exit = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--deterministic-provider",
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
    monkeypatch.setattr(llm_live_smoke, "_deterministic_product_chat_entry_provider", lambda: resume_provider)

    resume_exit = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--deterministic-provider",
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
            "--deterministic-provider",
            "--deterministic-entry-pending",
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
            "--deterministic-provider",
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
            "--deterministic-provider",
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
        "codex_runner": "deterministic_test",
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
            "--deterministic-provider",
            "--deterministic-entry-pending",
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
                "--deterministic-provider",
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
        "codex_runner": "deterministic_test",
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
            "--deterministic-provider",
            "--deterministic-entry-pending",
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
            "--deterministic-provider",
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
        "codex_runner": "deterministic_test",
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
            "--deterministic-provider",
            "--deterministic-entry-pending",
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
            "--deterministic-provider",
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
        "codex_runner": "deterministic_test",
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
            "--deterministic-provider",
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
        "codex_runner": "deterministic_test",
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
            "--deterministic-provider",
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
        "codex_runner": "deterministic_test",
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
            "--deterministic-provider",
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
        "codex_runner": "deterministic_test",
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
                "--deterministic-provider",
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
        "codex_runner": "deterministic_test",
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
            _final_answer_response("ENTRY_MISMATCH_READINESS_CHECK_DIRECT_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_MISMATCH_READINESS_CHECK_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_mismatch_readiness_check",
            ),
            _final_answer_response("ENTRY_MISMATCH_READINESS_CHECK_RESUME_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_MISMATCH_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_mismatch_pending",
            ),
        ]
    )
    monkeypatch.setattr(llm_live_smoke, "_deterministic_product_chat_entry_provider", lambda: provider)
    state_file = tmp_path / "entry-mismatch-state.json"
    first_exit = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--deterministic-provider",
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
            "--deterministic-provider",
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
        "codex_runner": "deterministic_test",
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
            _final_answer_response("ENTRY_ALREADY_READINESS_CHECK_DIRECT_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_ALREADY_READINESS_CHECK_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_already_readiness_check",
            ),
            _final_answer_response("ENTRY_ALREADY_READINESS_CHECK_RESUME_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_ALREADY_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_already_pending",
            ),
        ]
    )
    monkeypatch.setattr(llm_live_smoke, "_deterministic_product_chat_entry_provider", lambda: provider)
    state_file = tmp_path / "entry-already-state.json"
    first_exit = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--deterministic-provider",
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
            "--deterministic-provider",
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
            _final_answer_response("ENTRY_MISSING_READINESS_CHECK_DIRECT_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_MISSING_READINESS_CHECK_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_missing_readiness_check",
            ),
            _final_answer_response("ENTRY_MISSING_READINESS_CHECK_RESUME_SHOULD_NOT_LEAK"),
            _provider_response(
                prompt="ENTRY_MISSING_PENDING_TOOL_PROMPT_SHOULD_NOT_LEAK",
                call_id="call_entry_missing_pending",
            ),
        ]
    )
    monkeypatch.setattr(llm_live_smoke, "_deterministic_product_chat_entry_provider", lambda: provider)
    state_file = tmp_path / "entry-missing-state.json"
    first_exit = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--deterministic-provider",
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
            "--deterministic-provider",
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



def test_llm_product_chat_entry_cli_plain_output_is_public_metadata(tmp_path, capsys):
    exit_code = llm_live_smoke.main(
        [
            "product-chat-entry",
            "--deterministic-provider",
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
    assert "readiness_check_ready: true" in captured.out
    assert "entry_status: completed" in captured.out
    assert "assistant_message_present: true" in captured.out
    assert "ENTRY_CLI_PLAIN_MESSAGE_SHOULD_NOT_LEAK" not in captured.out
    assert "PRODUCT_CHAT_ENTRY_CLI_FINAL_ANSWER_SHOULD_NOT_LEAK" not in captured.out
