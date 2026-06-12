"""Endpoint-facing helpers for workspace-based Agent Group Chat."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .dispatcher import dispatch_channel_message
from .dispatcher import drain_channel_member_inboxes
from .coordination.inbox import MemberInboxStore
from .importer import import_channel_member_replies
from .runtime_bridge import (
    publish_workspace_message_to_runtime_group,
    runtime_payload_for_channel,
    sync_channel_runtime_group,
)
from .session_discovery import list_codex_session_candidates
from .store import AgentWorkspaceStore


def ensure_workspace_payload(
    state_root: Path | str,
    *,
    root_path: Path | str,
) -> dict[str, Any]:
    store = AgentWorkspaceStore(state_root)
    workspace = store.ensure_default_workspace(root_path=root_path)
    return workspace_payload(state_root, workspace.workspace_id)


def list_workspaces_payload(
    state_root: Path | str,
    *,
    root_path: Path | str,
) -> dict[str, Any]:
    store = AgentWorkspaceStore(state_root)
    if not store.list_workspaces():
        store.ensure_default_workspace(root_path=root_path)
    return {
        "status": "ok",
        "workspaces": [
            workspace.to_public_dict() for workspace in store.list_workspaces()
        ],
    }


def workspace_payload(state_root: Path | str, workspace_id: str) -> dict[str, Any]:
    return _workspace_payload(
        state_root,
        workspace_id,
        imports=[],
        inbox_drains=[],
    )


def workspace_tick_payload(state_root: Path | str, workspace_id: str) -> dict[str, Any]:
    store = AgentWorkspaceStore(state_root)
    workspace = store.load_workspace(workspace_id)
    channels = store.list_channels(workspace_id)
    imports: list[dict[str, Any]] = []
    inbox_drains: list[dict[str, Any]] = []
    for channel in channels:
        sync_channel_runtime_group(
            store=store,
            state_root=state_root,
            workspace=workspace,
            channel_id=channel.channel_id,
        )
        imports.extend(
            import_channel_member_replies(
                store=store,
                state_root=state_root,
                workspace=workspace,
                channel_id=channel.channel_id,
            )
        )
        inbox_drains.extend(
            drain_channel_member_inboxes(
                store=store,
                state_root=state_root,
                workspace=workspace,
                channel_id=channel.channel_id,
            )
        )
    return _workspace_payload(
        state_root,
        workspace_id,
        imports=imports,
        inbox_drains=inbox_drains,
    )


def _workspace_payload(
    state_root: Path | str,
    workspace_id: str,
    *,
    imports: list[dict[str, Any]],
    inbox_drains: list[dict[str, Any]],
) -> dict[str, Any]:
    store = AgentWorkspaceStore(state_root)
    workspace = store.load_workspace(workspace_id)
    channels = store.list_channels(workspace_id)
    direct_messages = store.list_direct_messages(workspace_id)
    inbox_store = MemberInboxStore(state_root)
    pending_counts: dict[str, int] = {}
    for channel in channels:
        for member_id, count in inbox_store.pending_counts_by_member(
            workspace_id,
            channel.channel_id,
        ).items():
            pending_counts[member_id] = pending_counts.get(member_id, 0) + count
    messages = [
        message.to_public_dict()
        for channel in channels
        for message in store.list_messages(
            workspace_id,
            "channel",
            channel.channel_id,
        )
    ]
    return {
        "status": "ok",
        "workspace": workspace.to_public_dict(),
        "channels": [channel.to_public_dict() for channel in channels],
        "direct_messages": [dm.to_public_dict() for dm in direct_messages],
        "members": [
            member.to_public_dict()
            for channel in channels
            for member in store.list_channel_members(workspace_id, channel.channel_id)
        ],
        "messages": messages,
        "imports": imports,
        "inbox_drains": inbox_drains,
        "inbox": {"pending_counts": pending_counts},
        "relays": [],
        "controls": store.list_control_events(workspace_id),
    }


def update_workspace_payload(
    state_root: Path | str,
    *,
    workspace_id: str,
    title: str,
    root_path: Path | str,
) -> dict[str, Any]:
    store = AgentWorkspaceStore(state_root)
    workspace = store.update_workspace(
        workspace_id=workspace_id,
        title=title,
        root_path=root_path,
    )
    return workspace_payload(state_root, workspace.workspace_id)


def create_channel_payload(
    state_root: Path | str,
    *,
    workspace_id: str,
    name: str,
    topic: str,
) -> dict[str, Any]:
    channel = AgentWorkspaceStore(state_root).create_channel(
        workspace_id=workspace_id,
        name=name,
        topic=topic,
    )
    return {"status": "ok", "channel": channel.to_public_dict()}


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
    store = AgentWorkspaceStore(state_root)
    workspace = store.load_workspace(workspace_id)
    conversation_type = _conversation_type_for(store, workspace_id, conversation_id)
    message_payload: dict[str, Any] = {"mode": mode}
    if conversation_type == "channel":
        message_payload.update(
            runtime_payload_for_channel(
                store=store,
                state_root=state_root,
                workspace=workspace,
                channel_id=conversation_id,
            )
        )
    stored = store.publish_message(
        workspace_id=workspace_id,
        conversation_type=conversation_type,
        conversation_id=conversation_id,
        from_actor="user",
        to_actor=None,
        message_type="user",
        summary=message,
        payload=message_payload,
    )
    dispatches: list[dict[str, Any]] = []
    if conversation_type == "channel":
        publish_workspace_message_to_runtime_group(
            store=store,
            state_root=state_root,
            workspace=workspace,
            channel_id=conversation_id,
            message=stored,
        )
        dispatches = dispatch_channel_message(
            store=store,
            state_root=state_root,
            workspace=workspace,
            channel_id=conversation_id,
            source_message_id=stored.message_id,
            user_message=message,
            mode=mode,
        )
    return {
        "status": "ok",
        "message": stored.to_public_dict(),
        "dispatches": dispatches,
    }


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
    conversation_type = _conversation_type_for(store, workspace_id, conversation_id)
    control = store.record_control(
        workspace_id=workspace_id,
        conversation_type=conversation_type,
        conversation_id=conversation_id,
        intent=intent,
        target=target,
        target_member_id=target_member_id,
        reason=reason,
    )
    if (
        intent == "terminate"
        and target == "member"
        and target_member_id
        and conversation_type == "channel"
    ):
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


def _conversation_type_for(
    store: AgentWorkspaceStore,
    workspace_id: str,
    conversation_id: str,
) -> str:
    if any(channel.channel_id == conversation_id for channel in store.list_channels(workspace_id)):
        return "channel"
    if any(dm.dm_id == conversation_id for dm in store.list_direct_messages(workspace_id)):
        return "dm"
    raise ValueError(f"conversation not found: {conversation_id}")
