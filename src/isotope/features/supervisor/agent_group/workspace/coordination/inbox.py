"""Persistent member inbox for Codex-backed workspace group chat."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Any, Iterable

from isotope.agents.loop.conversation import RAW_CONVERSATION_FIELDS
from isotope.platform.schemas.memory import MemoryRecord
from isotope.platform.state.memory_store import FileMemoryStore

from .._records import new_id, parse_timestamp, utc_now


INBOX_RECORD_KIND = "agent_workspace_member_inbox"
INBOX_STATUSES = {"pending", "dispatched"}


@dataclass(frozen=True)
class MemberInboxItem:
    inbox_item_id: str
    workspace_id: str
    channel_id: str
    target_member_id: str
    source_message_id: str
    from_actor: str
    summary: str
    status: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    managed_record_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.inbox_item_id, "inbox_item_id")
        _require_text(self.workspace_id, "workspace_id")
        _require_text(self.channel_id, "channel_id")
        _require_text(self.target_member_id, "target_member_id")
        _require_text(self.source_message_id, "source_message_id")
        _require_text(self.from_actor, "from_actor")
        _require_text(self.summary, "summary")
        if self.status not in INBOX_STATUSES:
            raise ValueError("status must be pending or dispatched")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dict")
        _require_text(self.created_at, "created_at")
        _require_text(self.updated_at, "updated_at")
        if self.managed_record_id is not None:
            _require_text(self.managed_record_id, "managed_record_id")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "inbox_item_id": self.inbox_item_id,
            "workspace_id": self.workspace_id,
            "channel_id": self.channel_id,
            "target_member_id": self.target_member_id,
            "source_message_id": self.source_message_id,
            "from_actor": self.from_actor,
            "summary": self.summary,
            "status": self.status,
            "payload": _copy_public_payload(self.payload),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "managed_record_id": self.managed_record_id,
        }


class MemberInboxStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser()
        self.memory = FileMemoryStore(self.root)

    def enqueue(
        self,
        *,
        workspace_id: str,
        channel_id: str,
        target_member_id: str,
        source_message_id: str,
        from_actor: str,
        summary: str,
        payload: dict[str, Any],
    ) -> MemberInboxItem:
        existing = self._load_latest_by_identity(
            workspace_id=workspace_id,
            channel_id=channel_id,
            target_member_id=target_member_id,
            source_message_id=source_message_id,
        )
        if existing is not None:
            return existing
        now = utc_now()
        item = MemberInboxItem(
            inbox_item_id=_inbox_item_id(
                workspace_id=workspace_id,
                channel_id=channel_id,
                target_member_id=target_member_id,
                source_message_id=source_message_id,
            ),
            workspace_id=workspace_id,
            channel_id=channel_id,
            target_member_id=target_member_id,
            source_message_id=source_message_id,
            from_actor=from_actor,
            summary=summary,
            status="pending",
            payload=dict(payload),
            created_at=now,
            updated_at=now,
            managed_record_id=None,
        )
        self.memory.append_record(_record_for_item(item, supersedes=()))
        return item

    def list_items(
        self,
        workspace_id: str,
        channel_id: str,
        target_member_id: str | None = None,
    ) -> list[MemberInboxItem]:
        latest: dict[str, MemberInboxItem] = {}
        for record in self.memory.list_records(scope="session"):
            if (
                record.content.get("kind") != INBOX_RECORD_KIND
                or record.content.get("workspace_id") != workspace_id
                or record.content.get("channel_id") != channel_id
            ):
                continue
            item = _item_from_record(record)
            if item is None:
                continue
            if target_member_id is not None and item.target_member_id != target_member_id:
                continue
            current = latest.get(item.inbox_item_id)
            if current is None or _item_sort_key(item) >= _item_sort_key(current):
                latest[item.inbox_item_id] = item
        return sorted(
            latest.values(),
            key=lambda item: (parse_timestamp(item.created_at), item.inbox_item_id),
        )

    def list_pending(
        self,
        workspace_id: str,
        channel_id: str,
        target_member_id: str,
    ) -> list[MemberInboxItem]:
        return [
            item
            for item in self.list_items(workspace_id, channel_id, target_member_id)
            if item.status == "pending"
        ]

    def mark_dispatched(
        self,
        *,
        workspace_id: str,
        channel_id: str,
        target_member_id: str,
        inbox_item_ids: Iterable[str],
        managed_record_id: str,
    ) -> list[MemberInboxItem]:
        requested = set(inbox_item_ids)
        updated: list[MemberInboxItem] = []
        for item in self.list_pending(workspace_id, channel_id, target_member_id):
            if item.inbox_item_id not in requested:
                continue
            dispatched = MemberInboxItem(
                inbox_item_id=item.inbox_item_id,
                workspace_id=item.workspace_id,
                channel_id=item.channel_id,
                target_member_id=item.target_member_id,
                source_message_id=item.source_message_id,
                from_actor=item.from_actor,
                summary=item.summary,
                status="dispatched",
                payload=dict(item.payload),
                created_at=item.created_at,
                updated_at=utc_now(),
                managed_record_id=managed_record_id,
            )
            self.memory.append_record(
                _record_for_item(dispatched, supersedes=(item.inbox_item_id,))
            )
            updated.append(dispatched)
        return updated

    def pending_counts_by_member(
        self,
        workspace_id: str,
        channel_id: str,
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.list_items(workspace_id, channel_id):
            if item.status != "pending":
                continue
            counts[item.target_member_id] = counts.get(item.target_member_id, 0) + 1
        return counts

    def _load_latest_by_identity(
        self,
        *,
        workspace_id: str,
        channel_id: str,
        target_member_id: str,
        source_message_id: str,
    ) -> MemberInboxItem | None:
        inbox_item_id = _inbox_item_id(
            workspace_id=workspace_id,
            channel_id=channel_id,
            target_member_id=target_member_id,
            source_message_id=source_message_id,
        )
        for item in self.list_items(workspace_id, channel_id, target_member_id):
            if item.inbox_item_id == inbox_item_id:
                return item
        return None


def _record_for_item(
    item: MemberInboxItem,
    *,
    supersedes: tuple[str, ...],
) -> MemoryRecord:
    payload = {"kind": INBOX_RECORD_KIND, **item.to_public_dict()}
    return MemoryRecord(
        memory_id=f"{INBOX_RECORD_KIND}_{item.inbox_item_id}_{new_id('rev')}",
        scope="session",
        content=payload,
        summary=f"Agent workspace inbox item for {item.target_member_id}",
        source_refs=[],
        provenance={
            "run_id": "agent_group_workspace",
            "execution_id": new_id("exec"),
            "action_type": INBOX_RECORD_KIND,
        },
        created_at=utc_now(),
        supersedes=list(supersedes),
        quality="agent_group_workspace",
    )


def _item_from_record(record: MemoryRecord) -> MemberInboxItem | None:
    try:
        return MemberInboxItem(
            inbox_item_id=str(record.content["inbox_item_id"]),
            workspace_id=str(record.content["workspace_id"]),
            channel_id=str(record.content["channel_id"]),
            target_member_id=str(record.content["target_member_id"]),
            source_message_id=str(record.content["source_message_id"]),
            from_actor=str(record.content["from_actor"]),
            summary=str(record.content["summary"]),
            status=str(record.content["status"]),
            payload=dict(record.content.get("payload") or {}),
            created_at=str(record.content["created_at"]),
            updated_at=str(record.content["updated_at"]),
            managed_record_id=_optional_text(record.content.get("managed_record_id")),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _inbox_item_id(
    *,
    workspace_id: str,
    channel_id: str,
    target_member_id: str,
    source_message_id: str,
) -> str:
    digest = hashlib.sha256(
        "\0".join(
            (workspace_id, channel_id, target_member_id, source_message_id)
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"inbox_{digest}"


def _item_sort_key(item: MemberInboxItem):
    return (parse_timestamp(item.updated_at), parse_timestamp(item.created_at))


def _copy_public_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _copy_public_payload(nested)
            for key, nested in value.items()
            if str(key) not in RAW_CONVERSATION_FIELDS
        }
    if isinstance(value, list):
        return [_copy_public_payload(item) for item in value]
    return value


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _require_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
