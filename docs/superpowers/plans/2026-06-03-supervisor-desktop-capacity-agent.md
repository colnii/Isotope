# Supervisor Desktop Capacity Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first backend slice of a shared Supervisor desktop conversation loop that can directly answer, call capabilities through agent loop, and record capability gaps.

**Architecture:** Add a product-level `conversation_loop.py` under `features/supervisor/` that adapts desktop chat and future Supervisor automation to the existing capability runner and agent loop. Keep agent loop as the lower-level execution substrate, keep capability discovery in `CapabilityRunner`, and keep desktop chat SSE event names compatible. Preserve the legacy `desktop_chat_capacity_provider` path while allowing the default chat provider to act as a JSON decision provider with plain-text fallback.

**Tech Stack:** Python 3.13, pytest, existing `isotope.capabilities.runner`, existing `isotope.features.supervisor.desktop_chat`, existing `isotope.features.supervisor.commands.handlers.capacity`.

---

## File Structure

- Create `src/isotope/features/supervisor/conversation_loop.py`
  - Product conversation loop, provider protocol, decision parser, event model, capability execution adapter, gap recorder, low-sensitive sanitizers.
- Modify `src/isotope/features/supervisor/desktop_chat.py`
  - Use conversation loop when `capacity_provider is None`; keep current legacy capacity pre-pass when `capacity_provider` is provided.
- Add `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`
  - Unit tests for direct answer, capability call loop, system context defaults, and gap recording.
- Modify `tests/integration/supervisor/test_supervisor_desktop_chat.py`
  - Add one integration test proving `/desktop/chat` can use the new conversation loop to emit `capacity_start`, `capacity_result`, and final `delta`.

## Task 1: Add Conversation Loop Direct Answer

**Files:**
- Create: `src/isotope/features/supervisor/conversation_loop.py`
- Test: `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`

- [ ] **Step 1: Write the failing direct-answer test**

Add this test file:

```python
from __future__ import annotations

import json
from typing import Any

from isotope.features.supervisor.conversation_loop import (
    SupervisorConversationEvent,
    run_supervisor_conversation_events,
)
from isotope.llm.provider import LLMResponse


class RecordingConversationProvider:
    provider = "fake"
    model = "fake-conversation"

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        content = self.responses.pop(0)
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=content,
            finish_reason="stop",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
            raw={"raw_response": "must not leak"},
        )


def test_conversation_loop_accepts_plain_text_as_direct_answer(tmp_path) -> None:
    provider = RecordingConversationProvider(["你好，我在。"])

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path / "repo",
            user_message="你好",
            provider=provider,
        )
    )

    assert events == [
        SupervisorConversationEvent(
            event="delta",
            payload={"text": "你好，我在。"},
            provider="fake",
            model="fake-conversation",
        )
    ]
    assert len(provider.calls) == 1
    messages = provider.calls[0]["messages"]
    assert messages[-1] == {"role": "user", "content": "你好"}
    rendered = json.dumps(messages, ensure_ascii=False)
    assert "capacity_manifest" in rendered
    assert "raw_response" not in rendered
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_accepts_plain_text_as_direct_answer -q
```

Expected: FAIL with `ModuleNotFoundError` or import error for `conversation_loop`.

- [ ] **Step 3: Add minimal conversation loop implementation**

Create `src/isotope/features/supervisor/conversation_loop.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
.venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_accepts_plain_text_as_direct_answer -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/features/supervisor/conversation_loop.py tests/unit/features/supervisor/test_supervisor_conversation_loop.py
git commit -m "feat(supervisor): add conversation direct answer loop"
```

## Task 2: Execute Capability Calls Through Agent Loop

**Files:**
- Modify: `src/isotope/features/supervisor/conversation_loop.py`
- Test: `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`

- [ ] **Step 1: Write failing capability-call test**

Append:

