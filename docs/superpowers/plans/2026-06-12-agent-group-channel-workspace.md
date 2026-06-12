# Agent Group Channel Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a usable desktop Agent Group Chat workspace with channels, direct messages, Codex session selection from `cwd` or `all`, channel-local permissions, readable transcript inspection, and stop controls.

**Architecture:** Add a focused `agent_group.workspace` backend subpackage for workspace/channel/DM records, then expose thin desktop web endpoints. Add a new desktop `agentWorkspace` frontend surface that replaces the fixture-only `AgentGroupWorkspace` path while reusing the existing Codex transcript endpoint and stop semantics.

**Tech Stack:** Python 3.13 dataclasses, `FileMemoryStore`, `worker_event_channel`, local Codex JSONL/session index readers, `http.server` supervisor web routes, Svelte 5, TypeScript, Vitest, pytest.

---

## Execution Setup

Run implementation in an isolated worktree because this is non-trivial Supervisor and desktop work.

- [ ] **Step 1: Create the implementation worktree**

```bash
git fetch origin
git worktree add .worktrees/agent-group-channel-workspace -b feat/agent-group-channel-workspace origin/main
cd .worktrees/agent-group-channel-workspace
```

Expected: `git status --short --branch` shows `## feat/agent-group-channel-workspace...origin/main` with no file changes.

- [ ] **Step 2: Install dependencies if the worktree does not already have them**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[test]"
cd apps/desktop
npm install
cd ../..
```

Expected: commands exit `0`.

- [ ] **Step 3: Keep `web/_impl.py` thin**

Before adding endpoints, check the line count:

```bash
wc -l src/isotope/features/supervisor/web/_impl.py
```

Expected today: about `954`. Do not add helper functions to this file. Add route parsing/API helpers in new modules and only add short dispatch branches in `_DashboardRequestHandler`.

## File Structure

Create these backend files:

- `src/isotope/features/supervisor/agent_group/workspace/__init__.py`: package exports.
- `src/isotope/features/supervisor/agent_group/workspace/contracts.py`: workspace, channel, DM, membership, message, and control dataclasses.
- `src/isotope/features/supervisor/agent_group/workspace/store.py`: `FileMemoryStore` persistence for the workspace model.
- `src/isotope/features/supervisor/agent_group/workspace/session_discovery.py`: `cwd` and `all` recent Codex session picker data.
- `src/isotope/features/supervisor/agent_group/workspace/api.py`: endpoint-facing orchestration helpers.
- `src/isotope/features/supervisor/web/routes/agent_workspaces.py`: path and JSON payload parsing for new endpoints.

Modify these backend files:

- `src/isotope/features/supervisor/web/_impl.py`: import new API and route parser helpers, add thin GET/POST dispatch branches.

Create these backend tests:

- `tests/unit/features/supervisor/agent_group/workspace/test_contracts.py`
- `tests/unit/features/supervisor/agent_group/workspace/test_store.py`
- `tests/unit/features/supervisor/agent_group/workspace/test_session_discovery.py`
- `tests/unit/features/supervisor/web/test_agent_workspace_routes.py`
- `tests/integration/supervisor/desktop/test_agent_workspace_channel_smoke.py`

Create these frontend files under a new directory so `components/agentGroup` does not exceed the file-count rule:

- `apps/desktop/src/lib/contracts/agentWorkspace.ts`
- `apps/desktop/src/lib/client/agentWorkspaceClient.ts`
- `apps/desktop/src/lib/components/agentWorkspace/AgentWorkspaceShell.svelte`
- `apps/desktop/src/lib/components/agentWorkspace/AgentWorkspaceSidebar.svelte`
- `apps/desktop/src/lib/components/agentWorkspace/AgentConversationPane.svelte`
- `apps/desktop/src/lib/components/agentWorkspace/AgentConversationComposer.svelte`
- `apps/desktop/src/lib/components/agentWorkspace/AgentChannelInspector.svelte`
- `apps/desktop/src/lib/components/agentWorkspace/CodexSessionPicker.svelte`
- `apps/desktop/src/lib/components/agentWorkspace/AgentWorkspaceShell.test.ts`
- `apps/desktop/src/lib/components/agentWorkspace/CodexSessionPicker.test.ts`

Modify these frontend files:

- `apps/desktop/src/lib/client/isotopeClient.ts`: expose `agentWorkspaceClient`.
- `apps/desktop/src/routes/+page.svelte`: replace fixture-based Agent Group mode with real workspace shell.

## Task 1: Backend Workspace Contracts

**Files:**
- Create: `src/isotope/features/supervisor/agent_group/workspace/__init__.py`
- Create: `src/isotope/features/supervisor/agent_group/workspace/contracts.py`
- Test: `tests/unit/features/supervisor/agent_group/workspace/test_contracts.py`

- [ ] **Step 1: Write failing contract tests**

Create `tests/unit/features/supervisor/agent_group/workspace/test_contracts.py`:

```python
from __future__ import annotations

import pytest

from isotope.features.supervisor.agent_group.workspace.contracts import (
    AgentChannel,
    AgentDirectMessage,
    AgentWorkspace,
    ChannelMembership,
    WorkspaceConversationMessage,
)


def test_workspace_channel_dm_and_membership_public_shapes():
    workspace = AgentWorkspace(
        workspace_id="workspace_rna",
        title="AI Camp RNA",
        root_path="/home/lumber/Github/AI_Camp_RNA_2026",
        status="active",
        created_at="2026-06-12T00:00:00Z",
        updated_at="2026-06-12T00:00:00Z",
    )
    channel = AgentChannel(
        channel_id="channel_research",
        workspace_id="workspace_rna",
        name="rna-research",
        topic="Research direction",
        status="active",
        created_at="2026-06-12T00:00:00Z",
        updated_at="2026-06-12T00:00:00Z",
    )
    dm = AgentDirectMessage(
        dm_id="dm_coordinator",
        workspace_id="workspace_rna",
        dm_kind="coordinator",
        title="Coordinator AI",
        target_member_id=None,
        status="active",
        created_at="2026-06-12T00:00:00Z",
        updated_at="2026-06-12T00:00:00Z",
    )
    member = ChannelMembership(
        member_id="member_research",
        workspace_id="workspace_rna",
        channel_id="channel_research",
        display_name="Research Codex",
        member_kind="codex_session",
        role="Explore RNA strategy.",
        goal="Find research directions.",
        send_policy="confirm",
        status="active",
        resume_session_id="session_research",
        source_path="/tmp/session_research.jsonl",
        managed_record_id=None,
        transcript_policy={"page_size": 200},
        created_at="2026-06-12T00:00:00Z",
        updated_at="2026-06-12T00:00:00Z",
    )
    message = WorkspaceConversationMessage(
        message_id="msg_1",
        workspace_id="workspace_rna",
        conversation_type="channel",
        conversation_id="channel_research",
        from_actor="user",
        to_actor=None,
        message_type="user",
        summary="把研究进展同步给工程 Codex。",
        payload={"mode": "queue"},
        created_at="2026-06-12T00:00:01Z",
    )

    assert workspace.to_public_dict()["root_path"].endswith("AI_Camp_RNA_2026")
    assert channel.to_public_dict()["name"] == "rna-research"
    assert dm.to_public_dict()["dm_kind"] == "coordinator"
    assert member.to_public_dict()["send_policy"] == "confirm"
    assert message.to_public_dict()["conversation_id"] == "channel_research"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workspace_status", "paused"),
        ("channel_status", "paused"),
        ("dm_kind", "group"),
        ("send_policy", "manual"),
        ("member_status", "stopped"),
        ("conversation_type", "group"),
        ("message_type", "raw_json"),
    ],
)
def test_contracts_reject_invalid_choices(field: str, value: str):
    if field == "workspace_status":
        with pytest.raises(ValueError, match="workspace status"):
            AgentWorkspace("workspace_rna", "RNA", "/tmp/rna", value, "now", "now")
    elif field == "channel_status":
        with pytest.raises(ValueError, match="channel status"):
            AgentChannel("channel_rna", "workspace_rna", "rna", "", value, "now", "now")
    elif field == "dm_kind":
        with pytest.raises(ValueError, match="dm_kind"):
            AgentDirectMessage("dm_1", "workspace_rna", value, "Bad", None, "active", "now", "now")
    elif field == "send_policy":
        with pytest.raises(ValueError, match="send_policy"):
            ChannelMembership(
                "member_1", "workspace_rna", "channel_rna", "Codex", "codex_session",
                "Role", "Goal", value, "active", "session_1", None, None, {}, "now", "now"
            )
    elif field == "member_status":
        with pytest.raises(ValueError, match="member status"):
            ChannelMembership(
                "member_1", "workspace_rna", "channel_rna", "Codex", "codex_session",
                "Role", "Goal", "confirm", value, "session_1", None, None, {}, "now", "now"
            )
    elif field == "conversation_type":
        with pytest.raises(ValueError, match="conversation_type"):
            WorkspaceConversationMessage("msg_1", "workspace_rna", value, "channel_rna", "user", None, "user", "text", {}, "now")
    else:
        with pytest.raises(ValueError, match="message_type"):
            WorkspaceConversationMessage("msg_1", "workspace_rna", "channel", "channel_rna", "user", None, value, "text", {}, "now")


def test_workspace_message_rejects_raw_payload_fields():
    with pytest.raises(ValueError, match="raw workspace payload"):
        WorkspaceConversationMessage(
            message_id="msg_1",
            workspace_id="workspace_rna",
            conversation_type="channel",
            conversation_id="channel_rna",
            from_actor="coordinator",
            to_actor=None,
            message_type="model_reply",
            summary="Public summary",
            payload={"model_prompt": "secret raw prompt"},
            created_at="2026-06-12T00:00:00Z",
        )
```

- [ ] **Step 2: Run contract tests and verify they fail**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/workspace/test_contracts.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'isotope.features.supervisor.agent_group.workspace'`.

- [ ] **Step 3: Add the contracts package**

Create `src/isotope/features/supervisor/agent_group/workspace/__init__.py`:

```python
"""Workspace/channel model for Supervisor Agent Group Chat."""
```

Create `src/isotope/features/supervisor/agent_group/workspace/contracts.py` with these dataclasses and helpers:

