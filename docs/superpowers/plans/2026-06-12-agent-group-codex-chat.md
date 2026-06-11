# Agent Group Codex Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the MVP Agent Group Chat desktop surface where users can connect Codex sessions, inspect high-fidelity transcripts, let a coordinator model decide whether to reply privately or send/draft member messages, and stop current runs or individual members.

**Architecture:** Reuse the existing Supervisor `agent_group` runtime and ledgers, but add a focused `codex_chat` subpackage for connected Codex-member metadata, private chat, send decisions, and runtime controls. Add a dedicated Codex transcript reader that pages JSONL events without the existing scan reader's head/tail truncation. Expose desktop HTTP/SSE endpoints and a Svelte workbench page backed by a small TypeScript client and focused components.

**Tech Stack:** Python 3.13, pytest, dataclasses, existing `FileMemoryStore` and `worker_event_channel`, existing Codex session lookup/adoption helpers, Svelte 5, TypeScript, Vite/Vitest, desktop SSE patterns from `/desktop/chat`.

---

## Scope Boundary

This plan implements the first working MVP from
`docs/superpowers/specs/2026-06-12-agent-group-codex-chat-design.md`.

It includes:

- Connected Codex member contracts and persistence.
- Private AI-human chat persistence separate from public group messages.
- Full-history transcript paging for Codex JSONL sessions.
- Coordinator send decision policy for `auto`, `confirm`, and `draft_only`.
- Runtime controls for `queue`, `interrupt`, and `terminate`.
- Desktop endpoints and frontend page for the MVP.
- Fake-session product smoke coverage.

It excludes:

- Killing arbitrary user-started terminal processes without an Isotope process handle.
- A broad autonomous organization framework.
- Replacing `/desktop/chat`.

## File Structure

Create a new backend subpackage:

- `src/isotope/features/supervisor/agent_group/codex_chat/__init__.py`:
  public exports for connected Codex chat.
- `src/isotope/features/supervisor/agent_group/codex_chat/contracts.py`:
  dataclasses and validation for connected members, private chat messages,
  send decisions, and runtime controls.
- `src/isotope/features/supervisor/agent_group/codex_chat/store.py`:
  persistence over `FileMemoryStore` and `worker_event_channel`.
- `src/isotope/features/supervisor/agent_group/codex_chat/runtime.py`:
  coordinator decision application, send policy handling, and member
  termination state.
- `src/isotope/features/supervisor/agent_group/codex_chat/api.py`:
  endpoint-facing helpers that return plain dictionaries for desktop routes.

Create transcript support:

- `src/isotope/integrations/codex/transcript.py`:
  paged JSONL transcript reader with readable and raw projections.

Add desktop routes:

- `src/isotope/features/supervisor/web/routes/agent_groups.py`:
  route parsing, request validation, and response helpers.
- Modify `src/isotope/features/supervisor/web/_impl.py`:
  wire HTTP routes and SSE stream endpoints.

Add frontend support:

- `apps/desktop/src/lib/contracts/agentGroup.ts`:
  TypeScript contracts for the page.
- `apps/desktop/src/lib/client/agentGroupClient.ts`:
  HTTP/SSE client for agent groups and transcript pages.
- Modify `apps/desktop/src/lib/client/isotopeClient.ts`:
  expose the new `agentGroupClient`.
- Create `apps/desktop/src/lib/components/agentGroup/AgentGroupWorkspace.svelte`.
- Create `apps/desktop/src/lib/components/agentGroup/AgentGroupMemberStrip.svelte`.
- Create `apps/desktop/src/lib/components/agentGroup/AgentGroupStream.svelte`.
- Create `apps/desktop/src/lib/components/agentGroup/AgentGroupPrivateChat.svelte`.
- Create `apps/desktop/src/lib/components/agentGroup/CodexTranscriptPanel.svelte`.
- Modify `apps/desktop/src/routes/+page.svelte`:
  add a local mode switch between existing Supervisor chat and Agent Group Chat.

Add tests:

- `tests/unit/features/supervisor/agent_group/codex_chat/test_contracts.py`
- `tests/unit/features/supervisor/agent_group/codex_chat/test_store.py`
- `tests/unit/features/supervisor/agent_group/codex_chat/test_runtime.py`
- `tests/unit/integrations/codex/test_codex_transcript.py`
- `tests/unit/features/supervisor/web/test_agent_group_routes.py`
- `tests/integration/supervisor/desktop/test_agent_group_codex_chat_smoke.py`
- `apps/desktop/src/lib/client/agentGroupClient.test.ts`
- `apps/desktop/src/lib/components/agentGroup/AgentGroupWorkspace.test.ts`

## Directory Rules

- Do not add more files to `apps/desktop/src/lib/components/main/`; it already
  has 8 source/test files. Use `apps/desktop/src/lib/components/agentGroup/`.
- Keep `src/isotope/features/supervisor/agent_group/` focused. New Codex-chat
  implementation lives under `agent_group/codex_chat/`.
- Keep Python source files under 500 lines. If a file approaches 500 lines,
  split by responsibility before adding more behavior.

---

### Task 1: Connected Codex Chat Contracts

**Files:**
- Create: `src/isotope/features/supervisor/agent_group/codex_chat/__init__.py`
- Create: `src/isotope/features/supervisor/agent_group/codex_chat/contracts.py`
- Create: `tests/unit/features/supervisor/agent_group/codex_chat/test_contracts.py`

- [ ] **Step 1: Write the failing contract tests**

Create `tests/unit/features/supervisor/agent_group/codex_chat/test_contracts.py`:

```python
from __future__ import annotations

import pytest

from isotope.features.supervisor.agent_group.codex_chat.contracts import (
    ConnectedCodexMember,
    CoordinatorDecision,
    PrivateChatMessage,
    RuntimeControlRequest,
)


def test_connected_codex_member_public_dict():
    member = ConnectedCodexMember(
        member_id="member_research",
        group_id="group_rna",
        display_name="Research Codex",
        member_kind="codex_session",
        role="Explore RNA strategy.",
        goal="Find promising research directions.",
        send_policy="confirm",
        status="active",
        resume_session_id="019e9830-8a72-7ff1-8b2e-310b9d66372b",
        source_path="/home/lumber/.codex/sessions/rollout.jsonl",
        managed_record_id=None,
        transcript_policy={"page_size": 200, "raw_view": True},
        created_at="2026-06-12T00:00:00Z",
        updated_at="2026-06-12T00:00:00Z",
    )

    assert member.to_public_dict() == {
        "member_id": "member_research",
        "group_id": "group_rna",
        "display_name": "Research Codex",
        "member_kind": "codex_session",
        "role": "Explore RNA strategy.",
        "goal": "Find promising research directions.",
        "send_policy": "confirm",
        "status": "active",
        "resume_session_id": "019e9830-8a72-7ff1-8b2e-310b9d66372b",
        "source_path": "/home/lumber/.codex/sessions/rollout.jsonl",
        "managed_record_id": None,
        "transcript_policy": {"page_size": 200, "raw_view": True},
        "created_at": "2026-06-12T00:00:00Z",
        "updated_at": "2026-06-12T00:00:00Z",
    }


def test_private_chat_message_is_not_group_broadcast():
    message = PrivateChatMessage(
        message_id="priv_1",
        group_id="group_rna",
        role="assistant",
        content="Engineering Codex is blocked; ask before sending.",
        created_at="2026-06-12T00:00:01Z",
    )

    assert message.to_public_dict()["channel"] == "private_human_chat"
    assert message.to_public_dict()["content"] == "Engineering Codex is blocked; ask before sending."


def test_coordinator_decision_public_dict_for_confirm_send():
    decision = CoordinatorDecision(
        decision_id="decision_1",
        group_id="group_rna",
        action="send_member",
        target_member_id="member_engineering",
        content="Research found that the input schema changed; inspect /saisdata/56.",
        reason="Engineering needs the research update.",
        created_at="2026-06-12T00:00:02Z",
    )

    assert decision.to_public_dict()["action"] == "send_member"
    assert decision.to_public_dict()["target_member_id"] == "member_engineering"


def test_runtime_control_request_public_dict_for_terminate():
    request = RuntimeControlRequest(
        control_id="control_1",
        group_id="group_rna",
        intent="terminate",
        target="member",
        target_member_id="member_research",
        reason="User pressed member Stop.",
        created_at="2026-06-12T00:00:03Z",
    )

    assert request.to_public_dict()["intent"] == "terminate"
    assert request.to_public_dict()["target_member_id"] == "member_research"


@pytest.mark.parametrize(
    ("factory", "kwargs", "message"),
    [
        (
            ConnectedCodexMember,
            {
                "member_id": "",
                "group_id": "group_rna",
                "display_name": "Research",
                "member_kind": "codex_session",
                "role": "role",
                "goal": "",
                "send_policy": "confirm",
                "status": "active",
                "resume_session_id": "session",
                "source_path": None,
                "managed_record_id": None,
                "transcript_policy": {},
                "created_at": "now",
                "updated_at": "now",
            },
            "member_id must be a non-empty string",
        ),
        (
            ConnectedCodexMember,
            {
                "member_id": "member_research",
                "group_id": "group_rna",
                "display_name": "Research",
                "member_kind": "codex_session",
                "role": "role",
                "goal": "",
                "send_policy": "silent_auto",
                "status": "active",
                "resume_session_id": "session",
                "source_path": None,
                "managed_record_id": None,
                "transcript_policy": {},
                "created_at": "now",
                "updated_at": "now",
            },
            "send_policy must be one of",
        ),
        (
            CoordinatorDecision,
            {
                "decision_id": "decision_1",
                "group_id": "group_rna",
                "action": "route_by_keyword",
                "target_member_id": None,
                "content": "x",
                "reason": "x",
                "created_at": "now",
            },
            "decision action must be one of",
        ),
        (
            RuntimeControlRequest,
            {
                "control_id": "control_1",
                "group_id": "group_rna",
                "intent": "kill_everything",
                "target": "member",
                "target_member_id": "member_research",
                "reason": "x",
                "created_at": "now",
            },
            "control intent must be one of",
        ),
    ],
)
def test_contracts_reject_invalid_values(factory, kwargs, message):
    with pytest.raises(ValueError, match=message):
        factory(**kwargs)


def test_payload_guards_reject_raw_or_secret_fields():
    with pytest.raises(ValueError, match="raw codex chat payload is not accepted"):
        ConnectedCodexMember(
            member_id="member_research",
            group_id="group_rna",
            display_name="Research",
            member_kind="codex_session",
            role="role",
            goal="",
            send_policy="confirm",
            status="active",
            resume_session_id="session",
            source_path=None,
            managed_record_id=None,
            transcript_policy={"raw_response": "secret"},
            created_at="now",
            updated_at="now",
        )
```

