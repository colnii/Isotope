"""Memory record conversion helpers for agent workspaces."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from isotope.platform.schemas.memory import MemoryRecord

from .contracts import (
    AgentChannel,
    AgentDirectMessage,
    AgentWorkspace,
    ChannelMembership,
)


WORKSPACE_RECORD_KIND = "agent_workspace"
CHANNEL_RECORD_KIND = "agent_workspace_channel"
DM_RECORD_KIND = "agent_workspace_dm"
MEMBER_RECORD_KIND = "agent_workspace_channel_member"


def record_for_workspace(workspace: AgentWorkspace) -> MemoryRecord:
    return _record(
        record_id=f"agent_workspace_{workspace.workspace_id}",
        kind=WORKSPACE_RECORD_KIND,
        content=workspace.to_public_dict(),
        summary=f"Agent workspace {workspace.title}: {workspace.root_path}",
    )


def record_for_channel(channel: AgentChannel) -> MemoryRecord:
    return _record(
        record_id=f"agent_workspace_channel_{channel.workspace_id}_{channel.channel_id}",
        kind=CHANNEL_RECORD_KIND,
        content=channel.to_public_dict(),
        summary=f"Agent workspace channel #{channel.name}",
    )


def record_for_dm(dm: AgentDirectMessage) -> MemoryRecord:
    return _record(
        record_id=f"agent_workspace_dm_{dm.workspace_id}_{dm.dm_id}",
        kind=DM_RECORD_KIND,
        content=dm.to_public_dict(),
        summary=f"Agent workspace DM {dm.title}",
    )


def record_for_member(member: ChannelMembership) -> MemoryRecord:
    return _record(
        record_id=(
            f"agent_workspace_member_{member.workspace_id}_"
            f"{member.channel_id}_{member.member_id}_{new_id('rev')}"
        ),
        kind=MEMBER_RECORD_KIND,
        content=member.to_public_dict(),
        summary=f"Agent workspace member {member.display_name}: {member.status}",
    )


def workspace_from_record(record: MemoryRecord) -> AgentWorkspace | None:
    try:
        return AgentWorkspace(
            workspace_id=str(record.content["workspace_id"]),
            title=str(record.content["title"]),
            root_path=str(record.content["root_path"]),
            status=str(record.content["status"]),
            created_at=str(record.content["created_at"]),
            updated_at=str(record.content["updated_at"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def channel_from_record(record: MemoryRecord) -> AgentChannel | None:
    try:
        return AgentChannel(
            channel_id=str(record.content["channel_id"]),
            workspace_id=str(record.content["workspace_id"]),
            name=str(record.content["name"]),
            topic=str(record.content.get("topic") or ""),
            status=str(record.content["status"]),
            created_at=str(record.content["created_at"]),
            updated_at=str(record.content["updated_at"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def dm_from_record(record: MemoryRecord) -> AgentDirectMessage | None:
    try:
        return AgentDirectMessage(
            dm_id=str(record.content["dm_id"]),
            workspace_id=str(record.content["workspace_id"]),
            dm_kind=str(record.content["dm_kind"]),
            title=str(record.content["title"]),
            target_member_id=optional_string(record.content.get("target_member_id")),
            status=str(record.content["status"]),
            created_at=str(record.content["created_at"]),
            updated_at=str(record.content["updated_at"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def member_from_record(record: MemoryRecord) -> ChannelMembership | None:
    try:
        return ChannelMembership(
            member_id=str(record.content["member_id"]),
            workspace_id=str(record.content["workspace_id"]),
            channel_id=str(record.content["channel_id"]),
            display_name=str(record.content["display_name"]),
            member_kind=str(record.content["member_kind"]),
            role=str(record.content["role"]),
            goal=str(record.content.get("goal") or ""),
            send_policy=str(record.content["send_policy"]),
            status=str(record.content["status"]),
            resume_session_id=optional_string(record.content.get("resume_session_id")),
            source_path=optional_string(record.content.get("source_path")),
            managed_record_id=optional_string(record.content.get("managed_record_id")),
            transcript_policy=dict(record.content.get("transcript_policy") or {}),
            created_at=str(record.content["created_at"]),
            updated_at=str(record.content["updated_at"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _record(
    *,
    record_id: str,
    kind: str,
    content: dict[str, Any],
    summary: str,
) -> MemoryRecord:
    payload = {"kind": kind, **content}
    return MemoryRecord(
        memory_id=record_id,
        scope="session",
        content=payload,
        summary=summary,
        source_refs=[],
        provenance={
            "run_id": "agent_group_workspace",
            "execution_id": new_id("exec"),
            "action_type": kind,
        },
        created_at=utc_now(),
        supersedes=[],
        quality="agent_group_workspace",
    )