```python
"""Contracts for workspace-based Agent Group Chat."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


WORKSPACE_STATUSES = {"active", "archived", "error"}
CHANNEL_STATUSES = {"active", "archived", "error"}
DM_KINDS = {"coordinator", "codex_member"}
MEMBER_KINDS = {"codex_session", "internal_agent", "supervisor"}
SEND_POLICIES = {"auto", "confirm", "draft_only"}
MEMBER_STATUSES = {"active", "running", "idle", "needs_user", "terminated", "blocked", "archived"}
CONVERSATION_TYPES = {"channel", "dm"}
MESSAGE_TYPES = {
    "user",
    "model_reply",
    "private_note",
    "draft_send",
    "sent_to_member",
    "member_observation",
    "runtime_control",
    "status",
    "approval",
    "error",
}
CONTROL_INTENTS = {"queue", "interrupt", "terminate"}
CONTROL_TARGETS = {"current_run", "member"}
RAW_WORKSPACE_FIELDS = {
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
class AgentWorkspace:
    workspace_id: str
    title: str
    root_path: str
    status: str
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        _require_text(self.workspace_id, "workspace_id")
        _require_text(self.title, "title")
        _require_text(self.root_path, "root_path")
        _require_choice(self.status, WORKSPACE_STATUSES, "workspace status")
        _require_text(self.created_at, "created_at")
        _require_text(self.updated_at, "updated_at")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "title": self.title,
            "root_path": self.root_path,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class AgentChannel:
    channel_id: str
    workspace_id: str
    name: str
    topic: str
    status: str
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        _require_text(self.channel_id, "channel_id")
        _require_text(self.workspace_id, "workspace_id")
        _require_text(self.name, "name")
        _require_choice(self.status, CHANNEL_STATUSES, "channel status")
        _require_text(self.created_at, "created_at")
        _require_text(self.updated_at, "updated_at")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "workspace_id": self.workspace_id,
            "name": self.name,
            "topic": self.topic,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class AgentDirectMessage:
    dm_id: str
    workspace_id: str
    dm_kind: str
    title: str
    target_member_id: str | None
    status: str
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        _require_text(self.dm_id, "dm_id")
        _require_text(self.workspace_id, "workspace_id")
        _require_choice(self.dm_kind, DM_KINDS, "dm_kind")
        _require_text(self.title, "title")
        _require_optional_text(self.target_member_id, "target_member_id")
        _require_choice(self.status, CHANNEL_STATUSES, "dm status")
        _require_text(self.created_at, "created_at")
        _require_text(self.updated_at, "updated_at")
        if self.dm_kind == "codex_member" and not self.target_member_id:
            raise ValueError("target_member_id is required for codex_member DM")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "dm_id": self.dm_id,
            "workspace_id": self.workspace_id,
            "dm_kind": self.dm_kind,
            "title": self.title,
            "target_member_id": self.target_member_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ChannelMembership:
    member_id: str
    workspace_id: str
    channel_id: str
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
        _require_text(self.workspace_id, "workspace_id")
        _require_text(self.channel_id, "channel_id")
        _require_text(self.display_name, "display_name")
        _require_choice(self.member_kind, MEMBER_KINDS, "member_kind")
        _require_text(self.role, "role")
        _require_choice(self.send_policy, SEND_POLICIES, "send_policy")
        _require_choice(self.status, MEMBER_STATUSES, "member status")
        _require_optional_text(self.resume_session_id, "resume_session_id")
        _require_optional_text(self.source_path, "source_path")
        _require_optional_text(self.managed_record_id, "managed_record_id")
        if not isinstance(self.transcript_policy, dict):
            raise ValueError("transcript_policy must be a dict")
        _reject_raw_workspace_payload(self.transcript_policy)
        _require_text(self.created_at, "created_at")
        _require_text(self.updated_at, "updated_at")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "member_id": self.member_id,
            "workspace_id": self.workspace_id,
            "channel_id": self.channel_id,
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
class WorkspaceConversationMessage:
    message_id: str
    workspace_id: str
    conversation_type: str
    conversation_id: str
    from_actor: str
    to_actor: str | None
    message_type: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        _require_text(self.message_id, "message_id")
        _require_text(self.workspace_id, "workspace_id")
        _require_choice(self.conversation_type, CONVERSATION_TYPES, "conversation_type")
        _require_text(self.conversation_id, "conversation_id")
        _require_text(self.from_actor, "from_actor")
        _require_optional_text(self.to_actor, "to_actor")
        _require_choice(self.message_type, MESSAGE_TYPES, "message_type")
        _require_text(self.summary, "summary")
        _require_text(self.created_at, "created_at")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dict")
        _reject_raw_workspace_payload(self.payload)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "workspace_id": self.workspace_id,
            "conversation_type": self.conversation_type,
            "conversation_id": self.conversation_id,
            "from_actor": self.from_actor,
            "to_actor": self.to_actor,
            "message_type": self.message_type,
            "summary": self.summary,
            "payload": _copy_public_payload(self.payload),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class WorkspaceRuntimeControl:
    control_id: str
    workspace_id: str
    conversation_type: str
    conversation_id: str
    intent: str
    target: str
    target_member_id: str | None
    reason: str
    created_at: str

    def __post_init__(self) -> None:
        _require_text(self.control_id, "control_id")
        _require_text(self.workspace_id, "workspace_id")
        _require_choice(self.conversation_type, CONVERSATION_TYPES, "conversation_type")
        _require_text(self.conversation_id, "conversation_id")
        _require_choice(self.intent, CONTROL_INTENTS, "control intent")
        _require_choice(self.target, CONTROL_TARGETS, "control target")
        _require_optional_text(self.target_member_id, "target_member_id")
        _require_text(self.reason, "reason")
        _require_text(self.created_at, "created_at")
        if self.target == "member" and not self.target_member_id:
            raise ValueError("target_member_id is required for member target")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "control_id": self.control_id,
            "workspace_id": self.workspace_id,
            "conversation_type": self.conversation_type,
            "conversation_id": self.conversation_id,
            "intent": self.intent,
            "target": self.target,
            "target_member_id": self.target_member_id,
            "reason": self.reason,
            "created_at": self.created_at,
        }


def _require_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_optional_text(value: object, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be null or a non-empty string")


def _require_choice(value: object, choices: set[str], field_name: str) -> None:
    if value not in choices:
        options = ", ".join(sorted(choices))
        raise ValueError(f"{field_name} must be one of: {options}")


def _reject_raw_workspace_payload(value: Any) -> None:
    if isinstance(value, dict):
        if RAW_WORKSPACE_FIELDS.intersection(value):
            raise ValueError("raw workspace payload is not accepted")
        for nested in value.values():
            _reject_raw_workspace_payload(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_raw_workspace_payload(nested)


def _copy_public_payload(value: dict[str, Any]) -> dict[str, Any]:
    _reject_raw_workspace_payload(value)
    return {str(key): _copy_public_value(nested) for key, nested in value.items()}


def _copy_public_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _copy_public_payload(value)
    if isinstance(value, list):
        return [_copy_public_value(item) for item in value]
    return value
```

- [ ] **Step 4: Run contract tests**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/workspace/test_contracts.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 5: Commit contracts**

```bash
git add src/isotope/features/supervisor/agent_group/workspace tests/unit/features/supervisor/agent_group/workspace/test_contracts.py
git commit -m "feat(supervisor): add agent workspace contracts"
```

## Task 2: Backend Workspace Store

**Files:**
- Create: `src/isotope/features/supervisor/agent_group/workspace/store.py`
- Test: `tests/unit/features/supervisor/agent_group/workspace/test_store.py`

- [ ] **Step 1: Write failing store tests**

Create `tests/unit/features/supervisor/agent_group/workspace/test_store.py`:

```python
from __future__ import annotations

import pytest

from isotope.features.supervisor.agent_group.workspace.store import AgentWorkspaceStore


def test_store_creates_default_workspace_channel_and_coordinator_dm(tmp_path):
    root_path = tmp_path / "AI_Camp_RNA_2026"
    root_path.mkdir()
    store = AgentWorkspaceStore(tmp_path / ".codex")

    workspace = store.ensure_default_workspace(root_path=root_path)

    assert workspace.title == "AI_Camp_RNA_2026"
    assert workspace.root_path == str(root_path)
    channels = store.list_channels(workspace.workspace_id)
    dms = store.list_direct_messages(workspace.workspace_id)
    assert [channel.name for channel in channels] == ["general"]
    assert [dm.dm_kind for dm in dms] == ["coordinator"]


def test_store_adds_channel_member_and_rejects_duplicate_session(tmp_path):
    root_path = tmp_path / "repo"
    root_path.mkdir()
    store = AgentWorkspaceStore(tmp_path / ".codex")
    workspace = store.ensure_default_workspace(root_path=root_path)
    channel = store.create_channel(
        workspace_id=workspace.workspace_id,
        name="rna-research",
        topic="Research direction",
    )

    member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="Research Codex",
        role="Explore RNA strategy.",
        goal="Find research directions.",
        send_policy="confirm",
        resume_session_id="session_research",
        source_path="/tmp/session_research.jsonl",
        managed_record_id=None,
    )

    assert member.display_name == "Research Codex"
    assert store.list_channel_members(workspace.workspace_id, channel.channel_id)[0].send_policy == "confirm"
    with pytest.raises(ValueError, match="already present"):
        store.add_channel_member(
            workspace_id=workspace.workspace_id,
            channel_id=channel.channel_id,
            display_name="Research Codex duplicate",
            role="Explore RNA strategy.",
            goal="Find research directions.",
            send_policy="confirm",
            resume_session_id="session_research",
            source_path="/tmp/session_research.jsonl",
            managed_record_id=None,
        )


def test_store_updates_member_permission_and_records_message_and_control(tmp_path):
    root_path = tmp_path / "repo"
    root_path.mkdir()
    store = AgentWorkspaceStore(tmp_path / ".codex")
    workspace = store.ensure_default_workspace(root_path=root_path)
    channel = store.list_channels(workspace.workspace_id)[0]
    member = store.add_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        display_name="Engineering Codex",
        role="Push engineering.",
        goal="Keep implementation moving.",
        send_policy="auto",
        resume_session_id="session_engineering",
        source_path=None,
        managed_record_id="managed_engineering",
    )

    updated = store.update_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel.channel_id,
        member_id=member.member_id,
        send_policy="draft_only",
        status="terminated",
    )
    message = store.publish_message(
        workspace_id=workspace.workspace_id,
        conversation_type="channel",
        conversation_id=channel.channel_id,
        from_actor="user",
        to_actor=None,
        message_type="user",
        summary="Stop engineering lane.",
        payload={"mode": "interrupt"},
    )
    control = store.record_control(
        workspace_id=workspace.workspace_id,
        conversation_type="channel",
        conversation_id=channel.channel_id,
        intent="terminate",
        target="member",
        target_member_id=member.member_id,
        reason="User pressed member Stop.",
    )

    assert updated.send_policy == "draft_only"
    assert updated.status == "terminated"
    assert store.list_messages(workspace.workspace_id, "channel", channel.channel_id)[0].message_id == message.message_id
    assert store.list_control_events(workspace.workspace_id)[0]["payload"]["control_id"] == control.control_id
```

- [ ] **Step 2: Run store tests and verify they fail**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/workspace/test_store.py -q
```

Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `AgentWorkspaceStore`.

- [ ] **Step 3: Implement `AgentWorkspaceStore`**

Create `src/isotope/features/supervisor/agent_group/workspace/store.py`. Use `FileMemoryStore` for durable records and `publish_worker_event` for conversation/control streams.

Core constants and class shape:

```python
WORKSPACE_RECORD_KIND = "agent_workspace"
CHANNEL_RECORD_KIND = "agent_workspace_channel"
DM_RECORD_KIND = "agent_workspace_dm"
MEMBER_RECORD_KIND = "agent_workspace_channel_member"
MESSAGE_EVENT_CHANNEL = "agent-workspace"
CONTROL_EVENT_CHANNEL = "agent-workspace-control"


class AgentWorkspaceStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser()
        self.memory = FileMemoryStore(self.root)
