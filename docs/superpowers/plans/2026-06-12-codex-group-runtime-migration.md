# Codex Group Runtime Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate Agent Workspace Codex group chat from direct relay/resume behavior to the unified AgentGroup candidate, arbiter, and member-inbox runtime.

**Architecture:** Keep the current workspace UI/session shell, transcript reader, Codex session discovery, and core AgentGroup ledger. Add a focused workspace coordination package that parses explicit Codex group candidates, persists member inbox items, runs `AgentConversationMessage` arbitration, and publishes only arbiter-selected visible messages. Existing direct relay code becomes legacy fallback only during migration and must not be used by new tests or new runtime paths.

**Tech Stack:** Python 3.13, pytest, `FileMemoryStore`, `worker_event_channel`, `AgentGroupStore`, `AgentConversationMessage`, `arbitrate_agent_conversation_turn`, existing Supervisor desktop HTTP/SSE routes.

---

## Scope

This plan implements the backend runtime migration slice from `docs/superpowers/specs/2026-06-12-agent-group-codex-chat-design.md`.

Included:

- Codex group candidate parsing from explicit `GROUP_CHAT_*` marker blocks.
- Member inbox persistence and idempotent pending delivery.
- Arbiter-backed publishing of selected public group messages.
- Importer migration so ordinary Codex assistant output remains transcript-only.
- Dispatcher/API migration so running members receive inbox items instead of new `codex resume` processes.
- Backend projection of inbox counts and turn results for later frontend use.
- Tests that make the direct relay path fail if it is accidentally used as the new behavior.

Excluded:

- Full frontend redesign.
- Real OS-level interrupt support for non-managed Codex processes.
- Replacing the current transcript reader.
- Removing every legacy helper in one commit. Legacy helpers may remain if unused by new code paths and covered by removal criteria.

## File Structure

Create a new subpackage because `workspace/` is already near the directory file-count limit.

- Create: `src/isotope/features/supervisor/agent_group/workspace/coordination/__init__.py`
  - Public exports for the new coordination helpers.
- Create: `src/isotope/features/supervisor/agent_group/workspace/coordination/candidates.py`
  - `CodexGroupCandidate` contract.
  - `parse_codex_group_candidate(...)`.
  - `candidate_to_agent_message(...)`.
- Create: `src/isotope/features/supervisor/agent_group/workspace/coordination/inbox.py`
  - `MemberInboxItem` contract.
  - `MemberInboxStore` over `FileMemoryStore`.
  - Idempotent enqueue/list/mark-dispatched helpers.
- Create: `src/isotope/features/supervisor/agent_group/workspace/coordination/turns.py`
  - Channel candidate arbitration.
  - Selected-message publishing to workspace and core AgentGroup ledgers.
  - Delivery enqueue for other members.
- Modify: `src/isotope/features/supervisor/agent_group/workspace/importer.py`
  - Parse explicit candidates.
  - Stop importing ordinary assistant text as public `member_observation`.
  - Record silent/internal candidates as turn metadata.
- Modify: `src/isotope/features/supervisor/agent_group/workspace/dispatcher.py`
  - Route public channel messages through inbox enqueue/drain.
  - Stop using direct member-observation relay for new behavior.
  - Avoid duplicate recent-message prompt content.
- Modify: `src/isotope/features/supervisor/agent_group/workspace/api.py`
  - Replace `relay_runtime_member_observations(...)` calls with candidate import and inbox drain.
  - Project inbox and turn summaries.
- Modify: `src/isotope/features/supervisor/agent_group/workspace/runtime_bridge.py`
  - Keep workspace-to-core message sync, but add helpers that publish selected candidates with explicit turn metadata.
- Modify tests under `tests/unit/features/supervisor/agent_group/workspace/`.

## Preflight

- [ ] **Step 0.1: Create an isolated worktree**

Run:

```bash
git worktree add .worktrees/codex-group-runtime-migration -b feature/codex-group-runtime-migration
cd .worktrees/codex-group-runtime-migration
```

Expected: worktree is created from current `main`.

- [ ] **Step 0.2: Run baseline tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest --import-mode=importlib tests/unit/features/supervisor/agent_group/workspace -q
```

Expected: existing workspace tests pass before changes.

---

### Task 1: Add Codex Group Candidate Contract And Parser

**Files:**

- Create: `src/isotope/features/supervisor/agent_group/workspace/coordination/__init__.py`
- Create: `src/isotope/features/supervisor/agent_group/workspace/coordination/candidates.py`
- Test: `tests/unit/features/supervisor/agent_group/workspace/test_group_candidates.py`

- [ ] **Step 1.1: Write failing candidate parser tests**

Create `tests/unit/features/supervisor/agent_group/workspace/test_group_candidates.py`:

```python
from __future__ import annotations

import pytest

from isotope.features.supervisor.agent_group.workspace.coordination.candidates import (
    CodexGroupCandidate,
    candidate_to_agent_message,
    parse_codex_group_candidate,
)


def test_parse_codex_group_candidate_respond_marker() -> None:
    candidate = parse_codex_group_candidate(
        text=(
            "工程验证完成。\n\n"
            "GROUP_CHAT_INTENT: respond\n"
            "GROUP_CHAT_SUMMARY: 工程侧已经完成镜像 smoke，建议科研侧确认 schema。\n"
            "GROUP_CHAT_PRIORITY: 70\n"
            "GROUP_CHAT_STATE_LOCK: rna:submission\n"
        ),
        workspace_id="workspace_1",
        channel_id="channel_1",
        member_id="member_training",
        display_name="RNA训练",
        resume_session_id="session_training",
        event_index=42,
        transcript_ref={"session_id": "session_training", "event_index": 42},
    )

    assert candidate == CodexGroupCandidate(
        candidate_id="candidate_member_training_session_training_42_respond",
        workspace_id="workspace_1",
        channel_id="channel_1",
        member_id="member_training",
        display_name="RNA训练",
        resume_session_id="session_training",
        event_index=42,
        intent="respond",
        summary="工程侧已经完成镜像 smoke，建议科研侧确认 schema。",
        priority=70,
        state_lock="rna:submission",
        transcript_ref={"session_id": "session_training", "event_index": 42},
    )


def test_parse_codex_group_candidate_silent_marker() -> None:
    candidate = parse_codex_group_candidate(
        text=(
            "已读。\n\n"
            "GROUP_CHAT_INTENT: silent\n"
            "GROUP_CHAT_SUMMARY: 当前只是状态同步，我继续原工作。\n"
            "GROUP_CHAT_PRIORITY: 0\n"
        ),
        workspace_id="workspace_1",
        channel_id="channel_1",
        member_id="member_research",
        display_name="rna探索",
        resume_session_id="session_research",
        event_index=9,
        transcript_ref={"session_id": "session_research", "event_index": 9},
    )

    assert candidate.intent == "silent"
    assert candidate.summary == "当前只是状态同步，我继续原工作。"
    assert candidate.priority == 0
    assert candidate.state_lock is None


def test_parse_codex_group_candidate_absent_marker_returns_none() -> None:
    assert (
        parse_codex_group_candidate(
            text="普通 Codex 工作输出，不应进入群聊。",
            workspace_id="workspace_1",
            channel_id="channel_1",
            member_id="member_training",
            display_name="RNA训练",
            resume_session_id="session_training",
            event_index=3,
            transcript_ref={"session_id": "session_training", "event_index": 3},
        )
        is None
    )


def test_parse_codex_group_candidate_rejects_bad_intent() -> None:
    with pytest.raises(ValueError, match="GROUP_CHAT_INTENT"):
        parse_codex_group_candidate(
            text=(
                "GROUP_CHAT_INTENT: maybe\n"
                "GROUP_CHAT_SUMMARY: bad\n"
                "GROUP_CHAT_PRIORITY: 1\n"
            ),
            workspace_id="workspace_1",
            channel_id="channel_1",
            member_id="member_training",
            display_name="RNA训练",
            resume_session_id="session_training",
            event_index=3,
            transcript_ref={"session_id": "session_training", "event_index": 3},
        )


