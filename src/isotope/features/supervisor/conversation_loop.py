"""Product-level Supervisor conversation loop over capabilities and agent loop."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from isotope.capabilities.runner import CapabilityRunner
from isotope.llm.provider import LLMResponse

from .desktop_chat_context import compact_desktop_chat_history_messages


class SupervisorConversationProvider(Protocol):
    provider: str
    model: str

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        raise NotImplementedError


@dataclass(frozen=True)
class SupervisorConversationEvent:
    event: str
    payload: dict[str, Any]
    provider: str = "unknown"
    model: str = "unknown"


def run_supervisor_conversation_events(
    *,
    state_root: Path | str,
    cwd: Path | str,
    user_message: str,
    provider: SupervisorConversationProvider,
    max_tokens: int = 512,
    history: list[dict[str, str]] | None = None,
    capacity_runner: CapabilityRunner | None = None,
    max_turns: int = 3,
) -> Iterator[SupervisorConversationEvent]:
    clean_message = _require_text(user_message, "user_message")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ValueError("max_tokens must be a positive integer")
    if isinstance(max_turns, bool) or not isinstance(max_turns, int) or max_turns <= 0:
        raise ValueError("max_turns must be a positive integer")
    context = _conversation_context(
        state_root=Path(state_root).expanduser(),
        cwd=Path(cwd).expanduser(),
        capacity_runner=capacity_runner,
    )
    response = provider.generate(
        _conversation_messages(clean_message, context, history=history),
        max_tokens=max_tokens,
    )
    answer = _plain_text_or_direct_answer(response.content)
    if not answer:
        raise ValueError("provider returned empty answer")
    yield SupervisorConversationEvent(
        event="delta",
        payload={"text": answer},
        provider=response.provider,
        model=response.model,
    )


def _conversation_context(
    *,
    state_root: Path,
    cwd: Path,
    capacity_runner: CapabilityRunner | None,
) -> dict[str, Any]:
    runner = capacity_runner if capacity_runner is not None else CapabilityRunner()
    capabilities = [
        {
            "capability_id": capability.get("capability_id"),
            "title": capability.get("title"),
            "description": capability.get("description"),
            "shelf": capability.get("shelf"),
            "domain_tags": capability.get("domain_tags"),
            "input_contract": capability.get("input_contract"),
        }
        for capability in runner.list_capabilities()
    ]
    return {
        "kind": "supervisor_conversation_context",
        "entrypoint": "desktop_chat",
        "system_context": {
            "state_root": str(state_root),
            "root": str(state_root),
            "cwd": str(cwd),
        },
        "capacity_manifest": {
            "kind": "capacity_manifest",
            "source": "registered_capabilities",
            "capability_count": len(capabilities),
            "capabilities": capabilities,
        },
    }


def _conversation_messages(
    user_message: str,
    context: dict[str, Any],
    *,
    history: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    messages = [
        {
            "role": "system",
            "content": (
                "你是 Isotope Supervisor 的对话 agent。可以直接回答，也可以返回 "
                "JSON 决策调用 capability 或记录 capability gap。系统会校验并执行。"
            ),
        },
        {
            "role": "system",
            "content": "supervisor_conversation_context:\n"
            + json.dumps(context, ensure_ascii=False, sort_keys=True),
        },
    ]
    messages.extend(_history_messages(history))
    messages.append({"role": "user", "content": user_message})
    return messages


def _history_messages(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    if history is None:
        return []
    clean: list[dict[str, str]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        stripped = content.strip()
        if stripped:
            clean.append({"role": role, "content": stripped})
    return compact_desktop_chat_history_messages(clean)


def _plain_text_or_direct_answer(content: str) -> str:
    stripped = _require_text(content, "provider response")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    if not isinstance(payload, dict):
        return stripped
    if payload.get("kind") != "direct_answer":
        return stripped
    answer = payload.get("answer")
    return answer.strip() if isinstance(answer, str) else ""


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()
