# Agent Group Chat Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first CLI-level Agent group chat runtime where Supervisor creates an internal LLM-agent group, sends messages, runs one arbitrated turn, persists public messages, and lists group state.

**Architecture:** Add a focused `agent_group` package under `src/isotope/features/supervisor/`. Store durable group/member/turn records in `FileMemoryStore`, publish public chat messages through the existing `worker_event_channel`, reuse `AgentConversationMessage` plus `arbitrate_agent_conversation_turn(...)` for turn selection, and expose CLI commands through the existing Supervisor parser/dispatch pattern.

**Tech Stack:** Python 3.13, pytest, dataclasses, existing Supervisor CLI parser/dispatch, `FileMemoryStore`, `worker_event_channel`, and `isotope.agents.loop.conversation`.

---

## Reuse Audit

- Reuse `isotope.platform.state.worker_event_channel.publish_worker_event(...)` and `list_worker_events(...)` for public group messages.
- Reuse `isotope.platform.state.memory_store.FileMemoryStore` for group/member/turn records.
- Reuse `isotope.agents.loop.conversation.AgentConversationMessage` and `arbitrate_agent_conversation_turn(...)`; do not create a separate arbiter.
- Reuse Supervisor CLI parser split: add a parser helper under `commands/parser/` and a handler under `commands/handlers/`.
- Reuse `--state-root` / hidden `--codex-home` semantics through `add_state_root_arg(...)`.
- Do not touch managed Codex registry/fanout/merge code in this first slice.
- Do not add desktop chat or SSE wiring in this plan; those come after the runtime contract is stable.

## File Structure

- Create `src/isotope/features/supervisor/agent_group/__init__.py`: public exports for the package.
- Create `src/isotope/features/supervisor/agent_group/contracts.py`: dataclasses, validation, raw-payload guard.
- Create `src/isotope/features/supervisor/agent_group/store.py`: memory-backed group/member/turn persistence and worker-event message publishing.
- Create `src/isotope/features/supervisor/agent_group/runtime.py`: create group, send message, run deterministic/provider-backed tick, list groups.
- Create `src/isotope/features/supervisor/commands/parser/agent_group.py`: CLI parser registration.
- Create `src/isotope/features/supervisor/commands/handlers/agent_group.py`: CLI handler and plain renderers.
- Modify `src/isotope/features/supervisor/commands/parser/__init__.py`: register `agent-group`.
- Modify `src/isotope/features/supervisor/commands/dispatch.py`: dispatch `agent-group`.
- Create `tests/unit/features/supervisor/agent_group/test_agent_group_contracts.py`.
- Create `tests/unit/features/supervisor/agent_group/test_agent_group_store.py`.
- Create `tests/integration/supervisor/test_supervisor_agent_group_cli.py`.

## Task 1: Contracts

**Files:**
- Create: `src/isotope/features/supervisor/agent_group/__init__.py`
- Create: `src/isotope/features/supervisor/agent_group/contracts.py`
- Create: `tests/unit/features/supervisor/agent_group/test_agent_group_contracts.py`

- [ ] **Step 1: Write failing contract tests**

Create `tests/unit/features/supervisor/agent_group/test_agent_group_contracts.py`:

```python
from __future__ import annotations

import pytest

from isotope.features.supervisor.agent_group.contracts import (
    AgentGroup,
    AgentGroupMessage,
    AgentMember,
    AgentTurn,
)


def test_agent_group_contracts_to_public_dicts():
    group = AgentGroup(
        group_id="group_001",
        title="Feature group",
        goal="Design agent group chat.",
        status="active",
        created_at="2026-06-04T00:00:00Z",
        updated_at="2026-06-04T00:00:00Z",
    )
    member = AgentMember(
        member_id="member_planner",
        group_id="group_001",
        name="planner",
        role="Plan the work.",
        goal="Find risks.",
        model_profile="default",
        allowed_capabilities=("memory.query",),
        status="active",
    )
    message = AgentGroupMessage(
        message_id="msg_001",
        group_id="group_001",
        turn_id="turn_001",
        from_member="supervisor",
        to_member=None,
        message_type="task",
        summary="Start with risks.",
        payload={"priority": "normal"},
        created_at="2026-06-04T00:00:01Z",
    )
    turn = AgentTurn(
        turn_id="turn_001",
        group_id="group_001",
        input_message_ids=("msg_001",),
        candidate_messages=("candidate_001",),
        selected_message_ids=("msg_002",),
        queued_messages=({"message_id": "candidate_002", "reason": "visible_limit"},),
        dropped_messages=(),
        status="selected",
        supervisor_summary="Planner replied.",
        created_at="2026-06-04T00:00:02Z",
    )

    assert group.to_public_dict()["goal"] == "Design agent group chat."
    assert member.to_public_dict()["allowed_capabilities"] == ["memory.query"]
    assert message.to_public_dict()["to_member"] is None
    assert turn.to_public_dict()["selected_message_ids"] == ["msg_002"]


@pytest.mark.parametrize(
    "factory, kwargs, message",
    [
        (
            AgentGroup,
            {
                "group_id": "",
                "title": "x",
                "goal": "x",
                "status": "active",
                "created_at": "now",
                "updated_at": "now",
            },
            "group_id must be a non-empty string",
        ),
        (
            AgentMember,
            {
                "member_id": "member_1",
                "group_id": "group_1",
                "name": "worker",
                "role": "role",
                "goal": "goal",
                "model_profile": "default",
                "allowed_capabilities": (),
                "status": "running",
            },
            "member status must be one of",
        ),
        (
            AgentGroupMessage,
            {
                "message_id": "msg_1",
                "group_id": "group_1",
                "turn_id": "turn_1",
                "from_member": "supervisor",
                "to_member": None,
                "message_type": "raw",
                "summary": "x",
                "payload": {},
                "created_at": "now",
            },
            "message_type must be one of",
        ),
    ],
)
def test_contracts_reject_invalid_values(factory, kwargs, message):
    with pytest.raises(ValueError, match=message):
        factory(**kwargs)


def test_group_message_rejects_raw_payload_keys():
    with pytest.raises(ValueError, match="raw group payload is not accepted"):
        AgentGroupMessage(
            message_id="msg_raw",
            group_id="group_1",
            turn_id="turn_1",
            from_member="member_a",
            to_member=None,
            message_type="reply",
            summary="Do not leak raw content.",
            payload={"raw_response": "secret"},
            created_at="2026-06-04T00:00:00Z",
        )
```