def test_candidate_to_agent_message_preserves_visibility_metadata() -> None:
    candidate = CodexGroupCandidate(
        candidate_id="candidate_member_training_session_training_42_respond",
        workspace_id="workspace_1",
        channel_id="channel_1",
        member_id="member_training",
        display_name="RNA训练",
        resume_session_id="session_training",
        event_index=42,
        intent="respond",
        summary="工程侧 ready。",
        priority=50,
        state_lock="rna:submission",
        transcript_ref={"session_id": "session_training", "event_index": 42},
    )

    message = candidate_to_agent_message(candidate)

    assert message.message_id == candidate.candidate_id
    assert message.agent_id == "member_training"
    assert message.intent == "respond"
    assert message.summary == "工程侧 ready。"
    assert message.priority == 50
    assert message.state_lock == "rna:submission"
    assert message.metadata == {
        "source": "codex_group_candidate",
        "workspace_id": "workspace_1",
        "channel_id": "channel_1",
        "display_name": "RNA训练",
        "resume_session_id": "session_training",
        "event_index": 42,
        "transcript_ref": {"session_id": "session_training", "event_index": 42},
    }
```

- [ ] **Step 1.2: Run parser tests to verify they fail**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest --import-mode=importlib tests/unit/features/supervisor/agent_group/workspace/test_group_candidates.py -q
```

Expected: fails with `ModuleNotFoundError` for `workspace.coordination`.

- [ ] **Step 1.3: Implement candidate contract and parser**

Create `src/isotope/features/supervisor/agent_group/workspace/coordination/__init__.py`:

```python
"""Coordination runtime helpers for Codex-backed Agent Workspace channels."""
```

Create `src/isotope/features/supervisor/agent_group/workspace/coordination/candidates.py`:

```python
"""Codex group-chat candidate parsing and projection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from isotope.agents.loop.conversation import AgentConversationMessage


GROUP_CHAT_INTENTS = {"respond", "interrupt", "internal_note", "silent"}


@dataclass(frozen=True)
class CodexGroupCandidate:
    candidate_id: str
    workspace_id: str
    channel_id: str
    member_id: str
    display_name: str
    resume_session_id: str
    event_index: int
    intent: str
    summary: str
    priority: int = 0
    state_lock: str | None = None
    transcript_ref: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.candidate_id, "candidate_id")
        _require_text(self.workspace_id, "workspace_id")
        _require_text(self.channel_id, "channel_id")
        _require_text(self.member_id, "member_id")
        _require_text(self.display_name, "display_name")
        _require_text(self.resume_session_id, "resume_session_id")
        if isinstance(self.event_index, bool) or not isinstance(self.event_index, int):
            raise ValueError("event_index must be an integer")
        if self.intent not in GROUP_CHAT_INTENTS:
            raise ValueError("GROUP_CHAT_INTENT must be respond, interrupt, internal_note, or silent")
        _require_text(self.summary, "summary")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise ValueError("priority must be an integer")
        if self.priority < 0:
            raise ValueError("priority must be non-negative")
        if self.state_lock is not None:
            _require_text(self.state_lock, "state_lock")
        if not isinstance(self.transcript_ref, dict):
            raise ValueError("transcript_ref must be a dict")

    def to_public_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "candidate_id": self.candidate_id,
            "workspace_id": self.workspace_id,
            "channel_id": self.channel_id,
            "member_id": self.member_id,
            "display_name": self.display_name,
            "resume_session_id": self.resume_session_id,
            "event_index": self.event_index,
            "intent": self.intent,
            "summary": self.summary,
            "priority": self.priority,
            "transcript_ref": dict(self.transcript_ref),
        }
        if self.state_lock is not None:
            payload["state_lock"] = self.state_lock
        return payload


def parse_codex_group_candidate(
    *,
    text: str,
    workspace_id: str,
    channel_id: str,
    member_id: str,
    display_name: str,
    resume_session_id: str,
    event_index: int,
    transcript_ref: dict[str, Any],
) -> CodexGroupCandidate | None:
    markers = _marker_values(text)
    if "GROUP_CHAT_INTENT" not in markers:
        return None
    intent = markers["GROUP_CHAT_INTENT"].strip()
    summary = markers.get("GROUP_CHAT_SUMMARY", "").strip()
    priority_text = markers.get("GROUP_CHAT_PRIORITY", "0").strip()
    state_lock = markers.get("GROUP_CHAT_STATE_LOCK", "").strip() or None
    if intent not in GROUP_CHAT_INTENTS:
        raise ValueError("GROUP_CHAT_INTENT must be respond, interrupt, internal_note, or silent")
    if not summary:
        raise ValueError("GROUP_CHAT_SUMMARY must be non-empty")
    try:
        priority = int(priority_text)
    except ValueError as exc:
        raise ValueError("GROUP_CHAT_PRIORITY must be an integer") from exc
    return CodexGroupCandidate(
        candidate_id=f"candidate_{member_id}_{resume_session_id}_{event_index}_{intent}",
        workspace_id=workspace_id,
        channel_id=channel_id,
        member_id=member_id,
        display_name=display_name,
        resume_session_id=resume_session_id,
        event_index=event_index,
        intent=intent,
        summary=summary,
        priority=priority,
        state_lock=state_lock,
        transcript_ref=dict(transcript_ref),
    )


def candidate_to_agent_message(candidate: CodexGroupCandidate) -> AgentConversationMessage:
    return AgentConversationMessage(
        message_id=candidate.candidate_id,
        agent_id=candidate.member_id,
        intent=candidate.intent,
        summary=candidate.summary,
        priority=candidate.priority,
        interrupt_reason=(
            candidate.summary if candidate.intent == "interrupt" else None
        ),
        state_lock=candidate.state_lock,
        metadata={
            "source": "codex_group_candidate",
            "workspace_id": candidate.workspace_id,
            "channel_id": candidate.channel_id,
            "display_name": candidate.display_name,
            "resume_session_id": candidate.resume_session_id,
            "event_index": candidate.event_index,
            "transcript_ref": dict(candidate.transcript_ref),
        },
    )


def _marker_values(text: str) -> dict[str, str]:
    markers: dict[str, str] = {}
    for raw_line in text.splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        key = key.strip()
        if key.startswith("GROUP_CHAT_"):
            markers[key] = value.strip()
    return markers


def _require_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
```

- [ ] **Step 1.4: Run parser tests to verify they pass**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest --import-mode=importlib tests/unit/features/supervisor/agent_group/workspace/test_group_candidates.py -q
```

Expected: all tests in `test_group_candidates.py` pass.

- [ ] **Step 1.5: Commit candidate parser**

Run:

```bash
git add src/isotope/features/supervisor/agent_group/workspace/coordination tests/unit/features/supervisor/agent_group/workspace/test_group_candidates.py
git commit -m "feat(supervisor): parse codex group candidates"
```

---

### Task 2: Add Member Inbox Persistence

**Files:**

- Create: `src/isotope/features/supervisor/agent_group/workspace/coordination/inbox.py`
- Test: `tests/unit/features/supervisor/agent_group/workspace/test_member_inbox.py`

- [ ] **Step 2.1: Write failing inbox tests**

Create `tests/unit/features/supervisor/agent_group/workspace/test_member_inbox.py`:

```python
from __future__ import annotations

from isotope.features.supervisor.agent_group.workspace.coordination.inbox import (
    MemberInboxItem,
    MemberInboxStore,
)


