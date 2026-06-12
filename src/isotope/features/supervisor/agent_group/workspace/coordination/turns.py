"""Arbiter-backed Codex candidate turns for workspace channels."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from isotope.agents.loop.conversation import arbitrate_agent_conversation_turn
from isotope.features.supervisor.agent_group.store import AgentGroupStore

from ..contracts import AgentWorkspace, ChannelMembership, WorkspaceConversationMessage
from ..runtime_bridge import (
    RUNTIME_MESSAGE_LIMIT,
    sync_channel_runtime_group,
)
from ..store import AgentWorkspaceStore
from .candidates import CodexGroupCandidate, candidate_to_agent_message
from .inbox import MemberInboxStore


def run_channel_candidate_turn(
    *,
    store: AgentWorkspaceStore,
    state_root: Path | str,
    workspace: AgentWorkspace,
    channel_id: str,
    candidates: Iterable[CodexGroupCandidate],
    max_visible_messages: int,
) -> dict[str, Any]:
    candidate_list = list(candidates)
    group_id = sync_channel_runtime_group(
        store=store,
        state_root=state_root,
        workspace=workspace,
        channel_id=channel_id,
    )
    group_store = AgentGroupStore(state_root)
    turn_id = f"turn_codex_{len(group_store.list_turns(group_id)) + 1:04d}"
    arbitration = arbitrate_agent_conversation_turn(
        [candidate_to_agent_message(candidate) for candidate in candidate_list],
        turn_id=turn_id,
        max_visible_messages=max_visible_messages,
    )
    candidate_by_id = {
        candidate.candidate_id: candidate
        for candidate in candidate_list
    }
    selected_workspace_messages: list[WorkspaceConversationMessage] = []
    selected_group_message_ids: list[str] = []
    enqueued_count = 0

    for selected in arbitration["visible_messages"]:
        candidate = candidate_by_id[str(selected["message_id"])]
        message_type = "interrupt" if candidate.intent == "interrupt" else "reply"
        workspace_message = _publish_workspace_candidate(
            store=store,
            workspace=workspace,
            channel_id=channel_id,
            candidate=candidate,
            turn_id=turn_id,
            group_id=group_id,
        )
        selected_workspace_messages.append(workspace_message)
        group_message = group_store.publish_message(
            group_id=group_id,
            turn_id=turn_id,
            from_member=candidate.member_id,
            to_member=None,
            message_type=message_type,
            summary=candidate.summary,
            payload={
                "source": "codex_group_candidate",
                "workspace_id": workspace.workspace_id,
                "channel_id": channel_id,
                "workspace_message_id": workspace_message.message_id,
                "candidate_id": candidate.candidate_id,
                "intent": candidate.intent,
                "priority": candidate.priority,
            },
        )
        selected_group_message_ids.append(group_message.message_id)
        enqueued_count += _enqueue_visible_message_for_other_members(
            store=store,
            state_root=state_root,
            workspace=workspace,
            channel_id=channel_id,
            source_candidate=candidate,
            source_message=workspace_message,
            group_id=group_id,
            turn_id=turn_id,
        )

    input_message_ids = tuple(
        message.message_id
        for message in group_store.list_group_messages(
            group_id,
            limit=RUNTIME_MESSAGE_LIMIT,
        )[-10:]
    )
    turn = group_store.record_turn(
        group_id=group_id,
        input_message_ids=input_message_ids,
        candidate_messages=tuple(candidate.candidate_id for candidate in candidate_list),
        selected_message_ids=tuple(selected_group_message_ids),
        queued_messages=tuple(arbitration["queued_messages"]),
        dropped_messages=tuple(arbitration["dropped_messages"]),
        status=str(arbitration["status"]),
        supervisor_summary=_turn_summary(arbitration),
    )
    return {
        "status": arbitration["status"],
        "runtime_group_id": group_id,
        "turn": turn.to_public_dict(),
        "arbitration": arbitration,
        "published_messages": [
            {
                **message.to_public_dict(),
                "candidate_id": message.payload.get("candidate_id"),
            }
            for message in selected_workspace_messages
        ],
        "enqueued_count": enqueued_count,
    }


def _publish_workspace_candidate(
    *,
    store: AgentWorkspaceStore,
    workspace: AgentWorkspace,
    channel_id: str,
    candidate: CodexGroupCandidate,
    turn_id: str,
    group_id: str,
) -> WorkspaceConversationMessage:
    return store.publish_message(
        workspace_id=workspace.workspace_id,
        conversation_type="channel",
        conversation_id=channel_id,
        from_actor=candidate.member_id,
        to_actor=None,
        message_type="member_observation",
        summary=candidate.summary,
        payload={
            "source": "codex_group_candidate",
            "candidate_id": candidate.candidate_id,
            "member_id": candidate.member_id,
            "display_name": candidate.display_name,
            "resume_session_id": candidate.resume_session_id,
            "event_index": candidate.event_index,
            "intent": candidate.intent,
            "priority": candidate.priority,
            "state_lock": candidate.state_lock,
            "turn_id": turn_id,
            "runtime_group_id": group_id,
            "transcript_ref": dict(candidate.transcript_ref),
        },
    )


def _enqueue_visible_message_for_other_members(
    *,
    store: AgentWorkspaceStore,
    state_root: Path | str,
    workspace: AgentWorkspace,
    channel_id: str,
    source_candidate: CodexGroupCandidate,
    source_message: WorkspaceConversationMessage,
    group_id: str,
    turn_id: str,
) -> int:
    inbox = MemberInboxStore(state_root)
    count = 0
    for member in _deliverable_members(
        store.list_channel_members(workspace.workspace_id, channel_id),
        source_member_id=source_candidate.member_id,
    ):
        inbox.enqueue(
            workspace_id=workspace.workspace_id,
            channel_id=channel_id,
            target_member_id=member.member_id,
            source_message_id=source_message.message_id,
            from_actor=source_candidate.member_id,
            summary=source_candidate.summary,
            payload={
                "source": "codex_group_visible_message",
                "workspace_message_id": source_message.message_id,
                "candidate_id": source_candidate.candidate_id,
                "runtime_group_id": group_id,
                "turn_id": turn_id,
            },
        )
        count += 1
    return count


def _deliverable_members(
    members: Iterable[ChannelMembership],
    *,
    source_member_id: str,
) -> list[ChannelMembership]:
    return [
        member
        for member in members
        if member.member_id != source_member_id
        and member.member_kind == "codex_session"
        and member.status not in {"archived", "terminated"}
    ]


def _turn_summary(arbitration: dict[str, Any]) -> str:
    visible = arbitration.get("visible_messages") or []
    if visible:
        return f"Selected {len(visible)} visible Codex group message(s)."
    dropped = arbitration.get("dropped_messages") or []
    if dropped:
        return f"No visible Codex group messages selected; dropped {len(dropped)}."
    return "No visible Codex group messages selected."
