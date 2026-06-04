"""Deterministic LLM providers and responses for developer demo scenarios."""

from __future__ import annotations

from typing import Any

from ...llm.provider import LLMFinalAnswerResponse, LLMResponse, LLMToolCall, LLMToolCallResponse

ACTION_EXECUTION_EVENTS = {
    "action.started",
    "artifact.created",
    "action.completed",
    "action.failed",
    "run.completed",
}


class _DemoToolCallProvider:
    provider = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(self, responses: list[LLMToolCallResponse] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = list(responses) if responses is not None else [_demo_tool_call_response()]

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
        if self._responses:
            return self._responses.pop(0)
        return _demo_tool_call_response()


class _DemoProductChatProvider:
    provider = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(
        self,
        responses: list[LLMToolCallResponse | LLMFinalAnswerResponse] | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = list(responses) if responses is not None else [
            _demo_final_answer_response()
        ]

    def select_chat_turn(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]],
        max_tokens: int = 512,
    ) -> LLMToolCallResponse | LLMFinalAnswerResponse:
        self.calls.append(
            {
                "messages": list(messages),
                "tools": list(tools),
                "max_tokens": max_tokens,
            }
        )
        if self._responses:
            return self._responses.pop(0)
        return _demo_final_answer_response()


def _demo_tool_call_response(
    call_id: str = "call_demo_provider_route",
    prompt: str = "LLM_PROVIDER_DEMO_PROMPT_SHOULD_NOT_LEAK",
    summary: str = "provider-selected Codex demo",
) -> LLMToolCallResponse:
    return LLMToolCallResponse(
        provider=_DemoToolCallProvider.provider,
        model=_DemoToolCallProvider.model,
        finish_reason="tool_calls",
        usage={"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11},
        tool_call=LLMToolCall(
            call_id=call_id,
            tool_name="codex_task",
            arguments={
                "prompt": prompt,
                "summary": summary,
            },
        ),
    )


def _demo_terminal_tool_call_response() -> LLMToolCallResponse:
    return LLMToolCallResponse(
        provider=_DemoProductChatProvider.provider,
        model=_DemoProductChatProvider.model,
        finish_reason="tool_calls",
        usage={"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11},
        tool_call=LLMToolCall(
            call_id="call_demo_terminal_tool",
            tool_name="terminal_exec",
            arguments={
                "argv": ["printf", "TERMINAL_TOOL_LOOP_STDOUT_SHOULD_NOT_LEAK"],
                "summary": "provider-selected terminal command",
            },
        ),
    )


def _demo_final_answer_response() -> LLMFinalAnswerResponse:
    return LLMFinalAnswerResponse(
        provider=_DemoProductChatProvider.provider,
        model=_DemoProductChatProvider.model,
        finish_reason="stop",
        usage={"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13},
        content="APP_ENTRY_DEMO_FINAL_ANSWER_SHOULD_NOT_LEAK",
    )


def _demo_terminal_final_answer_response() -> LLMFinalAnswerResponse:
    return LLMFinalAnswerResponse(
        provider=_DemoProductChatProvider.provider,
        model=_DemoProductChatProvider.model,
        finish_reason="stop",
        usage={"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13},
        content="TERMINAL_TOOL_LOOP_FINAL_ANSWER_SHOULD_NOT_LEAK",
    )


def _demo_product_chat_ready_readiness_check() -> dict[str, Any]:
    return {
        "ready": True,
        "gate": "passed",
        "category": "ready",
        "status": "completed",
        "reason_code": "llm_product_chat_live_smoke_completed",
        "summary": "product-chat smoke completed direct answer, approval pause, and resume final answer",
        "next_step": "use this as a dev-only readiness_check before product-chat app entry",
    }


def _demo_product_chat_blocked_readiness_check() -> dict[str, Any]:
    return {
        "ready": False,
        "gate": "blocked",
        "category": "missing_configuration",
        "status": "missing_configuration",
        "reason_code": "llm_provider_not_configured",
        "summary": "LLM provider is not configured",
        "next_step": "configure provider credentials before product-chat app entry",
    }