```

Implement these public methods:

```python
def ensure_default_workspace(self, *, root_path: Path | str) -> AgentWorkspace: ...
def list_workspaces(self) -> list[AgentWorkspace]: ...
def load_workspace(self, workspace_id: str) -> AgentWorkspace: ...
def create_channel(self, *, workspace_id: str, name: str, topic: str = "") -> AgentChannel: ...
def list_channels(self, workspace_id: str) -> list[AgentChannel]: ...
def list_direct_messages(self, workspace_id: str) -> list[AgentDirectMessage]: ...
def add_channel_member(... ) -> ChannelMembership: ...
def update_channel_member(... ) -> ChannelMembership: ...
def remove_channel_member(self, *, workspace_id: str, channel_id: str, member_id: str) -> ChannelMembership: ...
def list_channel_members(self, workspace_id: str, channel_id: str) -> list[ChannelMembership]: ...
def publish_message(... ) -> WorkspaceConversationMessage: ...
def list_messages(self, workspace_id: str, conversation_type: str, conversation_id: str, *, limit: int = 100) -> list[WorkspaceConversationMessage]: ...
def record_control(... ) -> WorkspaceRuntimeControl: ...
def list_control_events(self, workspace_id: str, *, limit: int = 50) -> list[dict[str, Any]]: ...
```

Use this default workspace creation behavior:

```python
def ensure_default_workspace(self, *, root_path: Path | str) -> AgentWorkspace:
    existing = self.list_workspaces()
    if existing:
        return existing[0]
    normalized_root = str(Path(root_path).expanduser())
    now = _utc_now()
    workspace = AgentWorkspace(
        workspace_id=_new_id("workspace"),
        title=Path(normalized_root).name or "Agent Workspace",
        root_path=normalized_root,
        status="active",
        created_at=now,
        updated_at=now,
    )
    self.memory.append_record(_record_for_workspace(workspace))
    self.memory.append_record(_record_for_channel(
        AgentChannel(
            channel_id=_new_id("channel"),
            workspace_id=workspace.workspace_id,
            name="general",
            topic="General agent coordination.",
            status="active",
            created_at=now,
            updated_at=now,
        )
    ))
    self.memory.append_record(_record_for_dm(
        AgentDirectMessage(
            dm_id=_new_id("dm"),
            workspace_id=workspace.workspace_id,
            dm_kind="coordinator",
            title="Coordinator AI",
            target_member_id=None,
            status="active",
            created_at=now,
            updated_at=now,
        )
    ))
    return workspace
```

Use this duplicate membership guard inside `add_channel_member`:

```python
if resume_session_id:
    for existing in self.list_channel_members(workspace_id, channel_id):
        if existing.resume_session_id == resume_session_id and existing.status != "archived":
            raise ValueError(f"Codex session already present in channel: {resume_session_id}")
```

Use append-only updates for members:

```python
updated = replace(
    member,
    send_policy=send_policy or member.send_policy,
    status=status or member.status,
    role=role or member.role,
    goal=goal if goal is not None else member.goal,
    updated_at=_next_timestamp_after(member.updated_at),
)
self.memory.append_record(_record_for_member(updated))
return updated
```

- [ ] **Step 4: Run store tests**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/workspace/test_store.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 5: Commit store**

```bash
git add src/isotope/features/supervisor/agent_group/workspace/store.py tests/unit/features/supervisor/agent_group/workspace/test_store.py
git commit -m "feat(supervisor): persist agent workspace channels"
```

## Task 3: Codex Recent Session Discovery

**Files:**
- Create: `src/isotope/features/supervisor/agent_group/workspace/session_discovery.py`
- Test: `tests/unit/features/supervisor/agent_group/workspace/test_session_discovery.py`

- [ ] **Step 1: Write failing session discovery tests**

Create `tests/unit/features/supervisor/agent_group/workspace/test_session_discovery.py`:

```python
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from isotope.features.supervisor.agent_group.workspace.session_discovery import (
    list_codex_session_candidates,
)


