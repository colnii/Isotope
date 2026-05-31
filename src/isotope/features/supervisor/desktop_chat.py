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

from .desktop_snapshot import build_desktop_snapshot


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
    snapshot = build_desktop_snapshot(codex_home=codex_home)
    response = provider.generate(
        _desktop_chat_messages(clean_question, snapshot),
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
        snapshot = build_desktop_snapshot(codex_home=codex_home)
        yielded = False
        for chunk in stream_generate(
            _desktop_chat_messages(clean_question, snapshot),
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


def _desktop_chat_messages(question: str, snapshot: dict[str, Any]) -> list[dict[str, str]]:
    desktop_context = build_desktop_chat_context()
    return [
        {
            "role": "system",
            "content": (
                "你是 Isotope 桌面端助手。根据提供的低敏 Supervisor 状态和 "
                "desktop_context 回答。不要编造不存在的 worker、goal、approval "
                "或 artifact。用户问 capacity、loop、backend wiring 时，优先使用 "
                "desktop_context.capabilities 和 loop_capacity_path；不要因为 "
                "Supervisor idle 就说 capacity 没接入。/desktop/chat 只解释和展示"
                "这些低敏上下文，不直接执行 capacity；真正执行发生在 Supervisor "
                "loop 的 call_capacity/agent_loop 路径。回答要短，用中文，说人话。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": question,
                    "desktop_snapshot": snapshot,
                    "desktop_context": desktop_context,
                    "output_requirements": [
                        "不要输出 JSON",
                        "一到三句话",
                        "只描述低敏状态",
                        "capacity 或 loop 接线问题要回答已注册的 capability 和当前执行边界",
                        "不要说 /desktop/chat 会直接触发或执行 capacity",
                        "能给下一步就给下一步",
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    ]


def build_desktop_chat_context() -> dict[str, Any]:
    return {
        "capabilities": [
            _desktop_chat_capability_summary(capability)
            for capability in CapabilityRunner().list_capabilities()
        ],
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
