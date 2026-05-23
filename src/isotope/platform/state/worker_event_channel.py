"""Memory-backed event channel for worker coordination."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

from isotope.platform.schemas.actions import ActionExecution
from isotope.platform.schemas.memory import MemoryRecord
from isotope.platform.state.memory_store import FileMemoryStore


DEFAULT_CHANNEL = "default"
WORKER_EVENT_KIND = "worker_event"


@dataclass(frozen=True)
class WorkerEvent:
    """Structured worker event that can be persisted as a memory record."""

    event_id: str
    channel: str
    event_type: str
    from_worker: str
    to_worker: str | None
    message: str
    payload: dict[str, Any]
    created_at: str
    execution_id: str

    def __post_init__(self) -> None:
        _required_text(self.event_id, "event_id")
        _required_text(self.channel, "channel")
        _required_text(self.event_type, "event_type")
        _required_text(self.from_worker, "from_worker")
        _required_text(self.message, "message")
        _required_text(self.created_at, "created_at")
        _required_text(self.execution_id, "execution_id")
        if self.to_worker is not None:
            _required_text(self.to_worker, "to_worker")
        if not isinstance(self.payload, dict):
            raise TypeError("payload must be a dict")

    def to_memory_record(self) -> MemoryRecord:
        return MemoryRecord(
            memory_id=self.event_id.strip(),
            scope="session",
            content={
                "kind": WORKER_EVENT_KIND,
                "channel": self.channel.strip(),
                "event_type": self.event_type.strip(),
                "from_worker": self.from_worker.strip(),
                "to_worker": self.to_worker.strip() if self.to_worker is not None else None,
                "message": self.message.strip(),
                "payload": dict(self.payload),
            },
            summary=_event_summary(
                from_worker=self.from_worker.strip(),
                to_worker=self.to_worker.strip() if self.to_worker is not None else None,
                event_type=self.event_type.strip(),
                message=self.message.strip(),
            ),
            source_refs=[],
            provenance={
                "run_id": "supervisor_worker_event_channel",
                "execution_id": self.execution_id.strip(),
                "action_type": "worker_event",
            },
            created_at=self.created_at.strip(),
            supersedes=[],
            quality="worker_event",
        )


def publish_worker_event(
    *,
    root: Path | str,
    from_worker: str,
    message: str,
    to_worker: str | None = None,
    event_type: str = "message",
    channel: str = DEFAULT_CHANNEL,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root_path = Path(root).expanduser()
    from_text = _required_text(from_worker, "from_worker")
    message_text = _required_text(message, "message")
    event_type_text = _required_text(event_type, "event_type")
    channel_text = _required_text(channel, "channel")
    to_text = _optional_text(to_worker)
    payload_dict = dict(payload or {})
    event = WorkerEvent(
        event_id="mem_event_" + uuid.uuid4().hex[:12],
        channel=channel_text,
        event_type=event_type_text,
        from_worker=from_text,
        to_worker=to_text,
        message=message_text,
        payload=payload_dict,
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        execution_id="exec_event_" + uuid.uuid4().hex[:12],
    )
    record = event.to_memory_record()
    execution = ActionExecution(
        execution_id=record.provenance["execution_id"],
        proposal_id="prop_event_" + uuid.uuid4().hex[:12],
        decision_id="dec_event_" + uuid.uuid4().hex[:12],
        action_type="write_memory",
        status="completed",
        effective_grants_snapshot={"tools": ["write_memory"]},
    )
    FileMemoryStore(root_path).save_record(
        record,
        execution=execution,
        grants={"tools": ["write_memory"]},
    )
    return {
        "status": "ok",
        "store": _store_payload(root_path),
        "event": _worker_event_preview(record),
    }


def list_worker_events(
    *,
    root: Path | str,
    channel: str | None = None,
    from_worker: str | None = None,
    to_worker: str | None = None,
    event_type: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    root_path = Path(root).expanduser()
    channel_text = _optional_text(channel)
    from_text = _optional_text(from_worker)
    to_text = _optional_text(to_worker)
    event_type_text = _optional_text(event_type)
    records = [
        record
        for record in FileMemoryStore(root_path).list_records(scope="session")
        if _is_matching_worker_event(
            record,
            channel=channel_text,
            from_worker=from_text,
            to_worker=to_text,
            event_type=event_type_text,
        )
    ]
    sorted_records = sorted(
        records,
        key=lambda record: (record.created_at, record.memory_id),
        reverse=True,
    )
    visible = sorted_records[:limit]
    return {
        "status": "ok",
        "store": _store_payload(root_path),
        "filters": {
            "channel": channel_text,
            "from_worker": from_text,
            "to_worker": to_text,
            "event_type": event_type_text,
        },
        "summary": {
            "total": len(records),
            "hidden_events": max(0, len(records) - len(visible)),
        },
        "events": [_worker_event_preview(record) for record in visible],
    }


def render_worker_event_channel_plain(payload: dict[str, Any]) -> str:
    store = payload.get("store") if isinstance(payload.get("store"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    lines = [
        "Worker event channel",
        f"root: {store.get('root', '')}",
        f"total: {summary.get('total', len(events))}",
    ]
    if summary.get("hidden_events"):
        lines.append(f"hidden_events: {summary['hidden_events']}")
    if not events:
        lines.append("events: none")
        return "\n".join(lines)
    lines.append("events:")
    for event in events:
        lines.append(
            "- {from_worker} -> {to_worker} / {event_type} / {message}".format(
                from_worker=event.get("from_worker", "unknown"),
                to_worker=event.get("to_worker") or "*",
                event_type=event.get("event_type", "message"),
                message=event.get("message", ""),
            )
        )
    return "\n".join(lines)


def _is_matching_worker_event(
    record: MemoryRecord,
    *,
    channel: str | None,
    from_worker: str | None,
    to_worker: str | None,
    event_type: str | None,
) -> bool:
    content = record.content
    if content.get("kind") != WORKER_EVENT_KIND:
        return False
    if channel is not None and content.get("channel") != channel:
        return False
    if from_worker is not None and content.get("from_worker") != from_worker:
        return False
    if event_type is not None and content.get("event_type") != event_type:
        return False
    target = content.get("to_worker")
    if to_worker is not None and target not in {to_worker, None}:
        return False
    return True


def _worker_event_preview(record: MemoryRecord) -> dict[str, Any]:
    content = record.content
    return {
        "record_id": record.memory_id,
        "channel": content.get("channel", DEFAULT_CHANNEL),
        "event_type": content.get("event_type", "message"),
        "from_worker": content.get("from_worker"),
        "to_worker": content.get("to_worker"),
        "message": content.get("message", ""),
        "payload": dict(content.get("payload") or {}),
        "created_at": record.created_at,
        "summary": record.summary,
        "quality": record.quality,
    }


def _event_summary(
    *,
    from_worker: str,
    to_worker: str | None,
    event_type: str,
    message: str,
) -> str:
    target = to_worker or "*"
    return f"{from_worker} -> {target} / {event_type} / {message}"


def _store_payload(root_path: Path) -> dict[str, str]:
    return {
        "root": str(root_path),
        "path": str(root_path / "memory"),
        "format": "file_memory_store",
    }


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None
