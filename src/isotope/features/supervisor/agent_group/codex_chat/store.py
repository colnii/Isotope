"""Storage for Codex-backed Agent Group Chat."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import uuid

from isotope.platform.schemas.memory import MemoryRecord
from isotope.platform.state.memory_store import FileMemoryStore
from isotope.platform.state.worker_event_channel import (
    list_worker_events,
    publish_worker_event,
)

from .contracts import (
    ConnectedCodexMember,
    PrivateChatMessage,
    RuntimeControlRequest,
)


MEMBER_RECORD_KIND = "agent_group_codex_member"
PRIVATE_CHAT_RECORD_KIND = "agent_group_private_chat"
CONTROL_EVENT_CHANNEL = "agent-group-control"


class CodexGroupChatStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser()
        self.memory = FileMemoryStore(self.root)

    def save_member(self, member: ConnectedCodexMember) -> ConnectedCodexMember:
        self.memory.append_record(_record_for_member(member))
        return member

    def list_members(self, group_id: str) -> list[ConnectedCodexMember]:
        latest: dict[str, ConnectedCodexMember] = {}
        for record in self.memory.list_records(scope="session"):
            if (
                record.content.get("kind") != MEMBER_RECORD_KIND
                or record.content.get("group_id") != group_id
            ):
                continue
            member = _member_from_record(record)
            if member is None:
                continue
            current = latest.get(member.member_id)
            if current is None or _member_sort_key(member) >= _member_sort_key(current):
                latest[member.member_id] = member
        return sorted(latest.values(), key=lambda item: item.member_id)

    def update_member_status(
        self,
        *,
        group_id: str,
        member_id: str,
        status: str,
    ) -> ConnectedCodexMember:
        for member in self.list_members(group_id):
            if member.member_id != member_id:
                continue
            updated = replace(
                member,
                status=status,
                updated_at=_next_timestamp_after(member.updated_at),
            )
            self.save_member(updated)
            return updated
        raise ValueError(f"connected member not found: {member_id}")

    def append_private_chat(
        self,
        *,
        group_id: str,
        role: str,
        content: str,
    ) -> PrivateChatMessage:
        message = PrivateChatMessage(
            message_id=_new_id("private"),
            group_id=group_id,
            role=role,
            content=content,
            created_at=_utc_now(),
        )
        self.memory.append_record(_record_for_private_chat(message))
        return message

    def list_private_chat(self, group_id: str) -> list[PrivateChatMessage]:
        messages = [
            _private_chat_from_record(record)
            for record in self.memory.list_records(scope="session")
            if record.content.get("kind") == PRIVATE_CHAT_RECORD_KIND
            and record.content.get("group_id") == group_id
        ]
        return sorted(
            [message for message in messages if message is not None],
            key=lambda item: (item.created_at, item.message_id),
        )

    def record_control(
        self,
        *,
        group_id: str,
        intent: str,
        target: str,
        target_member_id: str | None,
        reason: str,
    ) -> RuntimeControlRequest:
        control = RuntimeControlRequest(
            control_id=_new_id("control"),
            group_id=group_id,
            intent=intent,
            target=target,
            target_member_id=target_member_id,
            reason=reason,
            created_at=_utc_now(),
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
        group_id: str,
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
            raw_payload = event.get("payload")
            if isinstance(raw_payload, dict) and raw_payload.get("group_id") == group_id:
                events.append(event)
        return events


def _record_for_member(member: ConnectedCodexMember) -> MemoryRecord:
    return _record(
        record_id=(
            f"agent_group_codex_member_{member.group_id}_"
            f"{member.member_id}_{_new_id('rev')}"
        ),
        kind=MEMBER_RECORD_KIND,
        content=member.to_public_dict(),
        summary=f"Connected Codex member {member.display_name}: {member.status}",
    )


def _record_for_private_chat(message: PrivateChatMessage) -> MemoryRecord:
    return _record(
        record_id=f"agent_group_private_chat_{message.group_id}_{message.message_id}",
        kind=PRIVATE_CHAT_RECORD_KIND,
        content=message.to_public_dict(),
        summary=message.content,
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
            "run_id": "agent_group_codex_chat",
            "execution_id": _new_id("exec"),
            "action_type": kind,
        },
        created_at=_utc_now(),
        supersedes=[],
        quality="agent_group_codex_chat",
    )


def _member_from_record(record: MemoryRecord) -> ConnectedCodexMember | None:
    try:
        return ConnectedCodexMember(
            member_id=str(record.content["member_id"]),
            group_id=str(record.content["group_id"]),
            display_name=str(record.content["display_name"]),
            member_kind=str(record.content["member_kind"]),
            role=str(record.content["role"]),
            goal=str(record.content.get("goal") or ""),
            send_policy=str(record.content["send_policy"]),
            status=str(record.content["status"]),
            resume_session_id=_optional_string(record.content.get("resume_session_id")),
            source_path=_optional_string(record.content.get("source_path")),
            managed_record_id=_optional_string(record.content.get("managed_record_id")),
            transcript_policy=dict(record.content.get("transcript_policy") or {}),
            created_at=str(record.content["created_at"]),
            updated_at=str(record.content["updated_at"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _private_chat_from_record(record: MemoryRecord) -> PrivateChatMessage | None:
    try:
        return PrivateChatMessage(
            message_id=str(record.content["message_id"]),
            group_id=str(record.content["group_id"]),
            role=str(record.content["role"]),
            content=str(record.content["content"]),
            created_at=str(record.content["created_at"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _member_sort_key(member: ConnectedCodexMember) -> tuple[datetime, datetime]:
    return (_parse_timestamp(member.updated_at), _parse_timestamp(member.created_at))


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _next_timestamp_after(previous: str) -> str:
    now = datetime.now(timezone.utc)
    previous_time = _parse_timestamp(previous)
    if now <= previous_time:
        now = previous_time + timedelta(microseconds=1)
    return now.isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