- [ ] **Step 2: Run the test to verify RED**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/codex_chat/test_contracts.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'isotope.features.supervisor.agent_group.codex_chat'`.

- [ ] **Step 3: Implement the contracts**

Create `src/isotope/features/supervisor/agent_group/codex_chat/contracts.py`:

```python
"""Contracts for Codex-backed Supervisor Agent Group Chat."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


MEMBER_KINDS = {"codex_session", "internal_agent", "supervisor"}
SEND_POLICIES = {"auto", "confirm", "draft_only"}
CONNECTED_MEMBER_STATUSES = {
    "active",
    "running",
    "idle",
    "needs_user",
    "terminated",
    "blocked",
    "archived",
}
PRIVATE_CHAT_ROLES = {"user", "assistant", "system"}
COORDINATOR_ACTIONS = {
    "reply_group",
    "reply_private",
    "send_member",
    "draft_member_send",
    "wait",
    "record_gap",
}
CONTROL_INTENTS = {"queue", "interrupt", "terminate"}
CONTROL_TARGETS = {"current_run", "member"}
RAW_CODEX_CHAT_FIELDS = {
    "api_key",
    "full_content",
    "full_text",
    "messages",
    "model_prompt",
    "model_request",
    "model_response",
    "prompt",
    "raw_content",
    "raw_prompt",
    "raw_response",
    "secret",
    "stderr",
    "stdin",
    "stdout",
    "token",
}


@dataclass(frozen=True)
class ConnectedCodexMember:
    member_id: str
    group_id: str
    display_name: str
    member_kind: str
    role: str
    goal: str
    send_policy: str
    status: str
    resume_session_id: str | None
    source_path: str | None
    managed_record_id: str | None
    transcript_policy: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        _require_text(self.member_id, "member_id")
        _require_text(self.group_id, "group_id")
        _require_text(self.display_name, "display_name")
        _require_text(self.role, "role")
        _require_choice(self.member_kind, MEMBER_KINDS, "member_kind")
        _require_choice(self.send_policy, SEND_POLICIES, "send_policy")
        _require_choice(self.status, CONNECTED_MEMBER_STATUSES, "member status")
        _require_optional_text(self.resume_session_id, "resume_session_id")
        _require_optional_text(self.source_path, "source_path")
        _require_optional_text(self.managed_record_id, "managed_record_id")
        _require_text(self.created_at, "created_at")
        _require_text(self.updated_at, "updated_at")
        if not isinstance(self.transcript_policy, dict):
            raise ValueError("transcript_policy must be a dict")
        _reject_raw_codex_chat_payload(self.transcript_policy)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "member_id": self.member_id,
            "group_id": self.group_id,
            "display_name": self.display_name,
            "member_kind": self.member_kind,
            "role": self.role,
            "goal": self.goal,
            "send_policy": self.send_policy,
            "status": self.status,
            "resume_session_id": self.resume_session_id,
            "source_path": self.source_path,
            "managed_record_id": self.managed_record_id,
            "transcript_policy": _copy_public_payload(self.transcript_policy),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class PrivateChatMessage:
    message_id: str
    group_id: str
    role: str
    content: str
    created_at: str

    def __post_init__(self) -> None:
        _require_text(self.message_id, "message_id")
        _require_text(self.group_id, "group_id")
        _require_choice(self.role, PRIVATE_CHAT_ROLES, "private chat role")
        _require_text(self.content, "content")
        _require_text(self.created_at, "created_at")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "group_id": self.group_id,
            "channel": "private_human_chat",
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class CoordinatorDecision:
    decision_id: str
    group_id: str
    action: str
    target_member_id: str | None
    content: str
    reason: str
    created_at: str

    def __post_init__(self) -> None:
        _require_text(self.decision_id, "decision_id")
        _require_text(self.group_id, "group_id")
        _require_choice(self.action, COORDINATOR_ACTIONS, "decision action")
        _require_optional_text(self.target_member_id, "target_member_id")
        _require_text(self.content, "content")
        _require_text(self.reason, "reason")
        _require_text(self.created_at, "created_at")
        if self.action in {"send_member", "draft_member_send"} and not self.target_member_id:
            raise ValueError("target_member_id is required for member send decisions")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "group_id": self.group_id,
            "action": self.action,
            "target_member_id": self.target_member_id,
            "content": self.content,
            "reason": self.reason,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class RuntimeControlRequest:
    control_id: str
    group_id: str
    intent: str
    target: str
    target_member_id: str | None
    reason: str
    created_at: str

    def __post_init__(self) -> None:
        _require_text(self.control_id, "control_id")
        _require_text(self.group_id, "group_id")
        _require_choice(self.intent, CONTROL_INTENTS, "control intent")
        _require_choice(self.target, CONTROL_TARGETS, "control target")
        _require_optional_text(self.target_member_id, "target_member_id")
        _require_text(self.reason, "reason")
        _require_text(self.created_at, "created_at")
        if self.target == "member" and not self.target_member_id:
            raise ValueError("target_member_id is required for member controls")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "control_id": self.control_id,
            "group_id": self.group_id,
            "intent": self.intent,
            "target": self.target,
            "target_member_id": self.target_member_id,
            "reason": self.reason,
            "created_at": self.created_at,
        }


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_optional_text(value: object, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be null or a non-empty string")


def _require_choice(value: object, choices: set[str], field_name: str) -> None:
    if value not in choices:
        options = ", ".join(sorted(choices))
        raise ValueError(f"{field_name} must be one of: {options}")


def _reject_raw_codex_chat_payload(value: Any) -> None:
    if isinstance(value, dict):
        if RAW_CODEX_CHAT_FIELDS.intersection(value):
            raise ValueError("raw codex chat payload is not accepted")
        for nested in value.values():
            _reject_raw_codex_chat_payload(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_raw_codex_chat_payload(nested)


def _copy_public_payload(value: dict[str, Any]) -> dict[str, Any]:
    _reject_raw_codex_chat_payload(value)
    return {str(key): _copy_public_value(nested) for key, nested in value.items()}


def _copy_public_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _copy_public_payload(value)
    if isinstance(value, list):
        return [_copy_public_value(item) for item in value]
    return value
```

Create `src/isotope/features/supervisor/agent_group/codex_chat/__init__.py`:

```python
"""Codex-backed Agent Group Chat support."""

from .contracts import (
    ConnectedCodexMember,
    CoordinatorDecision,
    PrivateChatMessage,
    RuntimeControlRequest,
)

__all__ = [
    "ConnectedCodexMember",
    "CoordinatorDecision",
    "PrivateChatMessage",
    "RuntimeControlRequest",
]
```

- [ ] **Step 4: Run the contract test to verify GREEN**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/codex_chat/test_contracts.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/isotope/features/supervisor/agent_group/codex_chat/__init__.py src/isotope/features/supervisor/agent_group/codex_chat/contracts.py tests/unit/features/supervisor/agent_group/codex_chat/test_contracts.py
git commit -m "feat(supervisor): add codex group chat contracts"
```

---

### Task 2: Full-History Codex Transcript Reader

**Files:**
- Create: `src/isotope/integrations/codex/transcript.py`
- Modify: `src/isotope/integrations/codex/__init__.py`
- Create: `tests/unit/integrations/codex/test_codex_transcript.py`

- [ ] **Step 1: Write the failing transcript tests**

Create `tests/unit/integrations/codex/test_codex_transcript.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from isotope.integrations.codex.transcript import (
    read_codex_transcript_page,
)


def test_transcript_reader_pages_from_start_without_head_tail_truncation(tmp_path):
    path = tmp_path / "rollout.jsonl"
    rows = [
        {"type": "session_meta", "timestamp": "2026-06-12T00:00:00Z", "payload": {"id": "session_1", "cwd": "/repo"}},
        {"type": "response_item", "timestamp": "2026-06-12T00:00:01Z", "payload": {"type": "message", "role": "user", "content": [{"text": "first"}]}},
        {"type": "event_msg", "timestamp": "2026-06-12T00:00:02Z", "payload": {"type": "status", "message": "middle status"}},
        {"type": "response_item", "timestamp": "2026-06-12T00:00:03Z", "payload": {"type": "message", "role": "assistant", "content": "last"}},
    ]
    write_jsonl(path, rows)

    page = read_codex_transcript_page(path, offset=0, limit=2, include_raw=True)

    assert page["session_id"] == "session_1"
    assert page["source_path"] == str(path)
    assert page["source_size_bytes"] == path.stat().st_size
    assert page["has_more"] is True
    assert page["next_offset"] == 2
    assert [item["kind"] for item in page["events"]] == ["session_meta", "message"]
    assert page["events"][1]["text"] == "first"
    assert "raw" in page["events"][0]


def test_transcript_reader_pages_middle_and_preserves_late_events(tmp_path):
    path = tmp_path / "large-rollout.jsonl"
    rows = [{"type": "session_meta", "payload": {"id": "session_large"}}]
    rows.extend(
        {
            "type": "response_item",
            "timestamp": f"2026-06-12T00:{index:02d}:00Z",
            "payload": {"type": "message", "role": "assistant", "content": f"message-{index}"},
        }
        for index in range(40)
    )
    write_jsonl(path, rows)

    page = read_codex_transcript_page(path, offset=35, limit=10, include_raw=False)

    assert page["session_id"] == "session_large"
    assert page["offset"] == 35
    assert page["has_more"] is False
    assert page["events"][0]["text"] == "message-34"
    assert page["events"][-1]["text"] == "message-39"
    assert all("raw" not in item for item in page["events"])


def test_transcript_reader_projects_tool_and_error_events(tmp_path):
    path = tmp_path / "rollout-tools.jsonl"
    write_jsonl(
        path,
        [
            {"type": "session_meta", "payload": {"id": "session_tools"}},
            {"type": "response_item", "timestamp": "2026-06-12T00:00:01Z", "payload": {"type": "function_call", "name": "shell", "arguments": "{}"}},
            {"type": "event_msg", "timestamp": "2026-06-12T00:00:02Z", "payload": {"type": "error", "message": "command failed"}},
        ],
    )

    page = read_codex_transcript_page(path, offset=0, limit=10, include_raw=False)

    assert [item["kind"] for item in page["events"]] == ["session_meta", "tool_call", "error"]
    assert page["events"][1]["title"] == "shell"
    assert page["events"][2]["text"] == "command failed"


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
```

- [ ] **Step 2: Run the transcript test to verify RED**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/integrations/codex/test_codex_transcript.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'isotope.integrations.codex.transcript'`.

- [ ] **Step 3: Implement transcript paging**

Create `src/isotope/integrations/codex/transcript.py`:

```python
"""Paged transcript reader for local Codex JSONL sessions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_codex_transcript_page(
    path: Path | str,
    *,
    offset: int = 0,
    limit: int = 200,
    include_raw: bool = False,
) -> dict[str, Any]:
    source_path = Path(path).expanduser()
    clean_offset = max(int(offset), 0)
    clean_limit = min(max(int(limit), 1), 1000)
    parsed_events: list[dict[str, Any]] = []
    session_id = source_path.stem
    last_event_at: str | None = None
    total_events = 0

    with source_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            event = _loads_event(line)
            if event is None:
                continue
            total_events += 1
            timestamp = event.get("timestamp")
            if isinstance(timestamp, str) and timestamp:
                last_event_at = timestamp
            if event.get("type") == "session_meta":
                payload = event.get("payload")
                if isinstance(payload, dict) and isinstance(payload.get("id"), str):
                    session_id = payload["id"]
            event_index = total_events - 1
            if event_index < clean_offset:
                continue
            if len(parsed_events) >= clean_limit:
                continue
            parsed_events.append(_project_event(event, event_index=event_index, include_raw=include_raw))

    next_offset = clean_offset + len(parsed_events)
    return {
        "status": "ok",
        "session_id": session_id,
        "source_path": str(source_path),
        "source_size_bytes": source_path.stat().st_size,
        "last_event_at": last_event_at,
        "offset": clean_offset,
        "limit": clean_limit,
        "next_offset": next_offset,
        "has_more": next_offset < total_events,
        "total_events": total_events,
        "events": parsed_events,
    }


