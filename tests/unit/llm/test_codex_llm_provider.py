from __future__ import annotations

import json
from typing import Any

from isotope.llm.provider import (
    CodexCliLLMProvider,
    LLMFinalAnswerResponse,
    resolve_llm_chat_provider,
    resolve_llm_tool_call_provider,
)


class _StubCompletedProcess:
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
        return _StubCompletedProcess(
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


def test_codex_cli_provider_uses_latest_runtime_agent_message(tmp_path):
    stdout = "\n".join(
        [
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "First"},
                }
            ),
            json.dumps(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": "Second",
                    },
                }
            ),
        ]
    )

    class Runner:
        def __init__(self) -> None:
            self.calls = []

        def __call__(self, argv, **kwargs):
            self.calls.append({"argv": list(argv), "kwargs": dict(kwargs)})
            return _StubCompletedProcess(stdout=stdout + "\n")

    provider = CodexCliLLMProvider(
        workspace_root=str(tmp_path),
        executable="codex",
        process_runner=Runner(),
        executable_resolver=_resolve_codex_executable,
    )

    response = provider.generate([{"role": "user", "content": "hello"}])

    assert response.content == "Second"


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


def test_llm_chat_provider_resolution_configures_codex_api_without_api_key(tmp_path):
    resolution = resolve_llm_chat_provider(
        {
            "ISOTOPE_LLM_PROVIDER": "codex-api",
            "ISOTOPE_LLM_MODEL": "gpt-5-codex",
            "ISOTOPE_LLM_TIMEOUT_SECONDS": "13",
            "ISOTOPE_CODEX_WORKSPACE_ROOT": str(tmp_path),
            "ISOTOPE_CODEX_HOME": str(tmp_path / "codex-home"),
        },
        codex_executable_resolver=_resolve_codex_executable,
    )

    assert resolution.status == "configured"
    assert resolution.provider_name == "codex-api"
    assert resolution.provider is not None
    assert resolution.provider.provider == "codex-api"
    assert resolution.provider.model == "gpt-5-codex"


def test_llm_tool_call_resolution_keeps_codex_api_unsupported_until_tool_contract_exists(
    tmp_path,
):
    resolution = resolve_llm_tool_call_provider(
        {
            "ISOTOPE_LLM_PROVIDER": "codex-api",
            "ISOTOPE_CODEX_WORKSPACE_ROOT": str(tmp_path),
        },
        codex_executable_resolver=_resolve_codex_executable,
    )

    assert resolution.status == "missing_configuration"
    assert resolution.reason_code == "llm_provider_unsupported"
    assert resolution.provider_name == "codex-api"
    assert resolution.provider is None
