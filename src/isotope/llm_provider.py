"""Provider-to-model-tool-call boundary for controlled LLM tool selection."""

from __future__ import annotations

import copy
import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Protocol

from .platform.errors import KernelError
from .model_tool_bridge import submit_model_tool_call


Transport = Callable[[str, dict[str, Any], dict[str, str], int], dict[str, Any]]


@dataclass(frozen=True)
class LLMToolCall:
    call_id: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMToolCallResponse:
    provider: str
    model: str
    finish_reason: str
    usage: dict[str, Any]
    tool_call: LLMToolCall


@dataclass(frozen=True)
class LLMFinalAnswerResponse:
    provider: str
    model: str
    finish_reason: str
    usage: dict[str, Any]
    content: str


@dataclass(frozen=True)
class LLMResponse:
    provider: str
    model: str
    content: str
    finish_reason: str
    usage: dict[str, Any]
    raw: dict[str, Any]


LLMChatTurnResponse = LLMToolCallResponse | LLMFinalAnswerResponse


class ToolCallProvider(Protocol):
    provider: str
    model: str

    def select_tool(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]],
        max_tokens: int = 512,
    ) -> LLMToolCallResponse:
        ...


@dataclass(frozen=True)
class LLMProviderResolution:
    status: str
    reason_code: str
    provider_name: str
    provider: ToolCallProvider | None = field(default=None, repr=False)


