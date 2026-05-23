"""Parsing and validation helpers for OpenAI-compatible provider responses."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

from ..platform.errors import IsotopeError
from .provider_types import (
    LLMChatTurnResponse,
    LLMFinalAnswerResponse,
    LLMResponse,
    LLMToolCall,
    LLMToolCallResponse,
)


def _parse_tool_call_completion(
    raw: dict[str, Any],
    *,
    provider: str,
    fallback_model: str,
) -> LLMToolCallResponse:
    if not isinstance(raw, dict):
        raise ValueError("malformed model response")
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("malformed model response: missing choices")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("malformed model response: invalid choice")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("malformed model response: missing message")
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list) or len(tool_calls) != 1:
        raise ValueError("model response must include exactly one tool call")
    tool_call = _parse_tool_call(tool_calls[0])
    usage = raw.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    return LLMToolCallResponse(
        provider=provider,
        model=str(raw.get("model") or fallback_model),
        finish_reason=str(first_choice.get("finish_reason") or ""),
        usage=_safe_usage(usage),
        tool_call=tool_call,
    )


def _parse_chat_turn_completion(
    raw: dict[str, Any],
    *,
    provider: str,
    fallback_model: str,
) -> LLMChatTurnResponse:
    if not isinstance(raw, dict):
        raise ValueError("malformed model response")
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("malformed model response: missing choices")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("malformed model response: invalid choice")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("malformed model response: missing message")
    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        if len(tool_calls) != 1:
            raise ValueError("model response must include at most one tool call")
        return LLMToolCallResponse(
            provider=provider,
            model=str(raw.get("model") or fallback_model),
            finish_reason=str(first_choice.get("finish_reason") or ""),
            usage=_safe_usage(raw.get("usage", {}) if isinstance(raw.get("usage", {}), dict) else {}),
            tool_call=_parse_tool_call(tool_calls[0]),
        )
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("content must be a non-empty string")
    usage = raw.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    return LLMFinalAnswerResponse(
        provider=provider,
        model=str(raw.get("model") or fallback_model),
        finish_reason=str(first_choice.get("finish_reason") or ""),
        usage=_safe_usage(usage),
        content=content,
    )


def _parse_chat_completion(
    raw: dict[str, Any],
    *,
    provider: str,
    fallback_model: str,
) -> LLMResponse:
    if not isinstance(raw, dict):
        raise ValueError("malformed model response")
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("malformed model response: missing choices")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("malformed model response: invalid choice")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("malformed model response: missing message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("empty model response")
    usage = raw.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    return LLMResponse(
        provider=provider,
        model=str(raw.get("model") or fallback_model),
        content=content.strip(),
        finish_reason=str(first_choice.get("finish_reason") or ""),
        usage=_safe_usage(usage),
        raw=copy.deepcopy(raw),
    )


def _is_length_limited_reasoning_only_response(raw: dict[str, Any]) -> bool:
    if not isinstance(raw, dict):
        return False
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        return False
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return False
    if first_choice.get("finish_reason") != "length":
        return False
    message = first_choice.get("message")
    if not isinstance(message, dict):
        return False
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return False
    reasoning_content = message.get("reasoning_content")
    return isinstance(reasoning_content, str) and bool(reasoning_content.strip())


def _parse_tool_call(raw_call: Any) -> LLMToolCall:
    if not isinstance(raw_call, dict):
        raise ValueError("malformed tool call")
    call_id = _require_non_empty_string("tool_call_id", raw_call.get("id"))
    if raw_call.get("type") != "function":
        raise ValueError("tool call type must be function")
    function = raw_call.get("function")
    if not isinstance(function, dict):
        raise ValueError("malformed tool call function")
    tool_name = _require_non_empty_string("tool_name", function.get("name"))
    raw_arguments = function.get("arguments")
    if not isinstance(raw_arguments, str) or not raw_arguments:
        raise ValueError("tool call arguments must be a JSON object")
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        raise ValueError("tool call arguments must be a JSON object") from exc
    if not isinstance(arguments, dict):
        raise ValueError("tool call arguments must be a JSON object")
    return LLMToolCall(
        call_id=call_id,
        tool_name=tool_name,
        arguments=copy.deepcopy(arguments),
    )


def _to_openai_tool(tool: dict[str, Any]) -> dict[str, Any]:
    name = _require_non_empty_string("tool.name", tool.get("name"))
    input_schema = tool.get("input_schema", {})
    if not isinstance(input_schema, dict):
        input_schema = {}
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": _tool_description(tool),
            "parameters": copy.deepcopy(input_schema) or {"type": "object", "properties": {}},
        },
    }


def _tool_description(tool: dict[str, Any]) -> str:
    action = tool.get("action")
    result_kind = None
    output_contract = tool.get("output_contract")
    if isinstance(output_contract, dict):
        result_kind = output_contract.get("result_kind")
    pieces = [
        "Isotope controlled tool",
        f"action={action}" if isinstance(action, str) and action else "",
        f"result_kind={result_kind}" if isinstance(result_kind, str) and result_kind else "",
        "output is returned through artifact refs, not inline content",
    ]
    return "; ".join(piece for piece in pieces if piece)


def _validate_messages(messages: list[dict[str, str]]) -> None:
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty list")
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("each message must be a dict")
        role = message.get("role")
        content = message.get("content")
        if role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("message role must be system, user, assistant, or tool")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("message content must be a non-empty string")


def _validate_model_tools(tools: Any) -> list[dict[str, Any]]:
    if not isinstance(tools, list) or not tools:
        raise ValueError("tools must be a non-empty list")
    result: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            raise ValueError("each tool must be a dict")
        _require_non_empty_string("tool.name", tool.get("name"))
        result.append(copy.deepcopy(tool))
    return result


def _select_model_tools(
    tools: Any,
    *,
    tool_names: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    model_tools = _validate_model_tools(tools)
    if tool_names is None:
        return model_tools
    if not isinstance(tool_names, tuple) or not tool_names:
        raise ValueError("tool_names must be a non-empty tuple")
    selected_names = {_require_non_empty_string("tool_name", name) for name in tool_names}
    selected = [tool for tool in model_tools if tool["name"] in selected_names]
    if len(selected) != len(selected_names):
        available = {tool["name"] for tool in model_tools}
        missing = sorted(selected_names.difference(available))
        raise IsotopeError(
            "requested model tools are not enabled",
            code="llm_tool_not_enabled",
            category="not_enabled",
            retryable=False,
            http_status=501,
            details={"tool_names": missing},
        )
    return selected


def _safe_usage(usage: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in usage.items()
        if isinstance(key, str) and (isinstance(value, (str, int, float, bool)) or value is None)
    }


def _safe_provider_name(provider: Any) -> str:
    name = getattr(provider, "provider", None)
    if isinstance(name, str) and name:
        return name[:64]
    return "unknown"


def _require_tool_result_string(source: dict[str, Any], field_name: str, *, code: str) -> str:
    value = source.get(field_name)
    if isinstance(value, str) and value:
        return value
    raise IsotopeError(
        "llm tool result is missing required metadata",
        code=code,
        category="validation",
        retryable=False,
        http_status=400,
        details={"field": field_name},
    )


def _safe_tool_result_artifact_ref(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise IsotopeError(
            "completed llm tool result requires an artifact ref",
            code="llm_tool_result_missing_artifact_ref",
            category="validation",
            retryable=False,
            http_status=400,
            details={"field": "artifact_ref"},
        )
    safe_ref: dict[str, str] = {}
    for field_name in ("ref_type", "run_id", "artifact_id"):
        field_value = value.get(field_name)
        if not isinstance(field_value, str) or not field_value:
            raise IsotopeError(
                "completed llm tool result requires a structured artifact ref",
                code="llm_tool_result_missing_artifact_ref",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": f"artifact_ref.{field_name}"},
            )
        safe_ref[field_name] = field_value
    scope = value.get("scope")
    if isinstance(scope, str) and scope:
        safe_ref["scope"] = scope
    return safe_ref


def _parse_tool_result_message_content(message: dict[str, str]) -> dict[str, Any]:
    try:
        content = json.loads(message["content"])
    except (KeyError, json.JSONDecodeError, TypeError) as exc:
        raise IsotopeError(
            "llm tool result message has invalid content",
            code="llm_tool_result_invalid_execution",
            category="validation",
            retryable=False,
            http_status=400,
            details={"field": "content"},
        ) from exc
    if not isinstance(content, dict):
        raise IsotopeError(
            "llm tool result message content must be an object",
            code="llm_tool_result_invalid_execution",
            category="validation",
            retryable=False,
            http_status=400,
            details={"field": "content"},
        )
    return copy.deepcopy(content)


def _require_non_empty_string(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _env_string(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if not isinstance(value, str):
        return ""
    return value.strip()


def _normalized_provider_name(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def _resolve_provider_timeout(env: Mapping[str, str]) -> int | None:
    raw_value = _env_string(env, "ISOTOPE_LLM_TIMEOUT_SECONDS") or _env_string(
        env,
        "DEEPSEEK_TIMEOUT_SECONDS",
    )
    if not raw_value:
        return 60
    try:
        timeout = int(raw_value)
    except ValueError:
        return None
    if timeout <= 0:
        return None
    return timeout


def _require_final_answer_content(value: Any, *, provider: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IsotopeError(
            "model provider did not return a valid final answer",
            code="llm_final_answer_invalid_response",
            category="validation",
            retryable=False,
            http_status=400,
            details={"provider": provider},
        )
    return value