- [ ] **Step 2: Run contract tests to verify failure**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/test_agent_group_contracts.py -q
```

Expected: FAIL because `isotope.features.supervisor.agent_group` does not exist.

- [ ] **Step 3: Implement contracts**

Create `src/isotope/features/supervisor/agent_group/contracts.py`:

```python
"""Public contracts for Supervisor Agent group chat."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


GROUP_STATUSES = {"active", "paused", "done", "archived"}
MEMBER_STATUSES = {"active", "silent", "blocked", "done", "archived"}
MESSAGE_TYPES = {
    "task",
    "reply",
    "question",
    "observation",
    "summary",
    "interrupt",
    "status",
}
TURN_STATUSES = {"selected", "silent", "blocked", "error"}
RAW_GROUP_FIELDS = {
    "api_key",
    "artifact_content",
    "full_content",
    "full_text",
    "messages",
    "model_prompt",
    "model_request",
    "model_response",
    "prompt",
    "raw_artifact_content",
    "raw_content",
    "raw_prompt",
    "raw_response",
    "stderr",
    "stdin",
    "stdout",
}


@dataclass(frozen=True)
class AgentGroup:
    group_id: str
    title: str
    goal: str
    status: str
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        _require_text(self.group_id, "group_id")
        _require_text(self.title, "title")
        _require_text(self.goal, "goal")
        _require_text(self.created_at, "created_at")
        _require_text(self.updated_at, "updated_at")
        _require_choice(self.status, GROUP_STATUSES, "group status")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "title": self.title,
            "goal": self.goal,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class AgentMember:
    member_id: str
    group_id: str
    name: str
    role: str
    goal: str
    model_profile: str = "default"
    allowed_capabilities: tuple[str, ...] = ()
    status: str = "active"

    def __post_init__(self) -> None:
        _require_text(self.member_id, "member_id")
        _require_text(self.group_id, "group_id")
        _require_text(self.name, "name")
        _require_text(self.role, "role")
        _require_text(self.goal, "goal")
        _require_text(self.model_profile, "model_profile")
        _require_choice(self.status, MEMBER_STATUSES, "member status")
        if not isinstance(self.allowed_capabilities, tuple):
            raise ValueError("allowed_capabilities must be a tuple")
        for capability_id in self.allowed_capabilities:
            _require_text(capability_id, "allowed_capability")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "member_id": self.member_id,
            "group_id": self.group_id,
            "name": self.name,
            "role": self.role,
            "goal": self.goal,
            "model_profile": self.model_profile,
            "allowed_capabilities": list(self.allowed_capabilities),
            "status": self.status,
        }


@dataclass(frozen=True)
class AgentGroupMessage:
    message_id: str
    group_id: str
    turn_id: str
    from_member: str
    to_member: str | None
    message_type: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        _require_text(self.message_id, "message_id")
        _require_text(self.group_id, "group_id")
        _require_text(self.turn_id, "turn_id")
        _require_text(self.from_member, "from_member")
        if self.to_member is not None:
            _require_text(self.to_member, "to_member")
        _require_choice(self.message_type, MESSAGE_TYPES, "message_type")
        _require_text(self.summary, "summary")
        _require_text(self.created_at, "created_at")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dict")
        _reject_raw_group_payload(self.payload)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "group_id": self.group_id,
            "turn_id": self.turn_id,
            "from_member": self.from_member,
            "to_member": self.to_member,
            "message_type": self.message_type,
            "summary": self.summary,
            "payload": _copy_public_payload(self.payload),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class AgentTurn:
    turn_id: str
    group_id: str
    input_message_ids: tuple[str, ...]
    candidate_messages: tuple[str, ...]
    selected_message_ids: tuple[str, ...]
    queued_messages: tuple[dict[str, Any], ...]
    dropped_messages: tuple[dict[str, Any], ...]
    status: str
    supervisor_summary: str
    created_at: str

    def __post_init__(self) -> None:
        _require_text(self.turn_id, "turn_id")
        _require_text(self.group_id, "group_id")
        _require_choice(self.status, TURN_STATUSES, "turn status")
        _require_text(self.supervisor_summary, "supervisor_summary")
        _require_text(self.created_at, "created_at")
        for field_name in (
            "input_message_ids",
            "candidate_messages",
            "selected_message_ids",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, tuple):
                raise ValueError(f"{field_name} must be a tuple")
            for item in value:
                _require_text(item, field_name)
        for field_name in ("queued_messages", "dropped_messages"):
            value = getattr(self, field_name)
            if not isinstance(value, tuple):
                raise ValueError(f"{field_name} must be a tuple")
            for item in value:
                if not isinstance(item, dict):
                    raise ValueError(f"{field_name} items must be dicts")
                _reject_raw_group_payload(item)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "group_id": self.group_id,
            "input_message_ids": list(self.input_message_ids),
            "candidate_messages": list(self.candidate_messages),
            "selected_message_ids": list(self.selected_message_ids),
            "queued_messages": [_copy_public_payload(item) for item in self.queued_messages],
            "dropped_messages": [_copy_public_payload(item) for item in self.dropped_messages],
            "status": self.status,
            "supervisor_summary": self.supervisor_summary,
            "created_at": self.created_at,
        }


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_choice(value: object, choices: set[str], field_name: str) -> None:
    if value not in choices:
        options = ", ".join(sorted(choices))
        raise ValueError(f"{field_name} must be one of: {options}")


def _reject_raw_group_payload(value: Any) -> None:
    if isinstance(value, dict):
        if RAW_GROUP_FIELDS.intersection(value):
            raise ValueError("raw group payload is not accepted")
        for nested in value.values():
            _reject_raw_group_payload(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_raw_group_payload(nested)


def _copy_public_payload(value: dict[str, Any]) -> dict[str, Any]:
    _reject_raw_group_payload(value)
    return {str(key): _copy_public_value(nested) for key, nested in value.items()}


def _copy_public_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _copy_public_payload(value)
    if isinstance(value, list):
        return [_copy_public_value(item) for item in value]
    return value
```

Create `src/isotope/features/supervisor/agent_group/__init__.py`:

```python
"""Supervisor Agent group chat runtime."""

from __future__ import annotations

from .contracts import AgentGroup, AgentGroupMessage, AgentMember, AgentTurn

__all__ = [
    "AgentGroup",
    "AgentGroupMessage",
    "AgentMember",
    "AgentTurn",
]
```

- [ ] **Step 4: Run contract tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/test_agent_group_contracts.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit contracts**

```bash
git add src/isotope/features/supervisor/agent_group/__init__.py src/isotope/features/supervisor/agent_group/contracts.py tests/unit/features/supervisor/agent_group/test_agent_group_contracts.py
git commit -m "feat(supervisor): add agent group contracts"
```

## Task 2: Store And Public Message Ledger

**Files:**
- Create: `src/isotope/features/supervisor/agent_group/store.py`
- Create: `tests/unit/features/supervisor/agent_group/test_agent_group_store.py`

- [ ] **Step 1: Write failing store tests**

Create `tests/unit/features/supervisor/agent_group/test_agent_group_store.py`:

```python
from __future__ import annotations

from isotope.features.supervisor.agent_group.contracts import AgentMember
from isotope.features.supervisor.agent_group.store import AgentGroupStore


def test_store_creates_group_members_and_initial_message(tmp_path):
    store = AgentGroupStore(tmp_path)

    group = store.create_group(
        title="Feature group",
        goal="Discuss the feature.",
        members=[
            AgentMember(
                member_id="member_planner",
                group_id="pending",
                name="planner",
                role="Plan work.",
                goal="Find first steps.",
            ),
            AgentMember(
                member_id="member_reviewer",
                group_id="pending",
                name="reviewer",
                role="Review risk.",
                goal="Find missing tests.",
            ),
        ],
        initial_message="Start with risks.",
    )

    assert group.group_id.startswith("group_")
    members = store.list_members(group.group_id)
    assert [member.name for member in members] == ["planner", "reviewer"]
    messages = store.list_group_messages(group.group_id)
    assert len(messages) == 1
    assert messages[0].from_member == "supervisor"
    assert messages[0].message_type == "task"
    assert messages[0].summary == "Start with risks."


def test_store_publishes_directed_and_broadcast_messages(tmp_path):
    store = AgentGroupStore(tmp_path)
    group = store.create_group(
        title="Feature group",
        goal="Discuss the feature.",
        members=[],
        initial_message="Start.",
    )

    broadcast = store.publish_message(
        group_id=group.group_id,
        turn_id="turn_manual",
        from_member="member_a",
        to_member=None,
        message_type="reply",
        summary="Broadcast note.",
        payload={"kind": "safe"},
    )
    directed = store.publish_message(
        group_id=group.group_id,
        turn_id="turn_manual",
        from_member="member_a",
        to_member="member_b",
        message_type="question",
        summary="Question for B.",
        payload={},
    )

    messages = store.list_group_messages(group.group_id)
    assert [message.message_id for message in messages[-2:]] == [
        broadcast.message_id,
        directed.message_id,
    ]
    assert messages[-1].to_member == "member_b"


def test_store_records_turn(tmp_path):
    store = AgentGroupStore(tmp_path)
    group = store.create_group(
        title="Feature group",
        goal="Discuss the feature.",
        members=[],
        initial_message="Start.",
    )

    turn = store.record_turn(
        group_id=group.group_id,
        input_message_ids=("msg_input",),
        candidate_messages=("candidate_a", "candidate_b"),
        selected_message_ids=("msg_selected",),
        queued_messages=({"message_id": "candidate_b", "reason": "visible_limit"},),
        dropped_messages=(),
        status="selected",
        supervisor_summary="One reply selected.",
    )

    assert store.list_turns(group.group_id)[0].turn_id == turn.turn_id
    assert store.list_groups()[0].group_id == group.group_id
```

- [ ] **Step 2: Run store tests to verify failure**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/test_agent_group_store.py -q
```

Expected: FAIL because `AgentGroupStore` does not exist.

- [ ] **Step 3: Implement store**

Create `src/isotope/features/supervisor/agent_group/store.py`:

```python
"""Memory-backed store for Supervisor Agent group chat."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

