"""Dispatch workspace channel messages to connected Codex sessions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from isotope.features.supervisor.registry import resume_managed_codex

from .contracts import (
    TRIGGER_KIND_USER_MESSAGE,
    AgentWorkspace,
    ChannelMembership,
)
from .coordination.inbox import MemberInboxItem, MemberInboxStore
from .importer import mark_member_reply_import_baseline
from .runtime_bridge import (
    recent_runtime_group_messages,
    sync_channel_runtime_group,
)
from .store import AgentWorkspaceStore


TRIGGER_KIND_MEMBER_INBOX = "member_inbox"


def dispatch_channel_message(
    *,
    store: AgentWorkspaceStore,
    state_root: Path | str,
    workspace: AgentWorkspace,
    channel_id: str,
    source_message_id: str,
    user_message: str,
    mode: str,
) -> list[dict[str, Any]]:
    group_id = sync_channel_runtime_group(
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
                _enqueue_and_maybe_drain_member(
                    store=store,
                    state_root=state_root,
                    workspace=workspace,
                    channel_id=channel_id,
                    member=member,
                    source_message_id=source_message_id,
                    from_actor="用户",
                    summary=user_message,
                    mode=mode,
                    payload={
                        "source": "workspace_user_message",
                        "runtime_group_id": group_id,
                        "mode": mode,
                    },
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
                )
            )
    return dispatches


def drain_channel_member_inboxes(
    *,
    store: AgentWorkspaceStore,
    state_root: Path | str,
    workspace: AgentWorkspace,
    channel_id: str,
    mode: str = "queue",
) -> list[dict[str, Any]]:
    sync_channel_runtime_group(
        store=store,
        state_root=state_root,
        workspace=workspace,
        channel_id=channel_id,
    )
    drains: list[dict[str, Any]] = []
    inbox = MemberInboxStore(state_root)
    for member in store.list_channel_members(workspace.workspace_id, channel_id):
        if (
            member.member_kind != "codex_session"
            or member.send_policy != "auto"
            or member.status == "terminated"
        ):
            continue
        pending = inbox.list_pending(
            workspace.workspace_id,
            channel_id,
            member.member_id,
        )
        if not pending:
            continue
        if member.status == "running" and mode != "interrupt":
            drains.append(
                {
                    **_dispatch_result(
                        member,
                        status="queued",
                        managed_record_id=member.managed_record_id,
                    ),
                    "pending_count": len(pending),
                }
            )
            continue
        drains.append(
            _drain_member_inbox(
                store=store,
                state_root=state_root,
                workspace=workspace,
                channel_id=channel_id,
                member=member,
                mode=mode,
            )
        )
    return drains


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
    pending_count = len(
        inbox.list_pending(workspace.workspace_id, channel_id, member.member_id)
    )
    if member.status == "running" and mode != "interrupt":
        return {
            **_dispatch_result(
                member,
                status="queued",
                managed_record_id=member.managed_record_id,
            ),
            "pending_count": pending_count,
        }
    return _drain_member_inbox(
        store=store,
        state_root=state_root,
        workspace=workspace,
        channel_id=channel_id,
        member=member,
        mode=mode,
    )


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
            **_dispatch_result(
                member,
                status="idle",
                managed_record_id=member.managed_record_id,
            ),
            "pending_count": 0,
        }
    result = _send_to_auto_member(
        store=store,
        state_root=state_root,
        workspace=workspace,
        channel_id=channel_id,
        member=member,
        trigger_actor="群聊",
        trigger_message=_short_summary("; ".join(item.summary for item in pending)),
        trigger_kind=TRIGGER_KIND_MEMBER_INBOX,
        mode=mode,
        context_messages=[],
        prompt_override=_member_inbox_prompt(member, mode=mode, pending=pending),
        delivery_payload={
            "inbox_item_ids": [item.inbox_item_id for item in pending],
            "inbox_source_message_ids": [item.source_message_id for item in pending],
        },
    )
    managed_record_id = result.get("managed_record_id")
    if result.get("status") == "sent" and isinstance(managed_record_id, str):
        inbox.mark_dispatched(
            workspace_id=workspace.workspace_id,
            channel_id=channel_id,
            target_member_id=member.member_id,
            inbox_item_ids=tuple(item.inbox_item_id for item in pending),
            managed_record_id=managed_record_id,
        )
        return {**result, "pending_count": 0}
    return {**result, "pending_count": len(pending)}


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
    prompt_override: str | None = None,
    delivery_payload: dict[str, Any] | None = None,
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
            prompt=(
                prompt_override
                if prompt_override is not None
                else _member_prompt(
                    member,
                    trigger_actor=trigger_actor,
                    trigger_message=trigger_message,
                    mode=mode,
                    context_messages=context_messages,
                )
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
            **(delivery_payload or {}),
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
            "context_messages": context_messages,
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
            "请在当前 Codex 会话里理解上述群聊上下文；只有需要公开回应或推进时才简短回复群聊。",
            "如果需要公开群聊发言，请在回复末尾追加 GROUP_CHAT_INTENT、GROUP_CHAT_SUMMARY、GROUP_CHAT_PRIORITY 标记块。",
        ]
    )


def _member_inbox_prompt(
    member: ChannelMembership,
    *,
    mode: str,
    pending: list[MemberInboxItem],
) -> str:
    role = member.role.strip() or "Codex 会话成员"
    goal = member.goal.strip() or "继续当前会话目标"
    lines = [
        f"你正在 Agent Workspace 群聊中以“{member.display_name}”身份工作。",
        f"角色：{role}",
        f"成员目标：{goal}",
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
            "如果需要公开群聊发言，请在回复末尾追加以下标记块：",
            "GROUP_CHAT_INTENT: respond",
            "GROUP_CHAT_SUMMARY: <给群聊看的简短内容>",
            "GROUP_CHAT_PRIORITY: <0-100>",
            "如果不需要公开发言，不要输出空字符串；正常继续工作即可。",
        ]
    )
    return "\n".join(lines)


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
