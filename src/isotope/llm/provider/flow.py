"""Provider-to-Isotope tool-call and chat-turn submission flows."""

from __future__ import annotations

import copy
from dataclasses import asdict
from typing import Any

from ...platform.errors import IsotopeError
from .parsing import (
    _parse_tool_result_message_content,
    _require_final_answer_content,
    _require_non_empty_string,
    _safe_provider_name,
    _safe_usage,
    _select_model_tools,
    _validate_messages,
)
from .tool_result import (
    _build_llm_assistant_tool_call_message,
    _require_open_run_for_followup_submission,
    _safe_tool_result_followup_selection,
    build_llm_tool_result_message,
)
from .types import (
    LLMChatTurnResponse,
    LLMFinalAnswerResponse,
    LLMToolCallResponse,
    ToolCallProvider,
)
from ..tool_bridge import submit_model_tool_call


def submit_llm_tool_call(
    app: Any,
    run_id: str,
    provider: ToolCallProvider,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 512,
    tool_names: tuple[str, ...] | None = None,
    complete_run: bool = True,
) -> dict[str, Any]:
    """Let a provider select one catalog tool, then route it through Isotope controls."""

    _require_non_empty_string("run_id", run_id)
    if not isinstance(complete_run, bool):
        raise IsotopeError(
            "complete_run must be a bool",
            code="invalid_llm_tool_call",
            category="validation",
            retryable=False,
            http_status=400,
            details={"field": "complete_run"},
        )
    catalog = app.server.get_model_tool_catalog()
    tools = _select_model_tools(catalog.get("tools"), tool_names=tool_names)
    try:
        provider_response = provider.select_tool(
            copy.deepcopy(messages),
            tools=tools,
            max_tokens=max_tokens,
        )
    except IsotopeError:
        raise
    except ValueError as exc:
        raise IsotopeError(
            "model provider did not return a valid tool call",
            code="llm_tool_call_invalid_response",
            category="validation",
            retryable=False,
            http_status=400,
            details={"provider": _safe_provider_name(provider)},
        ) from exc
    except RuntimeError as exc:
        raise IsotopeError(
            "model provider request failed",
            code="llm_provider_request_failed",
            category="internal",
            retryable=True,
            http_status=502,
            details={"provider": _safe_provider_name(provider)},
        ) from exc

    provider_tool_name = _require_provider_selected_offered_tool(provider_response, tools)

    bridge_result = submit_model_tool_call(
        app,
        run_id,
        {
            "tool_name": provider_tool_name,
            "arguments": copy.deepcopy(provider_response.tool_call.arguments),
        },
        complete_run=complete_run,
    )
    return {
        "status": bridge_result.get("status"),
        "provider_status": "tool_call_selected",
        "provider": provider_response.provider,
        "model": provider_response.model,
        "finish_reason": provider_response.finish_reason,
        "usage": _safe_usage(provider_response.usage),
        "tool_name": provider_tool_name,
        "provider_tool_call_id": provider_response.tool_call.call_id,
        "requires_approval": bridge_result.get("requires_approval"),
        "tool_result": bridge_result,
    }


