"""Tool-result message and follow-up helpers for LLM provider flows."""

from __future__ import annotations

import copy
import json
from typing import Any

from ...platform.errors import IsotopeError
from .parsing import (
    _parse_tool_result_message_content,
    _require_non_empty_string,
    _require_tool_result_string,
    _safe_provider_name,
    _safe_tool_result_artifact_ref,
    _safe_usage,
    _select_model_tools,
    _validate_messages,
)
from .types import LLMToolCallResponse, ToolCallProvider
from ..tool_bridge import submit_model_tool_call


def build_llm_tool_result_message(
    llm_result: dict[str, Any],
    tool_execution_result: dict[str, Any],
) -> dict[str, str]:
    """Build a public tool-result message for the originating model call."""

    if not isinstance(llm_result, dict):
        raise IsotopeError(
            "llm tool result source must be a dict",
            code="llm_tool_result_invalid_source",
            category="validation",
            retryable=False,
            http_status=400,
            details={"field": "llm_result"},
        )
    if not isinstance(tool_execution_result, dict):
        raise IsotopeError(
            "llm tool execution result must be a dict",
            code="llm_tool_result_invalid_execution",
            category="validation",
            retryable=False,
            http_status=400,
            details={"field": "tool_execution_result"},
        )

    tool_call_id = _require_tool_result_string(
        llm_result,
        "provider_tool_call_id",
        code="llm_tool_result_invalid_source",
    )
    tool_name = _require_tool_result_string(
        llm_result,
        "tool_name",
        code="llm_tool_result_invalid_source",
    )
    status_value = tool_execution_result.get(
        "tool_execution_status",
        tool_execution_result.get("status"),
    )
    status = _require_tool_result_string(
        {"status": status_value},
        "status",
        code="llm_tool_result_invalid_execution",
    )

    content: dict[str, Any] = {
        "status": status,
        "tool_name": tool_name,
    }
    execution_id = tool_execution_result.get("execution_id")
    if isinstance(execution_id, str) and execution_id:
        content["execution_id"] = execution_id

    artifact_ref = tool_execution_result.get("artifact_ref")
    if status == "completed":
        content["artifact_ref"] = _safe_tool_result_artifact_ref(artifact_ref)
    elif artifact_ref is not None:
        content["artifact_ref"] = _safe_tool_result_artifact_ref(artifact_ref)

    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": json.dumps(content, sort_keys=True, separators=(",", ":")),
    }