def test_member_inbox_enqueue_is_idempotent_by_source_and_target(tmp_path):
    store = MemberInboxStore(tmp_path / ".codex")

    first = store.enqueue(
        workspace_id="workspace_1",
        channel_id="channel_1",
        target_member_id="member_training",
        source_message_id="msg_user_1",
        from_actor="user",
        summary="请同步当前进展。",
        payload={"runtime_group_id": "group_workspace_1"},
    )
    repeated = store.enqueue(
        workspace_id="workspace_1",
        channel_id="channel_1",
        target_member_id="member_training",
        source_message_id="msg_user_1",
        from_actor="user",
        summary="请同步当前进展。",
        payload={"runtime_group_id": "group_workspace_1"},
    )

    assert repeated == first
    assert store.list_pending("workspace_1", "channel_1", "member_training") == [
        first
    ]


def test_member_inbox_marks_items_dispatched(tmp_path):
    store = MemberInboxStore(tmp_path / ".codex")
    item = store.enqueue(
        workspace_id="workspace_1",
        channel_id="channel_1",
        target_member_id="member_training",
        source_message_id="msg_user_1",
        from_actor="user",
        summary="请同步当前进展。",
        payload={},
    )

    dispatched = store.mark_dispatched(
        workspace_id="workspace_1",
        channel_id="channel_1",
        target_member_id="member_training",
        inbox_item_ids=(item.inbox_item_id,),
        managed_record_id="managed-training",
    )

    assert dispatched[0].status == "dispatched"
    assert dispatched[0].managed_record_id == "managed-training"
    assert store.list_pending("workspace_1", "channel_1", "member_training") == []


def test_member_inbox_pending_counts_by_member(tmp_path):
    store = MemberInboxStore(tmp_path / ".codex")
    store.enqueue(
        workspace_id="workspace_1",
        channel_id="channel_1",
        target_member_id="member_training",
        source_message_id="msg_1",
        from_actor="user",
        summary="one",
        payload={},
    )
    store.enqueue(
        workspace_id="workspace_1",
        channel_id="channel_1",
        target_member_id="member_research",
        source_message_id="msg_2",
        from_actor="member_training",
        summary="two",
        payload={},
    )

    assert store.pending_counts_by_member("workspace_1", "channel_1") == {
        "member_training": 1,
        "member_research": 1,
    }


def test_member_inbox_public_dict_has_no_raw_payload_fields() -> None:
    item = MemberInboxItem(
        inbox_item_id="inbox_1",
        workspace_id="workspace_1",
        channel_id="channel_1",
        target_member_id="member_training",
        source_message_id="msg_1",
        from_actor="user",
        summary="hello",
        status="pending",
        payload={"runtime_group_id": "group_1"},
        managed_record_id=None,
        created_at="2026-06-12T00:00:00Z",
        updated_at="2026-06-12T00:00:00Z",
    )

    assert item.to_public_dict() == {
        "inbox_item_id": "inbox_1",
        "workspace_id": "workspace_1",
        "channel_id": "channel_1",
        "target_member_id": "member_training",
        "source_message_id": "msg_1",
        "from_actor": "user",
        "summary": "hello",
        "status": "pending",
        "payload": {"runtime_group_id": "group_1"},
        "managed_record_id": None,
        "created_at": "2026-06-12T00:00:00Z",
        "updated_at": "2026-06-12T00:00:00Z",
    }
```

- [ ] **Step 2.2: Run inbox tests to verify they fail**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest --import-mode=importlib tests/unit/features/supervisor/agent_group/workspace/test_member_inbox.py -q
```

Expected: fails because `workspace.coordination.inbox` does not exist.

- [ ] **Step 2.3: Implement inbox store**

Create `src/isotope/features/supervisor/agent_group/workspace/coordination/inbox.py`:

```python
"""Pending delivery inbox for Codex workspace members."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

from isotope.platform.schemas.memory import MemoryRecord
from isotope.platform.state.memory_store import FileMemoryStore

from ..contracts import _copy_public_payload, _reject_raw_workspace_payload


INBOX_RECORD_KIND = "agent_workspace_member_inbox"
INBOX_STATUSES = {"pending", "dispatched", "cancelled"}


@dataclass(frozen=True)
class MemberInboxItem:
    inbox_item_id: str
    workspace_id: str
    channel_id: str
    target_member_id: str
    source_message_id: str
    from_actor: str
    summary: str
    status: str
    payload: dict[str, Any]
    managed_record_id: str | None
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        _require_text(self.inbox_item_id, "inbox_item_id")
        _require_text(self.workspace_id, "workspace_id")
        _require_text(self.channel_id, "channel_id")
        _require_text(self.target_member_id, "target_member_id")
        _require_text(self.source_message_id, "source_message_id")
        _require_text(self.from_actor, "from_actor")
        _require_text(self.summary, "summary")
        if self.status not in INBOX_STATUSES:
            raise ValueError("inbox status must be pending, dispatched, or cancelled")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dict")
        _reject_raw_workspace_payload(self.payload)
        if self.managed_record_id is not None:
            _require_text(self.managed_record_id, "managed_record_id")
        _require_text(self.created_at, "created_at")
        _require_text(self.updated_at, "updated_at")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "inbox_item_id": self.inbox_item_id,
            "workspace_id": self.workspace_id,
            "channel_id": self.channel_id,
            "target_member_id": self.target_member_id,
            "source_message_id": self.source_message_id,
            "from_actor": self.from_actor,
            "summary": self.summary,
            "status": self.status,
            "payload": _copy_public_payload(self.payload),
            "managed_record_id": self.managed_record_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class MemberInboxStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser()
        self.memory = FileMemoryStore(self.root)

    def enqueue(
        self,
        *,
        workspace_id: str,
        channel_id: str,
        target_member_id: str,
        source_message_id: str,
        from_actor: str,
        summary: str,
        payload: dict[str, Any],
    ) -> MemberInboxItem:
        for existing in self.list_items(workspace_id, channel_id):
            if (
                existing.target_member_id == target_member_id
                and existing.source_message_id == source_message_id
                and existing.status == "pending"
            ):
                return existing
        now = _utc_now()
        item = MemberInboxItem(
            inbox_item_id=_new_id("inbox"),
            workspace_id=workspace_id,
            channel_id=channel_id,
            target_member_id=target_member_id,
            source_message_id=source_message_id,
            from_actor=from_actor,
            summary=summary,
            status="pending",
            payload=dict(payload),
            managed_record_id=None,
            created_at=now,
            updated_at=now,
        )
        self.memory.append_record(_record_for_inbox_item(item))
        return item

    def list_items(self, workspace_id: str, channel_id: str) -> list[MemberInboxItem]:
        latest: dict[str, tuple[MemberInboxItem, str]] = {}
        for record in self.memory.list_records(scope="session"):
            if (
                record.content.get("kind") != INBOX_RECORD_KIND
                or record.content.get("workspace_id") != workspace_id
                or record.content.get("channel_id") != channel_id
            ):
                continue
            item = _inbox_item_from_record(record)
            if item is None:
                continue
            current = latest.get(item.inbox_item_id)
            if current is None or record.created_at >= current[1]:
                latest[item.inbox_item_id] = (item, record.created_at)
        return sorted(
            [item for item, _created_at in latest.values()],
            key=lambda item: (item.created_at, item.inbox_item_id),
        )

    def list_pending(
        self,
        workspace_id: str,
        channel_id: str,
        target_member_id: str,
    ) -> list[MemberInboxItem]:
        return [
            item
            for item in self.list_items(workspace_id, channel_id)
            if item.target_member_id == target_member_id and item.status == "pending"
        ]

    def mark_dispatched(
        self,
        *,
        workspace_id: str,
        channel_id: str,
        target_member_id: str,
        inbox_item_ids: tuple[str, ...],
        managed_record_id: str,
    ) -> list[MemberInboxItem]:
        selected = set(inbox_item_ids)
        updated: list[MemberInboxItem] = []
        for item in self.list_pending(workspace_id, channel_id, target_member_id):
            if item.inbox_item_id not in selected:
                continue
            dispatched = replace(
                item,
                status="dispatched",
                managed_record_id=managed_record_id,
                updated_at=_utc_now(),
            )
            self.memory.append_record(_record_for_inbox_item(dispatched))
            updated.append(dispatched)
        return updated

    def pending_counts_by_member(
        self,
        workspace_id: str,
        channel_id: str,
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.list_items(workspace_id, channel_id):
            if item.status != "pending":
                continue
            counts[item.target_member_id] = counts.get(item.target_member_id, 0) + 1
        return counts


def _record_for_inbox_item(item: MemberInboxItem) -> MemoryRecord:
    return MemoryRecord(
        memory_id=(
            f"agent_workspace_inbox_{item.workspace_id}_{item.channel_id}_"
            f"{item.target_member_id}_{item.inbox_item_id}_{_new_id('rev')}"
        ),
        scope="session",
        content={"kind": INBOX_RECORD_KIND, **item.to_public_dict()},
        summary=f"Pending workspace inbox item for {item.target_member_id}: {item.summary}",
        source_refs=[],
        provenance={
            "run_id": "agent_group_workspace",
            "execution_id": _new_id("exec"),
            "action_type": INBOX_RECORD_KIND,
        },
        created_at=_utc_now(),
        supersedes=[],
        quality="agent_group_workspace",
    )


def _inbox_item_from_record(record: MemoryRecord) -> MemberInboxItem | None:
    try:
        return MemberInboxItem(
            inbox_item_id=str(record.content["inbox_item_id"]),
            workspace_id=str(record.content["workspace_id"]),
            channel_id=str(record.content["channel_id"]),
            target_member_id=str(record.content["target_member_id"]),
            source_message_id=str(record.content["source_message_id"]),
            from_actor=str(record.content["from_actor"]),
            summary=str(record.content["summary"]),
            status=str(record.content["status"]),
            payload=dict(record.content.get("payload") or {}),
            managed_record_id=_optional_string(record.content.get("managed_record_id")),
            created_at=str(record.content["created_at"]),
            updated_at=str(record.content["updated_at"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _require_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
```

