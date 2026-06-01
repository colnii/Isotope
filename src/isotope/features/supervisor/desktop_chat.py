"""Desktop chat answer flow over registered capacity metadata."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from time import monotonic
from typing import Any, Protocol

from isotope.capabilities.runner import CapabilityRunner
from isotope.features.supervisor.commands.handlers.capacity import (
    build_supervisor_capacity_plan,
)
from isotope.llm.capacity_calling import CapacityCallingProvider
from isotope.llm.prompts import load_system_prompt
from isotope.llm.provider import LLMResponse, LLMStreamChunk

from .desktop_chat_context import compact_desktop_chat_history_messages


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


@dataclass(frozen=True)
class DesktopChatStreamEvent:
    event: str
    payload: dict[str, Any]
    provider: str = "unknown"
    model: str = "unknown"


def answer_desktop_chat(
    *,
    codex_home: Path | str,
    question: str,
    provider: DesktopChatProvider,
    max_tokens: int = 512,
    history: list[dict[str, str]] | None = None,
) -> DesktopChatAnswer:
    clean_question = _require_question(question)
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ValueError("max_tokens must be a positive integer")
    chat_context = build_desktop_chat_context()
    response = _desktop_chat_response(
        clean_question,
        chat_context,
        provider=provider,
        max_tokens=max_tokens,
        history=history,
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


def stream_desktop_chat_events(
    *,
    codex_home: Path | str,
    question: str,
    provider: DesktopChatProvider,
    max_tokens: int = 512,
    capacity_provider: CapacityCallingProvider | None = None,
    capacity_runner: CapabilityRunner | None = None,
    capacity_timeout_seconds: float = 3.0,
    chat_timeout_seconds: float = 18.0,
    history: list[dict[str, str]] | None = None,
) -> Iterator[DesktopChatStreamEvent]:
    clean_question = _require_question(question)
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ValueError("max_tokens must be a positive integer")
    chat_context = build_desktop_chat_context(capacity_runner=capacity_runner)
    if capacity_provider is not None:
        for event in _desktop_chat_capacity_events(
            codex_home=codex_home,
            question=clean_question,
            provider=capacity_provider,
            runner=capacity_runner,
            timeout_seconds=capacity_timeout_seconds,
        ):
            chat_context["capacity_result"] = event.payload
            yield event
    for chunk in _stream_desktop_chat_chunks_with_timeout(
        clean_question,
        chat_context,
        provider=provider,
        max_tokens=max_tokens,
        timeout_seconds=chat_timeout_seconds,
        history=history,
    ):
        yield DesktopChatStreamEvent(
            event="delta",
            payload={"text": chunk.content},
            provider=chunk.provider,
            model=chunk.model,
        )


def _desktop_chat_response(
    question: str,
    chat_context: dict[str, Any],
    *,
    provider: DesktopChatProvider,
    max_tokens: int,
    history: list[dict[str, str]] | None = None,
) -> LLMResponse:
    response = provider.generate(
        _desktop_chat_messages(question, chat_context, history=history),
        max_tokens=max_tokens,
    )
    if not response.content.strip():
        raise ValueError("provider returned empty answer")
    return response


def stream_desktop_chat(
    *,
    codex_home: Path | str,
    question: str,
    provider: DesktopChatProvider,
    max_tokens: int = 512,
    history: list[dict[str, str]] | None = None,
) -> Iterator[LLMStreamChunk]:
    clean_question = _require_question(question)
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ValueError("max_tokens must be a positive integer")
    chat_context = build_desktop_chat_context()
    yield from _stream_desktop_chat_chunks(
        clean_question,
        chat_context,
        provider=provider,
        max_tokens=max_tokens,
        history=history,
    )


def _stream_desktop_chat_chunks(
    question: str,
    chat_context: dict[str, Any],
    *,
    provider: DesktopChatProvider,
    max_tokens: int,
    history: list[dict[str, str]] | None = None,
) -> Iterator[LLMStreamChunk]:
    stream_generate = getattr(provider, "stream_generate", None)
    if callable(stream_generate):
        yielded = False
        for chunk in stream_generate(
            _desktop_chat_messages(question, chat_context, history=history),
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

    response = _desktop_chat_response(
        question,
        chat_context,
        provider=provider,
        max_tokens=max_tokens,
        history=history,
    )
    for chunk in desktop_chat_answer_chunks(response.content.strip()):
        yield LLMStreamChunk(
            provider=response.provider,
            model=response.model,
            content=chunk,
            raw={},
        )


def _stream_desktop_chat_chunks_with_timeout(
    question: str,
    chat_context: dict[str, Any],
    *,
    provider: DesktopChatProvider,
    max_tokens: int,
    timeout_seconds: float,
    history: list[dict[str, str]] | None = None,
) -> Iterator[LLMStreamChunk]:
    if timeout_seconds <= 0:
        raise TimeoutError("desktop chat response timed out")
    queue: Queue[tuple[str, LLMStreamChunk | BaseException | None]] = Queue()

    def run_provider() -> None:
        try:
            for chunk in _stream_desktop_chat_chunks(
                question,
                chat_context,
                provider=provider,
                max_tokens=max_tokens,
                history=history,
            ):
                queue.put(("chunk", chunk))
            queue.put(("done", None))
        except BaseException as exc:  # noqa: BLE001 - forwarded to SSE error.
            queue.put(("error", exc))

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(run_provider)
    deadline = monotonic() + timeout_seconds
    try:
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                future.cancel()
                raise TimeoutError("desktop chat response timed out")
            try:
                kind, payload = queue.get(timeout=remaining)
            except Empty as exc:
                future.cancel()
                raise TimeoutError("desktop chat response timed out") from exc
            if kind == "chunk":
                if not isinstance(payload, LLMStreamChunk):
                    raise ValueError("provider returned malformed stream chunk")
                yield payload
            elif kind == "error":
                if isinstance(payload, BaseException):
                    raise payload
                raise RuntimeError("desktop chat provider failed")
            else:
                return
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def desktop_chat_answer_chunks(answer: str, *, chunk_size: int = 12) -> list[str]:
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")
    return [answer[index : index + chunk_size] for index in range(0, len(answer), chunk_size)]


def _desktop_chat_messages(
    question: str,
    chat_context: dict[str, Any],
    *,
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    capacity_manifest = _mapping(chat_context.get("capacity_manifest"))
    messages = [
        {
            "role": "system",
            "content": _desktop_chat_system_prompt(capacity_manifest),
        },
    ]
    capacity_result = _mapping(chat_context.get("capacity_result"))
    if capacity_result:
        messages.append(
            {
                "role": "system",
                "content": _json_context_message(
                    "capacity_result",
                    {
                        "kind": "capacity_result",
                        "result": capacity_result,
                    },
                ),
            }
        )
    messages.extend(_desktop_chat_history_messages(history))
    messages.append({"role": "user", "content": question})
    return messages


def _desktop_chat_system_prompt(capacity_manifest: dict[str, Any]) -> str:
    return "\n\n".join(
        (
            load_system_prompt("desktop_chat"),
            _json_context_message("capacity_manifest", capacity_manifest),
        )
    )


def _json_context_message(label: str, value: dict[str, Any]) -> str:
    return f"{label}:\n" + json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
    )


def _desktop_chat_history_messages(
    history: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    if history is None:
        return []
    messages: list[dict[str, str]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"}:
            continue
        if not isinstance(content, str):
            continue
        clean_content = content.strip()
        if not clean_content:
            continue
        messages.append({"role": role, "content": clean_content})
    return compact_desktop_chat_history_messages(messages)


def build_desktop_chat_context(
    *, capacity_runner: CapabilityRunner | None = None
) -> dict[str, Any]:
    runner = capacity_runner if capacity_runner is not None else CapabilityRunner()
    capabilities = [
        _desktop_chat_capability_summary(capability)
        for capability in runner.list_capabilities()
    ]
    return {
        "capacity_manifest": {
            "kind": "capacity_manifest",
            "source": "registered_capabilities",
            "capability_count": len(capabilities),
            "capabilities": capabilities,
        },
    }


def _desktop_chat_capacity_events(
    *,
    codex_home: Path | str,
    question: str,
    provider: CapacityCallingProvider,
    runner: CapabilityRunner | None,
    timeout_seconds: float,
) -> Iterator[DesktopChatStreamEvent]:
    root = Path(codex_home).expanduser()
    try:
        plan = _build_capacity_plan_with_timeout(
            timeout_seconds=timeout_seconds,
            goal=question,
            provider=provider,
            root=root,
            runner=runner,
        )
    except Exception as exc:  # noqa: BLE001 - chat should surface capacity failure safely.
        return
    if plan.get("status") == "skipped" and plan.get("status_reason") == "no_capacity":
        return
    result = _capacity_plan_projection(plan)
    yield DesktopChatStreamEvent(
        event="capacity_start",
        payload={
            **result,
            "status": "running",
            "result_summary": {},
            "details": [
                section
                for section in result["details"]
                if section.get("label") == "Inputs"
            ],
        },
    )
    yield DesktopChatStreamEvent(event="capacity_result", payload=result)


def _build_capacity_plan_with_timeout(
    *,
    timeout_seconds: float,
    goal: str,
    provider: CapacityCallingProvider,
    root: Path,
    runner: CapabilityRunner | None,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise TimeoutError("capacity selection timed out")
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(
        build_supervisor_capacity_plan,
        goal=goal,
        provider=provider,
        state_root=root / "supervisor" / "capacity-loop-runs",
        execute_agent_loop=True,
        runner=runner,
        input_defaults={
            "codex_home": str(root),
            "root": str(root),
            "run_id": "desktop_chat",
            "cwd": str(Path.cwd()),
        },
        allow_no_capacity=True,
    )
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        future.cancel()
        raise TimeoutError("capacity selection timed out") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _capacity_plan_projection(plan: dict[str, Any]) -> dict[str, Any]:
    selection = _mapping(plan.get("selection"))
    launch_plan = _mapping(plan.get("capability_launch_plan"))
    capacity_id = _string(
        selection.get("capacity_id")
        or launch_plan.get("capability_id")
        or _mapping(plan.get("supervisor_decision")).get("capacity_id")
        or "unknown"
    )
    arguments = _mapping(selection.get("arguments"))
    result_summary = _mapping(plan.get("agent_loop_summary"))
    status = "ok" if plan.get("status") == "ok" else "blocked"
    if plan.get("status_reason") not in (None, "ready"):
        result_summary = {
            **result_summary,
            "status_reason": plan.get("status_reason"),
        }
    details = [
        {
            "label": "Inputs",
            "kind": "json",
            "content": _safe_detail_value(arguments),
        }
    ]
    if selection:
        details.append(
            {
                "label": "Selection",
                "kind": "json",
                "content": _safe_detail_value(
                    {
                        "capacity_id": capacity_id,
                        "confidence": selection.get("confidence"),
                        "rationale": selection.get("rationale"),
                        "missing_inputs": selection.get("missing_inputs"),
                    }
                ),
            }
        )
    if result_summary:
        details.append(
            {
                "label": "Result summary",
                "kind": "json",
                "content": _safe_detail_value(result_summary),
            }
        )
    capability_run = _capability_run_from_plan(plan)
    if capability_run:
        details.append(
            {
                "label": "Capability result",
                "kind": "json",
                "content": _safe_detail_value(capability_run),
            }
        )
    return {
        "id": _capacity_event_id(capacity_id),
        "capacity_id": capacity_id,
        "title": _string(launch_plan.get("capability_title") or capacity_id),
        "status": status,
        "input_summary": _safe_detail_value(arguments),
        "result_summary": _safe_detail_value(result_summary),
        "details": details,
    }


def _capacity_error_projection(exc: Exception) -> dict[str, Any]:
    return {
        "id": "capacity_error",
        "capacity_id": "unknown",
        "title": "Capacity call",
        "status": "error",
        "input_summary": {},
        "result_summary": {
            "error_type": type(exc).__name__,
            "message": str(exc) or type(exc).__name__,
        },
        "details": [
            {
                "label": "Error",
                "kind": "json",
                "content": {
                    "error_type": type(exc).__name__,
                    "message": str(exc) or type(exc).__name__,
                },
            }
        ],
    }


def _capability_run_from_plan(plan: dict[str, Any]) -> dict[str, Any]:
    agent_loop = _mapping(plan.get("agent_loop"))
    tick_result = _mapping(agent_loop.get("tick_result"))
    planner_result = _mapping(tick_result.get("planner_result"))
    step_result = _mapping(planner_result.get("step_result"))
    action_result = _mapping(step_result.get("action_result"))
    return _mapping(action_result.get("capability_run"))


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


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string(value: Any) -> str:
    return value if isinstance(value, str) and value else str(value)


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
