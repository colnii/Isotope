"""Product-level Supervisor conversation loop over capabilities and agent loop."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from isotope.capabilities.runner import CapabilityRunner
from isotope.features.supervisor.commands.handlers.capacity import (
    _execute_agent_loop_capacity_step,
    agent_loop_json_summary,
)
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
    observations: list[dict[str, Any]] = []
    for _turn_index in range(max_turns):
        response = provider.generate(
            _conversation_messages(
                clean_message,
                context,
                history=history,
                observations=observations,
            ),
            max_tokens=max_tokens,
        )
        decision = _parse_decision(response.content)
        if decision["kind"] == "direct_answer":
            answer = _require_text(decision.get("answer"), "answer")
            yield SupervisorConversationEvent(
                event="delta",
                payload={"text": answer},
                provider=response.provider,
                model=response.model,
            )
            return
        if decision["kind"] == "call_capability":
            for event in _run_capability_decision(
                decision,
                state_root=Path(state_root).expanduser(),
                context=context,
            ):
                yield event
                if event.event == "capacity_result":
                    observations.append(
                        {
                            "kind": "capacity_observation",
                            "capacity_id": event.payload["capacity_id"],
                            "status": event.payload["status"],
                            "result_summary": event.payload.get("result_summary", {}),
                        }
                    )
            continue
    raise ValueError("conversation loop exhausted max_turns without a direct answer")


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
    observations: list[dict[str, Any]] | None = None,
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
    if observations:
        messages.append(
            {
                "role": "system",
                "content": "capacity_observation:\n"
                + json.dumps(
                    {"kind": "capacity_observations", "items": observations},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            }
        )
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


def _parse_decision(content: str) -> dict[str, Any]:
    stripped = _require_text(content, "provider response")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return {"kind": "direct_answer", "answer": stripped}
    if not isinstance(payload, dict):
        return {"kind": "direct_answer", "answer": stripped}
    kind = payload.get("kind")
    if kind not in {"direct_answer", "call_capability", "report_capability_gap"}:
        return {"kind": "direct_answer", "answer": stripped}
    return dict(payload)


def _run_capability_decision(
    decision: dict[str, Any],
    *,
    state_root: Path,
    context: dict[str, Any],
) -> Iterator[SupervisorConversationEvent]:
    capacity_id = _require_text(decision.get("capacity_id"), "capacity_id")
    arguments = decision.get("arguments", {})
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    inputs = {
        **arguments,
        **{
            key: value
            for key, value in context["system_context"].items()
            if key not in arguments
        },
    }
    yield SupervisorConversationEvent(
        event="capacity_start",
        payload={
            "id": _capacity_event_id(capacity_id),
            "capacity_id": capacity_id,
            "title": capacity_id,
            "status": "running",
            "input_summary": _safe_detail_value(inputs),
            "result_summary": {},
            "details": [
                {
                    "label": "Inputs",
                    "kind": "json",
                    "content": _safe_detail_value(inputs),
                }
            ],
        },
    )
    agent_loop = _execute_agent_loop_capacity_step(
        goal=f"Conversation capability call: {capacity_id}",
        capability_id=capacity_id,
        inputs=inputs,
        state_root=state_root / "supervisor" / "conversation-loop-runs",
    )
    result_summary = agent_loop_json_summary({"agent_loop": agent_loop})
    yield SupervisorConversationEvent(
        event="capacity_result",
        payload={
            "id": _capacity_event_id(capacity_id),
            "capacity_id": capacity_id,
            "title": capacity_id,
            "status": (
                "ok"
                if result_summary.get("agent_loop_tick_status") == "executed"
                else "blocked"
            ),
            "input_summary": _safe_detail_value(inputs),
            "result_summary": _safe_detail_value(result_summary),
            "details": [
                {
                    "label": "Inputs",
                    "kind": "json",
                    "content": _safe_detail_value(inputs),
                },
                {
                    "label": "Result summary",
                    "kind": "json",
                    "content": _safe_detail_value(result_summary),
                },
            ],
        },
    )


def _capacity_event_id(capacity_id: str) -> str:
    safe = "".join(char if char.isalnum() else "_" for char in capacity_id.lower())
    return f"capacity_{safe.strip('_') or 'unknown'}"


def _safe_detail_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return "[truncated: nested content]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 40:
                result["truncated"] = "object contained more than 40 keys"
                break
            if not isinstance(key, str) or _unsafe_detail_key(key):
                continue
            result[key] = _safe_detail_value(item, depth=depth + 1)
        return result
    if isinstance(value, list):
        items = [_safe_detail_value(item, depth=depth + 1) for item in value[:20]]
        if len(value) > 20:
            items.append({"truncated": f"list contained {len(value)} items"})
        return items
    if isinstance(value, str):
        return value if len(value) <= 4000 else value[:4000] + "\n[truncated]"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def _unsafe_detail_key(key: str) -> bool:
    lowered = key.lower()
    return any(
        marker in lowered
        for marker in (
            "api_key",
            "apikey",
            "secret",
            "token",
            "raw",
            "messages",
            "prompt",
            "transcript",
        )
    )


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()
