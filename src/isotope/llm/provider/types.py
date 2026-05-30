"""Shared LLM provider data contracts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


Transport = Callable[[str, dict[str, Any], dict[str, str], int], dict[str, Any]]
StreamTransport = Callable[
    [str, dict[str, Any], dict[str, str], int],
    Iterable[dict[str, Any]],
]


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


@dataclass(frozen=True)
class LLMStreamChunk:
    provider: str
    model: str
    content: str
    raw: dict[str, Any] = field(default_factory=dict)


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