class DeepSeekChatProvider:
    """OpenAI-compatible DeepSeek chat provider using only stdlib HTTP."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "deepseek-v4-flash",
        base_url: str = "https://api.deepseek.com",
        timeout: int = 60,
        transport: Transport | None = None,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("DEEPSEEK_API_KEY", "")
        if not isinstance(key, str) or not key.strip():
            raise ValueError("DEEPSEEK_API_KEY is required for DeepSeekChatProvider")
        self.api_key = key
        self.provider = "deepseek"
        self.model = _require_non_empty_string("model", model)
        self.base_url = _require_non_empty_string("base_url", base_url).rstrip("/")
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError("timeout must be a positive integer")
        self.timeout = timeout
        self._transport = transport if transport is not None else _urllib_transport

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        _validate_messages(messages)
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")

        payload = {
            "model": self.model,
            "messages": copy.deepcopy(messages),
            "thinking": {"type": "disabled"},
            "temperature": 0,
            "max_tokens": max_tokens,
            "stream": False,
        }
        raw = self._transport(
            f"{self.base_url}/chat/completions",
            payload,
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            self.timeout,
        )
        return _parse_chat_completion(raw, provider=self.provider, fallback_model=self.model)


class DeepSeekToolCallProvider:
    """OpenAI-compatible DeepSeek tool-call provider using only stdlib HTTP."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "deepseek-v4-flash",
        base_url: str = "https://api.deepseek.com",
        timeout: int = 60,
        transport: Transport | None = None,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("DEEPSEEK_API_KEY", "")
        if not isinstance(key, str) or not key.strip():
            raise ValueError("DEEPSEEK_API_KEY is required for DeepSeekToolCallProvider")
        self.api_key = key
        self.provider = "deepseek"
        self.model = _require_non_empty_string("model", model)
        self.base_url = _require_non_empty_string("base_url", base_url).rstrip("/")
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError("timeout must be a positive integer")
        self.timeout = timeout
        self._transport = transport if transport is not None else _urllib_transport

    def select_tool(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]],
        max_tokens: int = 512,
    ) -> LLMToolCallResponse:
        _validate_messages(messages)
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")
        model_tools = _validate_model_tools(tools)
        raw = self._request_completion(
            messages,
            model_tools,
            max_tokens=max_tokens,
            tool_choice="required",
        )
        return _parse_tool_call_completion(
            raw,
            provider=self.provider,
            fallback_model=self.model,
        )

    def select_chat_turn(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]],
        max_tokens: int = 512,
    ) -> LLMChatTurnResponse:
        _validate_messages(messages)
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")
        model_tools = _validate_model_tools(tools)
        raw = self._request_completion(
            messages,
            model_tools,
            max_tokens=max_tokens,
            tool_choice="auto",
        )
        return _parse_chat_turn_completion(
            raw,
            provider=self.provider,
            fallback_model=self.model,
        )

    def _request_completion(
        self,
        messages: list[dict[str, str]],
        model_tools: list[dict[str, Any]],
        *,
        max_tokens: int,
        tool_choice: str,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": copy.deepcopy(messages),
            "tools": [_to_openai_tool(tool) for tool in model_tools],
            "tool_choice": tool_choice,
            "thinking": {"type": "disabled"},
            "temperature": 0,
            "max_tokens": max_tokens,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        return self._transport(
            f"{self.base_url}/chat/completions",
            payload,
            headers,
            self.timeout,
        )


def resolve_llm_tool_call_provider(
    environ: Mapping[str, str] | None = None,
    *,
    transport: Transport | None = None,
) -> LLMProviderResolution:
    """Resolve the configured model tool-call provider without exposing secrets."""

    env = os.environ if environ is None else environ
    provider_name = _normalized_provider_name(_env_string(env, "ISOTOPE_LLM_PROVIDER"))
    if not provider_name:
        provider_name = "deepseek" if _env_string(env, "DEEPSEEK_API_KEY") else ""
    if not provider_name:
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_not_configured",
            provider_name="auto",
        )
    if provider_name != "deepseek":
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_unsupported",
            provider_name=provider_name,
        )

    api_key = _env_string(env, "ISOTOPE_LLM_API_KEY") or _env_string(env, "DEEPSEEK_API_KEY")
    if not api_key:
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_api_key_missing",
            provider_name=provider_name,
        )

    timeout = _resolve_provider_timeout(env)
    if timeout is None:
        return LLMProviderResolution(
            status="missing_configuration",
            reason_code="llm_provider_invalid_configuration",
            provider_name=provider_name,
        )

    provider = DeepSeekToolCallProvider(
        api_key=api_key,
        model=_env_string(env, "ISOTOPE_LLM_MODEL")
        or _env_string(env, "DEEPSEEK_MODEL")
        or "deepseek-v4-flash",
        base_url=_env_string(env, "ISOTOPE_LLM_BASE_URL")
        or _env_string(env, "DEEPSEEK_BASE_URL")
        or "https://api.deepseek.com",
        timeout=timeout,
        transport=transport,
    )
    return LLMProviderResolution(
        status="configured",
        reason_code="llm_provider_configured",
        provider_name=provider.provider,
        provider=provider,
    )


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
        raise KernelError(
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
    except KernelError:
        raise
    except ValueError as exc:
        raise KernelError(
            "model provider did not return a valid tool call",
            code="llm_tool_call_invalid_response",
            category="validation",
            retryable=False,
            http_status=400,
            details={"provider": _safe_provider_name(provider)},
        ) from exc
    except RuntimeError as exc:
        raise KernelError(
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
        raise KernelError(
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
        raise KernelError(
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
    raise KernelError(
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
        raise KernelError(
            "provider selected a tool that was not offered",
            code="llm_provider_selected_unoffered_tool",
            category="not_enabled",
            retryable=False,
            http_status=501,
            details={"tool_names": [provider_tool_name]},
        )
    return provider_tool_name


def build_llm_tool_result_message(
    llm_result: dict[str, Any],
    tool_execution_result: dict[str, Any],
) -> dict[str, str]:
    """Build a low-sensitive tool-result message for the originating model call."""

    if not isinstance(llm_result, dict):
        raise KernelError(
            "llm tool result source must be a dict",
            code="llm_tool_result_invalid_source",
            category="validation",
            retryable=False,
            http_status=400,
            details={"field": "llm_result"},
        )
    if not isinstance(tool_execution_result, dict):
        raise KernelError(
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
    """Send a low-sensitive tool result back to the provider for one follow-up choice."""

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
        raise KernelError(
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
        raise KernelError(
            "run is not open for tool-result follow-up submission",
            code="run_not_open_for_followup_submission",
            category="conflict",
            retryable=False,
            http_status=409,
            details={"run_id": run_id, "status": status},
        )


def _urllib_transport(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"DeepSeek API request failed with HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"DeepSeek API request failed: {exc.reason}") from exc


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
    except KernelError:
        raise
    except ValueError as exc:
        raise KernelError(
            "model provider did not return a valid follow-up tool call",
            code="llm_tool_call_invalid_response",
            category="validation",
            retryable=False,
            http_status=400,
            details={"provider": _safe_provider_name(provider)},
        ) from exc
    except RuntimeError as exc:
        raise KernelError(
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
        raise KernelError(
            "provider selected a tool that is not enabled",
            code="llm_tool_not_enabled",
            category="not_enabled",
            retryable=False,
            http_status=501,
            details={"tool_names": [tool_name]},
        )
    return provider_response, tool_result_message, tool_result_content


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
    except KernelError:
        raise
    except ValueError as exc:
        raise KernelError(
            "model provider did not return a valid chat turn",
            code="llm_chat_turn_invalid_response",
            category="validation",
            retryable=False,
            http_status=400,
            details={"provider": _safe_provider_name(provider)},
        ) from exc
    except RuntimeError as exc:
        raise KernelError(
            "model provider chat-turn request failed",
            code="llm_provider_request_failed",
            category="internal",
            retryable=True,
            http_status=502,
            details={"provider": _safe_provider_name(provider)},
        ) from exc

    if isinstance(response, (LLMToolCallResponse, LLMFinalAnswerResponse)):
        return response
    raise KernelError(
        "model provider did not return a valid chat turn",
        code="llm_chat_turn_invalid_response",
        category="validation",
        retryable=False,
        http_status=400,
        details={"provider": _safe_provider_name(provider)},
    )


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
        raise KernelError(
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
    raise KernelError(
        "llm tool result is missing required metadata",
        code=code,
        category="validation",
        retryable=False,
        http_status=400,
        details={"field": field_name},
    )


def _safe_tool_result_artifact_ref(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise KernelError(
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
            raise KernelError(
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
        raise KernelError(
            "llm tool result message has invalid content",
            code="llm_tool_result_invalid_execution",
            category="validation",
            retryable=False,
            http_status=400,
            details={"field": "content"},
        ) from exc
    if not isinstance(content, dict):
        raise KernelError(
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
        raise KernelError(
            "model provider did not return a valid final answer",
            code="llm_final_answer_invalid_response",
            category="validation",
            retryable=False,
            http_status=400,
            details={"provider": provider},
        )
    return value


__all__ = [
    "DeepSeekChatProvider",
    "DeepSeekToolCallProvider",
    "LLMChatTurnResponse",
    "LLMFinalAnswerResponse",
    "LLMProviderResolution",
    "LLMResponse",
    "LLMToolCall",
    "LLMToolCallResponse",
    "ToolCallProvider",
    "build_llm_tool_result_message",
    "resolve_llm_tool_call_provider",
    "select_llm_tool_result_followup",
    "submit_llm_chat_turn",
    "submit_llm_tool_result_followup",
    "submit_llm_tool_call",
]