def _loads_event(line: str) -> dict[str, Any] | None:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None


def _project_event(
    event: dict[str, Any],
    *,
    event_index: int,
    include_raw: bool,
) -> dict[str, Any]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    base: dict[str, Any] = {
        "event_index": event_index,
        "event_type": event.get("type") if isinstance(event.get("type"), str) else "unknown",
        "timestamp": event.get("timestamp") if isinstance(event.get("timestamp"), str) else None,
    }
    if event.get("type") == "session_meta":
        projected = {
            **base,
            "kind": "session_meta",
            "title": "session metadata",
            "text": str(payload.get("cwd") or payload.get("id") or ""),
        }
    elif event.get("type") == "response_item" and payload.get("type") == "message":
        projected = {
            **base,
            "kind": "message",
            "title": str(payload.get("role") or "message"),
            "role": payload.get("role") if isinstance(payload.get("role"), str) else None,
            "text": _content_text(payload.get("content")),
        }
    elif event.get("type") == "response_item" and payload.get("type") in {"function_call", "tool_call"}:
        projected = {
            **base,
            "kind": "tool_call",
            "title": str(payload.get("name") or payload.get("type") or "tool_call"),
            "text": _short_text(payload.get("arguments")),
        }
    elif event.get("type") == "event_msg" and payload.get("type") == "error":
        projected = {
            **base,
            "kind": "error",
            "title": "error",
            "text": str(payload.get("message") or ""),
        }
    elif event.get("type") == "event_msg":
        projected = {
            **base,
            "kind": "status",
            "title": str(payload.get("type") or "event"),
            "text": str(payload.get("message") or ""),
        }
    else:
        projected = {
            **base,
            "kind": "raw_event",
            "title": str(event.get("type") or "event"),
            "text": "",
        }
    if include_raw:
        projected["raw"] = event
    return projected


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts)


def _short_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
```

Modify `src/isotope/integrations/codex/__init__.py`:

```python
"""Codex CLI integration boundaries."""

from .transcript import read_codex_transcript_page

__all__ = ["read_codex_transcript_page"]
```

- [ ] **Step 4: Run the transcript test to verify GREEN**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/integrations/codex/test_codex_transcript.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/isotope/integrations/codex/transcript.py src/isotope/integrations/codex/__init__.py tests/unit/integrations/codex/test_codex_transcript.py
git commit -m "feat(codex): add paged transcript reader"
```

---

### Task 3: Store Connected Members And Private Chat

**Files:**
- Create: `src/isotope/features/supervisor/agent_group/codex_chat/store.py`
- Create: `tests/unit/features/supervisor/agent_group/codex_chat/test_store.py`

- [ ] **Step 1: Write the failing store tests**

Create `tests/unit/features/supervisor/agent_group/codex_chat/test_store.py`:

```python
from __future__ import annotations

from isotope.features.supervisor.agent_group.codex_chat.contracts import (
    ConnectedCodexMember,
)
from isotope.features.supervisor.agent_group.codex_chat.store import (
    CodexGroupChatStore,
)


def test_store_saves_connected_member_and_private_chat(tmp_path):
    store = CodexGroupChatStore(tmp_path)
    member = ConnectedCodexMember(
        member_id="member_research",
        group_id="group_rna",
        display_name="Research Codex",
        member_kind="codex_session",
        role="Explore RNA strategy.",
        goal="Find research directions.",
        send_policy="confirm",
        status="active",
        resume_session_id="session_research",
        source_path="/tmp/research.jsonl",
        managed_record_id=None,
        transcript_policy={"page_size": 200},
        created_at="2026-06-12T00:00:00Z",
        updated_at="2026-06-12T00:00:00Z",
    )

    store.save_member(member)
    store.append_private_chat(
        group_id="group_rna",
        role="assistant",
        content="Ask before sending this engineering update.",
    )

    assert store.list_members("group_rna")[0].to_public_dict()["display_name"] == "Research Codex"
    private_messages = store.list_private_chat("group_rna")
    assert private_messages[0].role == "assistant"
    assert private_messages[0].content == "Ask before sending this engineering update."


def test_store_updates_member_status_to_terminated(tmp_path):
    store = CodexGroupChatStore(tmp_path)
    store.save_member(
        ConnectedCodexMember(
            member_id="member_engineering",
            group_id="group_rna",
            display_name="Engineering Codex",
            member_kind="codex_session",
            role="Push engineering work.",
            goal="Keep Docker submission moving.",
            send_policy="auto",
            status="active",
            resume_session_id="session_engineering",
            source_path="/tmp/engineering.jsonl",
            managed_record_id="managed_engineering",
            transcript_policy={},
            created_at="2026-06-12T00:00:00Z",
            updated_at="2026-06-12T00:00:00Z",
        )
    )

    updated = store.update_member_status(
        group_id="group_rna",
        member_id="member_engineering",
        status="terminated",
    )

    assert updated.status == "terminated"
    assert store.list_members("group_rna")[0].status == "terminated"


def test_store_records_runtime_control_event(tmp_path):
    store = CodexGroupChatStore(tmp_path)

    control = store.record_control(
        group_id="group_rna",
        intent="terminate",
        target="member",
        target_member_id="member_research",
        reason="User pressed member Stop.",
    )

    assert control.intent == "terminate"
    events = store.list_control_events("group_rna")
    assert events[0]["payload"]["intent"] == "terminate"
    assert events[0]["payload"]["target_member_id"] == "member_research"
```