- [ ] **Step 2.4: Run inbox tests to verify they pass**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest --import-mode=importlib tests/unit/features/supervisor/agent_group/workspace/test_member_inbox.py -q
```

Expected: all inbox tests pass.

- [ ] **Step 2.5: Commit inbox store**

Run:

```bash
git add src/isotope/features/supervisor/agent_group/workspace/coordination/inbox.py tests/unit/features/supervisor/agent_group/workspace/test_member_inbox.py
git commit -m "feat(supervisor): persist codex member inbox"
```

---

### Task 3: Add Arbiter-Backed Channel Turn Runtime

**Files:**

- Create: `src/isotope/features/supervisor/agent_group/workspace/coordination/turns.py`
- Modify: `src/isotope/features/supervisor/agent_group/workspace/runtime_bridge.py`
- Test: `tests/unit/features/supervisor/agent_group/workspace/test_candidate_turns.py`

- [ ] **Step 3.1: Write failing turn-runtime tests**

Create `tests/unit/features/supervisor/agent_group/workspace/test_candidate_turns.py`:

```python
from __future__ import annotations

from isotope.features.supervisor.agent_group.store import AgentGroupStore
from isotope.features.supervisor.agent_group.workspace.coordination.candidates import (
    CodexGroupCandidate,
)
from isotope.features.supervisor.agent_group.workspace.coordination.inbox import (
    MemberInboxStore,
)
from isotope.features.supervisor.agent_group.workspace.coordination.turns import (
    run_channel_candidate_turn,
)
from isotope.features.supervisor.agent_group.workspace.runtime_bridge import runtime_group_id
from isotope.features.supervisor.agent_group.workspace.store import AgentWorkspaceStore


def test_candidate_turn_publishes_only_selected_visible_reply(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace_root = tmp_path / "AI_Camp_RNA_2026"
    workspace_root.mkdir()
    workspace_store = AgentWorkspaceStore(codex_home)
    workspace = workspace_store.ensure_default_workspace(root_path=workspace_root)
    channel = workspace_store.list_channels(workspace.workspace_id)[0]
    training = workspace_store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="RNA训练",
        role="工程推进",
        goal="验证训练链路。",
        send_policy="auto",
        resume_session_id="session_training",
        source_path=None,
        managed_record_id=None,
    )
    research = workspace_store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="rna探索",
        role="科研探索",
        goal="提出科研判断。",
        send_policy="auto",
        resume_session_id="session_research",
        source_path=None,
        managed_record_id=None,
    )

    result = run_channel_candidate_turn(
        store=workspace_store,
        state_root=codex_home,
        workspace=workspace,
        channel_id=channel.channel_id,
        candidates=[
            CodexGroupCandidate(
                candidate_id="candidate_training_1",
                workspace_id=workspace.workspace_id,
                channel_id=channel.channel_id,
                member_id=training.member_id,
                display_name="RNA训练",
                resume_session_id="session_training",
                event_index=2,
                intent="respond",
                summary="工程侧已经完成 smoke。",
                priority=50,
                state_lock=None,
                transcript_ref={"session_id": "session_training", "event_index": 2},
            ),
            CodexGroupCandidate(
                candidate_id="candidate_research_1",
                workspace_id=workspace.workspace_id,
                channel_id=channel.channel_id,
                member_id=research.member_id,
                display_name="rna探索",
                resume_session_id="session_research",
                event_index=7,
                intent="silent",
                summary="当前无需公开发言。",
                priority=0,
                state_lock=None,
                transcript_ref={"session_id": "session_research", "event_index": 7},
            ),
        ],
        max_visible_messages=1,
    )

    assert result["turn"]["status"] == "selected"
    assert result["published_messages"][0]["summary"] == "工程侧已经完成 smoke。"
    messages = workspace_store.list_messages(
        workspace.workspace_id,
        "channel",
        channel.channel_id,
    )
    assert [(message.from_actor, message.message_type, message.summary) for message in messages] == [
        (training.member_id, "member_observation", "工程侧已经完成 smoke。")
    ]
    turns = AgentGroupStore(codex_home).list_turns(
        runtime_group_id(workspace.workspace_id, channel.channel_id)
    )
    assert turns[-1].candidate_messages == (
        "candidate_training_1",
        "candidate_research_1",
    )
    assert turns[-1].dropped_messages == (
        {
            "message_id": "candidate_research_1",
            "agent_id": research.member_id,
            "reason": "silent",
        },
    )


def test_candidate_turn_enqueues_selected_reply_for_other_members(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace_root = tmp_path / "AI_Camp_RNA_2026"
    workspace_root.mkdir()
    workspace_store = AgentWorkspaceStore(codex_home)
    workspace = workspace_store.ensure_default_workspace(root_path=workspace_root)
    channel = workspace_store.list_channels(workspace.workspace_id)[0]
    training = workspace_store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="RNA训练",
        role="工程推进",
        goal="验证训练链路。",
        send_policy="auto",
        resume_session_id="session_training",
        source_path=None,
        managed_record_id=None,
    )
    research = workspace_store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="rna探索",
        role="科研探索",
        goal="提出科研判断。",
        send_policy="auto",
        resume_session_id="session_research",
        source_path=None,
        managed_record_id=None,
    )

    run_channel_candidate_turn(
        store=workspace_store,
        state_root=codex_home,
        workspace=workspace,
        channel_id=channel.channel_id,
        candidates=[
            CodexGroupCandidate(
                candidate_id="candidate_training_1",
                workspace_id=workspace.workspace_id,
                channel_id=channel.channel_id,
                member_id=training.member_id,
                display_name="RNA训练",
                resume_session_id="session_training",
                event_index=2,
                intent="respond",
                summary="工程侧已经完成 smoke。",
                priority=50,
                transcript_ref={"session_id": "session_training", "event_index": 2},
            ),
        ],
        max_visible_messages=1,
    )

    inbox = MemberInboxStore(codex_home)
    pending_for_source = inbox.list_pending(
        workspace.workspace_id,
        channel.channel_id,
        training.member_id,
    )
    pending_for_peer = inbox.list_pending(
        workspace.workspace_id,
        channel.channel_id,
        research.member_id,
    )
    assert pending_for_source == []
    assert len(pending_for_peer) == 1
    assert pending_for_peer[0].summary == "工程侧已经完成 smoke。"
    assert pending_for_peer[0].from_actor == training.member_id
