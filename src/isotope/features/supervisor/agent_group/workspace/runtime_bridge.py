"""Bridge Agent Workspace channels into the core AgentGroup runtime ledger."""

from __future__ import annotations

import hashlib
from pathlib import Path

from isotope.features.supervisor.agent_group.contracts import (
    AgentGroupMessage,
    AgentMember,
)
from isotope.features.supervisor.agent_group.store import AgentGroupStore

from .contracts import (
    AgentChannel,
    AgentWorkspace,
    ChannelMembership,
    WorkspaceConversationMessage,
)
from .store import AgentWorkspaceStore


RUNTIME_MESSAGE_LIMIT = 1000
RECENT_CONTEXT_LIMIT = 8


def runtime_group_id(workspace_id: str, channel_id: str) -> str:
    digest = hashlib.sha1(f"{workspace_id}:{channel_id}".encode("utf-8")).hexdigest()
    return f"group_workspace_{digest[:12]}"


def sync_channel_runtime_group(
    *,
    store: AgentWorkspaceStore,
    state_root: Path | str,
    workspace: AgentWorkspace,
    channel_id: str,
) -> str:
    channel = _load_channel(store, workspace.workspace_id, channel_id)
    group_id = runtime_group_id(workspace.workspace_id, channel_id)
    group_store = AgentGroupStore(state_root)
    group_store.ensure_group(
        group_id=group_id,
        title=f"{workspace.title} / {channel.name}",
        goal=channel.topic.strip() or f"Coordinate workspace channel {channel.name}.",
        initial_message=f"Agent Workspace channel #{channel.name} connected.",
    )
    for member in store.list_channel_members(workspace.workspace_id, channel_id):
        if member.member_kind != "codex_session" or member.status == "archived":
            continue
        group_store.ensure_member(_runtime_member(group_id, member))
    return group_id


def publish_workspace_message_to_runtime_group(
    *,
    store: AgentWorkspaceStore,
    state_root: Path | str,
    workspace: AgentWorkspace,
    channel_id: str,
    message: WorkspaceConversationMessage,
) -> AgentGroupMessage | None:
    if message.conversation_type != "channel":
        return None
    if message.message_type not in {"user", "member_observation"}:
        return None
    group_id = sync_channel_runtime_group(
        store=store,
        state_root=state_root,
        workspace=workspace,
        channel_id=channel_id,
    )
    source_key = _workspace_message_source_key(message)
    group_store = AgentGroupStore(state_root)
    for existing in group_store.list_group_messages(group_id, limit=RUNTIME_MESSAGE_LIMIT):
        if existing.payload.get("workspace_source_key") == source_key:
            return existing
    return group_store.publish_message(
        group_id=group_id,
        turn_id="turn_workspace",
        from_member=_runtime_from_member(message),
        to_member=None,
        message_type=_runtime_message_type(message),
        summary=message.summary,
        payload={
            "source": "agent_workspace",
            "workspace_id": workspace.workspace_id,
            "channel_id": channel_id,
            "workspace_message_id": message.message_id,
            "workspace_message_type": message.message_type,
            "workspace_source_key": source_key,
        },
    )


def recent_runtime_group_messages(
    *,
    store: AgentWorkspaceStore,
    state_root: Path | str,
    workspace: AgentWorkspace,
    channel_id: str,
    limit: int = RECENT_CONTEXT_LIMIT,
) -> list[dict[str, str]]:
    group_id = sync_channel_runtime_group(
        store=store,
        state_root=state_root,
        workspace=workspace,
        channel_id=channel_id,
    )
    display_names = {
        member.member_id: member.display_name
        for member in store.list_channel_members(workspace.workspace_id, channel_id)
    }
    messages = AgentGroupStore(state_root).list_group_messages(
        group_id,
        limit=RUNTIME_MESSAGE_LIMIT,
    )
    return [
        {
            "from": _display_name(message.from_member, display_names),
            "message_type": message.message_type,
            "summary": message.summary,
        }
        for message in messages[-limit:]
        if message.message_type in {"task", "reply", "question", "observation"}
    ]


def workspace_message_has_runtime_group(message: WorkspaceConversationMessage) -> bool:
    return isinstance(message.payload.get("runtime_group_id"), str)


def runtime_payload_for_channel(
    *,
    store: AgentWorkspaceStore,
    state_root: Path | str,
    workspace: AgentWorkspace,
    channel_id: str,
) -> dict[str, str]:
    group_id = sync_channel_runtime_group(
        store=store,
        state_root=state_root,
        workspace=workspace,
        channel_id=channel_id,
    )
    return {"runtime_group_id": group_id}


def _load_channel(
    store: AgentWorkspaceStore,
    workspace_id: str,
    channel_id: str,
) -> AgentChannel:
    for channel in store.list_channels(workspace_id):
        if channel.channel_id == channel_id:
            return channel
    raise ValueError(f"agent channel not found: {channel_id}")


def _runtime_member(group_id: str, member: ChannelMembership) -> AgentMember:
    return AgentMember(
        member_id=member.member_id,
        group_id=group_id,
        name=member.display_name,
        role=member.role,
        goal=member.goal or member.role,
        model_profile="codex_session",
        allowed_capabilities=(),
        status=_runtime_member_status(member.status),
    )


def _runtime_member_status(workspace_status: str) -> str:
    if workspace_status == "terminated":
        return "done"
    if workspace_status == "blocked":
        return "blocked"
    return "active"


def _runtime_from_member(message: WorkspaceConversationMessage) -> str:
    if message.message_type == "user":
        return "supervisor"
    return message.from_actor


def _runtime_message_type(message: WorkspaceConversationMessage) -> str:
    if message.message_type == "user":
        return "task"
    return "reply"


def _workspace_message_source_key(message: WorkspaceConversationMessage) -> str:
    if message.message_type != "member_observation":
        return f"workspace_message:{message.message_id}"
    payload = message.payload
    transcript_ref = payload.get("transcript_ref")
    if isinstance(transcript_ref, dict):
        session_id = payload.get("resume_session_id") or transcript_ref.get("session_id")
        event_index = payload.get("event_index", transcript_ref.get("event_index"))
        if isinstance(session_id, str) and event_index is not None:
            return f"codex_transcript:{message.from_actor}:{session_id}:{event_index}"
    return f"workspace_message:{message.message_id}"


def _display_name(member_id: str, display_names: dict[str, str]) -> str:
    if member_id == "supervisor":
        return "用户"
    return display_names.get(member_id, member_id)