- [ ] **Step 2: Run the store test to verify RED**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/codex_chat/test_store.py -q
```

Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `CodexGroupChatStore`.

- [ ] **Step 3: Implement the store**

Create `src/isotope/features/supervisor/agent_group/codex_chat/store.py`:

```python
"""Storage for Codex-backed Agent Group Chat."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import uuid

from isotope.platform.schemas.memory import MemoryRecord
from isotope.platform.state.memory_store import FileMemoryStore
from isotope.platform.state.worker_event_channel import (
    list_worker_events,
    publish_worker_event,
)

from .contracts import (
    ConnectedCodexMember,
    PrivateChatMessage,
    RuntimeControlRequest,
)


MEMBER_RECORD_KIND = "agent_group_codex_member"
PRIVATE_CHAT_RECORD_KIND = "agent_group_private_chat"
CONTROL_EVENT_CHANNEL = "agent-group-control"


class CodexGroupChatStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser()
        self.memory = FileMemoryStore(self.root)

    def save_member(self, member: ConnectedCodexMember) -> ConnectedCodexMember:
        self.memory.append_record(_record_for_member(member))
        return member

    def list_members(self, group_id: str) -> list[ConnectedCodexMember]:
        members = [
            _member_from_record(record)
            for record in self.memory.list_records(scope="session")
            if record.content.get("kind") == MEMBER_RECORD_KIND
            and record.content.get("group_id") == group_id
        ]
        latest: dict[str, ConnectedCodexMember] = {}
        for member in members:
            if member is not None:
                latest[member.member_id] = member
        return sorted(latest.values(), key=lambda item: item.member_id)

    def update_member_status(
        self,
        *,
        group_id: str,
        member_id: str,
        status: str,
    ) -> ConnectedCodexMember:
        for member in self.list_members(group_id):
            if member.member_id != member_id:
                continue
            updated = replace(member, status=status, updated_at=_now())
            self.save_member(updated)
            return updated
        raise ValueError(f"connected member not found: {member_id}")

    def append_private_chat(
        self,
        *,
        group_id: str,
        role: str,
        content: str,
    ) -> PrivateChatMessage:
        message = PrivateChatMessage(
            message_id=_new_id("private"),
            group_id=group_id,
            role=role,
            content=content,
            created_at=_now(),
        )
        self.memory.append_record(_record_for_private_chat(message))
        return message

    def list_private_chat(self, group_id: str) -> list[PrivateChatMessage]:
        messages = [
            _private_chat_from_record(record)
            for record in self.memory.list_records(scope="session")
            if record.content.get("kind") == PRIVATE_CHAT_RECORD_KIND
            and record.content.get("group_id") == group_id
        ]
        return sorted(
            [message for message in messages if message is not None],
            key=lambda item: (item.created_at, item.message_id),
        )

    def record_control(
        self,
        *,
        group_id: str,
        intent: str,
        target: str,
        target_member_id: str | None,
        reason: str,
    ) -> RuntimeControlRequest:
        control = RuntimeControlRequest(
            control_id=_new_id("control"),
            group_id=group_id,
            intent=intent,
            target=target,
            target_member_id=target_member_id,
            reason=reason,
            created_at=_now(),
        )
        publish_worker_event(
            root=self.root,
            from_worker="supervisor",
            to_worker=target_member_id,
            event_type="runtime_control",
            channel=CONTROL_EVENT_CHANNEL,
            message=reason,
            payload=control.to_public_dict(),
        )
        return control

    def list_control_events(self, group_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        payload = list_worker_events(
            root=self.root,
            channel=CONTROL_EVENT_CHANNEL,
            limit=max(limit, 1),
        )
        events: list[dict[str, Any]] = []
        for event in payload.get("events") or []:
            if not isinstance(event, dict):
                continue
            raw_payload = event.get("payload")
            if isinstance(raw_payload, dict) and raw_payload.get("group_id") == group_id:
                events.append(event)
        return events


def _record_for_member(member: ConnectedCodexMember) -> MemoryRecord:
    payload = {"kind": MEMBER_RECORD_KIND, **member.to_public_dict()}
    return _record(
        record_id=f"agent_group_codex_member_{member.group_id}_{member.member_id}_{_new_id('rev')}",
        kind=MEMBER_RECORD_KIND,
        content=payload,
        summary=f"Connected Codex member {member.display_name}: {member.status}",
    )


def _record_for_private_chat(message: PrivateChatMessage) -> MemoryRecord:
    payload = {"kind": PRIVATE_CHAT_RECORD_KIND, **message.to_public_dict()}
    return _record(
        record_id=f"agent_group_private_chat_{message.group_id}_{message.message_id}",
        kind=PRIVATE_CHAT_RECORD_KIND,
        content=payload,
        summary=message.content,
    )


def _record(
    *,
    record_id: str,
    kind: str,
    content: dict[str, Any],
    summary: str,
) -> MemoryRecord:
    return MemoryRecord(
        memory_id=record_id,
        scope="session",
        content=content,
        summary=summary,
        source_refs=[],
        provenance={
            "run_id": "agent_group_codex_chat",
            "execution_id": _new_id("exec"),
            "action_type": kind,
        },
        created_at=_now(),
        supersedes=[],
        quality="agent_group_codex_chat",
    )


def _member_from_record(record: MemoryRecord) -> ConnectedCodexMember | None:
    try:
        return ConnectedCodexMember(
            member_id=str(record.content["member_id"]),
            group_id=str(record.content["group_id"]),
            display_name=str(record.content["display_name"]),
            member_kind=str(record.content["member_kind"]),
            role=str(record.content["role"]),
            goal=str(record.content.get("goal") or ""),
            send_policy=str(record.content["send_policy"]),
            status=str(record.content["status"]),
            resume_session_id=_optional_string(record.content.get("resume_session_id")),
            source_path=_optional_string(record.content.get("source_path")),
            managed_record_id=_optional_string(record.content.get("managed_record_id")),
            transcript_policy=dict(record.content.get("transcript_policy") or {}),
            created_at=str(record.content["created_at"]),
            updated_at=str(record.content["updated_at"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _private_chat_from_record(record: MemoryRecord) -> PrivateChatMessage | None:
    try:
        return PrivateChatMessage(
            message_id=str(record.content["message_id"]),
            group_id=str(record.content["group_id"]),
            role=str(record.content["role"]),
            content=str(record.content["content"]),
            created_at=str(record.content["created_at"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
```

- [ ] **Step 4: Run the store test to verify GREEN**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/codex_chat/test_store.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/isotope/features/supervisor/agent_group/codex_chat/store.py tests/unit/features/supervisor/agent_group/codex_chat/test_store.py
git commit -m "feat(supervisor): persist connected codex chat state"
```

---

### Task 4: Runtime Send Policy And Stop Semantics

**Files:**
- Create: `src/isotope/features/supervisor/agent_group/codex_chat/runtime.py`
- Modify: `src/isotope/features/supervisor/agent_group/codex_chat/__init__.py`
- Create: `tests/unit/features/supervisor/agent_group/codex_chat/test_runtime.py`

- [ ] **Step 1: Write the failing runtime tests**

Create `tests/unit/features/supervisor/agent_group/codex_chat/test_runtime.py`:

```python
from __future__ import annotations

from isotope.features.supervisor.agent_group.codex_chat.contracts import (
    ConnectedCodexMember,
    CoordinatorDecision,
)
from isotope.features.supervisor.agent_group.codex_chat.runtime import (
    CodexGroupChatRuntime,
)


def test_confirm_policy_creates_draft_without_sending(tmp_path):
    runtime = CodexGroupChatRuntime(tmp_path)
    runtime.store.save_member(member(send_policy="confirm", status="active"))

    result = runtime.apply_decision(
        CoordinatorDecision(
            decision_id="decision_1",
            group_id="group_rna",
            action="send_member",
            target_member_id="member_research",
            content="Please inspect the new RNA data schema.",
            reason="Research update is useful.",
            created_at="2026-06-12T00:00:00Z",
        )
    )

    assert result["status"] == "draft"
    assert result["send_policy"] == "confirm"
    assert result["sent"] is False
    assert result["draft"]["target_member_id"] == "member_research"


def test_draft_only_policy_never_sends(tmp_path):
    runtime = CodexGroupChatRuntime(tmp_path)
    runtime.store.save_member(member(send_policy="draft_only", status="active"))

    result = runtime.apply_decision(
        CoordinatorDecision(
            decision_id="decision_1",
            group_id="group_rna",
            action="send_member",
            target_member_id="member_research",
            content="Draft only message.",
            reason="User wants manual copy.",
            created_at="2026-06-12T00:00:00Z",
        )
    )

    assert result["status"] == "draft"
    assert result["send_policy"] == "draft_only"
    assert result["sent"] is False


def test_auto_policy_uses_injected_sender(tmp_path):
    sent: list[dict[str, str]] = []
    runtime = CodexGroupChatRuntime(
        tmp_path,
        sender=lambda member_id, text: sent.append({"member_id": member_id, "text": text}),
    )
    runtime.store.save_member(member(send_policy="auto", status="active"))

    result = runtime.apply_decision(
        CoordinatorDecision(
            decision_id="decision_1",
            group_id="group_rna",
            action="send_member",
            target_member_id="member_research",
            content="Auto message.",
            reason="Safe automatic update.",
            created_at="2026-06-12T00:00:00Z",
        )
    )

    assert result["status"] == "sent"
    assert result["sent"] is True
    assert sent == [{"member_id": "member_research", "text": "Auto message."}]


def test_terminated_member_blocks_auto_send(tmp_path):
    sent: list[dict[str, str]] = []
    runtime = CodexGroupChatRuntime(
        tmp_path,
        sender=lambda member_id, text: sent.append({"member_id": member_id, "text": text}),
    )
    runtime.store.save_member(member(send_policy="auto", status="terminated"))

    result = runtime.apply_decision(
        CoordinatorDecision(
            decision_id="decision_1",
            group_id="group_rna",
            action="send_member",
            target_member_id="member_research",
            content="Should not send.",
            reason="Terminated member must be isolated.",
            created_at="2026-06-12T00:00:00Z",
        )
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "target_member_terminated"
    assert sent == []


def test_member_stop_marks_member_terminated(tmp_path):
    runtime = CodexGroupChatRuntime(tmp_path)
    runtime.store.save_member(member(send_policy="auto", status="active"))

    result = runtime.terminate_member(
        group_id="group_rna",
        member_id="member_research",
        reason="User pressed member Stop.",
    )

    assert result["status"] == "terminated"
    assert result["member"]["status"] == "terminated"
    assert runtime.store.list_members("group_rna")[0].status == "terminated"


def member(*, send_policy: str, status: str) -> ConnectedCodexMember:
    return ConnectedCodexMember(
        member_id="member_research",
        group_id="group_rna",
        display_name="Research Codex",
        member_kind="codex_session",
        role="Explore RNA strategy.",
        goal="Find research directions.",
        send_policy=send_policy,
        status=status,
        resume_session_id="session_research",
        source_path="/tmp/research.jsonl",
        managed_record_id=None,
        transcript_policy={},
        created_at="2026-06-12T00:00:00Z",
        updated_at="2026-06-12T00:00:00Z",
    )
```

- [ ] **Step 2: Run the runtime test to verify RED**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/codex_chat/test_runtime.py -q
```

Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `CodexGroupChatRuntime`.

- [ ] **Step 3: Implement runtime policy**

Create `src/isotope/features/supervisor/agent_group/codex_chat/runtime.py`:

```python
"""Runtime policy for Codex-backed Agent Group Chat."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .contracts import CoordinatorDecision
from .store import CodexGroupChatStore


SendMember = Callable[[str, str], None]


class CodexGroupChatRuntime:
    def __init__(
        self,
        root: Path | str,
        *,
        sender: SendMember | None = None,
    ) -> None:
        self.store = CodexGroupChatStore(root)
        self.sender = sender

    def apply_decision(self, decision: CoordinatorDecision) -> dict[str, object]:
        if decision.action == "reply_private":
            message = self.store.append_private_chat(
                group_id=decision.group_id,
                role="assistant",
                content=decision.content,
            )
            return {"status": "private_reply", "message": message.to_public_dict()}
        if decision.action in {"draft_member_send", "send_member"}:
            return self._apply_member_send(decision)
        return {
            "status": "recorded",
            "decision": decision.to_public_dict(),
        }

    def terminate_member(
        self,
        *,
        group_id: str,
        member_id: str,
        reason: str,
    ) -> dict[str, object]:
        control = self.store.record_control(
            group_id=group_id,
            intent="terminate",
            target="member",
            target_member_id=member_id,
            reason=reason,
        )
        member = self.store.update_member_status(
            group_id=group_id,
            member_id=member_id,
            status="terminated",
        )
        return {
            "status": "terminated",
            "control": control.to_public_dict(),
            "member": member.to_public_dict(),
        }

    def stop_current_run(self, *, group_id: str, reason: str) -> dict[str, object]:
        control = self.store.record_control(
            group_id=group_id,
            intent="terminate",
            target="current_run",
            target_member_id=None,
            reason=reason,
        )
        return {"status": "stop_requested", "control": control.to_public_dict()}

    def _apply_member_send(self, decision: CoordinatorDecision) -> dict[str, object]:
        if decision.target_member_id is None:
            raise ValueError("target_member_id is required")
        member = self._member(decision.group_id, decision.target_member_id)
        if member.status == "terminated":
            return {
                "status": "blocked",
                "sent": False,
                "reason": "target_member_terminated",
                "decision": decision.to_public_dict(),
            }
        if decision.action == "draft_member_send" or member.send_policy in {"confirm", "draft_only"}:
            return {
                "status": "draft",
                "sent": False,
                "send_policy": member.send_policy,
                "draft": decision.to_public_dict(),
            }
        if self.sender is None:
            return {
                "status": "draft",
                "sent": False,
                "send_policy": member.send_policy,
                "draft": decision.to_public_dict(),
                "reason": "sender_not_configured",
            }
        self.sender(member.member_id, decision.content)
        return {
            "status": "sent",
            "sent": True,
            "send_policy": member.send_policy,
            "decision": decision.to_public_dict(),
        }

    def _member(self, group_id: str, member_id: str):
        for member in self.store.list_members(group_id):
            if member.member_id == member_id:
                return member
        raise ValueError(f"connected member not found: {member_id}")
```

Modify `src/isotope/features/supervisor/agent_group/codex_chat/__init__.py`:

```python
"""Codex-backed Agent Group Chat support."""

from .contracts import (
    ConnectedCodexMember,
    CoordinatorDecision,
    PrivateChatMessage,
    RuntimeControlRequest,
)
from .runtime import CodexGroupChatRuntime
from .store import CodexGroupChatStore

__all__ = [
    "CodexGroupChatRuntime",
    "CodexGroupChatStore",
    "ConnectedCodexMember",
    "CoordinatorDecision",
    "PrivateChatMessage",
    "RuntimeControlRequest",
]
```

- [ ] **Step 4: Run the runtime test to verify GREEN**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/codex_chat/test_runtime.py -q
```

Expected: PASS.