def submit_llm_chat_turn(
    app: Any,
    run_id: str,
    provider: ToolCallProvider,
    messages: list[dict[str, str]],
    llm_result: dict[str, Any] | None = None,
    tool_execution_result: dict[str, Any] | None = None,
    *,
    max_tokens: int = 512,
    tool_names: tuple[str, ...] | None = None,
    complete_run: bool = True,
) -> dict[str, Any]:
    """Submit one product-chat model turn through Isotope controls."""

    _require_non_empty_string("run_id", run_id)
    if not isinstance(complete_run, bool):
        raise IsotopeError(
            "complete_run must be a bool",
            code="invalid_llm_tool_call",
            category="validation",
            retryable=False,
            http_status=400,
            details={"field": "complete_run"},
        )
    has_llm_result = llm_result is not None
    has_tool_execution_result = tool_execution_result is not None
    if has_llm_result != has_tool_execution_result:
        raise IsotopeError(
            "llm_result and tool_execution_result must be provided together",
            code="llm_tool_result_invalid_execution",
            category="validation",
            retryable=False,
            http_status=400,
            details={"field": "tool_result_context"},
        )

    app.server.get_run_state(run_id)
    _validate_messages(messages)
    catalog = app.server.get_model_tool_catalog()
    tools = _select_model_tools(catalog.get("tools"), tool_names=tool_names)
    provider_messages = copy.deepcopy(messages)
    tool_result_message: dict[str, str] | None = None
    tool_result_content: dict[str, Any] | None = None
    if has_llm_result:
        _require_open_run_for_followup_submission(app, run_id)
        assistant_tool_call_message = _build_llm_assistant_tool_call_message(llm_result or {})
        tool_result_message = build_llm_tool_result_message(llm_result or {}, tool_execution_result or {})
        tool_result_content = _parse_tool_result_message_content(tool_result_message)
        provider_messages.append(copy.deepcopy(assistant_tool_call_message))
        provider_messages.append(copy.deepcopy(tool_result_message))

    provider_response = _request_chat_turn(
        provider,
        provider_messages,
        tools=tools,
        max_tokens=max_tokens,
    )
    if isinstance(provider_response, LLMToolCallResponse):
        provider_tool_name = _require_provider_selected_offered_tool(provider_response, tools)
        bridge_result = submit_model_tool_call(
            app,
            run_id,
            {
                "tool_name": provider_tool_name,
                "arguments": copy.deepcopy(provider_response.tool_call.arguments),
            },
            complete_run=complete_run,
        )
        if tool_result_message is None or tool_result_content is None:
            return {
                "status": bridge_result.get("status"),
                "provider_status": "tool_call_selected",
                "provider": provider_response.provider,
                "model": provider_response.model,
                "finish_reason": provider_response.finish_reason,
                "usage": _safe_usage(provider_response.usage),
                "tool_name": provider_tool_name,
                "provider_tool_call_id": provider_response.tool_call.call_id,
                "requires_approval": bridge_result.get("requires_approval"),
                "tool_result": bridge_result,
            }
        result = _safe_tool_result_followup_selection(
            provider_response,
            tool_result_message,
            tool_result_content,
        )
        result.update(
            {
                "status": bridge_result.get("status"),
                "submission_status": bridge_result.get("status"),
                "requires_approval": bridge_result.get("requires_approval"),
                "tool_result": bridge_result,
            }
        )
        return result
    if isinstance(provider_response, LLMFinalAnswerResponse):
        return _submit_llm_final_answer(
            app,
            run_id,
            provider_response,
            tool_result_message=tool_result_message,
            tool_result_content=tool_result_content,
            complete_run=complete_run,
        )
    raise IsotopeError(
        "model provider did not return a valid chat turn",
        code="llm_chat_turn_invalid_response",
        category="validation",
        retryable=False,
        http_status=400,
        details={"provider": _safe_provider_name(provider)},
    )


def _require_provider_selected_offered_tool(
    provider_response: LLMToolCallResponse,
    tools: list[dict[str, Any]],
) -> str:
    offered_names = {tool["name"] for tool in tools}
    provider_tool_name = _require_non_empty_string(
        "tool_name",
        provider_response.tool_call.tool_name,
    )
    if provider_tool_name not in offered_names:
        raise IsotopeError(
            "provider selected a tool that was not offered",
            code="llm_provider_selected_unoffered_tool",
            category="unavailable",
            retryable=False,
            http_status=501,
            details={"tool_names": [provider_tool_name]},
        )
    return provider_tool_name