```

- [ ] **Step 3.2: Run turn-runtime tests to verify they fail**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest --import-mode=importlib tests/unit/features/supervisor/agent_group/workspace/test_candidate_turns.py -q
```

Expected: fails because `coordination.turns` does not exist.

- [ ] **Step 3.3: Implement turn runtime**

Create `src/isotope/features/supervisor/agent_group/workspace/coordination/turns.py`:

```python
"""AgentGroup arbiter integration for workspace Codex candidates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from isotope.agents.loop.conversation import arbitrate_agent_conversation_turn
from isotope.features.supervisor.agent_group.store import AgentGroupStore

from ..contracts import AgentWorkspace
from ..runtime_bridge import (
    publish_workspace_message_to_runtime_group,
    runtime_group_id,
    runtime_payload_for_channel,
    sync_channel_runtime_group,
)
from ..store import AgentWorkspaceStore
from .candidates import CodexGroupCandidate, candidate_to_agent_message
from .inbox import MemberInboxStore


def run_channel_candidate_turn(
    *,
    store: AgentWorkspaceStore,
    state_root: Path | str,
    workspace: AgentWorkspace,
    channel_id: str,
    candidates: list[CodexGroupCandidate],
    max_visible_messages: int = 2,
) -> dict[str, Any]:
    group_id = sync_channel_runtime_group(
        store=store,
        state_root=state_root,
        workspace=workspace,
        channel_id=channel_id,
    )
    group_store = AgentGroupStore(state_root)
    agent_messages = [candidate_to_agent_message(candidate) for candidate in candidates]
    turn_id = f"turn_workspace_{len(group_store.list_turns(group_id)) + 1:04d}"
    arbitration = arbitrate_agent_conversation_turn(
        agent_messages,
        turn_id=turn_id,
        max_visible_messages=max_visible_messages,
    )
    published_messages = []
    for selected in arbitration["visible_messages"]:
        candidate = _candidate_by_id(candidates, str(selected["message_id"]))
        if candidate is None:
            continue
        workspace_message = store.publish_message(
            workspace_id=workspace.workspace_id,
            conversation_type="channel",
            conversation_id=channel_id,
            from_actor=candidate.member_id,
            to_actor=None,
            message_type="member_observation",
            summary=candidate.summary,
            payload={
                **runtime_payload_for_channel(
                    store=store,
                    state_root=state_root,
                    workspace=workspace,
                    channel_id=channel_id,
                ),
                "member_id": candidate.member_id,
                "display_name": candidate.display_name,
                "resume_session_id": candidate.resume_session_id,
                "event_index": candidate.event_index,
                "candidate_id": candidate.candidate_id,
                "candidate_intent": candidate.intent,
                "candidate_priority": candidate.priority,
                "transcript_ref": dict(candidate.transcript_ref),
            },
        )
        publish_workspace_message_to_runtime_group(
            store=store,
            state_root=state_root,
            workspace=workspace,
            channel_id=channel_id,
            message=workspace_message,
        )
        _enqueue_visible_message_for_other_members(
            store=store,
            state_root=state_root,
            workspace=workspace,
            channel_id=channel_id,
            source_member_id=candidate.member_id,
            source_message_id=workspace_message.message_id,
            summary=candidate.summary,
            payload=workspace_message.payload,
        )
        published_messages.append(workspace_message.to_public_dict())
    turn = group_store.record_turn(
        group_id=group_id,
        input_message_ids=tuple(
            message.message_id
            for message in group_store.list_group_messages(group_id, limit=10)
        ),
        candidate_messages=tuple(candidate.candidate_id for candidate in candidates),
        selected_message_ids=tuple(
            item["message_id"]
            for item in published_messages
            if isinstance(item.get("message_id"), str)
        ),
        queued_messages=tuple(arbitration["queued_messages"]),
        dropped_messages=tuple(arbitration["dropped_messages"]),
        status=str(arbitration["status"]),
        supervisor_summary=_turn_summary(arbitration),
    )
    return {
        "status": "ok",
        "turn": turn.to_public_dict(),
        "published_messages": published_messages,
        "arbitration": arbitration,
    }


def _enqueue_visible_message_for_other_members(
    *,
    store: AgentWorkspaceStore,
    state_root: Path | str,
    workspace: AgentWorkspace,
    channel_id: str,
    source_member_id: str,
    source_message_id: str,
    summary: str,
    payload: dict[str, Any],
) -> None:
    inbox = MemberInboxStore(state_root)
    for member in store.list_channel_members(workspace.workspace_id, channel_id):
        if (
            member.member_kind != "codex_session"
            or member.member_id == source_member_id
            or member.status == "terminated"
        ):
            continue
        inbox.enqueue(
            workspace_id=workspace.workspace_id,
            channel_id=channel_id,
            target_member_id=member.member_id,
            source_message_id=source_message_id,
            from_actor=source_member_id,
            summary=summary,
            payload=payload,
        )


def _candidate_by_id(
    candidates: list[CodexGroupCandidate],
    candidate_id: str,
) -> CodexGroupCandidate | None:
    for candidate in candidates:
        if candidate.candidate_id == candidate_id:
            return candidate
    return None


def _turn_summary(arbitration: dict[str, Any]) -> str:
    visible = len(arbitration.get("visible_messages") or [])
    queued = len(arbitration.get("queued_messages") or [])
    dropped = len(arbitration.get("dropped_messages") or [])
    if visible == 0:
        return f"No visible Codex group replies; queued {queued}, dropped {dropped}."
    return f"Selected {visible} Codex group replies; queued {queued}, dropped {dropped}."
```

- [ ] **Step 3.4: Run turn-runtime tests to verify they pass**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest --import-mode=importlib tests/unit/features/supervisor/agent_group/workspace/test_candidate_turns.py -q
```

Expected: all candidate turn tests pass.

- [ ] **Step 3.5: Run parser and inbox tests together**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest --import-mode=importlib tests/unit/features/supervisor/agent_group/workspace/test_group_candidates.py tests/unit/features/supervisor/agent_group/workspace/test_member_inbox.py tests/unit/features/supervisor/agent_group/workspace/test_candidate_turns.py -q
```

Expected: all tests pass.

- [ ] **Step 3.6: Commit turn runtime**

Run:

```bash
git add src/isotope/features/supervisor/agent_group/workspace/coordination/turns.py tests/unit/features/supervisor/agent_group/workspace/test_candidate_turns.py
git commit -m "feat(supervisor): arbitrate codex group candidates"
```

---

### Task 4: Migrate Transcript Import To Explicit Candidates

**Files:**

- Modify: `src/isotope/features/supervisor/agent_group/workspace/importer.py`
- Test: `tests/unit/features/supervisor/agent_group/workspace/test_reply_importer.py`

- [ ] **Step 4.1: Add failing importer tests for non-marker and marker behavior**

Append these tests to `tests/unit/features/supervisor/agent_group/workspace/test_reply_importer.py`:

```python
def test_import_channel_member_replies_ignores_plain_assistant_output_for_group_stream(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    workspace_root = tmp_path / "AI_Camp_RNA_2026"
    workspace_root.mkdir()
    session_path = tmp_path / "session.jsonl"
    write_jsonl(
        session_path,
        [
            {"type": "session_meta", "payload": {"id": "session_training"}},
            _message_row("user", "请同步当前进展。", index=1),
            _message_row("assistant", "我继续训练链路验证，不需要公开发言。", index=2),
        ],
    )
    store = AgentWorkspaceStore(codex_home)
    workspace = store.ensure_default_workspace(root_path=workspace_root)
    channel = store.list_channels(workspace.workspace_id)[0]
    member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="RNA训练",
        role="工程推进",
        goal="继续训练。",
        send_policy="auto",
        resume_session_id="session_training",
        source_path=str(session_path),
        managed_record_id=None,
    )
    store.update_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=member.member_id,
        transcript_policy={
            **member.transcript_policy,
            "last_imported_event_index": 1,
        },
    )

    imports = import_channel_member_replies(
        store=store,
        state_root=codex_home,
        workspace=workspace,
        channel_id=channel.channel_id,
    )

    assert imports == [
        {
            "member_id": member.member_id,
            "display_name": "RNA训练",
            "status": "transcript_only",
            "imported_count": 0,
            "candidate_count": 0,
            "last_imported_event_index": 2,
        }
    ]
    assert store.list_messages(workspace.workspace_id, "channel", channel.channel_id) == []


def test_import_channel_member_replies_imports_respond_marker_via_arbiter(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace_root = tmp_path / "AI_Camp_RNA_2026"
    workspace_root.mkdir()
    session_path = tmp_path / "session.jsonl"
    write_jsonl(
        session_path,
        [
            {"type": "session_meta", "payload": {"id": "session_training"}},
            _message_row("user", "请同步当前进展。", index=1),
            _message_row(
                "assistant",
                (
                    "训练工作继续。\n\n"
                    "GROUP_CHAT_INTENT: respond\n"
                    "GROUP_CHAT_SUMMARY: 工程侧已经完成 smoke。\n"
                    "GROUP_CHAT_PRIORITY: 60\n"
                ),
                index=2,
            ),
        ],
    )
    store = AgentWorkspaceStore(codex_home)
    workspace = store.ensure_default_workspace(root_path=workspace_root)
    channel = store.list_channels(workspace.workspace_id)[0]
    member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="RNA训练",
        role="工程推进",
        goal="继续训练。",
        send_policy="auto",
        resume_session_id="session_training",
        source_path=str(session_path),
        managed_record_id=None,
    )
    store.update_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=member.member_id,
        transcript_policy={
            **member.transcript_policy,
            "last_imported_event_index": 1,
        },
    )

    imports = import_channel_member_replies(
        store=store,
        state_root=codex_home,
        workspace=workspace,
        channel_id=channel.channel_id,
    )

    assert imports[0]["status"] == "candidate_imported"
    assert imports[0]["candidate_count"] == 1
    messages = store.list_messages(workspace.workspace_id, "channel", channel.channel_id)
    assert [(message.from_actor, message.message_type, message.summary) for message in messages] == [
        (member.member_id, "member_observation", "工程侧已经完成 smoke。")
    ]
    assert messages[0].payload["candidate_intent"] == "respond"


def test_import_channel_member_replies_records_silent_marker_without_public_message(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    workspace_root = tmp_path / "AI_Camp_RNA_2026"
    workspace_root.mkdir()
    session_path = tmp_path / "session.jsonl"
    write_jsonl(
        session_path,
        [
            {"type": "session_meta", "payload": {"id": "session_research"}},
            _message_row("user", "请同步当前进展。", index=1),
            _message_row(
                "assistant",
                (
                    "我继续原科研判断。\n\n"
                    "GROUP_CHAT_INTENT: silent\n"
                    "GROUP_CHAT_SUMMARY: 当前无需公开发言。\n"
                    "GROUP_CHAT_PRIORITY: 0\n"
                ),
                index=2,
            ),
        ],
    )
    store = AgentWorkspaceStore(codex_home)
    workspace = store.ensure_default_workspace(root_path=workspace_root)
    channel = store.list_channels(workspace.workspace_id)[0]
    member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="rna探索",
        role="科研探索",
        goal="提出科研判断。",
        send_policy="auto",
        resume_session_id="session_research",
        source_path=str(session_path),
        managed_record_id=None,
    )
    store.update_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=member.member_id,
        transcript_policy={
            **member.transcript_policy,
            "last_imported_event_index": 1,
        },
    )

    imports = import_channel_member_replies(
        store=store,
        state_root=codex_home,
        workspace=workspace,
        channel_id=channel.channel_id,
    )

    assert imports[0]["status"] == "candidate_imported"
    assert imports[0]["candidate_count"] == 1
    assert imports[0]["published_count"] == 0
    assert store.list_messages(workspace.workspace_id, "channel", channel.channel_id) == []
```

Also add this helper near the bottom of the same test file:

```python
def _message_row(role: str, content: str, *, index: int) -> dict[str, object]:
    return {
        "type": "response_item",
        "timestamp": f"2026-06-12T00:00:0{index}Z",
        "payload": {
            "type": "message",
            "role": role,
            "content": content,
        },
    }
```

- [ ] **Step 4.2: Run importer tests to verify new tests fail**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest --import-mode=importlib tests/unit/features/supervisor/agent_group/workspace/test_reply_importer.py -q
```

Expected: new tests fail because importer still imports plain assistant text as public `member_observation`.

- [ ] **Step 4.3: Modify importer to parse candidates**

In `src/isotope/features/supervisor/agent_group/workspace/importer.py`:

- Import:

```python
from .coordination.candidates import parse_codex_group_candidate
from .coordination.turns import run_channel_candidate_turn
```

- Inside `import_member_replies(...)`, replace the plain-text publish loop with candidate collection:

```python
candidates = []
plain_assistant_count = 0
for event in page.get("terminal_events") or []:
    if not isinstance(event, dict):
        continue
    if event.get("kind") != "message" or event.get("role") != "assistant":
        continue
    has_non_empty_assistant_message = True
    text = str(event.get("text") or "").strip()
    if not text:
        continue
    event_index = int(event.get("event_index") or 0)
    transcript_ref = {
        "session_id": session_id,
        "event_index": event_index,
        "offset": event_index,
        "limit": 1,
    }
    candidate = parse_codex_group_candidate(
        text=text,
        workspace_id=workspace.workspace_id,
        channel_id=channel_id,
        member_id=member.member_id,
        display_name=member.display_name,
        resume_session_id=session_id,
        event_index=event_index,
        transcript_ref=transcript_ref,
    )
    if candidate is None:
        plain_assistant_count += 1
        continue
    if _candidate_already_imported(
        store=store,
        workspace=workspace,
        channel_id=channel_id,
        member=member,
        candidate_id=candidate.candidate_id,
    ):
        continue
    candidates.append(candidate)
```

- After updating `last_seen`, run the arbiter only when candidates exist:

```python
turn_result = None
if candidates:
    turn_result = run_channel_candidate_turn(
        store=store,
        state_root=state_root,
        workspace=workspace,
        channel_id=channel_id,
        candidates=candidates,
        max_visible_messages=2,
    )
published_count = len((turn_result or {}).get("published_messages") or [])
```

- Return statuses:

```python
if candidates:
    return {
        "member_id": member.member_id,
        "display_name": member.display_name,
        "status": "candidate_imported",
        "imported_count": published_count,
        "candidate_count": len(candidates),
        "published_count": published_count,
        "last_imported_event_index": last_seen,
    }
if plain_assistant_count:
    return {
        "member_id": member.member_id,
        "display_name": member.display_name,
        "status": "transcript_only",
        "imported_count": 0,
        "candidate_count": 0,
        "last_imported_event_index": last_seen,
    }