- [ ] **Step 5: Run focused backend tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/codex_chat tests/unit/integrations/codex/test_codex_transcript.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add src/isotope/features/supervisor/agent_group/codex_chat/__init__.py src/isotope/features/supervisor/agent_group/codex_chat/runtime.py tests/unit/features/supervisor/agent_group/codex_chat/test_runtime.py
git commit -m "feat(supervisor): apply codex group chat runtime controls"
```

---

### Task 5: Desktop Agent Group API

**Files:**
- Create: `src/isotope/features/supervisor/agent_group/codex_chat/api.py`
- Create: `src/isotope/features/supervisor/web/routes/agent_groups.py`
- Modify: `src/isotope/features/supervisor/web/_impl.py`
- Create: `tests/unit/features/supervisor/web/test_agent_group_routes.py`

- [ ] **Step 1: Write route-helper tests**

Create `tests/unit/features/supervisor/web/test_agent_group_routes.py`:

```python
from __future__ import annotations

import pytest

from isotope.features.supervisor.web.routes.agent_groups import (
    agent_group_id_from_path,
    codex_session_id_from_transcript_path,
    parse_agent_group_chat_payload,
    parse_agent_group_control_payload,
)


def test_agent_group_id_from_path():
    assert agent_group_id_from_path("/desktop/agent-groups/group_rna") == "group_rna"
    assert agent_group_id_from_path("/desktop/agent-groups/group_rna/chat") is None


def test_codex_session_id_from_transcript_path():
    assert (
        codex_session_id_from_transcript_path("/desktop/codex-sessions/session_1/transcript")
        == "session_1"
    )
    assert codex_session_id_from_transcript_path("/desktop/codex-sessions/session_1") is None


def test_parse_agent_group_chat_payload():
    payload = parse_agent_group_chat_payload(
        {
            "message": "summarize the current state",
            "mode": "interrupt",
        }
    )

    assert payload == {"message": "summarize the current state", "mode": "interrupt"}


def test_parse_agent_group_control_payload():
    payload = parse_agent_group_control_payload(
        {
            "intent": "terminate",
            "target": "member",
            "target_member_id": "member_research",
            "reason": "User pressed Stop.",
        }
    )

    assert payload["intent"] == "terminate"
    assert payload["target_member_id"] == "member_research"


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "", "mode": "queue"},
        {"message": "x", "mode": "drop"},
    ],
)
def test_parse_agent_group_chat_payload_rejects_invalid_values(payload):
    with pytest.raises(ValueError):
        parse_agent_group_chat_payload(payload)
```

- [ ] **Step 2: Run route-helper tests to verify RED**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/web/test_agent_group_routes.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `web.routes.agent_groups`.

- [ ] **Step 3: Implement route helpers**

Create `src/isotope/features/supervisor/web/routes/agent_groups.py`:

```python
"""Desktop Agent Group Chat route helpers."""

from __future__ import annotations

from urllib.parse import unquote


def agent_group_id_from_path(path: str) -> str | None:
    prefix = "/desktop/agent-groups/"
    if not path.startswith(prefix):
        return None
    group_id = unquote(path[len(prefix):])
    if "/" in group_id or not group_id:
        return None
    return group_id


def codex_session_id_from_transcript_path(path: str) -> str | None:
    prefix = "/desktop/codex-sessions/"
    suffix = "/transcript"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    session_id = unquote(path[len(prefix):-len(suffix)])
    if "/" in session_id or not session_id:
        return None
    return session_id


