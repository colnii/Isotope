"""Dispatch workspace channel messages to connected Codex sessions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from isotope.features.supervisor.registry import resume_managed_codex

from .contracts import (
    MAX_MEMBER_OBSERVATION_RELAY_DEPTH,
    TRIGGER_KIND_MEMBER_OBSERVATION_RELAY,
    TRIGGER_KIND_USER_MESSAGE,
    AgentWorkspace,
    ChannelMembership,
    WorkspaceConversationMessage,
    relay_depth_from_payload,
)
from .importer import mark_member_reply_import_baseline
from .runtime_bridge import (
    recent_runtime_group_messages,
    sync_channel_runtime_group,
    workspace_message_has_runtime_group,
)
from .store import AgentWorkspaceStore


def dispatch_channel_message(
    *,
    store: AgentWorkspaceStore,
    state_root: Path | str,
    workspace: AgentWorkspace,
    channel_id: str,
    user_message: str,
    mode: str,
) -> list[dict[str, Any]]:
    sync_channel_runtime_group(
        store=store,
        state_root=state_root,
        workspace=workspace,
        channel_id=channel_id,
    )
    context_messages = recent_runtime_group_messages(
        store=store,
        state_root=state_root,
        workspace=workspace,
        channel_id=channel_id,
    )
    dispatches: list[dict[str, Any]] = []
    for member in store.list_channel_members(workspace.workspace_id, channel_id):
        if member.member_kind != "codex_session" or member.status == "terminated":
            continue
        if member.send_policy == "auto":
            dispatches.append(
                _send_to_auto_member(
                    store=store,
                    state_root=state_root,
                    workspace=workspace,
                    channel_id=channel_id,
                    member=member,
                    trigger_actor="用户",
                    trigger_message=user_message,
                    trigger_kind=TRIGGER_KIND_USER_MESSAGE,
                    mode=mode,
                    context_messages=context_messages,
                    relay_depth=0,
                )
            )
        else:
            dispatches.append(
                _surface_member_draft(
                    store=store,
                    workspace=workspace,
                    channel_id=channel_id,
                    member=member,
                    trigger_actor="用户",
                    trigger_message=user_message,
                    trigger_kind=TRIGGER_KIND_USER_MESSAGE,
                    mode=mode,
                    context_messages=context_messages,
                    relay_depth=0,
                )
            )
    return dispatches


def relay_runtime_member_observations(
    *,
    store: AgentWorkspaceStore,
    state_root: Path | str,
    workspace: AgentWorkspace,
    channel_id: str,
) -> list[dict[str, Any]]:
    sync_channel_runtime_group(
        store=store,
        state_root=state_root,
        workspace=workspace,
        channel_id=channel_id,
    )
    relays: list[dict[str, Any]] = []
    messages = store.list_messages(
        workspace.workspace_id,
        "channel",
        channel_id,
        limit=1000,
    )
    members = store.list_channel_members(workspace.workspace_id, channel_id)
    member_names = {member.member_id: member.display_name for member in members}
    context_messages = recent_runtime_group_messages(
        store=store,
        state_root=state_root,
        workspace=workspace,
        channel_id=channel_id,
    )
    for message in messages:
        if message.message_type != "member_observation":
            continue
        if not workspace_message_has_runtime_group(message):
            continue
        if not _member_observation_can_relay(message):
            continue
        source_member_id = message.from_actor
        source_name = member_names.get(source_member_id, source_member_id)
        relay_depth = relay_depth_from_payload(message.payload) + 1
        for member in members:
            if (
                member.member_id == source_member_id
                or member.member_kind != "codex_session"
                or member.status == "terminated"
            ):
                continue
            if _relay_already_sent(
                messages,
                source_message_id=message.message_id,
                target_member_id=member.member_id,
            ):
                continue
            if member.send_policy == "auto":
                relays.append(
                    _send_to_auto_member(
                        store=store,
                        state_root=state_root,
                        workspace=workspace,
                        channel_id=channel_id,
                        member=member,
                        trigger_actor=source_name,
                        trigger_message=message.summary,
                        trigger_kind=TRIGGER_KIND_MEMBER_OBSERVATION_RELAY,
                        mode="queue",
                        context_messages=context_messages,
                        relay_source_message_id=message.message_id,
                        relay_depth=relay_depth,
                    )
                )
            else:
                relays.append(
                    _surface_member_draft(
                        store=store,
                        workspace=workspace,
                        channel_id=channel_id,
                        member=member,
                        trigger_actor=source_name,
                        trigger_message=message.summary,
                        trigger_kind=TRIGGER_KIND_MEMBER_OBSERVATION_RELAY,
                        mode="queue",
                        context_messages=context_messages,
                        relay_source_message_id=message.message_id,
                        relay_depth=relay_depth,
                    )
                )
            messages = store.list_messages(
                workspace.workspace_id,
                "channel",
                channel_id,
                limit=1000,
            )
    return relays


def _send_to_auto_member(
    *,
    store: AgentWorkspaceStore,
    state_root: Path | str,
    workspace: AgentWorkspace,
    channel_id: str,
    member: ChannelMembership,
    trigger_actor: str,
    trigger_message: str,
    trigger_kind: str,
    mode: str,
    context_messages: list[dict[str, str]],
    relay_source_message_id: str | None = None,
    relay_depth: int = 0,
) -> dict[str, Any]:
    if not member.resume_session_id:
        return _surface_send_error(
            store=store,
            workspace=workspace,
            channel_id=channel_id,
            member=member,
            summary=f"{member.display_name} 缺少 Codex session，无法发送。",
        )
    member = mark_member_reply_import_baseline(
        store=store,
        state_root=state_root,
        member=member,
    )
    try:
        record = resume_managed_codex(
            codex_home=state_root,
            cwd=workspace.root_path,
            name=member.display_name,
            prompt=_member_prompt(
                member,
                trigger_actor=trigger_actor,
                trigger_message=trigger_message,
                mode=mode,
                context_messages=context_messages,
            ),
            session_id=member.resume_session_id,
        )
    except Exception as exc:
        return _surface_send_error(
            store=store,
            workspace=workspace,
            channel_id=channel_id,
            member=member,
            summary=f"发送给 {member.display_name} 失败：{exc}",
        )
    store.update_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel_id,
        member_id=member.member_id,
        status="running",
        managed_record_id=record.record_id,
    )
    store.publish_message(
        workspace_id=workspace.workspace_id,
        conversation_type="channel",
        conversation_id=channel_id,
        from_actor="supervisor",
        to_actor=member.member_id,
        message_type="sent_to_member",
        summary=f"已发送给 {member.display_name}：{_short_summary(trigger_message)}",
        payload={
            "member_id": member.member_id,
            "send_policy": member.send_policy,
            "status": "sent",
            "managed_record_id": record.record_id,
            "resume_session_id": member.resume_session_id,
            "trigger_kind": trigger_kind,
            "relay_depth": relay_depth,
            **(
                {"relay_source_message_id": relay_source_message_id}
                if relay_source_message_id
                else {}
            ),
        },
    )
    return _dispatch_result(
        member,
        status="sent",
        managed_record_id=record.record_id,
    )


def _surface_send_error(
    *,
    store: AgentWorkspaceStore,
    workspace: AgentWorkspace,
    channel_id: str,
    member: ChannelMembership,
    summary: str,
) -> dict[str, Any]:
    store.update_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel_id,
        member_id=member.member_id,
        status="blocked",
    )
    store.publish_message(
        workspace_id=workspace.workspace_id,
        conversation_type="channel",
        conversation_id=channel_id,
        from_actor="supervisor",
        to_actor=member.member_id,
        message_type="error",
        summary=summary,
        payload={
            "member_id": member.member_id,
            "send_policy": member.send_policy,
            "status": "error",
        },
    )
    return _dispatch_result(member, status="error", managed_record_id=None)


def _surface_member_draft(
    *,
    store: AgentWorkspaceStore,
    workspace: AgentWorkspace,
    channel_id: str,
    member: ChannelMembership,
    trigger_actor: str,
    trigger_message: str,
    trigger_kind: str,
    mode: str,
    context_messages: list[dict[str, str]],
    relay_source_message_id: str | None = None,
    relay_depth: int = 0,
) -> dict[str, Any]:
    store.update_channel_member(
        workspace_id=workspace.workspace_id,
        channel_id=channel_id,
        member_id=member.member_id,
        status="needs_user",
    )
    store.publish_message(
        workspace_id=workspace.workspace_id,
        conversation_type="channel",
        conversation_id=channel_id,
        from_actor="supervisor",
        to_actor=member.member_id,
        message_type="draft_send",
        summary=f"等待确认发送给 {member.display_name}：{_short_summary(trigger_message)}",
        payload={
            "member_id": member.member_id,
            "send_policy": member.send_policy,
            "status": "draft",
            "mode": mode,
            "resume_session_id": member.resume_session_id,
            "trigger_actor": trigger_actor,
            "trigger_kind": trigger_kind,
            "relay_depth": relay_depth,
            "context_messages": context_messages,
            **(
                {"relay_source_message_id": relay_source_message_id}
                if relay_source_message_id
                else {}
            ),
        },
    )
    return _dispatch_result(member, status="draft", managed_record_id=None)


def _dispatch_result(
    member: ChannelMembership,
    *,
    status: str,
    managed_record_id: str | None,
) -> dict[str, Any]:
    return {
        "member_id": member.member_id,
        "display_name": member.display_name,
        "send_policy": member.send_policy,
        "status": status,
        "managed_record_id": managed_record_id,
        "resume_session_id": member.resume_session_id,
    }


def _member_prompt(
    member: ChannelMembership,
    *,
    trigger_actor: str,
    trigger_message: str,
    mode: str,
    context_messages: list[dict[str, str]],
) -> str:
    role = member.role.strip() or "Codex 会话成员"
    goal = member.goal.strip() or "继续当前会话目标"
    context = _format_context_messages(context_messages)
    return "\n".join(
        [
            f"你正在 Agent Workspace 群聊中以“{member.display_name}”身份工作。",
            f"角色：{role}",
            f"成员目标：{goal}",
            f"发送模式：{mode}",
            "",
            "群聊中新消息：",
            f"{trigger_actor}：{trigger_message.strip()}",
            "",
            "最近群聊消息：",
            context,
            "",
            "如果新消息只是确认、ACK、握手收尾或不需要你推进，请保持沉默，不要为了礼貌再次回复。",
            "请在当前 Codex 会话里理解上述群聊上下文；只有需要回应或推进时才简短回复群聊。",
        ]
    )


def _relay_already_sent(
    messages,
    *,
    source_message_id: str,
    target_member_id: str,
) -> bool:
    for message in messages:
        if message.message_type != "sent_to_member" or message.to_actor != target_member_id:
            continue
        if message.payload.get("relay_source_message_id") == source_message_id:
            return True
    return False


def _member_observation_can_relay(message: WorkspaceConversationMessage) -> bool:
    payload = message.payload
    if payload.get("trigger_kind") == TRIGGER_KIND_MEMBER_OBSERVATION_RELAY:
        return False
    if isinstance(payload.get("reply_to_relay_source_message_id"), str):
        return False
    return relay_depth_from_payload(payload) < MAX_MEMBER_OBSERVATION_RELAY_DEPTH


def _format_context_messages(messages: list[dict[str, str]]) -> str:
    if not messages:
        return "（暂无）"
    return "\n".join(
        f"- {message.get('from', '未知')}：{message.get('summary', '')}"
        for message in messages
    )


def _short_summary(value: str, *, limit: int = 120) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."
