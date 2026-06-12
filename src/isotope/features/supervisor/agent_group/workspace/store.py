"""Storage for workspace-based Agent Group Chat."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

from isotope.platform.state.memory_store import FileMemoryStore
from isotope.platform.state.worker_event_channel import (
    list_worker_events,
    publish_worker_event,
)

from .contracts import (
    AgentChannel,
    AgentDirectMessage,
    AgentWorkspace,
    ChannelMembership,
    WorkspaceConversationMessage,
    WorkspaceRuntimeControl,
)
from ._records import (
    CHANNEL_RECORD_KIND,
    DM_RECORD_KIND,
    MEMBER_RECORD_KIND,
    WORKSPACE_RECORD_KIND,
    channel_from_record,
    dm_from_record,
    member_from_record,
    new_id,
    parse_timestamp,
    record_for_channel,
    record_for_dm,
    record_for_member,
    record_for_workspace,
    utc_now,
    workspace_from_record,
)


MESSAGE_EVENT_CHANNEL = "agent-workspace"
CONTROL_EVENT_CHANNEL = "agent-workspace-control"


class AgentWorkspaceStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser()
        self.memory = FileMemoryStore(self.root)

    def ensure_default_workspace(self, *, root_path: Path | str) -> AgentWorkspace:
        existing = self.list_workspaces()
        if existing:
            return existing[0]
        normalized_root = str(Path(root_path).expanduser())
        now = utc_now()
        workspace = AgentWorkspace(
            workspace_id=new_id("workspace"),
            title=Path(normalized_root).name or "Agent Workspace",
            root_path=normalized_root,
            status="active",
            created_at=now,
            updated_at=now,
        )
        self.memory.append_record(record_for_workspace(workspace))
        channel = AgentChannel(
            channel_id=new_id("channel"),
            workspace_id=workspace.workspace_id,
            name="general",
            topic="General agent coordination.",
            status="active",
            created_at=now,
            updated_at=now,
        )
        dm = AgentDirectMessage(
            dm_id=new_id("dm"),
            workspace_id=workspace.workspace_id,
            dm_kind="coordinator",
            title="Coordinator AI",
            target_member_id=None,
            status="active",
            created_at=now,
            updated_at=now,
        )
        self.memory.append_record(record_for_channel(channel))
        self.memory.append_record(record_for_dm(dm))
        return workspace

    def list_workspaces(self) -> list[AgentWorkspace]:
        workspaces = [
            workspace_from_record(record)
            for record in self.memory.list_records(scope="session")
            if record.content.get("kind") == WORKSPACE_RECORD_KIND
        ]
        return sorted(
            [workspace for workspace in workspaces if workspace is not None],
            key=lambda workspace: (workspace.created_at, workspace.workspace_id),
        )

    def load_workspace(self, workspace_id: str) -> AgentWorkspace:
        for workspace in self.list_workspaces():
            if workspace.workspace_id == workspace_id:
                return workspace
        raise ValueError(f"agent workspace not found: {workspace_id}")

    def create_channel(
        self,
        *,
        workspace_id: str,
        name: str,
        topic: str = "",
    ) -> AgentChannel:
        self.load_workspace(workspace_id)
        now = utc_now()
        channel = AgentChannel(
            channel_id=new_id("channel"),
            workspace_id=workspace_id,
            name=name.strip().lstrip("#"),
            topic=topic.strip(),
            status="active",
            created_at=now,
            updated_at=now,
        )
        self.memory.append_record(record_for_channel(channel))
        return channel

    def list_channels(self, workspace_id: str) -> list[AgentChannel]:
        channels = [
            channel_from_record(record)
            for record in self.memory.list_records(scope="session")
            if record.content.get("kind") == CHANNEL_RECORD_KIND
            and record.content.get("workspace_id") == workspace_id
        ]
        return sorted(
            [
                channel
                for channel in channels
                if channel is not None and channel.status != "archived"
            ],
            key=lambda channel: (channel.created_at, channel.channel_id),
        )

    def list_direct_messages(self, workspace_id: str) -> list[AgentDirectMessage]:
        dms = [
            dm_from_record(record)
            for record in self.memory.list_records(scope="session")
            if record.content.get("kind") == DM_RECORD_KIND
            and record.content.get("workspace_id") == workspace_id
        ]
        return sorted(
            [dm for dm in dms if dm is not None and dm.status != "archived"],
            key=lambda dm: (dm.created_at, dm.dm_id),
        )

    def add_channel_member(
        self,
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
    ) -> ChannelMembership:
        self.load_workspace(workspace_id)
        self._load_channel(workspace_id, channel_id)
        if resume_session_id:
            for existing in self.list_channel_members(workspace_id, channel_id):
                if (
                    existing.resume_session_id == resume_session_id
                    and existing.status != "archived"
                ):
                    raise ValueError(
                        f"Codex session already present in channel: {resume_session_id}"
                    )
        now = utc_now()
        member = ChannelMembership(
            member_id=new_id("member"),
            workspace_id=workspace_id,
            channel_id=channel_id,
            display_name=display_name.strip(),
            member_kind="codex_session",
            role=role.strip(),
            goal=goal.strip(),
            send_policy=send_policy,
            status="active",
            resume_session_id=resume_session_id,
            source_path=source_path,
            managed_record_id=managed_record_id,
            transcript_policy={"page_size": 200, "raw_view": True},
            created_at=now,
            updated_at=now,
        )
        self.memory.append_record(record_for_member(member))
        return member

    def update_channel_member(
        self,
        *,
        workspace_id: str,
        channel_id: str,
        member_id: str,
        send_policy: str | None = None,
        status: str | None = None,
        role: str | None = None,
        goal: str | None = None,
    ) -> ChannelMembership:
        member = self._load_member(workspace_id, channel_id, member_id)
        updated = replace(
            member,
            send_policy=send_policy or member.send_policy,
            status=status or member.status,
            role=role or member.role,
            goal=goal if goal is not None else member.goal,
            updated_at=_next_timestamp_after(member.updated_at),
        )
        self.memory.append_record(record_for_member(updated))
        return updated

    def remove_channel_member(
        self,
        *,
        workspace_id: str,
        channel_id: str,
        member_id: str,
    ) -> ChannelMembership:
        return self.update_channel_member(
            workspace_id=workspace_id,
            channel_id=channel_id,
            member_id=member_id,
            status="archived",
        )

    def list_channel_members(
        self,
        workspace_id: str,
        channel_id: str,
    ) -> list[ChannelMembership]:
        latest: dict[str, ChannelMembership] = {}
        for record in self.memory.list_records(scope="session"):
            if (
                record.content.get("kind") != MEMBER_RECORD_KIND
                or record.content.get("workspace_id") != workspace_id
                or record.content.get("channel_id") != channel_id
            ):
                continue
            member = member_from_record(record)
            if member is None:
                continue
            current = latest.get(member.member_id)
            if current is None or _member_sort_key(member) >= _member_sort_key(current):
                latest[member.member_id] = member
        return sorted(
            [member for member in latest.values() if member.status != "archived"],
            key=lambda member: member.member_id,
        )

    def publish_message(
        self,
        *,
        workspace_id: str,
        conversation_type: str,
        conversation_id: str,
        from_actor: str,
        to_actor: str | None,
        message_type: str,
        summary: str,
        payload: dict[str, Any],
    ) -> WorkspaceConversationMessage:
        message = WorkspaceConversationMessage(
            message_id=new_id("msg"),
            workspace_id=workspace_id,
            conversation_type=conversation_type,
            conversation_id=conversation_id,
            from_actor=from_actor,
            to_actor=to_actor,
            message_type=message_type,
            summary=summary,
            payload=dict(payload),
            created_at=utc_now(),
        )
        publish_worker_event(
            root=self.root,
            from_worker=from_actor,
            to_worker=to_actor,
            event_type=message_type,
            channel=MESSAGE_EVENT_CHANNEL,
            message=summary,
            payload=message.to_public_dict(),
        )
        return message

    def list_messages(
        self,
        workspace_id: str,
        conversation_type: str,
        conversation_id: str,
        *,
        limit: int = 100,
    ) -> list[WorkspaceConversationMessage]:
        payload = list_worker_events(
            root=self.root,
            channel=MESSAGE_EVENT_CHANNEL,
            limit=max(limit, 1),
        )
        messages: list[WorkspaceConversationMessage] = []
        for event in payload.get("events") or []:
            if not isinstance(event, dict):
                continue
            raw = event.get("payload")
            if (
                not isinstance(raw, dict)
                or raw.get("workspace_id") != workspace_id
                or raw.get("conversation_type") != conversation_type
                or raw.get("conversation_id") != conversation_id
            ):
                continue
            try:
                messages.append(WorkspaceConversationMessage(**raw))
            except (TypeError, ValueError):
                continue
        return sorted(messages, key=lambda item: (item.created_at, item.message_id))

    def record_control(
        self,
        *,
        workspace_id: str,
        conversation_type: str,
        conversation_id: str,
        intent: str,
        target: str,
        target_member_id: str | None,
        reason: str,
    ) -> WorkspaceRuntimeControl:
        control = WorkspaceRuntimeControl(
            control_id=new_id("control"),
            workspace_id=workspace_id,
            conversation_type=conversation_type,
            conversation_id=conversation_id,
            intent=intent,
            target=target,
            target_member_id=target_member_id,
            reason=reason,
            created_at=utc_now(),
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

    def list_control_events(
        self,
        workspace_id: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        payload = list_worker_events(
            root=self.root,
            channel=CONTROL_EVENT_CHANNEL,
            limit=max(limit, 1),
        )
        events: list[dict[str, Any]] = []
        for event in payload.get("events") or []:
            if not isinstance(event, dict):
                continue
            raw = event.get("payload")
            if isinstance(raw, dict) and raw.get("workspace_id") == workspace_id:
                events.append(event)
        return events

    def _load_channel(self, workspace_id: str, channel_id: str) -> AgentChannel:
        for channel in self.list_channels(workspace_id):
            if channel.channel_id == channel_id:
                return channel
        raise ValueError(f"agent channel not found: {channel_id}")

    def _load_member(
        self,
        workspace_id: str,
        channel_id: str,
        member_id: str,
    ) -> ChannelMembership:
        for member in self.list_channel_members(workspace_id, channel_id):
            if member.member_id == member_id:
                return member
        raise ValueError(f"channel member not found: {member_id}")


def _member_sort_key(member: ChannelMembership):
    return (parse_timestamp(member.updated_at), parse_timestamp(member.created_at))


def _next_timestamp_after(previous: str) -> str:
    now = parse_timestamp(utc_now())
    previous_time = parse_timestamp(previous)
    if now <= previous_time:
        now = previous_time + timedelta(microseconds=1)
    return now.isoformat().replace("+00:00", "Z")