def parse_agent_group_chat_payload(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    message = _required_string(value.get("message"), "message")
    mode = _required_string(value.get("mode"), "mode")
    if mode not in {"queue", "interrupt"}:
        raise ValueError("mode must be queue or interrupt")
    return {"message": message, "mode": mode}


def parse_agent_group_control_payload(value: object) -> dict[str, str | None]:
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    intent = _required_string(value.get("intent"), "intent")
    target = _required_string(value.get("target"), "target")
    target_member_id = _optional_string(value.get("target_member_id"))
    reason = _required_string(value.get("reason"), "reason")
    if intent not in {"queue", "interrupt", "terminate"}:
        raise ValueError("intent must be queue, interrupt, or terminate")
    if target not in {"current_run", "member"}:
        raise ValueError("target must be current_run or member")
    if target == "member" and not target_member_id:
        raise ValueError("target_member_id is required for member target")
    return {
        "intent": intent,
        "target": target,
        "target_member_id": target_member_id,
        "reason": reason,
    }


def _required_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()
```

- [ ] **Step 4: Implement API helpers**

Create `src/isotope/features/supervisor/agent_group/codex_chat/api.py`:

```python
"""Endpoint-facing helpers for Codex-backed Agent Group Chat."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from isotope.features.supervisor.agent_group.runtime import AgentGroupRuntime
from isotope.features.supervisor.registry.session_lookup import find_codex_session_snapshot
from isotope.integrations.codex.transcript import read_codex_transcript_page

from .contracts import ConnectedCodexMember, CoordinatorDecision
from .runtime import CodexGroupChatRuntime


def list_agent_groups_payload(state_root: Path | str) -> dict[str, Any]:
    return AgentGroupRuntime(state_root).list_groups()


def agent_group_payload(state_root: Path | str, group_id: str) -> dict[str, Any]:
    group_payload = AgentGroupRuntime(state_root).list_group(group_id)
    chat_runtime = CodexGroupChatRuntime(state_root)
    group_payload["connected_members"] = [
        member.to_public_dict() for member in chat_runtime.store.list_members(group_id)
    ]
    group_payload["private_chat"] = [
        message.to_public_dict() for message in chat_runtime.store.list_private_chat(group_id)
    ]
    return group_payload


def add_codex_member_payload(
    state_root: Path | str,
    *,
    group_id: str,
    member_id: str,
    display_name: str,
    role: str,
    goal: str,
    send_policy: str,
    resume_session_id: str,
) -> dict[str, Any]:
    snapshot = find_codex_session_snapshot(codex_home=state_root, session_id=resume_session_id)
    source_path = str(snapshot.source_path) if snapshot is not None else None
    member = ConnectedCodexMember(
        member_id=member_id,
        group_id=group_id,
        display_name=display_name,
        member_kind="codex_session",
        role=role,
        goal=goal,
        send_policy=send_policy,
        status="active",
        resume_session_id=resume_session_id,
        source_path=source_path,
        managed_record_id=None,
        transcript_policy={"page_size": 200, "raw_view": True},
        created_at=_now_placeholder(),
        updated_at=_now_placeholder(),
    )
    saved = CodexGroupChatRuntime(state_root).store.save_member(member)
    return {"status": "ok", "member": saved.to_public_dict()}


def transcript_payload(
    state_root: Path | str,
    *,
    session_id: str,
    offset: int,
    limit: int,
    include_raw: bool,
) -> dict[str, Any]:
    snapshot = find_codex_session_snapshot(codex_home=state_root, session_id=session_id)
    if snapshot is None:
        raise ValueError(f"Codex session not found: {session_id}")
    return read_codex_transcript_page(
        snapshot.source_path,
        offset=offset,
        limit=limit,
        include_raw=include_raw,
    )


def apply_chat_decision_payload(
    state_root: Path | str,
    *,
    group_id: str,
    message: str,
    mode: str,
) -> dict[str, Any]:
    runtime = CodexGroupChatRuntime(state_root)
    if mode == "interrupt":
        runtime.store.record_control(
            group_id=group_id,
            intent="interrupt",
            target="current_run",
            target_member_id=None,
            reason="User interrupted with a new message.",
        )
    decision = CoordinatorDecision(
        decision_id=f"decision_user_{abs(hash((group_id, message))) % 1000000}",
        group_id=group_id,
        action="reply_private",
        target_member_id=None,
        content=message,
        reason="MVP echoes user message into private chat for coordinator handoff.",
        created_at=_now_placeholder(),
    )
    return runtime.apply_decision(decision)


def control_payload(
    state_root: Path | str,
    *,
    group_id: str,
    intent: str,
    target: str,
    target_member_id: str | None,
    reason: str,
) -> dict[str, Any]:
    runtime = CodexGroupChatRuntime(state_root)
    if intent == "terminate" and target == "member" and target_member_id:
        return runtime.terminate_member(group_id=group_id, member_id=target_member_id, reason=reason)
    if intent == "terminate" and target == "current_run":
        return runtime.stop_current_run(group_id=group_id, reason=reason)
    control = runtime.store.record_control(
        group_id=group_id,
        intent=intent,
        target=target,
        target_member_id=target_member_id,
        reason=reason,
    )
    return {"status": "ok", "control": control.to_public_dict()}


def _now_placeholder() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
```

- [ ] **Step 5: Wire `_impl.py` endpoints**

Modify `src/isotope/features/supervisor/web/_impl.py` imports:

```python
from .routes.agent_groups import (
    agent_group_id_from_path,
    codex_session_id_from_transcript_path,
    parse_agent_group_chat_payload,
    parse_agent_group_control_payload,
)
from ..agent_group.codex_chat.api import (
    agent_group_payload,
    apply_chat_decision_payload,
    control_payload as agent_group_control_payload,
    list_agent_groups_payload,
    transcript_payload,
)
```

Add server methods inside `SupervisorDashboardServer`:

```python
    def agent_groups_payload(self) -> dict[str, Any]:
        return list_agent_groups_payload(self.codex_home)

    def agent_group_payload(self, group_id: str) -> dict[str, Any]:
        return agent_group_payload(self.codex_home, group_id)

    def codex_transcript_payload(
        self,
        session_id: str,
        *,
        offset: int,
        limit: int,
        include_raw: bool,
    ) -> dict[str, Any]:
        return transcript_payload(
            self.codex_home,
            session_id=session_id,
            offset=offset,
            limit=limit,
            include_raw=include_raw,
        )
```

Add `do_GET` branches before `self.send_error(404, "not found")`:

```python
        if path == "/desktop/agent-groups":
            self._send_json(self.server.agent_groups_payload())
            return
        group_id = agent_group_id_from_path(path)
        if group_id is not None:
            self._send_json(self.server.agent_group_payload(group_id))
            return
        transcript_session_id = codex_session_id_from_transcript_path(path)
        if transcript_session_id is not None:
            query = urlparse(self.path).query
            params = dict(item.split("=", 1) for item in query.split("&") if "=" in item)
            self._send_json(
                self.server.codex_transcript_payload(
                    transcript_session_id,
                    offset=int(params.get("offset", "0")),
                    limit=int(params.get("limit", "200")),
                    include_raw=params.get("include_raw", "false") == "true",
                )
            )
            return
```

Add `do_POST` branches before `self._send_json(... unknown endpoint ...)`:

```python
        if path.endswith("/chat") and path.startswith("/desktop/agent-groups/"):
            group_id = path[len("/desktop/agent-groups/") : -len("/chat")]
            payload = parse_agent_group_chat_payload(self._read_json_body())
            self._send_json(
                apply_chat_decision_payload(
                    self.server.codex_home,
                    group_id=group_id,
                    message=payload["message"],
                    mode=payload["mode"],
                )
            )
            return
        if path.endswith("/control") and path.startswith("/desktop/agent-groups/"):
            group_id = path[len("/desktop/agent-groups/") : -len("/control")]
            payload = parse_agent_group_control_payload(self._read_json_body())
            self._send_json(
                agent_group_control_payload(
                    self.server.codex_home,
                    group_id=group_id,
                    intent=str(payload["intent"]),
                    target=str(payload["target"]),
                    target_member_id=payload["target_member_id"],
                    reason=str(payload["reason"]),
                )
            )
            return
```

- [ ] **Step 6: Run route helper tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/web/test_agent_group_routes.py -q
```

Expected: PASS.

- [ ] **Step 7: Run focused backend regression**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/codex_chat tests/unit/integrations/codex/test_codex_transcript.py tests/unit/features/supervisor/web/test_agent_group_routes.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 5**

```bash
git add src/isotope/features/supervisor/agent_group/codex_chat/api.py src/isotope/features/supervisor/web/routes/agent_groups.py src/isotope/features/supervisor/web/_impl.py tests/unit/features/supervisor/web/test_agent_group_routes.py
git commit -m "feat(desktop): expose codex agent group endpoints"
```

---

### Task 6: Frontend Contracts And Client

**Files:**
- Create: `apps/desktop/src/lib/contracts/agentGroup.ts`
- Create: `apps/desktop/src/lib/client/agentGroupClient.ts`
- Modify: `apps/desktop/src/lib/client/isotopeClient.ts`
- Create: `apps/desktop/src/lib/client/agentGroupClient.test.ts`

- [ ] **Step 1: Write the failing client tests**

Create `apps/desktop/src/lib/client/agentGroupClient.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import { createAgentGroupClient } from './agentGroupClient';

describe('agentGroupClient', () => {
  it('loads agent group detail', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        status: 'ok',
        group: { group_id: 'group_rna', title: 'RNA group', goal: 'Coordinate RNA work', status: 'active' },
        connected_members: [],
        private_chat: [],
        messages: [],
        turns: []
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    const client = createAgentGroupClient('http://localhost:8765');
    const payload = await client.loadGroup('group_rna');

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8765/desktop/agent-groups/group_rna',
      { cache: 'no-store' }
    );
    expect(payload.group.group_id).toBe('group_rna');
  });

  it('requests member stop through control endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: 'terminated' }));
    vi.stubGlobal('fetch', fetchMock);

    const client = createAgentGroupClient('http://localhost:8765');
    await client.stopMember('group_rna', 'member_research');

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      intent: 'terminate',
      target: 'member',
      target_member_id: 'member_research',
      reason: 'desktop member stop'
    });
  });

  it('loads transcript with offset limit and raw flag', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        status: 'ok',
        session_id: 'session_1',
        offset: 20,
        limit: 50,
        has_more: false,
        next_offset: 21,
        events: []
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    const client = createAgentGroupClient('http://localhost:8765');
    await client.loadTranscript('session_1', { offset: 20, limit: 50, includeRaw: true });

    expect(fetchMock.mock.calls[0][0]).toBe(
      'http://localhost:8765/desktop/codex-sessions/session_1/transcript?offset=20&limit=50&include_raw=true'
    );
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'content-type': 'application/json' }
  });
}
```

- [ ] **Step 2: Run the client tests to verify RED**

Run:

```bash
cd apps/desktop && npm test -- --run src/lib/client/agentGroupClient.test.ts
```

Expected: FAIL because `agentGroupClient.ts` does not exist.

- [ ] **Step 3: Implement frontend contracts**

Create `apps/desktop/src/lib/contracts/agentGroup.ts`:

```ts
export type AgentGroupSummary = {
  group_id: string;
  title: string;
  goal: string;
  status: string;
};

export type ConnectedCodexMember = {
  member_id: string;
  group_id: string;
  display_name: string;
  member_kind: 'codex_session' | 'internal_agent' | 'supervisor';
  role: string;
  goal: string;
  send_policy: 'auto' | 'confirm' | 'draft_only';
  status: 'active' | 'running' | 'idle' | 'needs_user' | 'terminated' | 'blocked' | 'archived';
  resume_session_id?: string | null;
  source_path?: string | null;
  managed_record_id?: string | null;
  transcript_policy?: Record<string, unknown>;
};

export type AgentGroupMessage = {
  message_id: string;
  group_id: string;
  from_member: string;
  to_member?: string | null;
  message_type: string;
  summary: string;
  payload?: Record<string, unknown>;
  created_at?: string;
};

export type PrivateChatMessage = {
  message_id: string;
  group_id: string;
  channel: 'private_human_chat';
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
};

export type AgentGroupDetail = {
  status: 'ok';
  group: AgentGroupSummary;
  connected_members: ConnectedCodexMember[];
  private_chat: PrivateChatMessage[];
  messages: AgentGroupMessage[];
  turns: unknown[];
};

export type TranscriptEvent = {
  event_index: number;
  kind: string;
  title: string;
  text: string;
  timestamp?: string | null;
  role?: string | null;
  raw?: unknown;
};

export type CodexTranscriptPage = {
  status: 'ok';
  session_id: string;
  source_path: string;
  source_size_bytes?: number;
  last_event_at?: string | null;
  offset: number;
  limit: number;
  next_offset: number;
  has_more: boolean;
  total_events: number;
  events: TranscriptEvent[];
};
```

- [ ] **Step 4: Implement frontend client**

Create `apps/desktop/src/lib/client/agentGroupClient.ts`:

```ts
import type { AgentGroupDetail, CodexTranscriptPage } from '../contracts/agentGroup';

export type TranscriptRequest = {
  offset?: number;
  limit?: number;
  includeRaw?: boolean;
};

export type AgentGroupClient = {
  loadGroup(groupId: string): Promise<AgentGroupDetail>;
  stopCurrentRun(groupId: string): Promise<Record<string, unknown>>;
  stopMember(groupId: string, memberId: string): Promise<Record<string, unknown>>;
  loadTranscript(sessionId: string, request?: TranscriptRequest): Promise<CodexTranscriptPage>;
};

export function createAgentGroupClient(baseUrl: string | null): AgentGroupClient {
  const apiBaseUrl = normalizeBaseUrl(baseUrl);
  return {
    async loadGroup(groupId) {
      const base = requiredBase(apiBaseUrl);
      const response = await fetch(`${base}/desktop/agent-groups/${encodeURIComponent(groupId)}`, {
        cache: 'no-store'
      });
      if (!response.ok) throw new Error(await responseErrorMessage(response));
      return (await response.json()) as AgentGroupDetail;
    },
    async stopCurrentRun(groupId) {
      return postControl(requiredBase(apiBaseUrl), groupId, {
        intent: 'terminate',
        target: 'current_run',
        target_member_id: null,
        reason: 'desktop current run stop'
      });
    },
    async stopMember(groupId, memberId) {
      return postControl(requiredBase(apiBaseUrl), groupId, {
        intent: 'terminate',
        target: 'member',
        target_member_id: memberId,
        reason: 'desktop member stop'
      });
    },
    async loadTranscript(sessionId, request = {}) {
      const base = requiredBase(apiBaseUrl);
      const offset = request.offset ?? 0;
      const limit = request.limit ?? 200;
      const includeRaw = request.includeRaw === true;
      const response = await fetch(
        `${base}/desktop/codex-sessions/${encodeURIComponent(sessionId)}/transcript?offset=${offset}&limit=${limit}&include_raw=${includeRaw}`,
        { cache: 'no-store' }
      );
      if (!response.ok) throw new Error(await responseErrorMessage(response));
      return (await response.json()) as CodexTranscriptPage;
    }
  };
}

async function postControl(
  base: string,
  groupId: string,
  payload: Record<string, unknown>
): Promise<Record<string, unknown>> {
  const response = await fetch(`${base}/desktop/agent-groups/${encodeURIComponent(groupId)}/control`, {
    method: 'POST',
    cache: 'no-store',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!response.ok) throw new Error(await responseErrorMessage(response));
  return (await response.json()) as Record<string, unknown>;
}

function normalizeBaseUrl(baseUrl: string | null): string | null {
  const trimmed = baseUrl?.trim();
  return trimmed ? trimmed.replace(/\/$/, '') : null;
}

function requiredBase(baseUrl: string | null): string {
  if (!baseUrl) throw new Error('Agent Group Chat 需要配置后端 URL');
  return baseUrl;
}

async function responseErrorMessage(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    const message = payload?.error?.message;
    if (typeof message === 'string' && message) return message;
  } catch {
    return `Agent Group Chat 请求失败：HTTP ${response.status}`;
  }
  return `Agent Group Chat 请求失败：HTTP ${response.status}`;
}
```

Modify `apps/desktop/src/lib/client/isotopeClient.ts`:

```ts
import { createAgentClient } from './agentClient';
import { createAgentGroupClient } from './agentGroupClient';

export function resolveDesktopApiBaseUrl(): string | null {
  const configured = import.meta.env.VITE_ISOTOPE_DESKTOP_API_BASE as string | undefined;
  const trimmed = configured?.trim();
  return trimmed ? trimmed.replace(/\/$/, '') : null;
}

export function createIsotopeClient(baseUrl: string | null = resolveDesktopApiBaseUrl()) {
  const apiBaseUrl = baseUrl?.trim() ? baseUrl.trim().replace(/\/$/, '') : null;

  return {
    apiBaseUrl,
    hasRealApiBaseUrl: apiBaseUrl !== null,
    agentClient: createAgentClient(apiBaseUrl),
    agentGroupClient: createAgentGroupClient(apiBaseUrl)
  };
}

export type IsotopeClient = ReturnType<typeof createIsotopeClient>;
```

- [ ] **Step 5: Run the client tests to verify GREEN**

Run:

```bash
cd apps/desktop && npm test -- --run src/lib/client/agentGroupClient.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit Task 6**

```bash
git add apps/desktop/src/lib/contracts/agentGroup.ts apps/desktop/src/lib/client/agentGroupClient.ts apps/desktop/src/lib/client/isotopeClient.ts apps/desktop/src/lib/client/agentGroupClient.test.ts
git commit -m "feat(desktop): add agent group client"
```

---

### Task 7: Agent Group Chat Frontend Page

**Files:**
- Create: `apps/desktop/src/lib/components/agentGroup/AgentGroupWorkspace.svelte`
- Create: `apps/desktop/src/lib/components/agentGroup/AgentGroupMemberStrip.svelte`
- Create: `apps/desktop/src/lib/components/agentGroup/AgentGroupStream.svelte`
- Create: `apps/desktop/src/lib/components/agentGroup/AgentGroupPrivateChat.svelte`
- Create: `apps/desktop/src/lib/components/agentGroup/CodexTranscriptPanel.svelte`
- Create: `apps/desktop/src/lib/components/agentGroup/AgentGroupWorkspace.test.ts`
- Modify: `apps/desktop/src/routes/+page.svelte`

- [ ] **Step 1: Write the failing workspace component test**

Create `apps/desktop/src/lib/components/agentGroup/AgentGroupWorkspace.test.ts`:

```ts
import { render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import AgentGroupWorkspace from './AgentGroupWorkspace.svelte';
import type { AgentGroupClient } from '../../client/agentGroupClient';

describe('AgentGroupWorkspace', () => {
  it('renders two-layer stop controls', () => {
    render(AgentGroupWorkspace, {
      props: {
        group: fixtureGroup(),
        isRunning: true,
        composerText: '',
        agentGroupClient: fakeClient()
      }
    });

    expect(screen.getByRole('button', { name: 'Stop current run' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Stop Research Codex' })).toBeTruthy();
  });

  it('renders queue and interrupt when composer has text during a run', () => {
    render(AgentGroupWorkspace, {
      props: {
        group: fixtureGroup(),
        isRunning: true,
        composerText: 'new instruction',
        agentGroupClient: fakeClient()
      }
    });

    expect(screen.getByRole('button', { name: 'Queue' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Interrupt' })).toBeTruthy();
  });
});

function fixtureGroup() {
  return {
    status: 'ok' as const,
    group: { group_id: 'group_rna', title: 'RNA group', goal: 'Coordinate RNA work', status: 'active' },
    connected_members: [
      {
        member_id: 'member_research',
        group_id: 'group_rna',
        display_name: 'Research Codex',
        member_kind: 'codex_session' as const,
        role: 'Explore RNA strategy.',
        goal: 'Find directions.',
        send_policy: 'confirm' as const,
        status: 'active' as const,
        resume_session_id: 'session_research',
        source_path: '/tmp/research.jsonl',
        managed_record_id: null,
        transcript_policy: {}
      }
    ],
    private_chat: [
      {
        message_id: 'private_1',
        group_id: 'group_rna',
        channel: 'private_human_chat' as const,
        role: 'assistant' as const,
        content: 'Ask before sending.',
        created_at: '2026-06-12T00:00:00Z'
      }
    ],
    messages: [
      {
        message_id: 'msg_1',
        group_id: 'group_rna',
        from_member: 'supervisor',
        message_type: 'status',
        summary: 'Group opened.'
      }
    ],
    turns: []
  };
}

function fakeClient(): AgentGroupClient {
  return {
    loadGroup: vi.fn(),
    stopCurrentRun: vi.fn(),
    stopMember: vi.fn(),
    loadTranscript: vi.fn()
  };
}
```

- [ ] **Step 2: Run the workspace test to verify RED**

Run:

```bash
cd apps/desktop && npm test -- --run src/lib/components/agentGroup/AgentGroupWorkspace.test.ts
```

Expected: FAIL because `AgentGroupWorkspace.svelte` does not exist.

- [ ] **Step 3: Implement member strip**

Create `apps/desktop/src/lib/components/agentGroup/AgentGroupMemberStrip.svelte`:

```svelte
<script lang="ts">
  import type { ConnectedCodexMember } from '../../contracts/agentGroup';

  let { members, onStopMember } = $props<{
    members: ConnectedCodexMember[];
    onStopMember: (memberId: string) => void;
  }>();
</script>

<aside class="border-b border-isotope-line bg-white px-4 py-3" aria-label="Connected AI sessions">
  <div class="flex gap-3 overflow-x-auto">
    {#each members as member (member.member_id)}
      <section class="min-w-64 border border-isotope-line bg-isotope-panel px-3 py-2">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="truncate text-sm font-semibold text-isotope-text">{member.display_name}</div>
            <div class="mt-1 text-xs text-isotope-muted">{member.send_policy} · {member.status}</div>
            <div class="mt-1 line-clamp-2 text-xs leading-5 text-isotope-muted">{member.role}</div>
          </div>
          <button
            class="shrink-0 border border-isotope-error bg-white px-2 py-1 text-xs font-semibold text-isotope-error disabled:opacity-50"
            type="button"
            disabled={member.status === 'terminated'}
            aria-label={`Stop ${member.display_name}`}
            onclick={() => onStopMember(member.member_id)}
          >
            Stop
          </button>
        </div>
      </section>
    {/each}
  </div>
</aside>
```

- [ ] **Step 4: Implement group stream**

Create `apps/desktop/src/lib/components/agentGroup/AgentGroupStream.svelte`:

```svelte
<script lang="ts">
  import type { AgentGroupMessage } from '../../contracts/agentGroup';

  let { messages } = $props<{ messages: AgentGroupMessage[] }>();
</script>

<section class="min-h-0 flex-1 overflow-y-auto px-5 py-4" aria-label="Agent group public stream">
  {#if messages.length === 0}
    <div class="border border-isotope-line bg-isotope-panel px-4 py-3 text-sm text-isotope-muted">
      还没有公共群聊消息。
    </div>
  {:else}
    <div class="space-y-3">
      {#each messages as message (message.message_id)}
        <article class="border border-isotope-line bg-white px-4 py-3">
          <div class="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase text-isotope-muted">
            <span>{message.from_member}</span>
            <span>{message.message_type}</span>
            {#if message.to_member}<span>to {message.to_member}</span>{/if}
          </div>
          <p class="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-isotope-text">{message.summary}</p>
        </article>
      {/each}
    </div>
  {/if}
</section>
```

- [ ] **Step 5: Implement private chat pane**

Create `apps/desktop/src/lib/components/agentGroup/AgentGroupPrivateChat.svelte`:

```svelte
<script lang="ts">
  import type { PrivateChatMessage } from '../../contracts/agentGroup';

  let { messages } = $props<{ messages: PrivateChatMessage[] }>();
</script>

<section class="border-l border-isotope-line bg-isotope-panel px-4 py-4" aria-label="AI human private chat">
  <div class="text-xs font-semibold uppercase text-isotope-muted">AI ↔ 人</div>
  <div class="mt-3 space-y-3">
    {#each messages as message (message.message_id)}
      <article class="border border-isotope-line bg-white px-3 py-2">
        <div class="text-xs font-semibold text-isotope-muted">{message.role}</div>
        <p class="mt-1 whitespace-pre-wrap break-words text-sm leading-6 text-isotope-text">{message.content}</p>
      </article>
    {/each}
  </div>
</section>
```

- [ ] **Step 6: Implement transcript panel**

Create `apps/desktop/src/lib/components/agentGroup/CodexTranscriptPanel.svelte`:

```svelte
<script lang="ts">
  import type { CodexTranscriptPage } from '../../contracts/agentGroup';

  let { transcript = null, showRaw = false, onToggleRaw } = $props<{
    transcript?: CodexTranscriptPage | null;
    showRaw?: boolean;
    onToggleRaw?: () => void;
  }>();
</script>

<section class="border-t border-isotope-line bg-white px-4 py-3" aria-label="Codex transcript">
  <div class="flex items-center justify-between gap-3">
    <div>
      <div class="text-xs font-semibold uppercase text-isotope-muted">Codex transcript</div>
      <div class="mt-1 text-sm font-semibold text-isotope-text">
        {transcript?.session_id ?? '未选择会话'}
      </div>
    </div>
    <button
      class="border border-isotope-line bg-isotope-panel px-3 py-1.5 text-xs font-semibold text-isotope-muted"
      type="button"
      onclick={() => onToggleRaw?.()}
    >
      {showRaw ? 'Readable' : 'Raw'}
    </button>
  </div>
  <div class="mt-3 max-h-80 overflow-auto border border-isotope-line bg-isotope-panel">
    {#if !transcript}
      <p class="px-3 py-2 text-sm text-isotope-muted">选择一个 Codex 成员查看 transcript。</p>
    {:else}
      {#each transcript.events as event (event.event_index)}
        <article class="border-b border-isotope-line px-3 py-2">
          <div class="flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase text-isotope-muted">
            <span>#{event.event_index}</span>
            <span>{event.kind}</span>
            {#if event.timestamp}<span>{event.timestamp}</span>{/if}
          </div>
          <pre class="mt-1 whitespace-pre-wrap break-words text-xs leading-5 text-isotope-text">{showRaw ? JSON.stringify(event.raw ?? event, null, 2) : event.text}</pre>
        </article>
      {/each}
    {/if}
  </div>
</section>
```

- [ ] **Step 7: Implement workspace component**

Create `apps/desktop/src/lib/components/agentGroup/AgentGroupWorkspace.svelte`:

```svelte
<script lang="ts">
  import type { AgentGroupClient } from '../../client/agentGroupClient';
  import type { AgentGroupDetail, CodexTranscriptPage } from '../../contracts/agentGroup';
  import AgentGroupMemberStrip from './AgentGroupMemberStrip.svelte';
  import AgentGroupPrivateChat from './AgentGroupPrivateChat.svelte';
  import AgentGroupStream from './AgentGroupStream.svelte';
  import CodexTranscriptPanel from './CodexTranscriptPanel.svelte';

  let {
    group,
    isRunning = false,
    composerText = '',
    agentGroupClient
  } = $props<{
    group: AgentGroupDetail;
    isRunning?: boolean;
    composerText?: string;
    agentGroupClient: AgentGroupClient;
  }>();

  let localComposerText = $state(composerText);
  let transcript = $state<CodexTranscriptPage | null>(null);
  let showRaw = $state(false);
  const composerIsEmpty = $derived(localComposerText.trim().length === 0);

  async function stopCurrentRun() {
    await agentGroupClient.stopCurrentRun(group.group.group_id);
  }

  async function stopMember(memberId: string) {
    await agentGroupClient.stopMember(group.group.group_id, memberId);
  }
</script>

<section class="flex min-h-screen flex-col bg-white text-isotope-text" aria-label="Agent Group Chat">
  <header class="border-b border-isotope-line px-5 py-4">
    <div class="text-xs font-semibold uppercase text-isotope-muted">Agent Group Chat</div>
    <h1 class="mt-1 text-xl font-semibold">{group.group.title}</h1>
  </header>

  <AgentGroupMemberStrip members={group.connected_members} onStopMember={stopMember} />

  <div class="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_22rem]">
    <AgentGroupStream messages={group.messages} />
    <AgentGroupPrivateChat messages={group.private_chat} />
  </div>

  <CodexTranscriptPanel {transcript} {showRaw} onToggleRaw={() => (showRaw = !showRaw)} />

  <footer class="border-t border-isotope-line px-5 py-4">
    <div class="flex gap-2">
      <input
        class="min-w-0 flex-1 border border-isotope-line px-3 py-2 text-sm"
        bind:value={localComposerText}
        placeholder="给协调模型发消息"
      />
      {#if isRunning && composerIsEmpty}
        <button class="border border-isotope-error bg-isotope-error px-4 py-2 text-sm font-semibold text-white" type="button" onclick={stopCurrentRun}>
          Stop current run
        </button>
      {:else if isRunning}
        <button class="border border-isotope-line bg-white px-4 py-2 text-sm font-semibold text-isotope-muted" type="button">
          Queue
        </button>
        <button class="border border-isotope-running bg-isotope-running px-4 py-2 text-sm font-semibold text-white" type="button">
          Interrupt
        </button>
      {:else}
        <button class="border border-isotope-running bg-isotope-running px-4 py-2 text-sm font-semibold text-white" type="button">
          Send
        </button>
      {/if}
    </div>
  </footer>
</section>
```

- [ ] **Step 8: Wire page-level mode switch**

Modify `apps/desktop/src/routes/+page.svelte`.

Add import:

```svelte
  import AgentGroupWorkspace from '$lib/components/agentGroup/AgentGroupWorkspace.svelte';
```

Add a temporary fixture near existing state declarations:

```svelte
  let desktopMode = $state<'chat' | 'agent-group'>('chat');
  const agentGroupFixture = {
    status: 'ok' as const,
    group: { group_id: 'group_rna', title: 'RNA Codex group', goal: 'Coordinate RNA research and engineering.', status: 'active' },
    connected_members: [],
    private_chat: [],
    messages: [],
    turns: []
  };
```

Inside the `surface !== 'mini'` branches, wrap the existing `MainWindowShell` with a mode switch:

```svelte
      <div class="fixed right-4 top-4 z-10 flex gap-2">
        <button class="border border-isotope-line bg-white px-3 py-1.5 text-xs font-semibold" type="button" onclick={() => (desktopMode = 'chat')}>Chat</button>
        <button class="border border-isotope-line bg-white px-3 py-1.5 text-xs font-semibold" type="button" onclick={() => (desktopMode = 'agent-group')}>Agent Group</button>
      </div>
      {#if desktopMode === 'agent-group'}
        <AgentGroupWorkspace
          group={agentGroupFixture}
          isRunning={false}
          agentGroupClient={isotopeClient.agentGroupClient}
        />
      {:else}
        <MainWindowShell
          snapshot={$snapshot}
          selectedActivity={$selectedActivity}
          chatMessages={$chatMessages}
          chatError={$chatError}
          isAskingDesktop={$isAskingDesktop}
          resolvingApprovalId={$isResolvingApproval}
          approvalError={$approvalError}
          agentClient={isotopeClient.agentClient}
          onAskDesktop={(question) => void appState.askDesktopQuestion(question)}
          onResolveApproval={(approvalId, resolution) => void appState.resolveApproval(approvalId, resolution)}
        />
      {/if}
```

Use the same pattern in both non-mini branches in this task. Keep the duplicate branch structure in `+page.svelte` for this MVP so the page wiring stays small and reviewable.

- [ ] **Step 9: Run workspace tests to verify GREEN**

Run:

```bash
cd apps/desktop && npm test -- --run src/lib/components/agentGroup/AgentGroupWorkspace.test.ts
```

Expected: PASS.

- [ ] **Step 10: Run frontend focused regression**

Run:

```bash
cd apps/desktop && npm test -- --run src/lib/client/agentGroupClient.test.ts src/lib/components/agentGroup/AgentGroupWorkspace.test.ts
```

Expected: PASS.

- [ ] **Step 11: Commit Task 7**

```bash
git add apps/desktop/src/lib/components/agentGroup apps/desktop/src/routes/+page.svelte
git commit -m "feat(desktop): add agent group chat workspace"
```

---

### Task 8: Product Smoke Test

**Files:**
- Create: `tests/integration/supervisor/desktop/test_agent_group_codex_chat_smoke.py`

- [ ] **Step 1: Write the failing integration smoke**

Create `tests/integration/supervisor/desktop/test_agent_group_codex_chat_smoke.py`:

```python
from __future__ import annotations

import json

from isotope.features.supervisor.agent_group.runtime import AgentGroupRuntime
from isotope.features.supervisor.agent_group.codex_chat.contracts import ConnectedCodexMember
from isotope.features.supervisor.agent_group.codex_chat.runtime import CodexGroupChatRuntime
from isotope.features.supervisor.agent_group.codex_chat.api import transcript_payload


def test_agent_group_codex_chat_fake_two_session_smoke(tmp_path):
    codex_home = tmp_path / ".codex"
    research_session = "019e9830-8a72-7ff1-8b2e-310b9d66372b"
    engineering_session = "019e9830-8a72-7ff1-8b2e-310b9d66372c"
    write_session(codex_home, research_session, "research update")
    write_session(codex_home, engineering_session, "engineering update")

    group = AgentGroupRuntime(codex_home).create_group(
        title="RNA Codex group",
        goal="Coordinate RNA research and engineering.",
        member_specs=[{"name": "coordinator", "role": "Coordinate.", "goal": "Keep lanes synced."}],
        initial_message="Open the group.",
    )
    group_id = group["group"]["group_id"]
    chat_runtime = CodexGroupChatRuntime(codex_home)
    chat_runtime.store.save_member(member(group_id, "member_research", "Research Codex", research_session))
    chat_runtime.store.save_member(member(group_id, "member_engineering", "Engineering Codex", engineering_session))

    research_page = transcript_payload(codex_home, session_id=research_session, offset=0, limit=20, include_raw=False)
    stop = chat_runtime.terminate_member(
        group_id=group_id,
        member_id="member_research",
        reason="User pressed member Stop.",
    )

    assert research_page["events"][-1]["text"] == "research update"
    assert stop["status"] == "terminated"
    assert chat_runtime.store.list_members(group_id)[0].status == "terminated"


def write_session(codex_home, session_id: str, assistant_text: str) -> None:
    path = codex_home / "sessions" / "2026" / "06" / "12" / f"rollout-{session_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"type": "session_meta", "timestamp": "2026-06-12T00:00:00Z", "payload": {"id": session_id, "cwd": "/home/lumber/Github/AI_Camp_RNA_2026"}},
        {"type": "response_item", "timestamp": "2026-06-12T00:00:01Z", "payload": {"type": "message", "role": "assistant", "content": assistant_text}},
    ]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def member(group_id: str, member_id: str, display_name: str, session_id: str) -> ConnectedCodexMember:
    return ConnectedCodexMember(
        member_id=member_id,
        group_id=group_id,
        display_name=display_name,
        member_kind="codex_session",
        role="Coordinate lane.",
        goal="Keep the lane moving.",
        send_policy="confirm",
        status="active",
        resume_session_id=session_id,
        source_path=None,
        managed_record_id=None,
        transcript_policy={},
        created_at="2026-06-12T00:00:00Z",
        updated_at="2026-06-12T00:00:00Z",
    )
```

- [ ] **Step 2: Run smoke to verify RED or fixture failure**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/supervisor/desktop/test_agent_group_codex_chat_smoke.py -q
```

Expected before previous tasks: FAIL. Expected after Tasks 1-5: PASS.

- [ ] **Step 3: Run smoke to verify GREEN after backend tasks**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/supervisor/desktop/test_agent_group_codex_chat_smoke.py -q
```

Expected: PASS.

- [ ] **Step 4: Run full focused regression**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group tests/unit/integrations/codex/test_codex_transcript.py tests/unit/features/supervisor/web/test_agent_group_routes.py tests/integration/supervisor/desktop/test_agent_group_codex_chat_smoke.py -q
cd apps/desktop && npm test -- --run src/lib/client/agentGroupClient.test.ts src/lib/components/agentGroup/AgentGroupWorkspace.test.ts
```

Expected: PASS.

- [ ] **Step 5: Run dev-eval changed-surface gate**

Run:

```bash
scripts/dev-eval changed_surface --base origin/main --json
```

Expected: command exits 0 and prints JSON. If `eval_required=true`, run the command in `recommended_smoke.full_command` from the JSON output and read any generated reviewer prompts under `.dev-eval-runs/**/state/dev-evals/reviewer-prompts/*.md`.

- [ ] **Step 6: Commit Task 8**

```bash
git add tests/integration/supervisor/desktop/test_agent_group_codex_chat_smoke.py
git commit -m "test(desktop): cover codex agent group chat smoke"
```

---

### Task 9: Final Verification And Integration Cleanup

**Files:**
- All files changed in Tasks 1-8.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group tests/unit/integrations/codex/test_codex_transcript.py tests/unit/features/supervisor/web/test_agent_group_routes.py tests/integration/supervisor/desktop/test_agent_group_codex_chat_smoke.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend focused tests**

Run:

```bash
cd apps/desktop && npm test -- --run src/lib/client/agentGroupClient.test.ts src/lib/components/agentGroup/AgentGroupWorkspace.test.ts
```

Expected: PASS.

- [ ] **Step 3: Run changed-surface gate**

Run:

```bash
scripts/dev-eval changed_surface --base origin/main --json
```

Expected: exits 0. If the JSON has `"eval_required": true`, run the recommended smoke command and report hard gates, scores, reviewer findings, and follow-up changes.

- [ ] **Step 4: Inspect the final diff**

Run:

```bash
git diff --stat origin/main...HEAD
git diff --check origin/main...HEAD
```

Expected: `git diff --check` exits 0.

- [ ] **Step 5: Commit final cleanup when Step 4 reveals small issues**

When Step 4 shows only intended changes and no cleanup commit is required, skip this step. When Step 4 reveals small naming or documentation cleanup, make the cleanup and commit:

```bash
git add <changed-files>
git commit -m "chore: polish codex agent group chat"
```

- [ ] **Step 6: Push the branch**

Run:

```bash
git push
```

Expected: remote accepts the push.

## Self-Review

Spec coverage:

- Page entry and frontend layout: Task 7.
- Connected Codex sessions and member metadata: Tasks 1, 3, 5, 6, 7.
- Private AI-human chat: Tasks 1, 3, 4, 7.
- High-fidelity transcript paging: Tasks 2, 5, 6, 7, 8.
- Model-owned send decision with `auto`, `confirm`, and `draft_only`: Task 4.
- Queue, interrupt, and terminate runtime controls: Tasks 4, 5, 7.
- Two-layer Stop UI: Task 7.
- Terminated member excluded from auto-send: Task 4.
- Product smoke for two Codex sessions: Task 8.
- Dev-eval gate for Supervisor/desktop surface: Task 8 and Task 9.

Placeholder scan:

- Search for red-flag placeholder terms from the writing-plans skill and remove any hits.

Type consistency:

- Python contract names are `ConnectedCodexMember`, `PrivateChatMessage`,
  `CoordinatorDecision`, and `RuntimeControlRequest`.
- Runtime class name is `CodexGroupChatRuntime`.
- Store class name is `CodexGroupChatStore`.
- Frontend client name is `AgentGroupClient`.
- Frontend detail type name is `AgentGroupDetail`.