```python
def test_conversation_loop_calls_capability_then_returns_final_answer(tmp_path) -> None:
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "artifact.review",
                    "arguments": {},
                    "rationale": "需要试跑 artifact review capability。",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "能力已执行，低敏结果已经返回。",
                    "rationale": "基于 capability observation 回答。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path,
            user_message="请 review artifact。",
            provider=provider,
            max_turns=3,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[0].payload["capacity_id"] == "artifact.review"
    assert events[0].payload["status"] == "running"
    assert events[1].payload["capacity_id"] == "artifact.review"
    assert events[1].payload["status"] == "ok"
    assert events[1].payload["result_summary"]["agent_loop_tick_status"] == "executed"
    assert events[2].payload == {"text": "能力已执行，低敏结果已经返回。"}
    assert len(provider.calls) == 2
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "capacity_observation" in second_prompt
    assert "raw_response" not in second_prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_calls_capability_then_returns_final_answer -q
```

Expected: FAIL because `call_capability` JSON is treated as plain text.

- [ ] **Step 3: Implement decision parsing and capability execution**

Update `conversation_loop.py`:

```python
from isotope.features.supervisor.commands.handlers.capacity import (
    _execute_agent_loop_capacity_step,
    agent_loop_json_summary,
)
```

Add a parsed decision helper:

```python
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
```

Replace the one-shot response block in `run_supervisor_conversation_events` with this bounded loop:

```python
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
```

Replace the `_conversation_messages` signature and observation handling with this complete version:

```python
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
```

Add `_run_capability_decision`:

```python
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
                {"label": "Inputs", "kind": "json", "content": _safe_detail_value(inputs)}
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
            "status": "ok" if result_summary.get("agent_loop_tick_status") == "executed" else "blocked",
            "input_summary": _safe_detail_value(inputs),
            "result_summary": _safe_detail_value(result_summary),
            "details": [
                {"label": "Inputs", "kind": "json", "content": _safe_detail_value(inputs)},
                {"label": "Result summary", "kind": "json", "content": _safe_detail_value(result_summary)},
            ],
        },
    )
```

Add these bounded projection helpers:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
.venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_calls_capability_then_returns_final_answer -q
```

Expected: PASS.

- [ ] **Step 5: Run direct-answer regression**

Run:

```bash
.venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/isotope/features/supervisor/conversation_loop.py tests/unit/features/supervisor/test_supervisor_conversation_loop.py
git commit -m "feat(supervisor): execute conversation capabilities"
```

## Task 3: Record Capability Gaps

**Files:**
- Modify: `src/isotope/features/supervisor/conversation_loop.py`
- Test: `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`

- [ ] **Step 1: Write failing gap test**

Append:

```python
def test_conversation_loop_records_low_sensitive_capability_gap(tmp_path) -> None:
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "report_capability_gap",
                    "gap": {
                        "missing_capability_kind": "supervisor.discovery.worker_list",
                        "reason": "需要查询 worker 列表，但没有对应 discovery capability。",
                        "needed_context": ["worker list", "active run state"],
                    },
                    "rationale": "缺少基础 discovery 能力。",
                }
            )
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path,
            user_message="看看哪个 worker 卡住了",
            provider=provider,
        )
    )

    assert [event.event for event in events] == ["capability_gap", "delta"]
    gap = events[0].payload
    assert gap["missing_capability_kind"] == "supervisor.discovery.worker_list"
    assert gap["source_entrypoint"] == "desktop_chat"
    assert gap["status"] == "recorded"
    assert events[1].payload["text"] == "我缺少对应的基础能力，已记录 capability gap。"
    gap_files = list((tmp_path / "supervisor" / "capability-gaps").glob("*.json"))
    assert len(gap_files) == 1
    saved = json.loads(gap_files[0].read_text(encoding="utf-8"))
    assert saved["missing_capability_kind"] == "supervisor.discovery.worker_list"
    rendered = json.dumps(saved, ensure_ascii=False)
    assert "raw_response" not in rendered
    assert "messages" not in rendered
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_records_low_sensitive_capability_gap -q
```

Expected: FAIL because `report_capability_gap` is not handled.

- [ ] **Step 3: Implement gap recording**

Add imports:

```python
from datetime import datetime, timezone
from uuid import uuid4
```

In the loop, handle `report_capability_gap`:

```python
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
```

Add helper:

```python
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
```

Add these helpers:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
.venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_records_low_sensitive_capability_gap -q
```

Expected: PASS.