def _request_chat_turn(
    provider: ToolCallProvider,
    messages: list[dict[str, str]],
    *,
    tools: list[dict[str, Any]],
    max_tokens: int,
) -> LLMChatTurnResponse:
    try:
        selector = getattr(provider, "select_chat_turn", None)
        if callable(selector):
            response = selector(
                copy.deepcopy(messages),
                tools=tools,
                max_tokens=max_tokens,
            )
        else:
            response = provider.select_tool(
                copy.deepcopy(messages),
                tools=tools,
                max_tokens=max_tokens,
            )
    except IsotopeError:
        raise
    except ValueError as exc:
        raise IsotopeError(
            "model provider did not return a valid chat turn",
            code="llm_chat_turn_invalid_response",
            category="validation",
            retryable=False,
            http_status=400,
            details={"provider": _safe_provider_name(provider)},
        ) from exc
    except RuntimeError as exc:
        raise IsotopeError(
            "model provider chat-turn request failed",
            code="llm_provider_request_failed",
            category="internal",
            retryable=True,
            http_status=502,
            details={"provider": _safe_provider_name(provider)},
        ) from exc

    if isinstance(response, (LLMToolCallResponse, LLMFinalAnswerResponse)):
        return response
    raise IsotopeError(
        "model provider did not return a valid chat turn",
        code="llm_chat_turn_invalid_response",
        category="validation",
        retryable=False,
        http_status=400,
        details={"provider": _safe_provider_name(provider)},
    )


def _submit_llm_final_answer(
    app: Any,
    run_id: str,
    provider_response: LLMFinalAnswerResponse,
    *,
    tool_result_message: dict[str, str] | None,
    tool_result_content: dict[str, Any] | None,
    complete_run: bool,
) -> dict[str, Any]:
    content = _require_final_answer_content(provider_response.content, provider=provider_response.provider)
    submit_result = app.server.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": content,
            "summary": "LLM final answer",
            "requested_tools": ["write_artifact_tool"],
        },
        requires_approval=False,
        complete_run=complete_run,
    )
    tool_result = _safe_submit_action_result(
        submit_result,
        tool_name="write_artifact_tool",
        requires_approval=False,
    )
    result: dict[str, Any] = {
        "status": tool_result.get("status"),
        "provider_status": "final_answer",
        "provider": provider_response.provider,
        "model": provider_response.model,
        "finish_reason": provider_response.finish_reason,
        "usage": _safe_usage(provider_response.usage),
        "requires_approval": False,
        "assistant_message": {"role": "assistant", "content": content},
        "tool_result": tool_result,
    }
    if tool_result_message is not None and tool_result_content is not None:
        result["previous_provider_tool_call_id"] = tool_result_message["tool_call_id"]
        result["tool_result_status"] = tool_result_content.get("status")
        artifact_ref = tool_result_content.get("artifact_ref")
        if isinstance(artifact_ref, dict):
            result["tool_result_artifact_ref"] = copy.deepcopy(artifact_ref)
    return result


def _safe_submit_action_result(
    result: dict[str, Any],
    *,
    tool_name: str,
    requires_approval: bool,
) -> dict[str, Any]:
    safe: dict[str, Any] = {
        "status": result.get("status"),
        "tool_name": tool_name,
        "requires_approval": requires_approval,
    }
    for key in ("proposal_id", "decision_id", "execution_id", "tool_execution_status"):
        if key in result:
            safe[key] = copy.deepcopy(result[key])
    artifact_ref = result.get("artifact_ref")
    if hasattr(artifact_ref, "to_dict"):
        safe["artifact_ref"] = artifact_ref.to_dict()
    elif isinstance(artifact_ref, dict):
        safe["artifact_ref"] = copy.deepcopy(artifact_ref)
    run_state = result.get("run_state")
    if hasattr(run_state, "__dataclass_fields__"):
        safe["run_state"] = asdict(run_state)
    elif isinstance(run_state, dict):
        safe["run_state"] = copy.deepcopy(run_state)
    return safe