def test_lists_cwd_scoped_recent_sessions(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "AI_Camp_RNA_2026"
    workspace.mkdir()
    matching = "019e-rna"
    unrelated = "019e-other"
    _write_session(codex_home, matching, str(workspace / "round2"), "research update")
    _write_session(codex_home, unrelated, str(tmp_path / "other"), "other update")
    _write_session_index(codex_home, [unrelated, matching])
    _write_state_threads(codex_home, [(matching, "RNA Research", 1_768_999_999)])

    payload = list_codex_session_candidates(
        codex_home=codex_home,
        scope="cwd",
        workspace_root=workspace,
        limit=10,
    )

    assert payload["status"] == "ok"
    assert [item["session_id"] for item in payload["sessions"]] == [matching]
    assert payload["sessions"][0]["title"] == "RNA Research"
    assert payload["sessions"][0]["preview"] == ["research update"]


def test_lists_all_recent_sessions_without_workspace_filter(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "AI_Camp_RNA_2026"
    workspace.mkdir()
    matching = "019e-rna"
    unrelated = "019e-other"
    _write_session(codex_home, matching, str(workspace), "research update")
    _write_session(codex_home, unrelated, str(tmp_path / "other"), "other update")
    _write_session_index(codex_home, [unrelated, matching])

    payload = list_codex_session_candidates(
        codex_home=codex_home,
        scope="all",
        workspace_root=workspace,
        limit=10,
    )

    assert [item["session_id"] for item in payload["sessions"]] == [unrelated, matching]


def test_rejects_invalid_scope(tmp_path):
    payload = list_codex_session_candidates(
        codex_home=tmp_path / ".codex",
        scope="project",
        workspace_root=tmp_path,
        limit=10,
    )

    assert payload["status"] == "error"
    assert payload["error"]["message"] == "scope must be cwd or all"


def _write_session(codex_home: Path, session_id: str, cwd: str, text: str) -> None:
    path = codex_home / "sessions" / "2026" / "06" / "12" / f"rollout-{session_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"type": "session_meta", "timestamp": "2026-06-12T00:00:00Z", "payload": {"id": session_id, "cwd": cwd}},
        {"type": "response_item", "timestamp": "2026-06-12T00:00:01Z", "payload": {"type": "message", "role": "assistant", "content": text}},
    ]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _write_session_index(codex_home: Path, session_ids: list[str]) -> None:
    codex_home.mkdir(parents=True, exist_ok=True)
    rows = [
        {"id": session_id, "thread_name": session_id, "updated_at": f"2026-06-12T00:00:0{index}Z"}
        for index, session_id in enumerate(session_ids)
    ]
    (codex_home / "session_index.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _write_state_threads(codex_home: Path, rows: list[tuple[str, str, int]]) -> None:
    connection = sqlite3.connect(codex_home / "state_5.sqlite")
    try:
        connection.execute("create table threads (id text primary key, title text, updated_at integer)")
        connection.executemany("insert into threads (id, title, updated_at) values (?, ?, ?)", rows)
        connection.commit()
    finally:
        connection.close()
```

- [ ] **Step 2: Run session discovery tests and verify they fail**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/workspace/test_session_discovery.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `session_discovery`.

- [ ] **Step 3: Implement session discovery**

Create `src/isotope/features/supervisor/agent_group/workspace/session_discovery.py`:

```python
"""Recent Codex session discovery for agent workspaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from isotope.integrations.codex.session_reader import (
    find_codex_session_paths,
    merge_recent_session_ids,
    read_codex_session,
    read_codex_session_index,
    read_codex_state_threads,
)


def list_codex_session_candidates(
    *,
    codex_home: Path | str,
    scope: str,
    workspace_root: Path | str,
    limit: int = 50,
) -> dict[str, Any]:
    if scope not in {"cwd", "all"}:
        return {"status": "error", "error": {"message": "scope must be cwd or all"}}
    root = Path(codex_home).expanduser()
    workspace_path = Path(workspace_root).expanduser()
    session_index = read_codex_session_index(root / "session_index.jsonl")
    state_threads = read_codex_state_threads(root / "state_5.sqlite")
    titles = {**session_index.titles, **state_threads.titles}
    recent_ids = merge_recent_session_ids(
        state_threads.recent_session_ids,
        session_index.recent_session_ids,
    )
    candidates: list[dict[str, Any]] = []
    for path in find_codex_session_paths(root, limit=limit, recent_session_ids=recent_ids):
        snapshot = read_codex_session(path)
        if snapshot is None:
            continue
        if scope == "cwd" and not _is_under_workspace(snapshot.cwd, workspace_path):
            continue
        candidates.append(
            {
                "session_id": snapshot.session_id,
                "short_session_id": _short_session_id(snapshot.session_id),
                "title": titles.get(snapshot.session_id) or _latest_thread_name(snapshot) or snapshot.session_id,
                "cwd": snapshot.cwd,
                "source_path": str(snapshot.source_path),
                "source_size_bytes": snapshot.source_size_bytes,
                "last_event_at": snapshot.last_event_at.isoformat() if snapshot.last_event_at else None,
                "preview": [message.text for message in snapshot.messages[-3:]],
            }
        )
        if len(candidates) >= limit:
            break
    return {
        "status": "ok",
        "scope": scope,
        "workspace_root": str(workspace_path),
        "sessions": candidates,
    }


def _is_under_workspace(cwd: str, workspace_root: Path) -> bool:
    if not cwd:
        return False
    try:
        session_path = Path(cwd).expanduser().resolve(strict=False)
        root_path = workspace_root.expanduser().resolve(strict=False)
    except OSError:
        return False
    return session_path == root_path or root_path in session_path.parents


def _latest_thread_name(snapshot: Any) -> str | None:
    if not snapshot.thread_updates:
        return None
    return snapshot.thread_updates[-1].thread_name


def _short_session_id(session_id: str) -> str:
    parts = session_id.split("-")
    return parts[0] if parts and parts[0] else session_id
```

- [ ] **Step 4: Run session discovery tests**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/agent_group/workspace/test_session_discovery.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 5: Commit session discovery**

```bash
git add src/isotope/features/supervisor/agent_group/workspace/session_discovery.py tests/unit/features/supervisor/agent_group/workspace/test_session_discovery.py
git commit -m "feat(supervisor): list recent codex sessions for workspaces"
```

## Task 4: Backend API And Route Helpers

**Files:**
- Create: `src/isotope/features/supervisor/agent_group/workspace/api.py`
- Create: `src/isotope/features/supervisor/web/routes/agent_workspaces.py`
- Test: `tests/unit/features/supervisor/web/test_agent_workspace_routes.py`

- [ ] **Step 1: Write failing route/API tests**

Create `tests/unit/features/supervisor/web/test_agent_workspace_routes.py`:

```python
from __future__ import annotations

import pytest

from isotope.features.supervisor.agent_group.workspace.api import (
    add_channel_member_payload,
    create_channel_payload,
    ensure_workspace_payload,
    remove_channel_member_payload,
    update_channel_member_payload,
)
from isotope.features.supervisor.web.routes.agent_workspaces import (
    agent_workspace_id_from_path,
    channel_members_path_ids,
    conversation_control_path_ids,
    conversation_chat_path_ids,
    parse_channel_member_payload,
    parse_codex_session_scope,
    parse_workspace_chat_payload,
    parse_workspace_channel_payload,
    parse_workspace_control_payload,
    parse_workspace_member_update_payload,
)


def test_route_helpers_parse_workspace_channel_and_conversation_paths():
    assert agent_workspace_id_from_path("/desktop/agent-workspaces/workspace_rna") == "workspace_rna"
    assert channel_members_path_ids(
        "/desktop/agent-workspaces/workspace_rna/channels/channel_research/members"
    ) == ("workspace_rna", "channel_research", None)
    assert channel_members_path_ids(
        "/desktop/agent-workspaces/workspace_rna/channels/channel_research/members/member_research"
    ) == ("workspace_rna", "channel_research", "member_research")
    assert conversation_chat_path_ids(
        "/desktop/agent-workspaces/workspace_rna/conversations/channel_research/chat"
    ) == ("workspace_rna", "channel_research")
    assert conversation_control_path_ids(
        "/desktop/agent-workspaces/workspace_rna/conversations/channel_research/control"
    ) == ("workspace_rna", "channel_research")


def test_parse_codex_session_scope():
    assert parse_codex_session_scope("scope=cwd") == "cwd"
    assert parse_codex_session_scope("scope=all") == "all"
    assert parse_codex_session_scope("") == "cwd"
    with pytest.raises(ValueError, match="scope must be cwd or all"):
        parse_codex_session_scope("scope=project")


def test_parse_channel_member_payload():
    payload = parse_channel_member_payload(
        {
            "display_name": "Research Codex",
            "role": "Explore RNA strategy.",
            "goal": "Find research directions.",
            "send_policy": "confirm",
            "resume_session_id": "session_research",
            "source_path": "/tmp/research.jsonl",
            "managed_record_id": None,
        }
    )

    assert payload["send_policy"] == "confirm"
    assert payload["resume_session_id"] == "session_research"


def test_parse_workspace_chat_payload():
    assert parse_workspace_chat_payload({"message": "sync lanes", "mode": "interrupt"}) == {
        "message": "sync lanes",
        "mode": "interrupt",
    }
    with pytest.raises(ValueError, match="mode must be queue or interrupt"):
        parse_workspace_chat_payload({"message": "sync lanes", "mode": "drop"})


def test_parse_channel_control_and_member_update_payloads():
    assert parse_workspace_channel_payload({"name": "rna-research", "topic": "Research"}) == {
        "name": "rna-research",
        "topic": "Research",
    }
    assert parse_workspace_control_payload(
        {
            "intent": "terminate",
            "target": "member",
            "target_member_id": "member_research",
            "reason": "User pressed Stop.",
        }
    ) == {
        "intent": "terminate",
        "target": "member",
        "target_member_id": "member_research",
        "reason": "User pressed Stop.",
    }
    assert parse_workspace_member_update_payload(
        {"send_policy": "draft_only", "status": "terminated"}
    ) == {
        "send_policy": "draft_only",
        "status": "terminated",
        "role": None,
        "goal": None,
    }


def test_workspace_api_creates_workspace_channel_and_member(tmp_path):
    root_path = tmp_path / "AI_Camp_RNA_2026"
    root_path.mkdir()
    workspace_payload = ensure_workspace_payload(tmp_path / ".codex", root_path=root_path)
    workspace_id = workspace_payload["workspace"]["workspace_id"]
    channel_payload = create_channel_payload(
        tmp_path / ".codex",
        workspace_id=workspace_id,
        name="rna-research",
        topic="Research direction",
    )
    member_payload = add_channel_member_payload(
        tmp_path / ".codex",
        workspace_id=workspace_id,
        channel_id=channel_payload["channel"]["channel_id"],
        display_name="Research Codex",
        role="Explore RNA strategy.",
        goal="Find research directions.",
        send_policy="confirm",
        resume_session_id="session_research",
        source_path=None,
        managed_record_id=None,
    )
    updated_payload = update_channel_member_payload(
        tmp_path / ".codex",
        workspace_id=workspace_id,
        channel_id=channel_payload["channel"]["channel_id"],
        member_id=member_payload["member"]["member_id"],
        send_policy="draft_only",
        status="terminated",
        role=None,
        goal=None,
    )
    removed_payload = remove_channel_member_payload(
        tmp_path / ".codex",
        workspace_id=workspace_id,
        channel_id=channel_payload["channel"]["channel_id"],
        member_id=member_payload["member"]["member_id"],
    )

    assert workspace_payload["status"] == "ok"
    assert channel_payload["channel"]["name"] == "rna-research"
    assert member_payload["member"]["display_name"] == "Research Codex"
    assert updated_payload["member"]["send_policy"] == "draft_only"
    assert removed_payload["member"]["status"] == "archived"
```

- [ ] **Step 2: Run route/API tests and verify they fail**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/web/test_agent_workspace_routes.py -q
```

Expected: FAIL because `agent_workspaces.py` and `workspace/api.py` do not exist.

- [ ] **Step 3: Implement route parsing helpers**

Create `src/isotope/features/supervisor/web/routes/agent_workspaces.py`. Include:

```python
from __future__ import annotations

from urllib.parse import parse_qs, unquote


WORKSPACE_PREFIX = "/desktop/agent-workspaces/"


def agent_workspace_id_from_path(path: str) -> str | None:
    if not path.startswith(WORKSPACE_PREFIX):
        return None
    rest = path[len(WORKSPACE_PREFIX):]
    if "/" in rest or not rest:
        return None
    return unquote(rest)


def channel_members_path_ids(path: str) -> tuple[str, str, str | None] | None:
    return _workspace_nested_ids(path, marker="/channels/", suffix="/members", allow_child=True)


def conversation_chat_path_ids(path: str) -> tuple[str, str] | None:
    parsed = _workspace_nested_ids(path, marker="/conversations/", suffix="/chat", allow_child=False)
    return None if parsed is None else (parsed[0], parsed[1])


def conversation_control_path_ids(path: str) -> tuple[str, str] | None:
    parsed = _workspace_nested_ids(path, marker="/conversations/", suffix="/control", allow_child=False)
    return None if parsed is None else (parsed[0], parsed[1])


def parse_codex_session_scope(query: str) -> str:
    params = parse_qs(query)
    scope = (params.get("scope") or ["cwd"])[0]
    if scope not in {"cwd", "all"}:
        raise ValueError("scope must be cwd or all")
    return scope


def parse_channel_member_payload(value: object) -> dict[str, str | None]:
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    send_policy = _required_string(value.get("send_policy"), "send_policy")
    if send_policy not in {"auto", "confirm", "draft_only"}:
        raise ValueError("send_policy must be auto, confirm, or draft_only")
    return {
        "display_name": _required_string(value.get("display_name"), "display_name"),
        "role": _required_string(value.get("role"), "role"),
        "goal": _optional_string(value.get("goal")) or "",
        "send_policy": send_policy,
        "resume_session_id": _optional_string(value.get("resume_session_id")),
        "source_path": _optional_string(value.get("source_path")),
        "managed_record_id": _optional_string(value.get("managed_record_id")),
    }


def parse_workspace_chat_payload(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    message = _required_string(value.get("message"), "message")
    mode = _required_string(value.get("mode"), "mode")
    if mode not in {"queue", "interrupt"}:
        raise ValueError("mode must be queue or interrupt")
    return {"message": message, "mode": mode}


def parse_workspace_channel_payload(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    return {
        "name": _required_string(value.get("name"), "name"),
        "topic": _optional_string(value.get("topic")) or "",
    }


def parse_workspace_control_payload(value: object) -> dict[str, str | None]:
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    intent = _required_string(value.get("intent"), "intent")
    target = _required_string(value.get("target"), "target")
    if intent not in {"queue", "interrupt", "terminate"}:
        raise ValueError("intent must be queue, interrupt, or terminate")
    if target not in {"current_run", "member"}:
        raise ValueError("target must be current_run or member")
    target_member_id = _optional_string(value.get("target_member_id"))
    if target == "member" and not target_member_id:
        raise ValueError("target_member_id is required for member target")
    return {
        "intent": intent,
        "target": target,
        "target_member_id": target_member_id,
        "reason": _required_string(value.get("reason"), "reason"),
    }


def parse_workspace_member_update_payload(value: object) -> dict[str, str | None]:
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    send_policy = _optional_string(value.get("send_policy"))
    if send_policy is not None and send_policy not in {"auto", "confirm", "draft_only"}:
        raise ValueError("send_policy must be auto, confirm, or draft_only")
    status = _optional_string(value.get("status"))
    if status is not None and status not in {
        "active",
        "running",
        "idle",
        "needs_user",
        "terminated",
        "blocked",
        "archived",
    }:
        raise ValueError("status is not supported")
    return {
        "send_policy": send_policy,
        "status": status,
        "role": _optional_string(value.get("role")),
        "goal": _optional_string(value.get("goal")),
    }
```

Add local helpers in the same file:

```python
def _workspace_nested_ids(
    path: str,
    *,
    marker: str,
    suffix: str,
    allow_child: bool,
) -> tuple[str, str, str | None] | None:
    if not path.startswith(WORKSPACE_PREFIX):
        return None
    rest = path[len(WORKSPACE_PREFIX):]
    if marker not in rest:
        return None
    workspace_id, remainder = rest.split(marker, 1)
    if not workspace_id:
        return None
    if allow_child:
        if remainder.endswith(suffix):
            child = remainder[: -len(suffix)]
            if "/" in child or not child:
                return None
            return (unquote(workspace_id), unquote(child), None)
        marker_with_slash = f"{suffix}/"
        if marker_with_slash not in remainder:
            return None
        parent, child = remainder.split(marker_with_slash, 1)
        if "/" in parent or "/" in child or not parent or not child:
            return None
        return (unquote(workspace_id), unquote(parent), unquote(child))
    if not remainder.endswith(suffix):
        return None
    parent = remainder[: -len(suffix)]
    if "/" in parent or not parent:
        return None
    return (unquote(workspace_id), unquote(parent), None)


def _required_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()
```

- [ ] **Step 4: Implement endpoint-facing API helpers**

Create `src/isotope/features/supervisor/agent_group/workspace/api.py`. Include:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from .session_discovery import list_codex_session_candidates
from .store import AgentWorkspaceStore


def ensure_workspace_payload(state_root: Path | str, *, root_path: Path | str) -> dict[str, Any]:
    store = AgentWorkspaceStore(state_root)
    workspace = store.ensure_default_workspace(root_path=root_path)
    return workspace_payload(state_root, workspace.workspace_id)


def list_workspaces_payload(state_root: Path | str, *, root_path: Path | str) -> dict[str, Any]:
    store = AgentWorkspaceStore(state_root)
    if not store.list_workspaces():
        store.ensure_default_workspace(root_path=root_path)
    return {"status": "ok", "workspaces": [item.to_public_dict() for item in store.list_workspaces()]}


def workspace_payload(state_root: Path | str, workspace_id: str) -> dict[str, Any]:
    store = AgentWorkspaceStore(state_root)
    workspace = store.load_workspace(workspace_id)
    channels = store.list_channels(workspace_id)
    dms = store.list_direct_messages(workspace_id)
    selected_conversation = channels[0].channel_id if channels else (dms[0].dm_id if dms else "")
    messages = (
        store.list_messages(workspace_id, "channel", selected_conversation)
        if selected_conversation and channels
        else []
    )
    return {
        "status": "ok",
        "workspace": workspace.to_public_dict(),
        "channels": [channel.to_public_dict() for channel in channels],
        "direct_messages": [dm.to_public_dict() for dm in dms],
        "members": [
            member.to_public_dict()
            for channel in channels
            for member in store.list_channel_members(workspace_id, channel.channel_id)
        ],
        "messages": [message.to_public_dict() for message in messages],
        "controls": store.list_control_events(workspace_id),
    }


def create_channel_payload(state_root: Path | str, *, workspace_id: str, name: str, topic: str) -> dict[str, Any]:
    channel = AgentWorkspaceStore(state_root).create_channel(
        workspace_id=workspace_id,
        name=name,
        topic=topic,
    )
    return {"status": "ok", "channel": channel.to_public_dict()}
```

Add the remaining helpers in the same file:

```python
def add_channel_member_payload(
    state_root: Path | str,
    *,
    workspace_id: str,
    channel_id: str,
    display_name: str,
    role: str,
    goal: str,
    send_policy: str,
    resume_session_id: str | None,
    source_path: str | None,
    managed_record_id: str | None,
) -> dict[str, Any]:
    member = AgentWorkspaceStore(state_root).add_channel_member(
        workspace_id=workspace_id,
        channel_id=channel_id,
        display_name=display_name,
        role=role,
        goal=goal,
        send_policy=send_policy,
        resume_session_id=resume_session_id,
        source_path=source_path,
        managed_record_id=managed_record_id,
    )
    return {"status": "ok", "member": member.to_public_dict()}


def update_channel_member_payload(
    state_root: Path | str,
    *,
    workspace_id: str,
    channel_id: str,
    member_id: str,
    send_policy: str | None,
    status: str | None,
    role: str | None,
    goal: str | None,
) -> dict[str, Any]:
    member = AgentWorkspaceStore(state_root).update_channel_member(
        workspace_id=workspace_id,
        channel_id=channel_id,
        member_id=member_id,
        send_policy=send_policy,
        status=status,
        role=role,
        goal=goal,
    )
    return {"status": "ok", "member": member.to_public_dict()}


def remove_channel_member_payload(
    state_root: Path | str,
    *,
    workspace_id: str,
    channel_id: str,
    member_id: str,
) -> dict[str, Any]:
    member = AgentWorkspaceStore(state_root).remove_channel_member(
        workspace_id=workspace_id,
        channel_id=channel_id,
        member_id=member_id,
    )
    return {"status": "ok", "member": member.to_public_dict()}


def conversation_chat_payload(
    state_root: Path | str,
    *,
    workspace_id: str,
    conversation_id: str,
    message: str,
    mode: str,
) -> dict[str, Any]:
    stored = AgentWorkspaceStore(state_root).publish_message(
        workspace_id=workspace_id,
        conversation_type="channel",
        conversation_id=conversation_id,
        from_actor="user",
        to_actor=None,
        message_type="user",
        summary=message,
        payload={"mode": mode},
    )
    return {"status": "ok", "message": stored.to_public_dict()}


def conversation_control_payload(
    state_root: Path | str,
    *,
    workspace_id: str,
    conversation_id: str,
    intent: str,
    target: str,
    target_member_id: str | None,
    reason: str,
) -> dict[str, Any]:
    store = AgentWorkspaceStore(state_root)
    control = store.record_control(
        workspace_id=workspace_id,
        conversation_type="channel",
        conversation_id=conversation_id,
        intent=intent,
        target=target,
        target_member_id=target_member_id,
        reason=reason,
    )
    if intent == "terminate" and target == "member" and target_member_id:
        store.update_channel_member(
            workspace_id=workspace_id,
            channel_id=conversation_id,
            member_id=target_member_id,
            send_policy=None,
            status="terminated",
            role=None,
            goal=None,
        )
    return {"status": "ok", "control": control.to_public_dict()}


def codex_sessions_payload(
    state_root: Path | str,
    *,
    workspace_id: str,
    scope: str,
) -> dict[str, Any]:
    workspace = AgentWorkspaceStore(state_root).load_workspace(workspace_id)
    return list_codex_session_candidates(
        codex_home=state_root,
        scope=scope,
        workspace_root=workspace.root_path,
        limit=50,
    )
```

- [ ] **Step 5: Run route/API tests**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/web/test_agent_workspace_routes.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 6: Commit API and route helpers**

```bash
git add src/isotope/features/supervisor/agent_group/workspace/api.py src/isotope/features/supervisor/web/routes/agent_workspaces.py tests/unit/features/supervisor/web/test_agent_workspace_routes.py
git commit -m "feat(supervisor): expose agent workspace API helpers"
```

## Task 5: Desktop Web Server Dispatch

**Files:**
- Modify: `src/isotope/features/supervisor/web/_impl.py`
- Test: `tests/integration/supervisor/desktop/test_agent_workspace_channel_smoke.py`

- [ ] **Step 1: Write failing HTTP smoke test**

Create `tests/integration/supervisor/desktop/test_agent_workspace_channel_smoke.py`:

```python
from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path

from isotope.features.supervisor.web import create_dashboard_server


def test_agent_workspace_http_creates_channel_adds_member_and_stops(tmp_path):
    workspace_root = tmp_path / "AI_Camp_RNA_2026"
    workspace_root.mkdir()
    server = create_dashboard_server(
        codex_home=tmp_path / ".codex",
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        workspaces = _request_json(host, port, "GET", "/desktop/agent-workspaces")
        workspace_id = workspaces["workspaces"][0]["workspace_id"]
        channel = _request_json(
            host,
            port,
            "POST",
            f"/desktop/agent-workspaces/{workspace_id}/channels",
            {"name": "rna-research", "topic": "Research direction"},
        )
        channel_id = channel["channel"]["channel_id"]
        member = _request_json(
            host,
            port,
            "POST",
            f"/desktop/agent-workspaces/{workspace_id}/channels/{channel_id}/members",
            {
                "display_name": "Research Codex",
                "role": "Explore RNA strategy.",
                "goal": "Find research directions.",
                "send_policy": "confirm",
                "resume_session_id": "session_research",
            },
        )
        updated = _request_json(
            host,
            port,
            "POST",
            f"/desktop/agent-workspaces/{workspace_id}/channels/{channel_id}/members/{member['member']['member_id']}",
            {"action": "update", "send_policy": "draft_only"},
        )
        message = _request_json(
            host,
            port,
            "POST",
            f"/desktop/agent-workspaces/{workspace_id}/conversations/{channel_id}/chat",
            {"message": "sync lanes", "mode": "queue"},
        )
        stop = _request_json(
            host,
            port,
            "POST",
            f"/desktop/agent-workspaces/{workspace_id}/conversations/{channel_id}/control",
            {
                "intent": "terminate",
                "target": "member",
                "target_member_id": member["member"]["member_id"],
                "reason": "User pressed member Stop.",
            },
        )
        removed = _request_json(
            host,
            port,
            "POST",
            f"/desktop/agent-workspaces/{workspace_id}/channels/{channel_id}/members/{member['member']['member_id']}",
            {"action": "remove"},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert channel["channel"]["name"] == "rna-research"
    assert member["member"]["send_policy"] == "confirm"
    assert updated["member"]["send_policy"] == "draft_only"
    assert message["message"]["summary"] == "sync lanes"
    assert stop["control"]["target_member_id"] == member["member"]["member_id"]
    assert removed["member"]["status"] == "archived"


def _request_json(host: str, port: int, method: str, path: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"content-type": "application/json"} if payload is not None else {}
    conn = http.client.HTTPConnection(host, port, timeout=5)
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    raw = response.read().decode("utf-8")
    assert response.status < 400, raw
    return json.loads(raw)
```

- [ ] **Step 2: Run HTTP smoke test and verify it fails**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/supervisor/desktop/test_agent_workspace_channel_smoke.py -q
```

Expected: FAIL with HTTP `404` for `/desktop/agent-workspaces`.

- [ ] **Step 3: Add thin dispatch imports in `_impl.py`**

In `src/isotope/features/supervisor/web/_impl.py`, import API helpers:

```python
from ..agent_group.workspace.api import (
    add_channel_member_payload as agent_workspace_add_member_payload,
    codex_sessions_payload as agent_workspace_codex_sessions_payload,
    conversation_chat_payload as agent_workspace_chat_payload,
    conversation_control_payload as agent_workspace_control_payload,
    create_channel_payload as agent_workspace_create_channel_payload,
    list_workspaces_payload as agent_workspace_list_payload,
    remove_channel_member_payload as agent_workspace_remove_member_payload,
    update_channel_member_payload as agent_workspace_update_member_payload,
    workspace_payload as agent_workspace_payload,
)
from .routes.agent_workspaces import (
    agent_workspace_id_from_path,
    channel_members_path_ids,
    conversation_chat_path_ids,
    conversation_control_path_ids,
    parse_channel_member_payload,
    parse_codex_session_scope,
    parse_workspace_chat_payload,
    parse_workspace_control_payload,
    parse_workspace_channel_payload,
)
```

- [ ] **Step 4: Add GET branches**

In `_DashboardRequestHandler.do_GET`, add short branches before existing `/events`:

```python
if path == "/desktop/agent-workspaces":
    self._send_json(
        agent_workspace_list_payload(
            self.server.codex_home,
            root_path=Path.cwd(),
        )
    )
    return
workspace_id = agent_workspace_id_from_path(path)
if workspace_id is not None:
    try:
        payload = agent_workspace_payload(self.server.codex_home, workspace_id)
    except ValueError as exc:
        self._send_json({"status": "error", "error": {"code": "codex_supervisor_web_error", "message": str(exc)}}, status_code=404)
        return
    self._send_json(payload)
    return
```

Add the Codex session list branch:

```python
if path.endswith("/codex-sessions") and path.startswith("/desktop/agent-workspaces/"):
    workspace_id = path.split("/")[3]
    try:
        scope = parse_codex_session_scope(urlparse(self.path).query)
        payload = agent_workspace_codex_sessions_payload(
            self.server.codex_home,
            workspace_id=workspace_id,
            scope=scope,
        )
    except ValueError as exc:
        self._send_json({"status": "error", "error": {"code": "codex_supervisor_web_error", "message": str(exc)}}, status_code=400)
        return
    self._send_json(payload)
    return
```

Keep this branch short. If it becomes more than about 25 lines, move it into a helper module instead of adding more logic to `_impl.py`.

- [ ] **Step 5: Add POST handling**

```python
if path.startswith("/desktop/agent-workspaces/") and path.endswith("/channels"):
    workspace_id = path.split("/")[3]
    payload = parse_workspace_channel_payload(self._read_json_body())
    self._send_json(agent_workspace_create_channel_payload(
        self.server.codex_home,
        workspace_id=workspace_id,
        name=payload["name"],
        topic=payload["topic"],
    ))
    return
member_ids = channel_members_path_ids(path)
if member_ids is not None and member_ids[2] is None:
    workspace_id, channel_id, _ = member_ids
    payload = parse_channel_member_payload(self._read_json_body())
    self._send_json(agent_workspace_add_member_payload(
        self.server.codex_home,
        workspace_id=workspace_id,
        channel_id=channel_id,
        **payload,
    ))
    return
if member_ids is not None and member_ids[2] is not None:
    workspace_id, channel_id, member_id = member_ids
    body = self._read_json_body()
    action = body.get("action") if isinstance(body, dict) else None
    if action == "update":
        payload = parse_workspace_member_update_payload(body)
        self._send_json(agent_workspace_update_member_payload(
            self.server.codex_home,
            workspace_id=workspace_id,
            channel_id=channel_id,
            member_id=member_id,
            send_policy=payload["send_policy"],
            status=payload["status"],
            role=payload["role"],
            goal=payload["goal"],
        ))
        return
    if action == "remove":
        self._send_json(agent_workspace_remove_member_payload(
            self.server.codex_home,
            workspace_id=workspace_id,
            channel_id=channel_id,
            member_id=member_id,
        ))
        return
    self._send_json({"status": "error", "error": {"code": "codex_supervisor_web_error", "message": "member action must be update or remove"}}, status_code=400)
    return
chat_ids = conversation_chat_path_ids(path)
if chat_ids is not None:
    workspace_id, conversation_id = chat_ids
    payload = parse_workspace_chat_payload(self._read_json_body())
    self._send_json(agent_workspace_chat_payload(
        self.server.codex_home,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        message=payload["message"],
        mode=payload["mode"],
    ))
    return
```

Add the control branch:

```python
control_ids = conversation_control_path_ids(path)
if control_ids is not None:
    workspace_id, conversation_id = control_ids
    payload = parse_workspace_control_payload(self._read_json_body())
    self._send_json(agent_workspace_control_payload(
        self.server.codex_home,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        intent=str(payload["intent"]),
        target=str(payload["target"]),
        target_member_id=payload["target_member_id"],
        reason=str(payload["reason"]),
    ))
    return
```

- [ ] **Step 6: Run HTTP smoke test**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/supervisor/desktop/test_agent_workspace_channel_smoke.py -q
```

Expected: test passes.

- [ ] **Step 7: Run focused backend tests from Tasks 1-5**

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/features/supervisor/agent_group/workspace \
  tests/unit/features/supervisor/web/test_agent_workspace_routes.py \
  tests/integration/supervisor/desktop/test_agent_workspace_channel_smoke.py \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit web endpoints**

```bash
git add src/isotope/features/supervisor/web/_impl.py tests/integration/supervisor/desktop/test_agent_workspace_channel_smoke.py
git commit -m "feat(desktop): expose agent workspace endpoints"
```

## Task 6: Frontend Contracts And Client

**Files:**
- Create: `apps/desktop/src/lib/contracts/agentWorkspace.ts`
- Create: `apps/desktop/src/lib/client/agentWorkspaceClient.ts`
- Modify: `apps/desktop/src/lib/client/isotopeClient.ts`
- Test: `apps/desktop/src/lib/client/agentWorkspaceClient.test.ts`

- [ ] **Step 1: Write failing client tests**

Create `apps/desktop/src/lib/client/agentWorkspaceClient.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import { createAgentWorkspaceClient } from './agentWorkspaceClient';

describe('agentWorkspaceClient', () => {
  it('loads workspace list', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: 'ok', workspaces: [] }));
    vi.stubGlobal('fetch', fetchMock);

    const client = createAgentWorkspaceClient('http://localhost:8765');
    await client.listWorkspaces();

    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8765/desktop/agent-workspaces', {
      cache: 'no-store'
    });
  });

  it('adds a channel member', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: 'ok', member: { member_id: 'member_research' } }));
    vi.stubGlobal('fetch', fetchMock);

    const client = createAgentWorkspaceClient('http://localhost:8765');
    await client.addChannelMember('workspace_rna', 'channel_research', {
      display_name: 'Research Codex',
      role: 'Explore RNA strategy.',
      goal: 'Find research directions.',
      send_policy: 'confirm',
      resume_session_id: 'session_research',
      source_path: null,
      managed_record_id: null
    });

    expect(fetchMock.mock.calls[0][0]).toBe(
      'http://localhost:8765/desktop/agent-workspaces/workspace_rna/channels/channel_research/members'
    );
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({
      display_name: 'Research Codex',
      send_policy: 'confirm'
    });
  });

  it('updates and removes a channel member through member action posts', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: 'ok', member: { member_id: 'member_research' } }));
    vi.stubGlobal('fetch', fetchMock);

    const client = createAgentWorkspaceClient('http://localhost:8765');
    await client.updateChannelMember('workspace_rna', 'channel_research', 'member_research', {
      send_policy: 'draft_only'
    });
    await client.removeChannelMember('workspace_rna', 'channel_research', 'member_research');

    expect(fetchMock.mock.calls[0][0]).toBe(
      'http://localhost:8765/desktop/agent-workspaces/workspace_rna/channels/channel_research/members/member_research'
    );
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      action: 'update',
      send_policy: 'draft_only'
    });
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      action: 'remove'
    });
  });

  it('loads cwd scoped codex sessions', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: 'ok', sessions: [] }));
    vi.stubGlobal('fetch', fetchMock);

    const client = createAgentWorkspaceClient('http://localhost:8765');
    await client.listCodexSessions('workspace_rna', 'cwd');

    expect(fetchMock.mock.calls[0][0]).toBe(
      'http://localhost:8765/desktop/agent-workspaces/workspace_rna/codex-sessions?scope=cwd'
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

- [ ] **Step 2: Run client tests and verify they fail**

```bash
cd apps/desktop
npm test -- agentWorkspaceClient.test.ts
cd ../..
```

Expected: FAIL because `agentWorkspaceClient.ts` does not exist.

- [ ] **Step 3: Add TypeScript contracts**

Create `apps/desktop/src/lib/contracts/agentWorkspace.ts` with exported types:

```ts
export type AgentWorkspace = {
  workspace_id: string;
  title: string;
  root_path: string;
  status: 'active' | 'archived' | 'error';
  created_at: string;
  updated_at: string;
};

export type AgentChannel = {
  channel_id: string;
  workspace_id: string;
  name: string;
  topic: string;
  status: 'active' | 'archived' | 'error';
  created_at: string;
  updated_at: string;
};

export type AgentDirectMessage = {
  dm_id: string;
  workspace_id: string;
  dm_kind: 'coordinator' | 'codex_member';
  title: string;
  target_member_id?: string | null;
  status: 'active' | 'archived' | 'error';
  created_at: string;
  updated_at: string;
};

export type ChannelMembership = {
  member_id: string;
  workspace_id: string;
  channel_id: string;
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

export type AgentWorkspaceMessage = {
  message_id: string;
  workspace_id: string;
  conversation_type: 'channel' | 'dm';
  conversation_id: string;
  from_actor: string;
  to_actor?: string | null;
  message_type: string;
  summary: string;
  payload?: Record<string, unknown>;
  created_at: string;
};

export type CodexSessionCandidate = {
  session_id: string;
  short_session_id: string;
  title: string;
  cwd: string;
  source_path: string;
  source_size_bytes?: number | null;
  last_event_at?: string | null;
  preview: string[];
};

export type AgentWorkspaceDetail = {
  status: 'ok';
  workspace: AgentWorkspace;
  channels: AgentChannel[];
  direct_messages: AgentDirectMessage[];
  members: ChannelMembership[];
  messages: AgentWorkspaceMessage[];
  controls: unknown[];
};
```

- [ ] **Step 4: Add client methods**

Create `apps/desktop/src/lib/client/agentWorkspaceClient.ts` with:

```ts
import type { AgentWorkspaceDetail, CodexSessionCandidate } from '../contracts/agentWorkspace';

export type AddChannelMemberRequest = {
  display_name: string;
  role: string;
  goal: string;
  send_policy: 'auto' | 'confirm' | 'draft_only';
  resume_session_id?: string | null;
  source_path?: string | null;
  managed_record_id?: string | null;
};

export type AgentWorkspaceClient = {
  listWorkspaces(): Promise<{ status: 'ok'; workspaces: AgentWorkspaceDetail['workspace'][] }>;
  loadWorkspace(workspaceId: string): Promise<AgentWorkspaceDetail>;
  createChannel(workspaceId: string, request: { name: string; topic: string }): Promise<Record<string, unknown>>;
  listCodexSessions(workspaceId: string, scope: 'cwd' | 'all'): Promise<{ status: 'ok'; sessions: CodexSessionCandidate[] }>;
  addChannelMember(workspaceId: string, channelId: string, request: AddChannelMemberRequest): Promise<Record<string, unknown>>;
  updateChannelMember(
    workspaceId: string,
    channelId: string,
    memberId: string,
    request: { send_policy?: 'auto' | 'confirm' | 'draft_only'; status?: string; role?: string; goal?: string }
  ): Promise<Record<string, unknown>>;
  removeChannelMember(workspaceId: string, channelId: string, memberId: string): Promise<Record<string, unknown>>;
  sendMessage(workspaceId: string, conversationId: string, message: string, mode: 'queue' | 'interrupt'): Promise<Record<string, unknown>>;
  stopCurrentRun(workspaceId: string, conversationId: string): Promise<Record<string, unknown>>;
  stopMember(workspaceId: string, conversationId: string, memberId: string): Promise<Record<string, unknown>>;
};
```

Use the same `normalizeBaseUrl`, `requiredBase`, and `responseErrorMessage` pattern from `agentGroupClient.ts`.

For `updateChannelMember` and `removeChannelMember`, use the member endpoint with action payloads:

```ts
async updateChannelMember(workspaceId, channelId, memberId, request) {
  return postJson(requiredBase(apiBaseUrl), `/desktop/agent-workspaces/${encodeURIComponent(workspaceId)}/channels/${encodeURIComponent(channelId)}/members/${encodeURIComponent(memberId)}`, {
    action: 'update',
    ...request
  });
},
async removeChannelMember(workspaceId, channelId, memberId) {
  return postJson(requiredBase(apiBaseUrl), `/desktop/agent-workspaces/${encodeURIComponent(workspaceId)}/channels/${encodeURIComponent(channelId)}/members/${encodeURIComponent(memberId)}`, {
    action: 'remove'
  });
}
```

Define `postJson` in the same file:

```ts
async function postJson(
  base: string,
  path: string,
  payload: Record<string, unknown>
): Promise<Record<string, unknown>> {
  const response = await fetch(`${base}${path}`, {
    method: 'POST',
    cache: 'no-store',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!response.ok) throw new Error(await responseErrorMessage(response));
  return (await response.json()) as Record<string, unknown>;
}
```

- [ ] **Step 5: Wire `isotopeClient`**

In `apps/desktop/src/lib/client/isotopeClient.ts`, add:

```ts
import { createAgentWorkspaceClient } from './agentWorkspaceClient';
```

And return:

```ts
agentWorkspaceClient: createAgentWorkspaceClient(apiBaseUrl)
```

- [ ] **Step 6: Run client tests**

```bash
cd apps/desktop
npm test -- agentWorkspaceClient.test.ts
cd ../..
```

Expected: all tests in the file pass.

- [ ] **Step 7: Commit frontend client**

```bash
git add apps/desktop/src/lib/contracts/agentWorkspace.ts apps/desktop/src/lib/client/agentWorkspaceClient.ts apps/desktop/src/lib/client/agentWorkspaceClient.test.ts apps/desktop/src/lib/client/isotopeClient.ts
git commit -m "feat(desktop): add agent workspace client"
```

## Task 7: Frontend Workspace Shell And Targeted Composer

**Files:**
- Create: `apps/desktop/src/lib/components/agentWorkspace/AgentWorkspaceShell.svelte`
- Create: `apps/desktop/src/lib/components/agentWorkspace/AgentWorkspaceSidebar.svelte`
- Create: `apps/desktop/src/lib/components/agentWorkspace/AgentConversationPane.svelte`
- Create: `apps/desktop/src/lib/components/agentWorkspace/AgentConversationComposer.svelte`
- Test: `apps/desktop/src/lib/components/agentWorkspace/AgentWorkspaceShell.test.ts`

- [ ] **Step 1: Write failing shell source tests**

Create `apps/desktop/src/lib/components/agentWorkspace/AgentWorkspaceShell.test.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

describe('AgentWorkspaceShell source contract', () => {
  test('has Slack-like channel and DM navigation', () => {
    const sidebar = readSource('AgentWorkspaceSidebar.svelte');
    expect(sidebar).toContain('Channels');
    expect(sidebar).toContain('Direct messages');
    expect(sidebar).toContain('onCreateChannel');
  });

  test('composer names the active target and separates stop from queue interrupt', () => {
    const composer = readSource('AgentConversationComposer.svelte');
    expect(composer).toContain('targetLabel');
    expect(composer).toContain('isRunning && composerIsEmpty');
    expect(composer).toContain('Queue');
    expect(composer).toContain('Interrupt');
    expect(composer).toContain('Stop');
  });
});

function readSource(fileName: string): string {
  return readFileSync(
    join(process.cwd(), 'src/lib/components/agentWorkspace', fileName),
    'utf8'
  );
}
```

- [ ] **Step 2: Run shell tests and verify they fail**

```bash
cd apps/desktop
npm test -- AgentWorkspaceShell.test.ts
cd ../..
```

Expected: FAIL because `components/agentWorkspace` files do not exist.

- [ ] **Step 3: Add sidebar component**

Create `AgentWorkspaceSidebar.svelte`:

```svelte
<script lang="ts">
  import type { AgentChannel, AgentDirectMessage } from '../../contracts/agentWorkspace';

  let {
    workspaceTitle,
    channels,
    directMessages,
    selectedConversationId,
    onSelectConversation,
    onCreateChannel
  } = $props<{
    workspaceTitle: string;
    channels: AgentChannel[];
    directMessages: AgentDirectMessage[];
    selectedConversationId: string;
    onSelectConversation: (conversationType: 'channel' | 'dm', conversationId: string) => void;
    onCreateChannel: () => void;
  }>();
</script>

<aside class="flex min-h-0 w-64 flex-col border-r border-isotope-line bg-isotope-panel">
  <div class="border-b border-isotope-line px-4 py-3">
    <div class="text-sm font-semibold text-isotope-text">{workspaceTitle}</div>
  </div>
  <div class="min-h-0 flex-1 overflow-y-auto px-3 py-3">
    <div class="mb-2 flex items-center justify-between">
      <div class="text-xs font-semibold uppercase text-isotope-muted">Channels</div>
      <button class="border border-isotope-line bg-white px-2 py-1 text-xs font-semibold" type="button" onclick={onCreateChannel}>+</button>
    </div>
    <div class="space-y-1">
      {#each channels as channel (channel.channel_id)}
        <button
          class:selected={selectedConversationId === channel.channel_id}
          class="w-full border border-transparent px-2 py-1.5 text-left text-sm text-isotope-text selected:border-isotope-running selected:bg-white"
          type="button"
          onclick={() => onSelectConversation('channel', channel.channel_id)}
        >
          # {channel.name}
        </button>
      {/each}
    </div>
    <div class="mt-5 mb-2 text-xs font-semibold uppercase text-isotope-muted">Direct messages</div>
    <div class="space-y-1">
      {#each directMessages as dm (dm.dm_id)}
        <button
          class:selected={selectedConversationId === dm.dm_id}
          class="w-full border border-transparent px-2 py-1.5 text-left text-sm text-isotope-text selected:border-isotope-running selected:bg-white"
          type="button"
          onclick={() => onSelectConversation('dm', dm.dm_id)}
        >
          {dm.title}
        </button>
      {/each}
    </div>
  </div>
</aside>
```

- [ ] **Step 4: Add composer component**

Create `AgentConversationComposer.svelte`:

```svelte
<script lang="ts">
  let {
    targetLabel,
    isRunning = false,
    onSend,
    onStop
  } = $props<{
    targetLabel: string;
    isRunning?: boolean;
    onSend: (message: string, mode: 'queue' | 'interrupt') => void;
    onStop: () => void;
  }>();

  let text = $state('');
  const composerIsEmpty = $derived(text.trim().length === 0);

  function submit(mode: 'queue' | 'interrupt') {
    const message = text.trim();
    if (!message) return;
    onSend(message, mode);
    text = '';
  }
</script>

<footer class="border-t border-isotope-line bg-white px-4 py-3">
  <div class="flex gap-2">
    <input
      class="min-w-0 flex-1 border border-isotope-line px-3 py-2 text-sm"
      bind:value={text}
      placeholder={`Message ${targetLabel}`}
    />
    {#if isRunning && composerIsEmpty}
      <button class="border border-isotope-error bg-isotope-error px-4 py-2 text-sm font-semibold text-white" type="button" onclick={onStop}>Stop</button>
    {:else if isRunning}
      <button class="border border-isotope-line bg-white px-4 py-2 text-sm font-semibold" type="button" onclick={() => submit('queue')}>Queue</button>
      <button class="border border-isotope-running bg-isotope-running px-4 py-2 text-sm font-semibold text-white" type="button" onclick={() => submit('interrupt')}>Interrupt</button>
    {:else}
      <button class="border border-isotope-running bg-isotope-running px-4 py-2 text-sm font-semibold text-white" type="button" onclick={() => submit('queue')}>Send</button>
    {/if}
  </div>
</footer>
```

- [ ] **Step 5: Add conversation pane and shell**

Create `AgentConversationPane.svelte` to render header, messages, and composer. Create `AgentWorkspaceShell.svelte` to own selected conversation state and pass callbacks to sidebar/pane.

Minimum `AgentWorkspaceShell.svelte` props:

```ts
workspace: AgentWorkspaceDetail;
isRunning?: boolean;
client: AgentWorkspaceClient;
```

Required state:

```ts
let selectedConversationType = $state<'channel' | 'dm'>('channel');
let selectedConversationId = $state(workspace.channels[0]?.channel_id ?? workspace.direct_messages[0]?.dm_id ?? '');
```

Required target label:

```ts
const selectedTargetLabel = $derived(
  selectedConversationType === 'channel'
    ? `#${workspace.channels.find((item) => item.channel_id === selectedConversationId)?.name ?? 'channel'}`
    : workspace.direct_messages.find((item) => item.dm_id === selectedConversationId)?.title ?? 'direct message'
);
```

- [ ] **Step 6: Run shell tests**

```bash
cd apps/desktop
npm test -- AgentWorkspaceShell.test.ts
cd ../..
```

Expected: all tests in the file pass.

- [ ] **Step 7: Commit workspace shell**

```bash
git add apps/desktop/src/lib/components/agentWorkspace/AgentWorkspace*.svelte apps/desktop/src/lib/components/agentWorkspace/AgentConversation*.svelte apps/desktop/src/lib/components/agentWorkspace/AgentWorkspaceShell.test.ts
git commit -m "feat(desktop): add agent workspace shell"
```

## Task 8: Channel Inspector And Codex Session Picker

**Files:**
- Create: `apps/desktop/src/lib/components/agentWorkspace/AgentChannelInspector.svelte`
- Create: `apps/desktop/src/lib/components/agentWorkspace/CodexSessionPicker.svelte`
- Test: `apps/desktop/src/lib/components/agentWorkspace/CodexSessionPicker.test.ts`
- Modify: `apps/desktop/src/lib/components/agentWorkspace/AgentWorkspaceShell.svelte`

- [ ] **Step 1: Write failing picker source tests**

Create `apps/desktop/src/lib/components/agentWorkspace/CodexSessionPicker.test.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

describe('CodexSessionPicker source contract', () => {
  test('exposes cwd all and manual session entry modes', () => {
    const source = readSource('CodexSessionPicker.svelte');
    expect(source).toContain("'cwd'");
    expect(source).toContain("'all'");
    expect(source).toContain('manualSessionId');
    expect(source).toContain('resume_session_id');
  });

  test('channel inspector exposes member permission and member stop controls', () => {
    const source = readSource('AgentChannelInspector.svelte');
    expect(source).toContain('send_policy');
    expect(source).toContain('Stop');
    expect(source).toContain('onStopMember');
    expect(source).toContain('onUpdateMember');
    expect(source).toContain('onRemoveMember');
  });
});

function readSource(fileName: string): string {
  return readFileSync(
    join(process.cwd(), 'src/lib/components/agentWorkspace', fileName),
    'utf8'
  );
}
```

- [ ] **Step 2: Run picker tests and verify they fail**

```bash
cd apps/desktop
npm test -- CodexSessionPicker.test.ts
cd ../..
```

Expected: FAIL because the picker and inspector files do not exist.

- [ ] **Step 3: Add Codex session picker**

Create `CodexSessionPicker.svelte` with:

```svelte
<script lang="ts">
  import type { AddChannelMemberRequest } from '../../client/agentWorkspaceClient';
  import type { CodexSessionCandidate } from '../../contracts/agentWorkspace';

  let {
    sessions,
    scope,
    onScopeChange,
    onAddMember
  } = $props<{
    sessions: CodexSessionCandidate[];
    scope: 'cwd' | 'all';
    onScopeChange: (scope: 'cwd' | 'all') => void;
    onAddMember: (request: AddChannelMemberRequest) => void;
  }>();

  let manualSessionId = $state('');
  let manualDisplayName = $state('');
  let manualRole = $state('Coordinate this Codex session.');
  let manualGoal = $state('');
  let manualSendPolicy = $state<'auto' | 'confirm' | 'draft_only'>('confirm');

  function addCandidate(candidate: CodexSessionCandidate) {
    onAddMember({
      display_name: candidate.title || candidate.short_session_id,
      role: 'Coordinate this Codex session.',
      goal: '',
      send_policy: 'confirm',
      resume_session_id: candidate.session_id,
      source_path: candidate.source_path,
      managed_record_id: null
    });
  }

  function addManual() {
    const sessionId = manualSessionId.trim();
    if (!sessionId) return;
    onAddMember({
      display_name: manualDisplayName.trim() || sessionId,
      role: manualRole.trim(),
      goal: manualGoal.trim(),
      send_policy: manualSendPolicy,
      resume_session_id: sessionId,
      source_path: null,
      managed_record_id: null
    });
  }
</script>
```

Render `cwd` and `all` buttons, candidate rows with title/cwd/preview, and manual inputs for session id, display name, role, goal, and send policy:

```svelte
<section class="border-t border-isotope-line">
  <div class="flex gap-2 px-3 py-2">
    <button type="button" class:selected={scope === 'cwd'} onclick={() => onScopeChange('cwd')}>cwd</button>
    <button type="button" class:selected={scope === 'all'} onclick={() => onScopeChange('all')}>all</button>
  </div>
  <div class="max-h-56 overflow-y-auto">
    {#each sessions as session (session.session_id)}
      <button class="w-full border-t border-isotope-line px-3 py-2 text-left" type="button" onclick={() => addCandidate(session)}>
        <div class="text-sm font-semibold">{session.title}</div>
        <div class="mt-1 text-xs text-isotope-muted">{session.short_session_id} · {session.cwd}</div>
        {#if session.preview.length > 0}
          <div class="mt-1 break-words text-xs text-isotope-muted">{session.preview.join(' / ')}</div>
        {/if}
      </button>
    {/each}
  </div>
  <div class="space-y-2 border-t border-isotope-line px-3 py-3">
    <input bind:value={manualSessionId} placeholder="session id" />
    <input bind:value={manualDisplayName} placeholder="display name" />
    <input bind:value={manualRole} placeholder="role" />
    <input bind:value={manualGoal} placeholder="goal" />
    <select bind:value={manualSendPolicy}>
      <option value="auto">auto</option>
      <option value="confirm">confirm</option>
      <option value="draft_only">draft_only</option>
    </select>
    <button type="button" onclick={addManual}>Add Codex</button>
  </div>
</section>
```

- [ ] **Step 4: Add channel inspector**

Create `AgentChannelInspector.svelte` with props:

```ts
workspaceId: string;
channelId: string;
members: ChannelMembership[];
sessions: CodexSessionCandidate[];
sessionScope: 'cwd' | 'all';
onScopeChange: (scope: 'cwd' | 'all') => void;
onAddMember: (request: AddChannelMemberRequest) => void;
onUpdateMember: (memberId: string, request: { send_policy?: 'auto' | 'confirm' | 'draft_only' }) => void;
onRemoveMember: (memberId: string) => void;
onStopMember: (memberId: string) => void;
```

Render each member with `display_name`, `resume_session_id`, editable `send_policy`, `status`, a remove button, and a `Stop` button:

```svelte
{#each members as member (member.member_id)}
  <article class="border-b border-isotope-line px-3 py-2">
    <div class="text-sm font-semibold">{member.display_name}</div>
    <div class="mt-1 text-xs text-isotope-muted">{member.resume_session_id}</div>
    <div class="mt-2 flex items-center gap-2">
      <select
        class="border border-isotope-line bg-white px-2 py-1 text-xs"
        value={member.send_policy}
        onchange={(event) => onUpdateMember(member.member_id, { send_policy: event.currentTarget.value as 'auto' | 'confirm' | 'draft_only' })}
      >
        <option value="auto">auto</option>
        <option value="confirm">confirm</option>
        <option value="draft_only">draft_only</option>
      </select>
      <button type="button" class="border border-isotope-line px-2 py-1 text-xs" onclick={() => onRemoveMember(member.member_id)}>
        Remove
      </button>
      <button type="button" class="border border-isotope-error px-2 py-1 text-xs" onclick={() => onStopMember(member.member_id)}>
        Stop
      </button>
    </div>
  </article>
{/each}
```

Include `CodexSessionPicker` below the member list.

- [ ] **Step 5: Wire inspector into shell**

In `AgentWorkspaceShell.svelte`, load session candidates when scope changes:

```ts
let sessionScope = $state<'cwd' | 'all'>('cwd');
let codexSessions = $state<CodexSessionCandidate[]>([]);

async function loadCodexSessions(scope: 'cwd' | 'all') {
  sessionScope = scope;
  const payload = await client.listCodexSessions(workspace.workspace.workspace_id, scope);
  codexSessions = payload.sessions;
}
```

Call `loadCodexSessions('cwd')` in `onMount`.

Wire add and stop:

```ts
async function addMember(request: AddChannelMemberRequest) {
  if (selectedConversationType !== 'channel') return;
  await client.addChannelMember(workspace.workspace.workspace_id, selectedConversationId, request);
}

async function stopMember(memberId: string) {
  await client.stopMember(workspace.workspace.workspace_id, selectedConversationId, memberId);
}

async function updateMember(memberId: string, request: { send_policy?: 'auto' | 'confirm' | 'draft_only' }) {
  if (selectedConversationType !== 'channel') return;
  await client.updateChannelMember(workspace.workspace.workspace_id, selectedConversationId, memberId, request);
}

async function removeMember(memberId: string) {
  if (selectedConversationType !== 'channel') return;
  await client.removeChannelMember(workspace.workspace.workspace_id, selectedConversationId, memberId);
}
```

- [ ] **Step 6: Run picker tests and shell tests**

```bash
cd apps/desktop
npm test -- CodexSessionPicker.test.ts AgentWorkspaceShell.test.ts
cd ../..
```

Expected: selected tests pass.

- [ ] **Step 7: Commit inspector and picker**

```bash
git add apps/desktop/src/lib/components/agentWorkspace/AgentChannelInspector.svelte apps/desktop/src/lib/components/agentWorkspace/CodexSessionPicker.svelte apps/desktop/src/lib/components/agentWorkspace/CodexSessionPicker.test.ts apps/desktop/src/lib/components/agentWorkspace/AgentWorkspaceShell.svelte
git commit -m "feat(desktop): add channel inspector and codex picker"
```

## Task 9: Replace Fixture Entry With Real Workspace Loading

**Files:**
- Modify: `apps/desktop/src/routes/+page.svelte`
- Test: `apps/desktop/src/lib/components/agentWorkspace/AgentWorkspaceShell.test.ts`

- [ ] **Step 1: Extend source test for no fixture dependency**

Append to `AgentWorkspaceShell.test.ts`:

```ts
test('desktop page uses real agent workspace client instead of agent group fixture', () => {
  const page = readFileSync(join(process.cwd(), 'src/routes/+page.svelte'), 'utf8');
  expect(page).toContain('agentWorkspaceClient');
  expect(page).toContain('AgentWorkspaceShell');
  expect(page).not.toContain('agentGroupFixture');
});
```

- [ ] **Step 2: Run test and verify it fails**

```bash
cd apps/desktop
npm test -- AgentWorkspaceShell.test.ts
cd ../..
```

Expected: FAIL because `+page.svelte` still contains `agentGroupFixture`.

- [ ] **Step 3: Update `+page.svelte` imports and state**

Replace `AgentGroupWorkspace` and `AgentGroupDetail` imports with:

```ts
import type { AgentWorkspaceDetail } from '$lib/contracts/agentWorkspace';
import AgentWorkspaceShell from '$lib/components/agentWorkspace/AgentWorkspaceShell.svelte';
```

Remove the `agentGroupFixture` constant. Add state:

```ts
let agentWorkspace = $state<AgentWorkspaceDetail | null>(null);
let agentWorkspaceError = $state<string | null>(null);
```

In `onMount`, after `appState.initialize()`, load workspaces:

```ts
isotopeClient.agentWorkspaceClient
  .listWorkspaces()
  .then(async (payload) => {
    const firstWorkspace = payload.workspaces[0];
    if (!firstWorkspace) return;
    agentWorkspace = await isotopeClient.agentWorkspaceClient.loadWorkspace(firstWorkspace.workspace_id);
  })
  .catch((error: unknown) => {
    agentWorkspaceError = error instanceof Error ? error.message : '加载 Agent Workspace 失败。';
  });
```

- [ ] **Step 4: Replace Agent Group rendering**

For both `surface === 'main'` and dev surface branches, replace:

```svelte
<AgentGroupWorkspace
  group={agentGroupFixture}
  isRunning={false}
  agentGroupClient={isotopeClient.agentGroupClient}
/>
```

With:

```svelte
{#if agentWorkspace}
  <AgentWorkspaceShell
    workspace={agentWorkspace}
    isRunning={false}
    client={isotopeClient.agentWorkspaceClient}
  />
{:else}
  <div class="border border-isotope-line bg-white p-5 text-sm text-isotope-muted">
    {agentWorkspaceError ?? '正在加载 Agent Workspace'}
  </div>
{/if}
```

- [ ] **Step 5: Run source test**

```bash
cd apps/desktop
npm test -- AgentWorkspaceShell.test.ts
cd ../..
```

Expected: selected test passes and confirms no `agentGroupFixture` remains.

- [ ] **Step 6: Commit real entry loading**

```bash
git add apps/desktop/src/routes/+page.svelte apps/desktop/src/lib/components/agentWorkspace/AgentWorkspaceShell.test.ts
git commit -m "feat(desktop): load real agent workspace page"
```

## Task 10: Focused Verification, Dev Eval, And Merge Hygiene

**Files:**
- Test-only updates if verification reveals a missing focused assertion.

- [ ] **Step 1: Run backend focused tests**

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/features/supervisor/agent_group/workspace \
  tests/unit/features/supervisor/web/test_agent_workspace_routes.py \
  tests/integration/supervisor/desktop/test_agent_workspace_channel_smoke.py \
  tests/unit/features/supervisor/agent_group/codex_chat \
  tests/unit/features/supervisor/web/test_agent_group_routes.py \
  tests/integration/supervisor/desktop/test_agent_group_codex_chat_smoke.py \
  -q
```

Expected: all selected backend tests pass.

- [ ] **Step 2: Run frontend focused tests**

```bash
cd apps/desktop
npm test -- agentWorkspaceClient.test.ts AgentWorkspaceShell.test.ts CodexSessionPicker.test.ts agentGroupClient.test.ts
cd ../..
```

Expected: all selected frontend tests pass.

- [ ] **Step 3: Run Svelte type check**

```bash
cd apps/desktop
npm run check
cd ../..
```

Expected: `svelte-check` reports 0 errors.

- [ ] **Step 4: Run changed-surface dev eval gate**

```bash
scripts/dev-eval changed_surface --base origin/main --json
```

Expected: command exits `0`. If the JSON says `"eval_required": true`, run the recommended smoke command shown in `full_command` or `recommended_command`, then read generated `.dev-eval-runs/**/state/dev-evals/reviewer-prompts/*.md` and address hard gates before merging.

- [ ] **Step 5: Inspect final diff**

```bash
git status --short --branch
git diff --stat origin/main...HEAD
git diff --check origin/main...HEAD
```

Expected: only files from this plan are changed; `git diff --check` exits `0`.

- [ ] **Step 6: Commit any final verification fixes**

If Step 1 to Step 5 required changes:

```bash
git add \
  src/isotope/features/supervisor/agent_group/workspace \
  src/isotope/features/supervisor/web/_impl.py \
  src/isotope/features/supervisor/web/routes/agent_workspaces.py \
  tests/unit/features/supervisor/agent_group/workspace \
  tests/unit/features/supervisor/web/test_agent_workspace_routes.py \
  tests/integration/supervisor/desktop/test_agent_workspace_channel_smoke.py \
  apps/desktop/src/lib/contracts/agentWorkspace.ts \
  apps/desktop/src/lib/client/agentWorkspaceClient.ts \
  apps/desktop/src/lib/client/agentWorkspaceClient.test.ts \
  apps/desktop/src/lib/client/isotopeClient.ts \
  apps/desktop/src/lib/components/agentWorkspace \
  apps/desktop/src/routes/+page.svelte
git commit -m "test(desktop): cover agent workspace channel flow"
```

Expected: no uncommitted changes except ignored build artifacts.

- [ ] **Step 7: Rebase and push the feature branch**

```bash
git fetch origin
git rebase origin/main
git push -u origin feat/agent-group-channel-workspace
```

Expected: push succeeds.

- [ ] **Step 8: Merge linearly after review**

After review approval:

```bash
git checkout main
git pull --ff-only origin main
git merge --ff-only feat/agent-group-channel-workspace
git push origin main
```

Expected: fast-forward merge succeeds.

- [ ] **Step 9: Clean worktree and branch**

After `origin/main` contains the feature commit:

```bash
git worktree remove .worktrees/agent-group-channel-workspace
git branch -d feat/agent-group-channel-workspace
git push origin --delete feat/agent-group-channel-workspace
git worktree list
git branch --list 'feat/agent-group-channel-workspace'
git status --short --branch
```

Expected: worktree removed, local feature branch absent, remote feature branch deleted, main worktree clean.

## Self-Review

Spec coverage:

- Workspace/channel/DM model: Tasks 1, 2, 4, 7, and 9.
- `cwd` and `all` Codex session selection: Tasks 3, 4, 6, and 8.
- Manual session id entry: Task 8.
- Channel-local Codex membership and permissions: Tasks 1, 2, 4, 6, and 8.
- Distinct channel versus DM composer target: Tasks 7 and 9.
- Current-run stop and member stop: Tasks 2, 4, 5, 6, 7, and 8.
- High-fidelity transcript reuse: Task 8 reuses the existing transcript panel and Task 10 keeps the existing transcript smoke in scope.
- Backend route exposure: Tasks 4 and 5.
- Frontend entry replacement: Task 9.
- Verification and dev-eval gate: Task 10.

Placeholder scan:

- The plan contains no common placeholder markers or unspecified "add tests" steps.
- Each code-changing task includes a failing test step, implementation step, verification command, and commit command.

Type consistency:

- Backend uses `workspace_id`, `channel_id`, `dm_id`, `member_id`, `conversation_type`, and `conversation_id` consistently across contracts, store, API, routes, and frontend contracts.
- Frontend client methods use the same route ids as backend route helpers.
- Send policy values remain `auto`, `confirm`, and `draft_only`.