from isotope.platform.schemas.memory import MemoryRecord
from isotope.platform.state.memory_store import FileMemoryStore
from isotope.platform.state.worker_event_channel import (
    DEFAULT_CHANNEL,
    list_worker_events,
    publish_worker_event,
)

from .contracts import AgentGroup, AgentGroupMessage, AgentMember, AgentTurn


GROUP_RECORD_KIND = "agent_group"
MEMBER_RECORD_KIND = "agent_group_member"
TURN_RECORD_KIND = "agent_group_turn"
GROUP_EVENT_CHANNEL = "agent-group"


class AgentGroupStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser()
        self.memory = FileMemoryStore(self.root)

    def create_group(
        self,
        *,
        title: str,
        goal: str,
        members: list[AgentMember],
        initial_message: str,
    ) -> AgentGroup:
        now = _utc_now()
        group = AgentGroup(
            group_id=_new_id("group"),
            title=title.strip(),
            goal=goal.strip(),
            status="active",
            created_at=now,
            updated_at=now,
        )
        self.memory.append_record(_memory_record_for_group(group))
        for member in members:
            normalized = replace(member, group_id=group.group_id)
            self.memory.append_record(_memory_record_for_member(normalized))
        self.publish_message(
            group_id=group.group_id,
            turn_id="turn_initial",
            from_member="supervisor",
            to_member=None,
            message_type="task",
            summary=initial_message,
            payload={"source": "agent_group_create"},
        )
        return group

    def list_groups(self) -> list[AgentGroup]:
        groups = [
            _group_from_record(record)
            for record in self.memory.list_records(scope="session")
            if record.content.get("kind") == GROUP_RECORD_KIND
        ]
        return sorted(
            [group for group in groups if group is not None],
            key=lambda group: (group.created_at, group.group_id),
        )

    def load_group(self, group_id: str) -> AgentGroup:
        for group in self.list_groups():
            if group.group_id == group_id:
                return group
        raise ValueError(f"agent group not found: {group_id}")

    def list_members(self, group_id: str) -> list[AgentMember]:
        members = [
            _member_from_record(record)
            for record in self.memory.list_records(scope="session")
            if record.content.get("kind") == MEMBER_RECORD_KIND
            and record.content.get("group_id") == group_id
        ]
        return sorted(
            [member for member in members if member is not None],
            key=lambda member: member.member_id,
        )

    def publish_message(
        self,
        *,
        group_id: str,
        turn_id: str,
        from_member: str,
        to_member: str | None,
        message_type: str,
        summary: str,
        payload: dict[str, Any],
    ) -> AgentGroupMessage:
        message = AgentGroupMessage(
            message_id=_new_id("msg"),
            group_id=group_id,
            turn_id=turn_id,
            from_member=from_member,
            to_member=to_member,
            message_type=message_type,
            summary=summary,
            payload=dict(payload),
            created_at=_utc_now(),
        )
        publish_worker_event(
            root=self.root,
            from_worker=from_member,
            to_worker=to_member,
            event_type=message_type,
            channel=GROUP_EVENT_CHANNEL,
            message=summary,
            payload=message.to_public_dict(),
        )
        return message

    def list_group_messages(self, group_id: str, *, limit: int = 50) -> list[AgentGroupMessage]:
        payload = list_worker_events(
            root=self.root,
            channel=GROUP_EVENT_CHANNEL,
            limit=max(limit, 1),
        )
        messages: list[AgentGroupMessage] = []
        for event in payload.get("events") or []:
            if not isinstance(event, dict):
                continue
            raw = event.get("payload")
            if not isinstance(raw, dict) or raw.get("group_id") != group_id:
                continue
            try:
                messages.append(AgentGroupMessage(**raw))
            except (TypeError, ValueError):
                continue
        return sorted(messages, key=lambda message: (message.created_at, message.message_id))

    def record_turn(
        self,
        *,
        group_id: str,
        input_message_ids: tuple[str, ...],
        candidate_messages: tuple[str, ...],
        selected_message_ids: tuple[str, ...],
        queued_messages: tuple[dict[str, Any], ...],
        dropped_messages: tuple[dict[str, Any], ...],
        status: str,
        supervisor_summary: str,
    ) -> AgentTurn:
        turn = AgentTurn(
            turn_id=_new_id("turn"),
            group_id=group_id,
            input_message_ids=input_message_ids,
            candidate_messages=candidate_messages,
            selected_message_ids=selected_message_ids,
            queued_messages=queued_messages,
            dropped_messages=dropped_messages,
            status=status,
            supervisor_summary=supervisor_summary,
            created_at=_utc_now(),
        )
        self.memory.append_record(_memory_record_for_turn(turn))
        return turn

    def list_turns(self, group_id: str) -> list[AgentTurn]:
        turns = [
            _turn_from_record(record)
            for record in self.memory.list_records(scope="session")
            if record.content.get("kind") == TURN_RECORD_KIND
            and record.content.get("group_id") == group_id
        ]
        return sorted(
            [turn for turn in turns if turn is not None],
            key=lambda turn: (turn.created_at, turn.turn_id),
        )


