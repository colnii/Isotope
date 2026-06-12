"""Import Codex member replies back into workspace channel conversations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from isotope.features.supervisor.registry.session_lookup import (
    find_codex_session_snapshot,
)
from isotope.integrations.codex.transcript import read_codex_transcript_page

from .contracts import AgentWorkspace, ChannelMembership
from .store import AgentWorkspaceStore


LAST_IMPORTED_EVENT_INDEX = "last_imported_event_index"
IMPORT_PAGE_LIMIT = 1000
GROUP_REPLY_LIMIT = 6000


def import_channel_member_replies(
    *,
    store: AgentWorkspaceStore,
    state_root: Path | str,
    workspace: AgentWorkspace,
    channel_id: str,
) -> list[dict[str, Any]]:
    imports: list[dict[str, Any]] = []
    for member in store.list_channel_members(workspace.workspace_id, channel_id):
        if member.member_kind != "codex_session" or member.status == "terminated":
            continue
        result = import_member_replies(
            store=store,
            state_root=state_root,
            workspace=workspace,
            channel_id=channel_id,
            member=member,
        )
        if result is not None:
            imports.append(result)
    return imports


def import_member_replies(
    *,
    store: AgentWorkspaceStore,
    state_root: Path | str,
    workspace: AgentWorkspace,
    channel_id: str,
    member: ChannelMembership,
) -> dict[str, Any] | None:
    session_id = member.resume_session_id
    if not session_id:
        return None
    source_path = _member_source_path(state_root=state_root, member=member)
    if source_path is None:
        return None
    last_imported = _last_imported_index(member)
    latest_page = read_codex_transcript_page(
        source_path,
        limit=1,
        latest=True,
        include_raw=False,
    )
    current_tail = int(latest_page["next_offset"]) - 1
    if current_tail < 0:
        return None
    if last_imported is None:
        _update_member_import_index(
            store=store,
            member=member,
            last_imported_event_index=current_tail,
        )
        return None
    if current_tail <= last_imported:
        return None

    page = read_codex_transcript_page(
        source_path,
        offset=last_imported + 1,
        limit=IMPORT_PAGE_LIMIT,
        include_raw=False,
    )
    imported_count = 0
    for event in page.get("terminal_events") or []:
        if not isinstance(event, dict):
            continue
        if event.get("kind") != "message" or event.get("role") != "assistant":
            continue
        text = str(event.get("text") or "").strip()
        if not text:
            continue
        event_index = int(event.get("event_index") or 0)
        if _reply_already_imported(
            store=store,
            workspace=workspace,
            channel_id=channel_id,
            member=member,
            session_id=session_id,
            event_index=event_index,
        ):
            continue
        store.publish_message(
            workspace_id=workspace.workspace_id,
            conversation_type="channel",
            conversation_id=channel_id,
            from_actor=member.member_id,
            to_actor=None,
            message_type="member_observation",
            summary=_group_reply_summary(text),
            payload={
                "member_id": member.member_id,
                "display_name": member.display_name,
                "resume_session_id": session_id,
                "source_path": str(source_path),
                "event_index": event_index,
                "transcript_ref": {
                    "session_id": session_id,
                    "event_index": event_index,
                    "offset": event_index,
                    "limit": 1,
                },
            },
        )
        imported_count += 1

    last_seen = int(page["next_offset"]) - 1
    _update_member_import_index(
        store=store,
        member=member,
        last_imported_event_index=last_seen,
    )
    if imported_count == 0:
        return None
    return {
        "member_id": member.member_id,
        "display_name": member.display_name,
        "status": "imported",
        "imported_count": imported_count,
        "last_imported_event_index": last_seen,
    }


def mark_member_reply_import_baseline(
    *,
    store: AgentWorkspaceStore,
    state_root: Path | str,
    member: ChannelMembership,
) -> ChannelMembership:
    source_path = _member_source_path(state_root=state_root, member=member)
    if source_path is None:
        return member
    page = read_codex_transcript_page(
        source_path,
        limit=1,
        latest=True,
        include_raw=False,
    )
    last_seen = int(page["next_offset"]) - 1
    if last_seen < 0:
        return member
    return _update_member_import_index(
        store=store,
        member=member,
        last_imported_event_index=last_seen,
    )


def _member_source_path(
    *,
    state_root: Path | str,
    member: ChannelMembership,
) -> Path | None:
    if member.source_path:
        path = Path(member.source_path).expanduser()
        if path.is_file():
            return path
    if not member.resume_session_id:
        return None
    snapshot = find_codex_session_snapshot(
        codex_home=state_root,
        session_id=member.resume_session_id,
    )
    if snapshot is None:
        return None
    return snapshot.source_path


def _last_imported_index(member: ChannelMembership) -> int | None:
    value = member.transcript_policy.get(LAST_IMPORTED_EVENT_INDEX)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _update_member_import_index(
    *,
    store: AgentWorkspaceStore,
    member: ChannelMembership,
    last_imported_event_index: int,
) -> ChannelMembership:
    return store.update_channel_member(
        workspace_id=member.workspace_id,
        channel_id=member.channel_id,
        member_id=member.member_id,
        transcript_policy={
            **member.transcript_policy,
            LAST_IMPORTED_EVENT_INDEX: last_imported_event_index,
        },
    )


def _reply_already_imported(
    *,
    store: AgentWorkspaceStore,
    workspace: AgentWorkspace,
    channel_id: str,
    member: ChannelMembership,
    session_id: str,
    event_index: int,
) -> bool:
    for message in store.list_messages(
        workspace.workspace_id,
        "channel",
        channel_id,
        limit=1000,
    ):
        if (
            message.message_type != "member_observation"
            or message.from_actor != member.member_id
        ):
            continue
        payload = message.payload
        transcript_ref = payload.get("transcript_ref")
        if not isinstance(transcript_ref, dict):
            continue
        if (
            payload.get("member_id") == member.member_id
            and payload.get("resume_session_id") == session_id
            and int(payload.get("event_index") or -1) == event_index
            and transcript_ref.get("session_id") == session_id
            and int(transcript_ref.get("event_index") or -1) == event_index
        ):
            return True
    return False


def _group_reply_summary(text: str) -> str:
    if len(text) <= GROUP_REPLY_LIMIT:
        return text
    return text[: GROUP_REPLY_LIMIT - 1] + "..."