def select_llm_tool_result_followup(
    app: Any,
    run_id: str,
    provider: ToolCallProvider,
    messages: list[dict[str, str]],
    llm_result: dict[str, Any],
    tool_execution_result: dict[str, Any],
    *,
    max_tokens: int = 512,
    tool_names: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Send a public tool result back to the provider for one follow-up choice."""

    provider_response, tool_result_message, tool_result_content = _request_tool_result_followup(
        app,
        run_id,
        provider,
        messages,
        llm_result,
        tool_execution_result,
        max_tokens=max_tokens,
        tool_names=tool_names,
    )

    result = _safe_tool_result_followup_selection(
        provider_response,
        tool_result_message,
        tool_result_content,
    )
    result["submission_status"] = "not_submitted"
    return result


def submit_llm_tool_result_followup(
    app: Any,
    run_id: str,
    provider: ToolCallProvider,
    messages: list[dict[str, str]],
    llm_result: dict[str, Any],
    tool_execution_result: dict[str, Any],
    *,
    max_tokens: int = 512,
    tool_names: tuple[str, ...] | None = None,
    complete_run: bool = True,
) -> dict[str, Any]:
    """Send a tool result to the provider and submit the selected follow-up tool."""

    if not isinstance(complete_run, bool):
        raise IsotopeError(
            "complete_run must be a bool",
            code="invalid_llm_tool_call",
            category="validation",
            retryable=False,
            http_status=400,
            details={"field": "complete_run"},
        )
    _require_non_empty_string("run_id", run_id)
    _require_open_run_for_followup_submission(app, run_id)
    provider_response, tool_result_message, tool_result_content = _request_tool_result_followup(
        app,
        run_id,
        provider,
        messages,
        llm_result,
        tool_execution_result,
        max_tokens=max_tokens,
        tool_names=tool_names,
    )
    bridge_result = submit_model_tool_call(
        app,
        run_id,
        {
            "tool_name": provider_response.tool_call.tool_name,
            "arguments": copy.deepcopy(provider_response.tool_call.arguments),
        },
        complete_run=complete_run,
    )
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


def _require_open_run_for_followup_submission(app: Any, run_id: str) -> None:
    state = app.server.get_run_state(run_id)
    status = getattr(state, "status", None)
    if status != "running":
        raise IsotopeError(
            "run is not open for tool-result follow-up submission",
            code="run_not_open_for_followup_submission",
            category="conflict",
            retryable=False,
            http_status=409,
            details={"run_id": run_id, "status": status},
        )


def _request_tool_result_followup(
    app: Any,
    run_id: str,
    provider: ToolCallProvider,
    messages: list[dict[str, str]],
    llm_result: dict[str, Any],
    tool_execution_result: dict[str, Any],
    *,
    max_tokens: int,
    tool_names: tuple[str, ...] | None,
) -> tuple[LLMToolCallResponse, dict[str, str], dict[str, Any]]:
    _require_non_empty_string("run_id", run_id)
    app.server.get_run_state(run_id)
    _validate_messages(messages)
    catalog = app.server.get_model_tool_catalog()
    tools = _select_model_tools(catalog.get("tools"), tool_names=tool_names)
    assistant_tool_call_message = _build_llm_assistant_tool_call_message(llm_result)
    tool_result_message = build_llm_tool_result_message(llm_result, tool_execution_result)
    tool_result_content = _parse_tool_result_message_content(tool_result_message)
    followup_messages = copy.deepcopy(messages)
    followup_messages.append(copy.deepcopy(assistant_tool_call_message))
    followup_messages.append(copy.deepcopy(tool_result_message))

    try:
        provider_response = provider.select_tool(
            followup_messages,
            tools=tools,
            max_tokens=max_tokens,
        )
    except IsotopeError:
        raise
    except ValueError as exc:
        raise IsotopeError(
            "model provider did not return a valid follow-up tool call",
            code="llm_tool_call_invalid_response",
            category="validation",
            retryable=False,
            http_status=400,
            details={"provider": _safe_provider_name(provider)},
        ) from exc
    except RuntimeError as exc:
        raise IsotopeError(
            "model provider follow-up request failed",
            code="llm_provider_request_failed",
            category="internal",
            retryable=True,
            http_status=502,
            details={"provider": _safe_provider_name(provider)},
        ) from exc

    offered_names = {tool["name"] for tool in tools}
    tool_name = _require_non_empty_string("tool_name", provider_response.tool_call.tool_name)
    if tool_name not in offered_names:
        raise IsotopeError(
            "provider selected a tool outside the active catalog",
            code="llm_tool_unavailable",
            category="unavailable",
            retryable=False,
            http_status=501,
            details={"tool_names": [tool_name]},
        )
    return provider_response, tool_result_message, tool_result_content


def _build_llm_assistant_tool_call_message(llm_result: dict[str, Any]) -> dict[str, Any]:
    tool_call_id = _require_tool_result_string(
        llm_result,
        "provider_tool_call_id",
        code="llm_tool_result_invalid_source",
    )
    tool_name = _require_tool_result_string(
        llm_result,
        "tool_name",
        code="llm_tool_result_invalid_source",
    )
    return {
        "role": "assistant",
        "content": "Tool call selected by Isotope.",
        "tool_calls": [
            {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": "{}",
                },
            }
        ],
    }


def _safe_tool_result_followup_selection(
    provider_response: LLMToolCallResponse,
    tool_result_message: dict[str, str],
    tool_result_content: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "tool_call_selected",
        "provider_status": "tool_result_followup_selected",
        "provider": provider_response.provider,
        "model": provider_response.model,
        "finish_reason": provider_response.finish_reason,
        "usage": _safe_usage(provider_response.usage),
        "tool_name": _require_non_empty_string("tool_name", provider_response.tool_call.tool_name),
        "provider_tool_call_id": _require_non_empty_string(
            "provider_tool_call_id",
            provider_response.tool_call.call_id,
        ),
        "previous_provider_tool_call_id": tool_result_message["tool_call_id"],
        "tool_result_status": tool_result_content.get("status"),
    }
    artifact_ref = tool_result_content.get("artifact_ref")
    if isinstance(artifact_ref, dict):
        result["tool_result_artifact_ref"] = copy.deepcopy(artifact_ref)
    return result
