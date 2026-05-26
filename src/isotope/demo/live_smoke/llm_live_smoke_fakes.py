"""Fake providers and runners for LLM live-smoke CLI tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...llm.provider import (
    LLMFinalAnswerResponse,
    LLMToolCall,
    LLMToolCallResponse,
    ToolCallProvider,
)


class _RecordingFakeCodexRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv: Any, **kwargs: Any) -> "_FakeCompletedProcess":
        self.calls.append({"argv_count": len(list(argv)), "timeout": kwargs.get("timeout")})
        return _FakeCompletedProcess()


class _FakeCompletedProcess:
    returncode = 0
    stdout = '{"event":"task_complete","secret":"PRODUCT_CHAT_CLI_FAKE_STDOUT_SHOULD_NOT_LEAK"}\n'
    stderr = ""


def _fake_codex_executable_resolver(executable: str) -> str | None:
    if not isinstance(executable, str) or not executable:
        return None
    if "/" in executable or "\\" in executable:
        return None
    return str(Path("/tmp/isotope-fake-codex-bin") / executable)


class _SequencedProductChatSmokeProvider:
    provider = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(
        self,
        *,
        include_entry_response: bool = False,
        entry_pending: bool = False,
    ) -> None:
        self._responses: list[LLMFinalAnswerResponse | LLMToolCallResponse] = [
            LLMFinalAnswerResponse(
                provider=self.provider,
                model=self.model,
                finish_reason="stop",
                usage={"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11},
                content="Direct product-chat smoke answer.",
            ),
            LLMToolCallResponse(
                provider=self.provider,
                model=self.model,
                finish_reason="tool_calls",
                usage={"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
                tool_call=LLMToolCall(
                    call_id="call_product_chat_cli_fake",
                    tool_name="codex_task",
                    arguments={
                        "prompt": "PRODUCT_CHAT_CLI_FAKE_PROMPT_SHOULD_NOT_LEAK",
                        "summary": "product chat CLI fake provider task",
                    },
                ),
            ),
            LLMFinalAnswerResponse(
                provider=self.provider,
                model=self.model,
                finish_reason="stop",
                usage={"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13},
                content="Final product-chat smoke answer.",
            ),
        ]
        if include_entry_response and entry_pending:
            self._responses.append(
                LLMToolCallResponse(
                    provider=self.provider,
                    model=self.model,
                    finish_reason="tool_calls",
                    usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    tool_call=LLMToolCall(
                        call_id="call_product_chat_entry_cli_fake",
                        tool_name="codex_task",
                        arguments={
                            "prompt": "PRODUCT_CHAT_ENTRY_CLI_PENDING_PROMPT_SHOULD_NOT_LEAK",
                            "summary": "product chat entry CLI fake pending task",
                        },
                    ),
                )
            )
        elif include_entry_response:
            self._responses.append(
                LLMFinalAnswerResponse(
                    provider=self.provider,
                    model=self.model,
                    finish_reason="stop",
                    usage={"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
                    content="PRODUCT_CHAT_ENTRY_CLI_FINAL_ANSWER_SHOULD_NOT_LEAK",
                )
            )

    def select_chat_turn(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]],
        max_tokens: int = 512,
    ) -> LLMFinalAnswerResponse | LLMToolCallResponse:
        del messages, tools, max_tokens
        if not self._responses:
            raise ValueError("fake product-chat smoke provider exhausted")
        return self._responses.pop(0)


def _fake_product_chat_provider() -> _SequencedProductChatSmokeProvider:
    return _SequencedProductChatSmokeProvider()


def _fake_product_chat_entry_provider(
    *,
    entry_pending: bool = False,
) -> _SequencedProductChatSmokeProvider:
    return _SequencedProductChatSmokeProvider(
        include_entry_response=True,
        entry_pending=entry_pending,
    )


class _FakeTerminalToolProvider:
    provider = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(self) -> None:
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
        return LLMToolCallResponse(
            provider=self.provider,
            model=self.model,
            finish_reason="tool_calls",
            usage={"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
            tool_call=LLMToolCall(
                call_id="call_terminal_tool_cli_fake",
                tool_name="terminal_exec",
                arguments={
                    "argv": ["printf", "TERMINAL_TOOL_CLI_FAKE_STDOUT_SHOULD_NOT_LEAK"],
                    "summary": "terminal tool CLI fake provider command",
                },
            ),
        )


def _fake_terminal_tool_provider() -> _FakeTerminalToolProvider:
    return _FakeTerminalToolProvider()


def _provider_call_count(provider: ToolCallProvider | None) -> int:
    calls = getattr(provider, "calls", None)
    if isinstance(calls, list):
        return len(calls)
    return 0
