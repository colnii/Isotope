"""Dispatch workspace channel messages to connected Codex sessions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from isotope.features.supervisor.registry import resume_managed_codex

from .contracts import AgentWorkspace, ChannelMembership
from .importer import mark_member_reply_import_baseline
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
                    user_message=user_message,
                    mode=mode,
                )
            )
        else:
            dispatches.append(
                _surface_member_draft(
                    store=store,
                    workspace=workspace,
                    channel_id=channel_id,
                    member=member,
                    user_message=user_message,
                    mode=mode,
                )
            )
    return dispatches


def _send_to_auto_member(
    *,
    store: AgentWorkspaceStore,
    state_root: Path | str,
    workspace: AgentWorkspace,
    channel_id: str,
    member: ChannelMembership,
    user_message: str,
    mode: str,
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
            prompt=_member_prompt(member, user_message=user_message, mode=mode),
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
        summary=f"已发送给 {member.display_name}：{_short_summary(user_message)}",
        payload={
            "member_id": member.member_id,
            "send_policy": member.send_policy,
            "status": "sent",
            "managed_record_id": record.record_id,
            "resume_session_id": member.resume_session_id,
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
    user_message: str,
    mode: str,
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
        summary=f"等待确认发送给 {member.display_name}：{_short_summary(user_message)}",
        payload={
            "member_id": member.member_id,
            "send_policy": member.send_policy,
            "status": "draft",
            "mode": mode,
            "resume_session_id": member.resume_session_id,
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
    user_message: str,
    mode: str,
) -> str:
    role = member.role.strip() or "Codex 会话成员"
    goal = member.goal.strip() or "继续当前会话目标"
    return "\n".join(
        [
            f"你正在 Agent Workspace 群聊中以“{member.display_name}”身份工作。",
            f"角色：{role}",
            f"成员目标：{goal}",
            f"发送模式：{mode}",
            "",
            "用户在群聊中发来：",
            user_message.strip(),
            "",
            "请在当前 Codex 会话里继续推进，并在需要时用简短进展说明回应群聊。",
        ]
    )


def _short_summary(value: str, *, limit: int = 120) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."
