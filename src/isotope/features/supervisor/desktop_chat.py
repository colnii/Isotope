"""Desktop chat answer flow over the low-sensitive Supervisor snapshot."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from isotope.capabilities.runner import CapabilityRunner
from isotope.capabilities.supervisor import SUPERVISOR_CODEX_OPERATION_CAPABILITY
from isotope.llm.provider import LLMResponse, LLMStreamChunk

from .state.projection import build_supervisor_state_snapshot


class DesktopChatProvider(Protocol):
    provider: str
    model: str

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        ...


@dataclass(frozen=True)
class DesktopChatAnswer:
    question: str
    answer: str
    provider: str
    model: str

    def done_payload(self) -> dict[str, str]:
        return {
            "status": "ok",
            "provider": self.provider,
            "model": self.model,
        }


def answer_desktop_chat(
    *,
    codex_home: Path | str,
    question: str,
    provider: DesktopChatProvider,
    max_tokens: int = 512,
) -> DesktopChatAnswer:
    clean_question = _require_question(question)
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ValueError("max_tokens must be a positive integer")
    supervisor_context = build_supervisor_chat_context(codex_home=codex_home)
    response = provider.generate(
        _desktop_chat_messages(clean_question, supervisor_context),
        max_tokens=max_tokens,
    )
    answer = response.content.strip()
    if not answer:
        raise ValueError("provider returned empty answer")
    return DesktopChatAnswer(
        question=clean_question,
        answer=answer,
        provider=response.provider,
        model=response.model,
    )


def stream_desktop_chat(
    *,
    codex_home: Path | str,
    question: str,
    provider: DesktopChatProvider,
    max_tokens: int = 512,
) -> Iterator[LLMStreamChunk]:
    clean_question = _require_question(question)
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ValueError("max_tokens must be a positive integer")
    stream_generate = getattr(provider, "stream_generate", None)
    if callable(stream_generate):
        supervisor_context = build_supervisor_chat_context(codex_home=codex_home)
        yielded = False
        for chunk in stream_generate(
            _desktop_chat_messages(clean_question, supervisor_context),
            max_tokens=max_tokens,
        ):
            if not isinstance(chunk, LLMStreamChunk):
                raise ValueError("provider returned malformed stream chunk")
            if not chunk.content:
                continue
            yielded = True
            yield chunk
        if not yielded:
            raise ValueError("provider returned empty answer")
        return

    answer = answer_desktop_chat(
        codex_home=codex_home,
        question=clean_question,
        provider=provider,
        max_tokens=max_tokens,
    )
    for chunk in desktop_chat_answer_chunks(answer.answer):
        yield LLMStreamChunk(
            provider=answer.provider,
            model=answer.model,
            content=chunk,
            raw={},
        )


def desktop_chat_answer_chunks(answer: str, *, chunk_size: int = 12) -> list[str]:
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")
    return [answer[index : index + chunk_size] for index in range(0, len(answer), chunk_size)]


def _desktop_chat_messages(
    question: str,
    supervisor_context: dict[str, Any],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是 Isotope 的产品内 AI 助手，服务对象是正在开发和调试 "
                "Isotope 的用户。你可以回答当前状态、架构、capacity、loop、"
                "前后端接线和下一步排障。回答时结合 supervisor_context "
                "自然说明你能确认的内容；信息不够时直接说还缺什么。中文、直接。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": question,
                    "supervisor_context": supervisor_context,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    ]


def build_supervisor_chat_context(*, codex_home: Path | str) -> dict[str, Any]:
    capabilities = [
        _desktop_chat_capability_summary(capability)
        for capability in CapabilityRunner().list_capabilities()
    ]
    return {
        "state": build_supervisor_state_snapshot(codex_home=codex_home),
        "capability_count": len(capabilities),
        "capabilities": capabilities,
        "loop_capacity_path": {
            "chat_entry": "/desktop/chat",
            "agent_loop_capacity_call": "call_capacity",
            "codex_operation_capacity": SUPERVISOR_CODEX_OPERATION_CAPABILITY,
            "execution_note": (
                "desktop_chat answers from context; Supervisor loop executes "
                "capacity calls through agent_loop"
            ),
        },
    }


def _desktop_chat_capability_summary(capability: dict[str, Any]) -> dict[str, Any]:
    input_contract = capability.get("input_contract")
    properties = (
        input_contract.get("properties", {})
        if isinstance(input_contract, dict)
        else {}
    )
    operation_property = (
        properties.get("operation", {}) if isinstance(properties, dict) else {}
    )
    operations = (
        operation_property.get("enum")
        if isinstance(operation_property, dict)
        else None
    )
    return _omit_empty(
        {
            "capability_id": capability.get("capability_id"),
            "title": capability.get("title"),
            "description": capability.get("description"),
            "shelf": capability.get("shelf"),
            "domain_tags": capability.get("domain_tags"),
            "required_inputs": (
                input_contract.get("required", [])
                if isinstance(input_contract, dict)
                else []
            ),
            "operations": operations,
            "network_required": capability.get("network_required"),
        }
    )


def _omit_empty(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item not in (None, "", [], {})
    }


def _require_question(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("question must be a string")
    stripped = value.strip()
    if not stripped:
        raise ValueError("question must not be empty")
    return stripped
