"""OpenAI-compatible LLM provider clients."""

from __future__ import annotations

import copy
import json
import os
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

from .parsing import (
    _is_length_limited_reasoning_only_response,
    _parse_chat_completion,
    _parse_chat_turn_completion,
    _parse_tool_call_completion,
    _require_non_empty_string,
    _stream_chat_completion_chunks,
    _to_openai_tool,
    _validate_messages,
    _validate_model_tools,
)
from .types import (
    LLMChatTurnResponse,
    LLMResponse,
    LLMStreamChunk,
    LLMToolCallResponse,
    StreamTransport,
    Transport,
)


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
        stream_transport: StreamTransport | None = None,
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
        self._stream_transport = (
            stream_transport if stream_transport is not None else _urllib_stream_transport
        )

    def generate(
        self,
        messages: list[dict[str, Any]],
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
        if _is_length_limited_reasoning_only_response(raw):
            retry_payload = copy.deepcopy(payload)
            retry_payload["thinking"] = {"type": "disabled"}
            raw = self._transport(
                f"{self.base_url}/chat/completions",
                retry_payload,
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                self.timeout,
            )
        return _parse_chat_completion(raw, provider=self.provider, fallback_model=self.model)

    def stream_generate(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 512,
    ) -> Iterator[LLMStreamChunk]:
        _validate_messages(messages)
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")

        payload = {
            "model": self.model,
            "messages": copy.deepcopy(messages),
            "thinking": {"type": "disabled"},
            "temperature": 0,
            "max_tokens": max_tokens,
            "stream": True,
        }
        return _stream_chat_completion_chunks(
            self._stream_transport(
                f"{self.base_url}/chat/completions",
                payload,
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                self.timeout,
            ),
            provider=self.provider,
            fallback_model=self.model,
        )


class OpenAICompatibleChatProvider:
    """Generic OpenAI-compatible chat provider using only stdlib HTTP."""

    def __init__(
        self,
        *,
        provider: str,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int = 60,
        transport: Transport | None = None,
        stream_transport: StreamTransport | None = None,
    ) -> None:
        self.provider = _require_non_empty_string("provider", provider)
        self.api_key = _require_non_empty_string("api_key", api_key)
        self.base_url = _require_non_empty_string("base_url", base_url).rstrip("/")
        self.model = _require_non_empty_string("model", model)
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError("timeout must be a positive integer")
        self.timeout = timeout
        self._transport = transport if transport is not None else _urllib_transport
        self._stream_transport = (
            stream_transport if stream_transport is not None else _urllib_stream_transport
        )

    def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        _validate_messages(messages)
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")

        payload = {
            "model": self.model,
            "messages": copy.deepcopy(messages),
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
        if _is_length_limited_reasoning_only_response(raw):
            retry_payload = copy.deepcopy(payload)
            retry_payload["thinking"] = {"type": "disabled"}
            raw = self._transport(
                f"{self.base_url}/chat/completions",
                retry_payload,
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                self.timeout,
            )
        return _parse_chat_completion(raw, provider=self.provider, fallback_model=self.model)

    def stream_generate(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 512,
    ) -> Iterator[LLMStreamChunk]:
        _validate_messages(messages)
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")

        payload = {
            "model": self.model,
            "messages": copy.deepcopy(messages),
            "temperature": 0,
            "max_tokens": max_tokens,
            "stream": True,
        }
        return _stream_chat_completion_chunks(
            self._stream_transport(
                f"{self.base_url}/chat/completions",
                payload,
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                self.timeout,
            ),
            provider=self.provider,
            fallback_model=self.model,
        )


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


def _urllib_stream_transport(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: int,
) -> Iterator[dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line or line.startswith(":") or not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    break
                try:
                    yield json.loads(data)
                except json.JSONDecodeError as exc:
                    raise RuntimeError("LLM stream returned invalid JSON") from exc
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"DeepSeek API request failed with HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"DeepSeek API request failed: {exc.reason}") from exc