def _memory_record_for_group(group: AgentGroup) -> MemoryRecord:
    return _record(
        record_id=f"agent_group_{group.group_id}",
        kind=GROUP_RECORD_KIND,
        content=group.to_public_dict(),
        summary=f"Agent group {group.title}: {group.goal}",
    )


def _memory_record_for_member(member: AgentMember) -> MemoryRecord:
    return _record(
        record_id=f"agent_group_member_{member.group_id}_{member.member_id}",
        kind=MEMBER_RECORD_KIND,
        content=member.to_public_dict(),
        summary=f"Agent group member {member.name}: {member.role}",
    )


def _memory_record_for_turn(turn: AgentTurn) -> MemoryRecord:
    return _record(
        record_id=f"agent_group_turn_{turn.group_id}_{turn.turn_id}",
        kind=TURN_RECORD_KIND,
        content=turn.to_public_dict(),
        summary=turn.supervisor_summary,
    )


def _record(*, record_id: str, kind: str, content: dict[str, Any], summary: str) -> MemoryRecord:
    payload = {"kind": kind, **content}
    return MemoryRecord(
        memory_id=record_id,
        scope="session",
        content=payload,
        summary=summary,
        source_refs=[],
        provenance={
            "run_id": "supervisor_agent_group",
            "execution_id": _new_id("exec"),
            "action_type": kind,
        },
        created_at=_utc_now(),
        supersedes=[],
        quality="agent_group",
    )


