"""Product-level Supervisor conversation loop over capabilities and agent loop."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from isotope.capabilities.runner import CapabilityRunner
from isotope.features.supervisor.commands.handlers.capacity import (
    _execute_agent_loop_capacity_step,
    agent_loop_json_summary,
)
from isotope.llm.prompts import render_json_prompt_template
from isotope.llm.provider import LLMResponse
from isotope.platform.schemas.input_contract import contract_properties

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
    timeout_seconds: float | None = None,
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
        response = _generate_with_timeout(
            provider,
            messages=_conversation_messages(
                clean_message,
                context,
                history=history,
                observations=observations,
            ),
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
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
                timeout_seconds=timeout_seconds,
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
        if decision["kind"] == "report_capability_gap":
            gap = _record_capability_gap(
                decision,
                state_root=Path(state_root).expanduser(),
                user_message=clean_message,
                source_entrypoint=str(context.get("entrypoint", "desktop_chat")),
            )
            yield SupervisorConversationEvent(event="capability_gap", payload=gap)
            yield SupervisorConversationEvent(
                event="delta",
                payload={"text": "我缺少对应的基础能力，已记录 capability gap。"},
                provider=response.provider,
                model=response.model,
            )
            return
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
            **_conversation_capability_summary(capability),
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
            "content": render_json_prompt_template(
                "supervisor_conversation_loop",
                {"capacity_manifest": context["capacity_manifest"]},
            ),
        },
    ]
    if observations:
        messages.append(
            {
                "role": "user",
                "content": _json_context_message(
                    "capacity_observation",
                    {"kind": "capacity_observations", "items": observations},
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


def _json_context_message(label: str, value: dict[str, Any]) -> str:
    return f"{label}:\n" + json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
    )


def _generate_with_timeout(
    provider: SupervisorConversationProvider,
    *,
    messages: list[dict[str, str]],
    max_tokens: int,
    timeout_seconds: float | None,
) -> LLMResponse:
    if timeout_seconds is None:
        return provider.generate(messages, max_tokens=max_tokens)
    if timeout_seconds <= 0:
        raise TimeoutError("desktop chat response timed out")
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(provider.generate, messages, max_tokens=max_tokens)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        future.cancel()
        raise TimeoutError("desktop chat response timed out") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _conversation_capability_summary(capability: dict[str, Any]) -> dict[str, Any]:
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
            "input_properties": _conversation_input_properties(properties),
            "operations": operations,
            "network_required": capability.get("network_required"),
        }
    )


def _conversation_input_properties(
    properties: dict[str, Any] | Any,
) -> dict[str, dict[str, Any]]:
    if not isinstance(properties, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for name, schema in properties.items():
        if not isinstance(name, str) or not isinstance(schema, dict):
            continue
        summary = {
            key: schema[key]
            for key in ("type", "enum", "default", "description")
            if key in schema
        }
        if summary:
            result[name] = summary
    return result


def _omit_empty(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item not in (None, [], {})
    }


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
    timeout_seconds: float | None,
) -> Iterator[SupervisorConversationEvent]:
    capacity_id = _require_text(decision.get("capacity_id"), "capacity_id")
    arguments = decision.get("arguments", {})
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    inputs = _capability_inputs_from_decision(
        capacity_id,
        arguments=arguments,
        context=context,
    )
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
    try:
        agent_loop = _execute_capacity_step_with_timeout(
            goal=f"Conversation capability call: {capacity_id}",
            capability_id=capacity_id,
            inputs=inputs,
            state_root=state_root / "supervisor" / "conversation-loop-runs",
            timeout_seconds=timeout_seconds,
        )
        result_summary = agent_loop_json_summary({"agent_loop": agent_loop})
        status = (
            "ok"
            if result_summary.get("agent_loop_tick_status") == "executed"
            else "blocked"
        )
    except Exception as exc:  # noqa: BLE001 - stream low-sensitive capacity failure.
        result_summary = {
            "error_type": type(exc).__name__,
            "message": str(exc) or type(exc).__name__,
        }
        status = "error"
    yield SupervisorConversationEvent(
        event="capacity_result",
        payload={
            "id": _capacity_event_id(capacity_id),
            "capacity_id": capacity_id,
            "title": capacity_id,
            "status": status,
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


def _execute_capacity_step_with_timeout(
    *,
    goal: str,
    capability_id: str,
    inputs: dict[str, Any],
    state_root: Path,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    if timeout_seconds is None:
        return _execute_agent_loop_capacity_step(
            goal=goal,
            capability_id=capability_id,
            inputs=inputs,
            state_root=state_root,
        )
    if timeout_seconds <= 0:
        raise TimeoutError("capacity execution timed out")
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(
        _execute_agent_loop_capacity_step,
        goal=goal,
        capability_id=capability_id,
        inputs=inputs,
        state_root=state_root,
    )
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        future.cancel()
        raise TimeoutError("capacity execution timed out") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _capability_inputs_from_decision(
    capacity_id: str,
    *,
    arguments: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    allowed_inputs = _capability_input_names(capacity_id)
    if not allowed_inputs:
        return dict(arguments)
    inputs = {
        key: value
        for key, value in arguments.items()
        if isinstance(key, str) and key in allowed_inputs
    }
    system_context = context.get("system_context")
    if isinstance(system_context, dict):
        for key, value in system_context.items():
            if key in allowed_inputs:
                inputs[key] = value
    inputs = _normalize_conversation_capability_inputs(capacity_id, inputs)
    return inputs


def _normalize_conversation_capability_inputs(
    capacity_id: str,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    if capacity_id != "research.search":
        return inputs
    if inputs.get("provider") == "tavily":
        return inputs
    return {
        key: value
        for key, value in inputs.items()
        if key not in {"allow_network", "tavily_max_results"}
    }


def _capability_input_names(capacity_id: str) -> set[str]:
    try:
        capability = CapabilityRunner().describe_capability(capacity_id)
    except ValueError:
        return set()
    input_contract = capability.get("input_contract")
    properties = contract_properties(
        input_contract if isinstance(input_contract, dict) else {}
    )
    return set(properties)


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


def _record_capability_gap(
    decision: dict[str, Any],
    *,
    state_root: Path,
    user_message: str,
    source_entrypoint: str,
) -> dict[str, Any]:
    raw_gap = decision.get("gap", {})
    if not isinstance(raw_gap, dict):
        raw_gap = {}
    gap_id = "gap_" + uuid4().hex[:12]
    payload = {
        "kind": "capability_gap",
        "gap_id": gap_id,
        "status": "recorded",
        "missing_capability_kind": _safe_string(
            raw_gap.get("missing_capability_kind"),
            default="unknown",
        ),
        "reason": _safe_string(raw_gap.get("reason"), default="capability gap reported"),
        "needed_context": _safe_string_list(raw_gap.get("needed_context")),
        "user_goal_summary": user_message[:500],
        "suggested_next_capability": _safe_string(
            raw_gap.get("suggested_next_capability"),
            default="",
        ),
        "source_entrypoint": source_entrypoint,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    gap_dir = state_root / "supervisor" / "capability-gaps"
    gap_dir.mkdir(parents=True, exist_ok=True)
    (gap_dir / f"{gap_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return payload


def _safe_string(value: Any, *, default: str) -> str:
    if not isinstance(value, str):
        return default
    stripped = value.strip()
    if not stripped:
        return default
    return stripped[:1000]


def _safe_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:20]:
        if isinstance(item, str) and item.strip():
            result.append(item.strip()[:500])
    return result


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()