```

- Add `_candidate_already_imported(...)` that scans recent `member_observation` payloads for `candidate_id`.

- Keep the existing empty-assistant completion behavior, but return `silent` only for empty final output with no marker and no text.

- [ ] **Step 4.4: Run importer tests to verify they pass**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest --import-mode=importlib tests/unit/features/supervisor/agent_group/workspace/test_reply_importer.py -q
```

Expected: importer tests pass.

- [ ] **Step 4.5: Run workspace parser/inbox/turn/importer tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest --import-mode=importlib tests/unit/features/supervisor/agent_group/workspace/test_group_candidates.py tests/unit/features/supervisor/agent_group/workspace/test_member_inbox.py tests/unit/features/supervisor/agent_group/workspace/test_candidate_turns.py tests/unit/features/supervisor/agent_group/workspace/test_reply_importer.py -q
```

Expected: all listed tests pass.

- [ ] **Step 4.6: Commit importer migration**

Run:

```bash
git add src/isotope/features/supervisor/agent_group/workspace/importer.py tests/unit/features/supervisor/agent_group/workspace/test_reply_importer.py
git commit -m "fix(supervisor): import codex replies as group candidates"
```

---

### Task 5: Replace New Direct Relay Path With Inbox Delivery

**Files:**

- Modify: `src/isotope/features/supervisor/agent_group/workspace/dispatcher.py`
- Modify: `src/isotope/features/supervisor/agent_group/workspace/api.py`
- Test: `tests/unit/features/supervisor/agent_group/workspace/test_api.py`
- Test: `tests/unit/features/supervisor/agent_group/workspace/test_relay_silence.py`

- [ ] **Step 5.1: Add failing API tests for running and idle delivery**

Append these tests to `tests/unit/features/supervisor/agent_group/workspace/test_api.py`:

```python
def test_conversation_chat_queues_for_running_auto_member_without_resume(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace_root = tmp_path / "AI_Camp_RNA_2026"
    workspace_root.mkdir()
    store = AgentWorkspaceStore(codex_home)
    workspace = store.ensure_default_workspace(root_path=workspace_root)
    channel = store.list_channels(workspace.workspace_id)[0]
    member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="RNA训练",
        role="工程推进",
        goal="继续训练。",
        send_policy="auto",
        resume_session_id="session_training",
        source_path=None,
        managed_record_id="managed-training",
    )
    store.update_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=member.member_id,
        status="running",
    )
    resumed_calls: list[dict[str, object]] = []

    def fake_resume_managed_codex(**kwargs):
        resumed_calls.append(kwargs)
        raise AssertionError("running members must not be resumed immediately")

    monkeypatch.setattr(dispatcher, "resume_managed_codex", fake_resume_managed_codex)

    payload = api.conversation_chat_payload(
        codex_home,
        workspace_id=workspace.workspace_id,
        conversation_id=channel.channel_id,
        message="请同步当前进展。",
        mode="queue",
    )

    assert resumed_calls == []
    assert payload["dispatches"] == [
        {
            "member_id": member.member_id,
            "display_name": "RNA训练",
            "send_policy": "auto",
            "status": "queued",
            "managed_record_id": "managed-training",
            "resume_session_id": "session_training",
            "pending_count": 1,
        }
    ]


def test_workspace_payload_drains_idle_member_inbox_once(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    workspace_root = tmp_path / "AI_Camp_RNA_2026"
    workspace_root.mkdir()
    store = AgentWorkspaceStore(codex_home)
    workspace = store.ensure_default_workspace(root_path=workspace_root)
    channel = store.list_channels(workspace.workspace_id)[0]
    member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="RNA训练",
        role="工程推进",
        goal="继续训练。",
        send_policy="auto",
        resume_session_id="session_training",
        source_path=None,
        managed_record_id=None,
    )
    from isotope.features.supervisor.agent_group.workspace.coordination.inbox import (
        MemberInboxStore,
    )

    inbox = MemberInboxStore(codex_home)
    inbox.enqueue(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        target_member_id=member.member_id,
        source_message_id="msg_user_1",
        from_actor="user",
        summary="请同步当前进展。",
        payload={"runtime_group_id": "group_workspace_1"},
    )
    resumed_calls: list[dict[str, object]] = []

    def fake_resume_managed_codex(**kwargs):
        resumed_calls.append(kwargs)
        return ManagedCodexRecord(
            record_id="managed-training",
            name=str(kwargs["name"]),
            cwd=str(kwargs["cwd"]),
            prompt=str(kwargs["prompt"]),
            command=("codex", "resume", "session_training"),
            pid=1234,
            started_at="2026-06-12T00:00:00Z",
            log_path=str(codex_home / "supervisor" / "logs" / "managed-training.log"),
            status="resumed",
            backend="codex_exec_resume",
            resume_session_id=str(kwargs["session_id"]),
        )

    monkeypatch.setattr(dispatcher, "resume_managed_codex", fake_resume_managed_codex)

    payload = api.workspace_payload(codex_home, workspace.workspace_id)

    assert len(resumed_calls) == 1
    assert "待处理群聊消息" in str(resumed_calls[0]["prompt"])
    assert "请同步当前进展。" in str(resumed_calls[0]["prompt"])
    assert payload["inbox"]["pending_counts"].get(member.member_id, 0) == 0
    assert inbox.list_pending(workspace.workspace_id, channel.channel_id, member.member_id) == []
```

- [ ] **Step 5.2: Update relay-silence test to assert no recursive resume**

Modify `tests/unit/features/supervisor/agent_group/workspace/test_relay_silence.py`:

- Keep the scenario with one member producing a public marker reply.
- Assert the other member receives a pending inbox item.
- Assert no immediate second `resume_managed_codex(...)` call is made while that member status is `running`.

Use this assertion shape:

```python
assert [call["session_id"] for call in resumed_calls] == []
pending = MemberInboxStore(codex_home).list_pending(
    workspace.workspace_id,
    channel.channel_id,
    training_member.member_id,
)
assert len(pending) == 1
assert pending[0].summary == "科研侧建议先做 schema readiness 审计。"
```

- [ ] **Step 5.3: Run API tests to verify they fail**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest --import-mode=importlib tests/unit/features/supervisor/agent_group/workspace/test_api.py tests/unit/features/supervisor/agent_group/workspace/test_relay_silence.py -q
```

Expected: new tests fail because dispatcher still calls `resume_managed_codex(...)` directly.

- [ ] **Step 5.4: Implement inbox enqueue and drain helpers in dispatcher**

In `src/isotope/features/supervisor/agent_group/workspace/dispatcher.py`:

- Import `MemberInboxStore`.
- Add `_enqueue_message_for_member(...)`.
- Add `_drain_member_inbox(...)`.
- Change `dispatch_channel_message(...)` so auto members call enqueue+drain, not `_send_to_auto_member(...)` directly.
- Leave `_send_to_auto_member(...)` as the low-level drain implementation.

Implementation shape:

```python
def _enqueue_and_maybe_drain_member(
    *,
    store: AgentWorkspaceStore,
    state_root: Path | str,
    workspace: AgentWorkspace,
    channel_id: str,
    member: ChannelMembership,
    source_message_id: str,
    from_actor: str,
    summary: str,
    mode: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    inbox = MemberInboxStore(state_root)
    inbox.enqueue(
        workspace_id=workspace.workspace_id,
        channel_id=channel_id,
        target_member_id=member.member_id,
        source_message_id=source_message_id,
        from_actor=from_actor,
        summary=summary,
        payload=payload,
    )
    if member.status == "running":
        return {
            **_dispatch_result(
                member,
                status="queued",
                managed_record_id=member.managed_record_id,
            ),
            "pending_count": len(
                inbox.list_pending(workspace.workspace_id, channel_id, member.member_id)
            ),
        }
    return _drain_member_inbox(
        store=store,
        state_root=state_root,
        workspace=workspace,
        channel_id=channel_id,
        member=member,
        mode=mode,
    )
```