def _group_from_record(record: MemoryRecord) -> AgentGroup | None:
    try:
        return AgentGroup(
            group_id=str(record.content["group_id"]),
            title=str(record.content["title"]),
            goal=str(record.content["goal"]),
            status=str(record.content["status"]),
            created_at=str(record.content["created_at"]),
            updated_at=str(record.content["updated_at"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _member_from_record(record: MemoryRecord) -> AgentMember | None:
    try:
        return AgentMember(
            member_id=str(record.content["member_id"]),
            group_id=str(record.content["group_id"]),
            name=str(record.content["name"]),
            role=str(record.content["role"]),
            goal=str(record.content["goal"]),
            model_profile=str(record.content.get("model_profile") or "default"),
            allowed_capabilities=tuple(record.content.get("allowed_capabilities") or ()),
            status=str(record.content.get("status") or "active"),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _turn_from_record(record: MemoryRecord) -> AgentTurn | None:
    try:
        return AgentTurn(
            turn_id=str(record.content["turn_id"]),
            group_id=str(record.content["group_id"]),
            input_message_ids=tuple(record.content.get("input_message_ids") or ()),
            candidate_messages=tuple(record.content.get("candidate_messages") or ()),
            selected_message_ids=tuple(record.content.get("selected_message_ids") or ()),
            queued_messages=tuple(record.content.get("queued_messages") or ()),
            dropped_messages=tuple(record.content.get("dropped_messages") or ()),
            status=str(record.content["status"]),
            supervisor_summary=str(record.content["supervisor_summary"]),
            created_at=str(record.content["created_at"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
```

- [ ] **Step 4: Update package exports**

Modify `src/isotope/features/supervisor/agent_group/__init__.py`:

```python
"""Supervisor Agent group chat runtime."""

from __future__ import annotations

from .contracts import AgentGroup, AgentGroupMessage, AgentMember, AgentTurn
from .store import AgentGroupStore

__all__ = [
    "AgentGroup",
    "AgentGroupMessage",
    "AgentGroupStore",
    "AgentMember",
    "AgentTurn",
]
```

- [ ] **Step 5: Run store tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/test_agent_group_store.py -q
```

Expected: PASS.

- [ ] **Step 6: Run contract regression**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/test_agent_group_contracts.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit store**

```bash
git add src/isotope/features/supervisor/agent_group/__init__.py src/isotope/features/supervisor/agent_group/store.py tests/unit/features/supervisor/agent_group/test_agent_group_store.py
git commit -m "feat(supervisor): persist agent group messages"
```

## Task 3: Runtime Tick

**Files:**
- Create: `src/isotope/features/supervisor/agent_group/runtime.py`
- Create: `tests/unit/features/supervisor/agent_group/test_agent_group_runtime.py`

- [ ] **Step 1: Write failing runtime tests**

Create `tests/unit/features/supervisor/agent_group/test_agent_group_runtime.py`:

```python
from __future__ import annotations

from isotope.agents.loop.conversation import AgentConversationMessage
from isotope.features.supervisor.agent_group.runtime import (
    AgentGroupRuntime,
    StaticAgentGroupProvider,
    SummaryAgentGroupProvider,
)


def test_runtime_tick_selects_visible_messages_and_records_turn(tmp_path):
    provider = StaticAgentGroupProvider(
        {
            "planner": AgentConversationMessage(
                message_id="candidate_planner",
                agent_id="planner",
                intent="respond",
                summary="Start with a narrow contract.",
                priority=50,
            ),
            "reviewer": AgentConversationMessage(
                message_id="candidate_reviewer",
                agent_id="reviewer",
                intent="respond",
                summary="Add failing tests first.",
                priority=40,
            ),
        }
    )
    runtime = AgentGroupRuntime(tmp_path, provider=provider)
    created = runtime.create_group(
        title="Feature group",
        goal="Discuss group chat.",
        member_specs=[
            {"name": "planner", "role": "Plan work.", "goal": "Find steps."},
            {"name": "reviewer", "role": "Review work.", "goal": "Find risks."},
        ],
        initial_message="Start.",
    )

    tick = runtime.tick_group(created["group"]["group_id"], max_visible_messages=1)

    assert tick["status"] == "ok"
    assert tick["turn"]["status"] == "selected"
    assert tick["turn"]["selected_message_ids"]
    assert tick["turn"]["queued_messages"][0]["reason"] == "visible_limit"
    messages = runtime.list_group(created["group"]["group_id"])["messages"]
    assert messages[-1]["summary"] == "Start with a narrow contract."


def test_runtime_tick_allows_silent_members(tmp_path):
    provider = StaticAgentGroupProvider(
        {
            "planner": AgentConversationMessage(
                message_id="candidate_planner",
                agent_id="planner",
                intent="silent",
                summary="No update.",
                priority=0,
            )
        }
    )
    runtime = AgentGroupRuntime(tmp_path, provider=provider)
    created = runtime.create_group(
        title="Feature group",
        goal="Discuss group chat.",
        member_specs=[{"name": "planner", "role": "Plan work.", "goal": "Find steps."}],
        initial_message="Start.",
    )

    tick = runtime.tick_group(created["group"]["group_id"])

    assert tick["turn"]["status"] == "silent"
    assert tick["turn"]["selected_message_ids"] == []
    assert len(runtime.list_group(created["group"]["group_id"])["messages"]) == 1


class FakeSummaryProvider:
    def summarize(self, messages: list[dict[str, str]]) -> str:
        return "Use a narrow first slice."


def test_summary_agent_group_provider_builds_member_reply(tmp_path):
    provider = SummaryAgentGroupProvider(FakeSummaryProvider())
    runtime = AgentGroupRuntime(tmp_path, provider=StaticAgentGroupProvider({}))
    created = runtime.create_group(
        title="Feature group",
        goal="Discuss group chat.",
        member_specs=[{"name": "planner", "role": "Plan work.", "goal": "Find steps."}],
        initial_message="Start.",
    )
    member = runtime.store.list_members(created["group"]["group_id"])[0]

    candidate = provider.candidate_for_member(
        member=member,
        group=created["group"],
        messages=created["messages"],
    )

    assert candidate.agent_id == member.member_id
    assert candidate.intent == "respond"
    assert candidate.summary == "Use a narrow first slice."
```

- [ ] **Step 2: Run runtime tests to verify failure**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/test_agent_group_runtime.py -q
```

Expected: FAIL because `AgentGroupRuntime` does not exist.

- [ ] **Step 3: Implement runtime**

Create `src/isotope/features/supervisor/agent_group/runtime.py`:

```python
"""Runtime for Supervisor internal Agent group chat."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Protocol

from isotope.agents.loop.conversation import (
    AgentConversationMessage,
    arbitrate_agent_conversation_turn,
)
from isotope.features.supervisor.llm_action.llm_pool import (
    SummaryProvider,
    resolve_summary_provider_from_env,
)

from .contracts import AgentMember
from .store import AgentGroupStore


class AgentGroupProvider(Protocol):
    def candidate_for_member(
        self,
        *,
        member: AgentMember,
        group: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> AgentConversationMessage:
        ...


class StaticAgentGroupProvider:
    def __init__(self, candidates: dict[str, AgentConversationMessage]) -> None:
        self.candidates = dict(candidates)

    def candidate_for_member(
        self,
        *,
        member: AgentMember,
        group: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> AgentConversationMessage:
        candidate = self.candidates.get(member.name)
        if candidate is None:
            return AgentConversationMessage(
                message_id=f"candidate_{member.name}_silent",
                agent_id=member.member_id,
                intent="silent",
                summary="No update.",
                priority=0,
            )
        return replace(candidate, agent_id=member.member_id)


class SummaryAgentGroupProvider:
    def __init__(self, summary_provider: SummaryProvider) -> None:
        self.summary_provider = summary_provider

    def candidate_for_member(
        self,
        *,
        member: AgentMember,
        group: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> AgentConversationMessage:
        answer = self.summary_provider.summarize(
            [
                {
                    "role": "system",
                    "content": (
                        "You are one internal Isotope Agent group member. "
                        "Reply with one concise low-sensitive message. "
                        "Do not include raw prompts, raw tool output, or private data."
                    ),
                },
                {
                    "role": "user",
                    "content": _member_prompt(
                        member=member,
                        group=group,
                        messages=messages,
                    ),
                },
            ]
        ).strip()
        if not answer:
            answer = "No update."
        return AgentConversationMessage(
            message_id=f"candidate_{member.member_id}",
            agent_id=member.member_id,
            intent="respond" if answer != "No update." else "silent",
            summary=answer,
            priority=10,
        )


class AgentGroupRuntime:
    def __init__(
        self,
        root: str,
        *,
        provider: AgentGroupProvider | None = None,
    ) -> None:
        self.store = AgentGroupStore(root)
        self.provider = provider

    def create_group(
        self,
        *,
        title: str,
        goal: str,
        member_specs: list[dict[str, Any]],
        initial_message: str,
    ) -> dict[str, Any]:
        pending_members = [
            AgentMember(
                member_id=f"member_{_safe_member_name(spec.get('name'))}",
                group_id="pending",
                name=_safe_member_name(spec.get("name")),
                role=_required_text(spec.get("role"), "role"),
                goal=_required_text(spec.get("goal"), "goal"),
                model_profile=str(spec.get("model_profile") or "default"),
                allowed_capabilities=tuple(spec.get("allowed_capabilities") or ()),
                status="active",
            )
            for spec in member_specs
        ]
        group = self.store.create_group(
            title=title,
            goal=goal,
            members=pending_members,
            initial_message=initial_message,
        )
        return self.list_group(group.group_id)

    def send_message(
        self,
        *,
        group_id: str,
        message: str,
        from_member: str = "supervisor",
        to_member: str | None = None,
        message_type: str = "task",
    ) -> dict[str, Any]:
        self.store.load_group(group_id)
        published = self.store.publish_message(
            group_id=group_id,
            turn_id="turn_manual",
            from_member=from_member,
            to_member=to_member,
            message_type=message_type,
            summary=message,
            payload={"source": "agent_group_send"},
        )
        return {"status": "ok", "message": published.to_public_dict()}

    def tick_group(
        self,
        group_id: str,
        *,
        max_visible_messages: int = 2,
    ) -> dict[str, Any]:
        group = self.store.load_group(group_id)
        members = [
            member
            for member in self.store.list_members(group_id)
            if member.status == "active"
        ]
        messages = [
            message.to_public_dict()
            for message in self.store.list_group_messages(group_id)
        ]
        provider = self._active_provider()
        candidates = [
            provider.candidate_for_member(
                member=member,
                group=group.to_public_dict(),
                messages=messages,
            )
            for member in members
        ]
        turn_id = f"turn_{len(self.store.list_turns(group_id)) + 1:04d}"
        arbitration = arbitrate_agent_conversation_turn(
            candidates,
            turn_id=turn_id,
            max_visible_messages=max_visible_messages,
        )
        selected_message_ids: list[str] = []
        for selected in arbitration["visible_messages"]:
            message_type = "interrupt" if selected["intent"] == "interrupt" else "reply"
            published = self.store.publish_message(
                group_id=group_id,
                turn_id=turn_id,
                from_member=str(selected["agent_id"]),
                to_member=None,
                message_type=message_type,
                summary=str(selected["summary"]),
                payload={
                    "candidate_message_id": selected["message_id"],
                    "intent": selected["intent"],
                    "priority": selected["priority"],
                },
            )
            selected_message_ids.append(published.message_id)
        supervisor_summary = _turn_summary(arbitration)
        turn = self.store.record_turn(
            group_id=group_id,
            input_message_ids=tuple(
                message["message_id"]
                for message in messages[-10:]
                if isinstance(message.get("message_id"), str)
            ),
            candidate_messages=tuple(candidate.message_id for candidate in candidates),
            selected_message_ids=tuple(selected_message_ids),
            queued_messages=tuple(arbitration["queued_messages"]),
            dropped_messages=tuple(arbitration["dropped_messages"]),
            status=str(arbitration["status"]),
            supervisor_summary=supervisor_summary,
        )
        return {"status": "ok", "turn": turn.to_public_dict()}

    def list_group(self, group_id: str) -> dict[str, Any]:
        group = self.store.load_group(group_id)
        return {
            "status": "ok",
            "group": group.to_public_dict(),
            "members": [member.to_public_dict() for member in self.store.list_members(group_id)],
            "messages": [
                message.to_public_dict()
                for message in self.store.list_group_messages(group_id)
            ],
            "turns": [turn.to_public_dict() for turn in self.store.list_turns(group_id)],
        }

    def list_groups(self) -> dict[str, Any]:
        groups = [group.to_public_dict() for group in self.store.list_groups()]
        return {
            "status": "ok",
            "summary": {"group_count": len(groups)},
            "groups": groups,
        }

    def _active_provider(self) -> AgentGroupProvider:
        if self.provider is not None:
            return self.provider
        return SummaryAgentGroupProvider(resolve_summary_provider_from_env())


def _member_prompt(
    *,
    member: AgentMember,
    group: dict[str, Any],
    messages: list[dict[str, Any]],
) -> str:
    recent = [
        {
            "from_member": message.get("from_member"),
            "to_member": message.get("to_member"),
            "message_type": message.get("message_type"),
            "summary": message.get("summary"),
        }
        for message in messages[-8:]
        if isinstance(message, dict)
    ]
    return (
        "Group goal: {group_goal}\n"
        "Your name: {name}\n"
        "Your role: {role}\n"
        "Your goal: {goal}\n"
        "Allowed capabilities: {capabilities}\n"
        "Recent public messages: {recent}\n"
        "Return the next useful group-chat message only."
    ).format(
        group_goal=group.get("goal", ""),
        name=member.name,
        role=member.role,
        goal=member.goal,
        capabilities=", ".join(member.allowed_capabilities) or "none",
        recent=recent,
    )


def _safe_member_name(value: object) -> str:
    text = _required_text(value, "name")
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in text)
    return safe.strip("_") or "agent"


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _turn_summary(arbitration: dict[str, Any]) -> str:
    visible = len(arbitration.get("visible_messages") or [])
    queued = len(arbitration.get("queued_messages") or [])
    dropped = len(arbitration.get("dropped_messages") or [])
    if visible == 0:
        return f"No visible agent replies; queued {queued}, dropped {dropped}."
    return f"Selected {visible} agent replies; queued {queued}, dropped {dropped}."
```

- [ ] **Step 4: Update exports**

Modify `src/isotope/features/supervisor/agent_group/__init__.py`:

```python
"""Supervisor Agent group chat runtime."""

from __future__ import annotations

from .contracts import AgentGroup, AgentGroupMessage, AgentMember, AgentTurn
from .runtime import AgentGroupRuntime, StaticAgentGroupProvider, SummaryAgentGroupProvider
from .store import AgentGroupStore

__all__ = [
    "AgentGroup",
    "AgentGroupMessage",
    "AgentGroupRuntime",
    "AgentGroupStore",
    "AgentMember",
    "AgentTurn",
    "StaticAgentGroupProvider",
    "SummaryAgentGroupProvider",
]
```

- [ ] **Step 5: Run runtime tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/test_agent_group_runtime.py -q
```

Expected: PASS.

- [ ] **Step 6: Run agent-group unit suite**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group -q
```

Expected: PASS.

- [ ] **Step 7: Commit runtime**

```bash
git add src/isotope/features/supervisor/agent_group/__init__.py src/isotope/features/supervisor/agent_group/runtime.py tests/unit/features/supervisor/agent_group/test_agent_group_runtime.py
git commit -m "feat(supervisor): run agent group turns"
```

## Task 4: CLI Entry

**Files:**
- Create: `src/isotope/features/supervisor/commands/parser/agent_group.py`
- Create: `src/isotope/features/supervisor/commands/handlers/agent_group.py`
- Modify: `src/isotope/features/supervisor/commands/parser/__init__.py`
- Modify: `src/isotope/features/supervisor/commands/dispatch.py`
- Create: `tests/integration/supervisor/test_supervisor_agent_group_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/integration/supervisor/test_supervisor_agent_group_cli.py`:

```python
from __future__ import annotations

import json

from isotope.features.supervisor import runner


class FakeSummaryProvider:
    def summarize(self, messages: list[dict[str, str]]) -> str:
        return "CLI fake agent reply."


def test_supervisor_agent_group_create_tick_and_list_cli(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(
        "isotope.features.supervisor.agent_group.runtime.resolve_summary_provider_from_env",
        lambda: FakeSummaryProvider(),
    )

    assert (
        runner.main(
            [
                "agent-group",
                "create",
                "--state-root",
                str(tmp_path),
                "--title",
                "Feature group",
                "--goal",
                "Discuss group chat.",
                "--member",
                "planner:Plan work.:Find first steps.",
                "--member",
                "reviewer:Review work.:Find missing tests.",
                "--message",
                "Start with risks.",
                "--json",
            ]
        )
        == 0
    )
    created = json.loads(capsys.readouterr().out)
    group_id = created["group"]["group_id"]
    assert created["status"] == "ok"
    assert [member["name"] for member in created["members"]] == ["planner", "reviewer"]

    assert (
        runner.main(
            [
                "agent-group",
                "tick",
                "--state-root",
                str(tmp_path),
                "--group",
                group_id,
                "--json",
            ]
        )
        == 0
    )
    ticked = json.loads(capsys.readouterr().out)
    assert ticked["status"] == "ok"
    assert ticked["turn"]["status"] == "selected"

    assert (
        runner.main(
            [
                "agent-group",
                "list",
                "--state-root",
                str(tmp_path),
                "--json",
            ]
        )
        == 0
    )
    listed = json.loads(capsys.readouterr().out)
    assert listed["summary"]["group_count"] == 1
    assert listed["groups"][0]["group_id"] == group_id


def test_supervisor_agent_group_send_cli(tmp_path, capsys):
    assert (
        runner.main(
            [
                "agent-group",
                "create",
                "--state-root",
                str(tmp_path),
                "--goal",
                "Discuss group chat.",
                "--member",
                "planner:Plan work.:Find first steps.",
                "--message",
                "Start.",
                "--json",
            ]
        )
        == 0
    )
    group_id = json.loads(capsys.readouterr().out)["group"]["group_id"]

    assert (
        runner.main(
            [
                "agent-group",
                "send",
                "--state-root",
                str(tmp_path),
                "--group",
                group_id,
                "--message",
                "Focus on the first test.",
                "--json",
            ]
        )
        == 0
    )
    sent = json.loads(capsys.readouterr().out)
    assert sent["message"]["summary"] == "Focus on the first test."
```

- [ ] **Step 2: Run CLI tests to verify failure**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/supervisor/test_supervisor_agent_group_cli.py -q
```

Expected: FAIL because `agent-group` command is not registered.

- [ ] **Step 3: Add parser**

Create `src/isotope/features/supervisor/commands/parser/agent_group.py`:

```python
"""Agent group parser registration for the Supervisor CLI."""

from __future__ import annotations

import argparse

from .common import add_state_root_arg


def add_agent_group_command_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "agent-group",
        help="Create and tick internal Supervisor Agent groups.",
    )
    group_subparsers = parser.add_subparsers(
        dest="agent_group_command",
        required=True,
    )

    create = group_subparsers.add_parser("create", help="Create an Agent group.")
    add_state_root_arg(create)
    create.add_argument("--title", default="Agent group")
    create.add_argument("--goal", required=True)
    create.add_argument(
        "--member",
        action="append",
        default=[],
        help="Member spec as name:role:goal. Repeatable.",
    )
    create.add_argument("--message", required=True)
    create.add_argument("--json", action="store_true", help="Print JSON output.")

    send = group_subparsers.add_parser("send", help="Send a message into a group.")
    add_state_root_arg(send)
    send.add_argument("--group", required=True, dest="group_id")
    send.add_argument("--message", required=True)
    send.add_argument("--from", dest="from_member", default="supervisor")
    send.add_argument("--to", dest="to_member")
    send.add_argument("--type", dest="message_type", default="task")
    send.add_argument("--json", action="store_true", help="Print JSON output.")

    tick = group_subparsers.add_parser("tick", help="Run one Agent group turn.")
    add_state_root_arg(tick)
    tick.add_argument("--group", required=True, dest="group_id")
    tick.add_argument("--max-visible-messages", type=int, default=2)
    tick.add_argument("--json", action="store_true", help="Print JSON output.")

    list_parser = group_subparsers.add_parser("list", help="List Agent groups.")
    add_state_root_arg(list_parser)
    list_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    inspect = group_subparsers.add_parser("inspect", help="Inspect one Agent group.")
    add_state_root_arg(inspect)
    inspect.add_argument("--group", required=True, dest="group_id")
    inspect.add_argument("--json", action="store_true", help="Print JSON output.")
```

Modify `src/isotope/features/supervisor/commands/parser/__init__.py`:

```python
from isotope.features.supervisor.commands.parser.agent_group import (
    add_agent_group_command_parser,
)
```

Then call it near the other parser registrations:

```python
add_agent_group_command_parser(subparsers)
```

- [ ] **Step 4: Add handler**

Create `src/isotope/features/supervisor/commands/handlers/agent_group.py`:

```python
"""Agent group command handlers."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from isotope.features.supervisor.agent_group.runtime import AgentGroupRuntime


def handle_agent_group_command(args: argparse.Namespace, *, api: Any) -> int:
    runtime = AgentGroupRuntime(Path(args.codex_home))
    if args.agent_group_command == "create":
        payload = runtime.create_group(
            title=args.title,
            goal=args.goal,
            member_specs=[_member_spec(raw) for raw in args.member],
            initial_message=args.message,
        )
        return _print(payload, json_output=args.json, api=api)
    if args.agent_group_command == "send":
        payload = runtime.send_message(
            group_id=args.group_id,
            message=args.message,
            from_member=args.from_member,
            to_member=args.to_member,
            message_type=args.message_type,
        )
        return _print(payload, json_output=args.json, api=api)
    if args.agent_group_command == "tick":
        payload = runtime.tick_group(
            args.group_id,
            max_visible_messages=args.max_visible_messages,
        )
        return _print(payload, json_output=args.json, api=api)
    if args.agent_group_command == "list":
        payload = runtime.list_groups()
        return _print(payload, json_output=args.json, api=api)
    if args.agent_group_command == "inspect":
        payload = runtime.list_group(args.group_id)
        return _print(payload, json_output=args.json, api=api)
    raise ValueError(f"unsupported agent-group command: {args.agent_group_command}")


def _member_spec(raw: str) -> dict[str, str]:
    parts = raw.split(":", 2)
    if len(parts) != 3 or not all(part.strip() for part in parts):
        raise ValueError("member must use name:role:goal")
    return {
        "name": parts[0].strip(),
        "role": parts[1].strip(),
        "goal": parts[2].strip(),
    }


def _print(payload: dict[str, Any], *, json_output: bool, api: Any) -> int:
    if json_output:
        api._print_json(payload)
    else:
        print_agent_group_plain(payload)
    return 0


def print_agent_group_plain(payload: dict[str, Any]) -> None:
    group = payload.get("group") if isinstance(payload.get("group"), dict) else None
    if group is not None:
        print("[Agent group]")
        print(f"group: {group.get('group_id', '')}")
        print(f"title: {group.get('title', '')}")
        print(f"goal: {group.get('goal', '')}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else None
    if summary is not None:
        print("[Agent groups]")
        print(f"groups: {summary.get('group_count', 0)}")
    members = payload.get("members")
    if isinstance(members, list):
        print("members:")
        for member in members:
            if isinstance(member, dict):
                print(f"- {member.get('name', '')}: {member.get('role', '')}")
    messages = payload.get("messages")
    if isinstance(messages, list):
        print("messages:")
        for message in messages[-10:]:
            if isinstance(message, dict):
                print(
                    "- {from_member} -> {to_member}: {summary}".format(
                        from_member=message.get("from_member", ""),
                        to_member=message.get("to_member") or "*",
                        summary=message.get("summary", ""),
                    )
                )
    turn = payload.get("turn") if isinstance(payload.get("turn"), dict) else None
    if turn is not None:
        print("[Agent group turn]")
        print(f"status: {turn.get('status', '')}")
        print(f"summary: {turn.get('supervisor_summary', '')}")
```

Modify `src/isotope/features/supervisor/commands/dispatch.py`:

```python
from .handlers.agent_group import (
    handle_agent_group_command as _handle_agent_group_command,
)
```

Add to `COMMAND_HANDLERS`:

```python
"agent-group": _handle_agent_group_command,
```

- [ ] **Step 5: Run CLI tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/supervisor/test_supervisor_agent_group_cli.py -q
```

Expected: PASS.

- [ ] **Step 6: Run parser/dispatch regression**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_runner_modularization.py tests/integration/supervisor/test_supervisor_worker_event_channel.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit CLI**

```bash
git add src/isotope/features/supervisor/commands/parser/agent_group.py src/isotope/features/supervisor/commands/parser/__init__.py src/isotope/features/supervisor/commands/handlers/agent_group.py src/isotope/features/supervisor/commands/dispatch.py tests/integration/supervisor/test_supervisor_agent_group_cli.py
git commit -m "feat(supervisor): add agent group cli"
```

## Task 5: Projection And Acceptance

**Files:**
- Modify: `src/isotope/features/supervisor/state/projection.py`
- Create: `tests/unit/features/supervisor/agent_group/test_agent_group_projection.py`
- Modify: `docs/current/terminology.md`
- Modify: `docs/current/supervisor-command-reference.md`

- [ ] **Step 1: Write failing projection test**

Create `tests/unit/features/supervisor/agent_group/test_agent_group_projection.py`:

```python
from __future__ import annotations

from isotope.features.supervisor.agent_group.runtime import AgentGroupRuntime
from isotope.features.supervisor.state.projection import build_supervisor_state_snapshot


def test_supervisor_state_snapshot_exposes_agent_group_summary(tmp_path):
    runtime = AgentGroupRuntime(tmp_path)
    runtime.create_group(
        title="Feature group",
        goal="Discuss group chat.",
        member_specs=[{"name": "planner", "role": "Plan work.", "goal": "Find steps."}],
        initial_message="Start.",
    )

    snapshot = build_supervisor_state_snapshot(codex_home=tmp_path)

    assert snapshot["summary"]["agent_groups"] == 1
    assert snapshot["agent_groups"]["total"] == 1
    assert snapshot["agent_groups"]["recent"][0]["title"] == "Feature group"
```

- [ ] **Step 2: Run projection test to verify failure**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/test_agent_group_projection.py -q
```

Expected: FAIL because the snapshot has no `agent_groups` block yet.

- [ ] **Step 3: Add projection helper**

Modify `src/isotope/features/supervisor/state/projection.py`:

```python
from isotope.features.supervisor.agent_group.store import AgentGroupStore
```

Inside `build_supervisor_state_snapshot(...)`, after `artifacts = ...`:

```python
agent_groups = _agent_group_payload(codex_home_path, limit=worker_event_limit)
```

Add to `summary`:

```python
"agent_groups": agent_groups["total"],
```

Add to `SupervisorStateSnapshot(...).to_dict()` result. If the dataclass does
not accept arbitrary fields, assign after `to_dict()`:

```python
snapshot = SupervisorStateSnapshot(...).to_dict()
snapshot["agent_groups"] = agent_groups
return snapshot
```

Add helper:

```python
def _agent_group_payload(codex_home: Path, *, limit: int) -> dict[str, Any]:
    try:
        groups = AgentGroupStore(codex_home).list_groups()
    except (OSError, TypeError, ValueError):
        groups = []
    recent = sorted(
        groups,
        key=lambda group: (group.updated_at, group.group_id),
        reverse=True,
    )[:limit]
    return {
        "total": len(groups),
        "recent": [group.to_public_dict() for group in recent],
    }
```

- [ ] **Step 4: Update docs**

Modify `docs/current/terminology.md` by adding a row near the Supervisor terms:

```markdown
| `agent group chat` | Supervisor 内部多 Agent 群聊运行时；成员是 Isotope 内部 LLM agent，不是外部 Codex worker；消息复用 worker event channel，回合选择复用 conversation arbiter | 产品功能/智能体/对话 | `src/isotope/features/supervisor/agent_group/` |
```

Modify `docs/current/supervisor-command-reference.md` by adding `agent-group` to
the command overview table:

```markdown
| `agent-group` | 创建、发送、tick 和查看 Supervisor 内部 Agent group chat。 | [terminology](./terminology.md) |
```

- [ ] **Step 5: Run projection and docs checks**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/test_agent_group_projection.py -q
git diff --check
```

Expected: test PASS and `git diff --check` produces no output.

- [ ] **Step 6: Run full feature regression**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group tests/integration/supervisor/test_supervisor_agent_group_cli.py -q
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/agents/loop/test_agent_loop_conversation_arbiter.py tests/integration/supervisor/test_supervisor_worker_event_channel.py -q
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py tests/integration/codex/test_codex_supervisor_readonly.py::test_codex_supervisor_runner_loop_fanout_launches_parallel_active_goals -q
git diff --check
```

Expected: all selected tests pass and diff check is clean.

- [ ] **Step 7: Manual CLI smoke**

Run:

```bash
tmp_root="$(mktemp -d)"
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner agent-group create --state-root "$tmp_root" --goal "Plan agent group chat." --member "planner:Plan work.:Find first steps." --member "reviewer:Review work.:Find risks." --message "Start with risks." --json
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner agent-group list --state-root "$tmp_root" --json
```

Expected: first command returns one group with two members; second command
returns `summary.group_count == 1`.

- [ ] **Step 8: Commit projection and docs**

```bash
git add src/isotope/features/supervisor/state/projection.py tests/unit/features/supervisor/agent_group/test_agent_group_projection.py docs/current/terminology.md docs/current/supervisor-command-reference.md
git commit -m "feat(supervisor): expose agent group state"
```

## Task 6: Final Verification

- [ ] **Step 1: Run feature suite**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group tests/integration/supervisor/test_supervisor_agent_group_cli.py -q
```

Expected: PASS.

- [ ] **Step 2: Run shared regression**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/agents/loop/test_agent_loop_conversation_arbiter.py tests/integration/supervisor/test_supervisor_worker_event_channel.py tests/unit/features/supervisor/test_supervisor_conversation_loop.py -q
```

Expected: PASS.

- [ ] **Step 3: Run targeted fanout regression**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/codex/test_codex_supervisor_readonly.py::test_codex_supervisor_runner_loop_fanout_launches_parallel_active_goals -q
```

Expected: PASS.

- [ ] **Step 4: Run diff hygiene**

```bash
git diff --check
git status --short --branch
```

Expected: no diff-check output. Status should show only intentional branch
ahead state and any unrelated pre-existing untracked files.

- [ ] **Step 5: Product acceptance**

Confirm:

- `agent-group create` creates one group, members, and initial Supervisor task message.
- `agent-group send` appends a public directed or broadcast message.
- `agent-group tick` runs internal agent candidates through the arbiter and persists selected messages plus turn metadata.
- `agent-group list` and `inspect` expose public state without raw model/provider payloads.
- Existing worker-event, conversation arbiter, desktop conversation loop, and managed Codex fanout tests still pass.

No commit is needed in this task unless verification requires small fixes. Commit any fixes with a narrow Conventional Commit message.