- [ ] **Step 5: Run conversation loop unit tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/isotope/features/supervisor/conversation_loop.py tests/unit/features/supervisor/test_supervisor_conversation_loop.py
git commit -m "feat(supervisor): record conversation capability gaps"
```

## Task 4: Wire Desktop Chat To Conversation Loop

**Files:**
- Modify: `src/isotope/features/supervisor/desktop_chat.py`
- Modify: `tests/integration/supervisor/test_supervisor_desktop_chat.py`

- [ ] **Step 1: Write failing desktop chat integration test**

Append to `tests/integration/supervisor/test_supervisor_desktop_chat.py`:

```python
def test_desktop_chat_stream_uses_conversation_loop_for_model_capacity_choice(tmp_path) -> None:
    provider = RecordingDesktopChatProvider(
        content=json.dumps(
            {
                "kind": "call_capability",
                "capacity_id": "artifact.review",
                "arguments": {},
                "rationale": "用户要求能力执行。",
            }
        )
    )
    provider.content = json.dumps(
        {
            "kind": "call_capability",
            "capacity_id": "artifact.review",
            "arguments": {},
            "rationale": "用户要求能力执行。",
        }
    )
    provider.responses = [
        provider.content,
        json.dumps(
            {
                "kind": "direct_answer",
                "answer": "已经通过 Supervisor agent loop 执行 capability。",
            }
        ),
    ]

    def generate(messages, *, max_tokens=512):
        provider.calls.append({"messages": messages, "max_tokens": max_tokens})
        return LLMResponse(
            provider=provider.provider,
            model=provider.model,
            content=provider.responses.pop(0),
            finish_reason="stop",
            usage={},
            raw={"raw_response": "must not leak"},
        )

    provider.generate = generate

    events = list(
        stream_desktop_chat_events(
            state_root=tmp_path,
            question="调用 artifact review capacity。",
            provider=provider,
        )
    )

    assert [event.event for event in events] == [
        "capacity_start",
        "capacity_result",
        "delta",
    ]
    assert events[1].payload["result_summary"]["agent_loop_tick_status"] == "executed"
    assert events[2].payload["text"] == "已经通过 Supervisor agent loop 执行 capability。"
    assert len(provider.calls) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/integration/supervisor/test_supervisor_desktop_chat.py::test_desktop_chat_stream_uses_conversation_loop_for_model_capacity_choice -q
```

Expected: FAIL because `stream_desktop_chat_events` treats JSON as answer text.

- [ ] **Step 3: Wire non-legacy desktop chat path to conversation loop**

In `desktop_chat.py`, import:

```python
from .conversation_loop import run_supervisor_conversation_events
```

In `stream_desktop_chat_events`, after building `clean_question` and validating `max_tokens`, route to conversation loop when `capacity_provider is None`:

```python
if capacity_provider is None:
    yield from run_supervisor_conversation_events(
        state_root=state_root,
        cwd=Path.cwd(),
        user_message=clean_question,
        provider=provider,
        max_tokens=max_tokens,
        history=history,
        capacity_runner=capacity_runner,
    )
    return
```

Leave the existing capacity pre-pass path unchanged for `capacity_provider is not None`.

- [ ] **Step 4: Run new integration test**

Run:

```bash
.venv/bin/python -m pytest tests/integration/supervisor/test_supervisor_desktop_chat.py::test_desktop_chat_stream_uses_conversation_loop_for_model_capacity_choice -q
```

Expected: PASS.

- [ ] **Step 5: Run desktop chat integration suite**

Run:

```bash
.venv/bin/python -m pytest tests/integration/supervisor/test_supervisor_desktop_chat.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/isotope/features/supervisor/desktop_chat.py tests/integration/supervisor/test_supervisor_desktop_chat.py
git commit -m "feat(supervisor): route desktop chat through conversation loop"
```

## Task 5: Final Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run focused regression tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py tests/integration/supervisor/test_supervisor_desktop_chat.py -q
```

Expected: PASS.

- [ ] **Step 2: Run agent loop and capability regression tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agents/loop tests/unit/capabilities -q
```

Expected: PASS.

- [ ] **Step 3: Run diff check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 4: Inspect worktree state**

Run:

```bash
git status --short --branch
```

Expected: clean branch after commits.
