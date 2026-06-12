"""Import Codex member replies back into workspace channel conversations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from isotope.features.supervisor.registry.session_lookup import (
    find_codex_session_snapshot,
)
from isotope.integrations.codex.transcript import read_codex_transcript_page

from .contracts import AgentWorkspace, ChannelMembership
from .coordination.candidates import parse_codex_group_candidate
from .coordination.rollback import ROLLBACK_STATUS_KIND
from .coordination.turns import run_channel_candidate_turn
from .store import AgentWorkspaceStore


LAST_IMPORTED_EVENT_INDEX = "last_imported_event_index"
LAST_ROLLBACK_EVENT_INDEX = "last_rollback_event_index"
IMPORT_PAGE_LIMIT = 1000


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
    rollback_event = _latest_rollback_event(page)
    rollback_event_index = (
        int(rollback_event["event_index"]) if rollback_event is not None else None
    )
    superseded_message_ids: list[str] = []
    if rollback_event_index is not None:
        superseded_message_ids = _active_member_observation_ids_at_or_before(
            store=store,
            workspace=workspace,
            channel_id=channel_id,
            member=member,
            resume_session_id=session_id,
            rollback_event_index=rollback_event_index,
        )
        _publish_codex_thread_rollback_status(
            store=store,
            workspace=workspace,
            channel_id=channel_id,
            member=member,
            resume_session_id=session_id,
            rollback_event=rollback_event,
            superseded_message_ids=superseded_message_ids,
        )
    candidates = []
    plain_assistant_count = 0
    has_assistant_message = _page_has_assistant_message(
        page,
        after_event_index=rollback_event_index,
    )
    has_non_empty_assistant_message = False
    for event in page.get("terminal_events") or []:
        if not isinstance(event, dict):
            continue
        event_index = int(event.get("event_index") or 0)
        if rollback_event_index is not None and event_index <= rollback_event_index:
            continue
        if event.get("kind") != "message" or event.get("role") != "assistant":
            continue
        text = str(event.get("text") or "").strip()
        if not text:
            continue
        has_non_empty_assistant_message = True
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

    last_seen = int(page["next_offset"]) - 1
    updated_member = _update_member_import_index(
        store=store,
        member=member,
        last_imported_event_index=last_seen,
        last_rollback_event_index=rollback_event_index,
    )
    _mark_running_member_idle(store=store, member=updated_member)
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
    if candidates:
        return _with_rollback_import_metadata(
            {
                "member_id": member.member_id,
                "display_name": member.display_name,
                "status": "candidate_imported",
                "imported_count": published_count,
                "candidate_count": len(candidates),
                "published_count": published_count,
                "last_imported_event_index": last_seen,
            },
            rollback_event_index=rollback_event_index,
            superseded_count=len(superseded_message_ids),
        )
    if plain_assistant_count:
        return _with_rollback_import_metadata(
            {
                "member_id": member.member_id,
                "display_name": member.display_name,
                "status": "transcript_only",
                "imported_count": 0,
                "candidate_count": 0,
                "last_imported_event_index": last_seen,
            },
            rollback_event_index=rollback_event_index,
            superseded_count=len(superseded_message_ids),
        )
    if has_assistant_message and not has_non_empty_assistant_message:
        return _with_rollback_import_metadata(
            {
                "member_id": member.member_id,
                "display_name": member.display_name,
                "status": "silent",
                "imported_count": 0,
                "last_imported_event_index": last_seen,
            },
            rollback_event_index=rollback_event_index,
            superseded_count=len(superseded_message_ids),
        )
    if rollback_event_index is not None:
        return {
            "member_id": member.member_id,
            "display_name": member.display_name,
            "status": "thread_rolled_back",
            "imported_count": 0,
            "candidate_count": 0,
            "last_imported_event_index": last_seen,
            "last_rollback_event_index": rollback_event_index,
            "superseded_count": len(superseded_message_ids),
        }
    return None


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


def _page_has_assistant_message(
    page: dict[str, Any],
    *,
    after_event_index: int | None = None,
) -> bool:
    for event in page.get("events") or []:
        if not isinstance(event, dict):
            continue
        event_index = int(event.get("event_index") or 0)
        if after_event_index is not None and event_index <= after_event_index:
            continue
        if event.get("kind") == "message" and event.get("role") == "assistant":
            return True
    return False


def _update_member_import_index(
    *,
    store: AgentWorkspaceStore,
    member: ChannelMembership,
    last_imported_event_index: int,
    last_rollback_event_index: int | None = None,
) -> ChannelMembership:
    transcript_policy = {
        **member.transcript_policy,
        LAST_IMPORTED_EVENT_INDEX: last_imported_event_index,
    }
    if last_rollback_event_index is not None:
        transcript_policy[LAST_ROLLBACK_EVENT_INDEX] = last_rollback_event_index
    return store.update_channel_member(
        workspace_id=member.workspace_id,
        channel_id=member.channel_id,
        member_id=member.member_id,
        transcript_policy=transcript_policy,
    )


def _mark_running_member_idle(
    *,
    store: AgentWorkspaceStore,
    member: ChannelMembership,
) -> ChannelMembership:
    if member.status != "running":
        return member
    return store.update_channel_member(
        workspace_id=member.workspace_id,
        channel_id=member.channel_id,
        member_id=member.member_id,
        status="idle",
    )


def _candidate_already_imported(
    *,
    store: AgentWorkspaceStore,
    workspace: AgentWorkspace,
    channel_id: str,
    member: ChannelMembership,
    candidate_id: str,
) -> bool:
    for message in store.list_messages(
        workspace.workspace_id,
        "channel",
        channel_id,
        limit=1000,
        include_superseded=True,
    ):
        if (
            message.message_type != "member_observation"
            or message.from_actor != member.member_id
        ):
            continue
        payload = message.payload
        if payload.get("candidate_id") == candidate_id:
            return True
    return False


def _latest_rollback_event(page: dict[str, Any]) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    for event in page.get("events") or []:
        if not isinstance(event, dict) or event.get("kind") != "rollback":
            continue
        if latest is None or int(event.get("event_index") or 0) >= int(
            latest.get("event_index") or 0
        ):
            latest = event
    return latest


def _active_member_observation_ids_at_or_before(
    *,
    store: AgentWorkspaceStore,
    workspace: AgentWorkspace,
    channel_id: str,
    member: ChannelMembership,
    resume_session_id: str,
    rollback_event_index: int,
) -> list[str]:
    message_ids: list[str] = []
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
        if payload.get("resume_session_id") != resume_session_id:
            continue
        event_index = _message_event_index(payload)
        if event_index is None or event_index > rollback_event_index:
            continue
        message_ids.append(message.message_id)
    return message_ids


def _message_event_index(payload: dict[str, Any]) -> int | None:
    event_index = payload.get("event_index")
    if event_index is None:
        transcript_ref = payload.get("transcript_ref")
        if isinstance(transcript_ref, dict):
            event_index = transcript_ref.get("event_index")
    try:
        return int(event_index)
    except (TypeError, ValueError):
        return None


def _publish_codex_thread_rollback_status(
    *,
    store: AgentWorkspaceStore,
    workspace: AgentWorkspace,
    channel_id: str,
    member: ChannelMembership,
    resume_session_id: str,
    rollback_event: dict[str, Any],
    superseded_message_ids: list[str],
) -> None:
    rollback_event_index = int(rollback_event.get("event_index") or 0)
    store.publish_message(
        workspace_id=workspace.workspace_id,
        conversation_type="channel",
        conversation_id=channel_id,
        from_actor=member.member_id,
        to_actor=None,
        message_type="status",
        summary="Codex thread rolled back.",
        payload={
            "status_kind": ROLLBACK_STATUS_KIND,
            "member_id": member.member_id,
            "display_name": member.display_name,
            "resume_session_id": resume_session_id,
            "rollback_event_index": rollback_event_index,
            "num_turns": rollback_event.get("num_turns"),
            "reason": rollback_event.get("reason"),
            "superseded_message_ids": list(superseded_message_ids),
            "transcript_ref": {
                "session_id": resume_session_id,
                "event_index": rollback_event_index,
                "offset": rollback_event_index,
                "limit": 1,
            },
        },
    )


def _with_rollback_import_metadata(
    result: dict[str, Any],
    *,
    rollback_event_index: int | None,
    superseded_count: int,
) -> dict[str, Any]:
    if rollback_event_index is None:
        return result
    return {
        **result,
        "last_rollback_event_index": rollback_event_index,
        "superseded_count": superseded_count,
    }
