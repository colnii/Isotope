"""Memory-backed store for Supervisor Agent group chat."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

from isotope.platform.schemas.memory import MemoryRecord
from isotope.platform.state.memory_store import FileMemoryStore
from isotope.platform.state.worker_event_channel import (
    list_worker_events,
    publish_worker_event,
)

from .contracts import AgentGroup, AgentGroupMessage, AgentMember, AgentTurn


GROUP_RECORD_KIND = "agent_group"
MEMBER_RECORD_KIND = "agent_group_member"
TURN_RECORD_KIND = "agent_group_turn"
GROUP_EVENT_CHANNEL = "agent-group"


class AgentGroupStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser()
        self.memory = FileMemoryStore(self.root)

    def create_group(
        self,
        *,
        title: str,
        goal: str,
        members: list[AgentMember],
        initial_message: str,
    ) -> AgentGroup:
        now = _utc_now()
        group = AgentGroup(
            group_id=_new_id("group"),
            title=title.strip(),
            goal=goal.strip(),
            status="active",
            created_at=now,
            updated_at=now,
        )
        self.memory.append_record(_memory_record_for_group(group))
        for member in members:
            normalized = replace(member, group_id=group.group_id)
            self.memory.append_record(_memory_record_for_member(normalized))
        self.publish_message(
            group_id=group.group_id,
            turn_id="turn_initial",
            from_member="supervisor",
            to_member=None,
            message_type="task",
            summary=initial_message,
            payload={"source": "agent_group_create"},
        )
        return group

    def list_groups(self) -> list[AgentGroup]:
        groups = [
            _group_from_record(record)
            for record in self.memory.list_records(scope="session")
            if record.content.get("kind") == GROUP_RECORD_KIND
        ]
        return sorted(
            [group for group in groups if group is not None],
            key=lambda group: (group.created_at, group.group_id),
        )

    def load_group(self, group_id: str) -> AgentGroup:
        for group in self.list_groups():
            if group.group_id == group_id:
                return group
        raise ValueError(f"agent group not found: {group_id}")

    def list_members(self, group_id: str) -> list[AgentMember]:
        members = [
            _member_from_record(record)
            for record in self.memory.list_records(scope="session")
            if record.content.get("kind") == MEMBER_RECORD_KIND
            and record.content.get("group_id") == group_id
        ]
        return sorted(
            [member for member in members if member is not None],
            key=lambda member: member.member_id,
        )

    def publish_message(
        self,
        *,
        group_id: str,
        turn_id: str,
        from_member: str,
        to_member: str | None,
        message_type: str,
        summary: str,
        payload: dict[str, Any],
    ) -> AgentGroupMessage:
        message = AgentGroupMessage(
            message_id=_new_id("msg"),
            group_id=group_id,
            turn_id=turn_id,
            from_member=from_member,
            to_member=to_member,
            message_type=message_type,
            summary=summary,
            payload=dict(payload),
            created_at=_utc_now(),
        )
        publish_worker_event(
            root=self.root,
            from_worker=from_member,
            to_worker=to_member,
            event_type=message_type,
            channel=GROUP_EVENT_CHANNEL,
            message=summary,
            payload=message.to_public_dict(),
        )
        return message

    def list_group_messages(
        self,
        group_id: str,
        *,
        limit: int = 50,
    ) -> list[AgentGroupMessage]:
        payload = list_worker_events(
            root=self.root,
            channel=GROUP_EVENT_CHANNEL,
            limit=max(limit, 1),
        )
        messages: list[AgentGroupMessage] = []
        for event in payload.get("events") or []:
            if not isinstance(event, dict):
                continue
            raw = event.get("payload")
            if not isinstance(raw, dict) or raw.get("group_id") != group_id:
                continue
            try:
                messages.append(AgentGroupMessage(**raw))
            except (TypeError, ValueError):
                continue
        return sorted(messages, key=lambda message: (message.created_at, message.message_id))

    def record_turn(
        self,
        *,
        group_id: str,
        input_message_ids: tuple[str, ...],
        candidate_messages: tuple[str, ...],
        selected_message_ids: tuple[str, ...],
        queued_messages: tuple[dict[str, Any], ...],
        dropped_messages: tuple[dict[str, Any], ...],
        status: str,
        supervisor_summary: str,
    ) -> AgentTurn:
        turn = AgentTurn(
            turn_id=_new_id("turn"),
            group_id=group_id,
            input_message_ids=input_message_ids,
            candidate_messages=candidate_messages,
            selected_message_ids=selected_message_ids,
            queued_messages=queued_messages,
            dropped_messages=dropped_messages,
            status=status,
            supervisor_summary=supervisor_summary,
            created_at=_utc_now(),
        )
        self.memory.append_record(_memory_record_for_turn(turn))
        return turn

    def list_turns(self, group_id: str) -> list[AgentTurn]:
        turns = [
            _turn_from_record(record)
            for record in self.memory.list_records(scope="session")
            if record.content.get("kind") == TURN_RECORD_KIND
            and record.content.get("group_id") == group_id
        ]
        return sorted(
            [turn for turn in turns if turn is not None],
            key=lambda turn: (turn.created_at, turn.turn_id),
        )


def _memory_record_for_group(group: AgentGroup) -> MemoryRecord:
    return _record(
        record_id=f"agent_group_{group.group_id}",
        kind=GROUP_RECORD_KIND,
        content=group.to_public_dict(),
        summary=f"Agent group {group.title}: {group.goal}",
    )


def _memory_record_for_member(member: AgentMember) -> MemoryRecord:
    return _record(
        record_id=f"agent_group_member_{member.group_id}_{member.member_id}",
        kind=MEMBER_RECORD_KIND,
        content=member.to_public_dict(),
        summary=f"Agent group member {member.name}: {member.role}",
    )


def _memory_record_for_turn(turn: AgentTurn) -> MemoryRecord:
    return _record(
        record_id=f"agent_group_turn_{turn.group_id}_{turn.turn_id}",
        kind=TURN_RECORD_KIND,
        content=turn.to_public_dict(),
        summary=turn.supervisor_summary,
    )


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
            "run_id": "supervisor_agent_group",
            "execution_id": _new_id("exec"),
            "action_type": kind,
        },
        created_at=_utc_now(),
        supersedes=[],
        quality="agent_group",
    )


def _group_from_record(record: MemoryRecord) -> AgentGroup | None:
    try:
        return AgentGroup(
            group_id=str(record.content["group_id"]),
            title=str(record.content["title"]),
            goal=str(record.content["goal"]),
            status=str(record.content["status"]),
            created_at=str(record.content["created_at"]),
            updated_at=str(record.content["updated_at"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _member_from_record(record: MemoryRecord) -> AgentMember | None:
    try:
        return AgentMember(
            member_id=str(record.content["member_id"]),
            group_id=str(record.content["group_id"]),
            name=str(record.content["name"]),
            role=str(record.content["role"]),
            goal=str(record.content["goal"]),
            model_profile=str(record.content.get("model_profile") or "default"),
            allowed_capabilities=tuple(record.content.get("allowed_capabilities") or ()),
            status=str(record.content.get("status") or "active"),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _turn_from_record(record: MemoryRecord) -> AgentTurn | None:
    try:
        return AgentTurn(
            turn_id=str(record.content["turn_id"]),
            group_id=str(record.content["group_id"]),
            input_message_ids=tuple(record.content.get("input_message_ids") or ()),
            candidate_messages=tuple(record.content.get("candidate_messages") or ()),
            selected_message_ids=tuple(record.content.get("selected_message_ids") or ()),
            queued_messages=tuple(record.content.get("queued_messages") or ()),
            dropped_messages=tuple(record.content.get("dropped_messages") or ()),
            status=str(record.content["status"]),
            supervisor_summary=str(record.content["supervisor_summary"]),
            created_at=str(record.content["created_at"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