Add `_drain_member_inbox(...)`:

```python
def _drain_member_inbox(
    *,
    store: AgentWorkspaceStore,
    state_root: Path | str,
    workspace: AgentWorkspace,
    channel_id: str,
    member: ChannelMembership,
    mode: str,
) -> dict[str, Any]:
    inbox = MemberInboxStore(state_root)
    pending = inbox.list_pending(workspace.workspace_id, channel_id, member.member_id)
    if not pending:
        return {
            **_dispatch_result(member, status="idle", managed_record_id=member.managed_record_id),
            "pending_count": 0,
        }
    prompt = _member_inbox_prompt(member, mode=mode, pending=pending)
    result = _send_to_auto_member(
        store=store,
        state_root=state_root,
        workspace=workspace,
        channel_id=channel_id,
        member=member,
        trigger_actor="群聊",
        trigger_message=prompt,
        trigger_kind=TRIGGER_KIND_USER_MESSAGE,
        mode=mode,
        context_messages=[],
    )
    managed_record_id = result.get("managed_record_id")
    if isinstance(managed_record_id, str):
        inbox.mark_dispatched(
            workspace_id=workspace.workspace_id,
            channel_id=channel_id,
            target_member_id=member.member_id,
            inbox_item_ids=tuple(item.inbox_item_id for item in pending),
            managed_record_id=managed_record_id,
        )
    return {**result, "pending_count": 0}
```

Add `_member_inbox_prompt(...)`:

```python
def _member_inbox_prompt(member: ChannelMembership, *, mode: str, pending) -> str:
    lines = [
        f"你正在 Agent Workspace 群聊中以“{member.display_name}”身份工作。",
        f"角色：{member.role.strip() or 'Codex 会话成员'}",
        f"成员目标：{member.goal.strip() or '继续当前会话目标'}",
        f"发送模式：{mode}",
        "",
        "待处理群聊消息：",
    ]
    for item in pending:
        lines.append(f"- {item.from_actor}：{item.summary}")
    lines.extend(
        [
            "",
            "这些是你尚未处理的群聊输入。请继续你的当前工作。",
            "只有当你明确要在公共群聊发言时，才在回复末尾追加 GROUP_CHAT_* 标记块。",
            "如果不需要公开发言，不要输出空字符串；正常说明你的工作状态即可。",
        ]
    )
    return "\n".join(lines)
```

- [ ] **Step 5.5: Modify API to drain inboxes on workspace payload**

In `src/isotope/features/supervisor/agent_group/workspace/api.py`:

- Import a dispatcher helper `drain_channel_member_inboxes`.
- Replace `relay_runtime_member_observations(...)` calls with `drain_channel_member_inboxes(...)`.
- Project pending counts:

```python
from .coordination.inbox import MemberInboxStore

...
inbox_store = MemberInboxStore(state_root)
...
"inbox": {
    "pending_counts": {
        member_id: count
        for channel in channels
        for member_id, count in inbox_store.pending_counts_by_member(
            workspace_id,
            channel.channel_id,
        ).items()
    }
},
```

- [ ] **Step 5.6: Run API and relay tests to verify they pass**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest --import-mode=importlib tests/unit/features/supervisor/agent_group/workspace/test_api.py tests/unit/features/supervisor/agent_group/workspace/test_relay_silence.py -q
```

Expected: API and relay tests pass.

- [ ] **Step 5.7: Commit inbox delivery migration**

Run:

```bash
git add src/isotope/features/supervisor/agent_group/workspace/dispatcher.py src/isotope/features/supervisor/agent_group/workspace/api.py tests/unit/features/supervisor/agent_group/workspace/test_api.py tests/unit/features/supervisor/agent_group/workspace/test_relay_silence.py
git commit -m "fix(supervisor): route codex group delivery through inbox"
```

---

### Task 6: Projection, Regression Sweep, And Legacy Removal Criteria

**Files:**

- Modify: `docs/superpowers/specs/2026-06-12-agent-group-codex-chat-design.md`
- Modify tests as needed under `tests/unit/features/supervisor/agent_group/workspace/`

- [ ] **Step 6.1: Add a regression assertion that old direct relay is not called from workspace payload**

In `tests/unit/features/supervisor/agent_group/workspace/test_api.py`, add:

```python
def test_workspace_payload_does_not_direct_relay_member_observations(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace_root = tmp_path / "AI_Camp_RNA_2026"
    workspace_root.mkdir()
    store = AgentWorkspaceStore(codex_home)
    workspace = store.ensure_default_workspace(root_path=workspace_root)
    channel = store.list_channels(workspace.workspace_id)[0]

    called = False

    def forbidden_relay(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("workspace_payload must not use direct relay")

    monkeypatch.setattr(
        api,
        "relay_runtime_member_observations",
        forbidden_relay,
        raising=False,
    )

    payload = api.workspace_payload(codex_home, workspace.workspace_id)

    assert payload["status"] == "ok"
    assert called is False
```

If `relay_runtime_member_observations` is removed from `api.py`, adapt this test to assert the attribute is absent:

```python
assert not hasattr(api, "relay_runtime_member_observations")
```

- [ ] **Step 6.2: Run full workspace unit tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest --import-mode=importlib tests/unit/features/supervisor/agent_group/workspace -q
```

Expected: all workspace unit tests pass.

- [ ] **Step 6.3: Run wider agent-group unit tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest --import-mode=importlib tests/unit/features/supervisor/agent_group tests/unit/agents/loop/test_agent_loop_conversation_arbiter.py -q
```

Expected: all listed tests pass.

- [ ] **Step 6.4: Run dev-eval changed surface gate**

Run:

```bash
scripts/dev-eval changed_surface --base origin/main --json
```

Expected: If `eval_required=false`, record that in final reporting. If `eval_required=true`, run the `recommended_command` exactly and inspect the generated reviewer prompts before final reporting.

- [ ] **Step 6.5: Document legacy direct relay removal criteria in the spec**

In `docs/superpowers/specs/2026-06-12-agent-group-codex-chat-design.md`, under `Migration stance`, add:

```markdown
Legacy direct relay removal criteria:

- `workspace_payload(...)` no longer imports or calls
  `relay_runtime_member_observations(...)`.
- Selected public Codex replies are delivered through member inbox records.
- A regression test fails if workspace payload reintroduces direct relay.
- The frontend reads public messages and inbox/turn metadata from the migrated
  projection.
```

- [ ] **Step 6.6: Run markdown and status checks**

Run:

```bash
git diff --check
git status --short --branch
```

Expected: `git diff --check` exits 0; status shows only intended files.

- [ ] **Step 6.7: Commit regression and docs**

Run:

```bash
git add docs/superpowers/specs/2026-06-12-agent-group-codex-chat-design.md tests/unit/features/supervisor/agent_group/workspace/test_api.py
git commit -m "test(supervisor): guard codex group relay migration"
```

---

## Final Verification

- [ ] **Step 7.1: Run final targeted verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest --import-mode=importlib tests/unit/features/supervisor/agent_group/workspace tests/unit/features/supervisor/agent_group tests/unit/agents/loop/test_agent_loop_conversation_arbiter.py -q
scripts/dev-eval changed_surface --base origin/main --json
```

Expected:

- pytest exits 0.
- dev-eval either reports `eval_required=false` or the recommended smoke command has been run and reviewed.

- [ ] **Step 7.2: Inspect commit history**

Run:

```bash
git log --oneline --decorate -8
git status --short --branch
```

Expected:

- The feature branch has the task commits from this plan.
- Worktree is clean.

- [ ] **Step 7.3: Report implementation status**

Final report must include:

- What changed.
- Which old direct relay behavior is no longer used by the new path.
- Which tests passed.
- Whether dev-eval was required.
- Any remaining frontend work.
