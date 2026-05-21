"""Read-only multi-worker status view for Supervisor runtime state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from isotope.memory import FileMemoryStore
from isotope.platform.schemas.memory import MemoryRecord

from .worker_event_channel import DEFAULT_CHANNEL, WORKER_EVENT_KIND


CAPACITY_KINDS = {"capacity_call", "capacity_call_selection"}


def build_multi_worker_status_payload(
    *,
    root: Path | str,
    worker: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    root_path = Path(root).expanduser()
    worker_filter = _optional_text(worker)
    records = FileMemoryStore(root_path).list_records()
    event_records = [record for record in records if _is_worker_event_record(record)]
    memory_records = [record for record in records if not _is_worker_event_record(record)]
    worker_names = _discover_worker_names(memory_records=memory_records, events=event_records)
    if worker_filter is not None:
        worker_names = [name for name in worker_names if name == worker_filter]

    worker_payloads = [
        _build_worker_payload(
            name=name,
            memory_records=memory_records,
            event_records=event_records,
        )
        for name in worker_names
    ]
    visible = worker_payloads[:limit]
    capacity_calls_total = sum(item["capacity_calls_total"] for item in worker_payloads)
    return {
        "status": "ok",
        "store": {
            "root": str(root_path),
            "path": str(root_path / "memory"),
            "format": "file_memory_store",
        },
        "filters": {"worker": worker_filter},
        "summary": {
            "worker_count": len(worker_payloads),
            "memory_records_total": len(memory_records),
            "worker_events_total": len(event_records),
            "capacity_calls_total": capacity_calls_total,
            "hidden_workers": max(0, len(worker_payloads) - len(visible)),
        },
        "workers": visible,
    }


def render_multi_worker_status_plain(payload: dict[str, Any]) -> str:
    store = payload.get("store") if isinstance(payload.get("store"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    workers = payload.get("workers") if isinstance(payload.get("workers"), list) else []
    lines = [
        "Worker manager",
        f"root: {store.get('root', '')}",
        f"workers: {summary.get('worker_count', len(workers))}",
        f"memory_records: {summary.get('memory_records_total', 0)}",
        f"worker_events: {summary.get('worker_events_total', 0)}",
        f"capacity_calls: {summary.get('capacity_calls_total', 0)}",
    ]
    if summary.get("hidden_workers"):
        lines.append(f"hidden_workers: {summary['hidden_workers']}")
    if not workers:
        lines.append("workers: none")
        return "\n".join(lines)

    lines.append("workers:")
    for item in workers:
        lines.append(
            "- {name} / memory={memory} / events in={incoming} out={outgoing} / "
            "capacity_calls={capacity}".format(
                name=item.get("name", "unknown"),
                memory=item.get("memory_records_total", 0),
                incoming=item.get("incoming_events_total", 0),
                outgoing=item.get("outgoing_events_total", 0),
                capacity=item.get("capacity_calls_total", 0),
            )
        )
        recent_event = item.get("recent_event")
        if isinstance(recent_event, dict):
            lines.append(
                "  event: {from_worker} -> {to_worker} / {event_type} / {message}".format(
                    from_worker=recent_event.get("from_worker") or "unknown",
                    to_worker=recent_event.get("to_worker") or "*",
                    event_type=recent_event.get("event_type") or "message",
                    message=recent_event.get("message") or "",
                )
            )
        recent_memory = item.get("recent_memory")
        if isinstance(recent_memory, dict):
            lines.append(
                "  memory: {record_id} / {scope} / {summary}".format(
                    record_id=recent_memory.get("record_id", "unknown"),
                    scope=recent_memory.get("scope", "unknown"),
                    summary=recent_memory.get("summary", ""),
                )
            )
    return "\n".join(lines)


def _build_worker_payload(
    *,
    name: str,
    memory_records: list[MemoryRecord],
    event_records: list[MemoryRecord],
) -> dict[str, Any]:
    related_memory = [record for record in memory_records if _record_worker_name(record) == name]
    related_events = [
        record for record in event_records if _event_belongs_to_worker(record, worker=name)
    ]
    incoming_events = [
        record
        for record in related_events
        if record.content.get("to_worker") in {name, None}
    ]
    outgoing_events = [
        record for record in related_events if record.content.get("from_worker") == name
    ]
    broadcast_events = [
        record for record in related_events if record.content.get("to_worker") is None
    ]
    capacity_records = [record for record in related_memory if _is_capacity_call(record)]
    capacity_ids = sorted(
        {
            capacity_id
            for capacity_id in (_capacity_id(record) for record in capacity_records)
            if capacity_id
        }
    )
    return {
        "name": name,
        "memory_records_total": len(related_memory),
        "incoming_events_total": len(incoming_events),
        "outgoing_events_total": len(outgoing_events),
        "broadcast_events_total": len(broadcast_events),
        "capacity_calls_total": len(capacity_records),
        "capacity_ids": capacity_ids,
        "recent_memory": _recent_memory_preview(related_memory),
        "recent_event": _recent_event_preview(related_events),
    }


def _discover_worker_names(
    *,
    memory_records: list[MemoryRecord],
    events: list[MemoryRecord],
) -> list[str]:
    names: set[str] = set()
    for record in memory_records:
        worker = _record_worker_name(record)
        if worker is not None:
            names.add(worker)
    for record in events:
        for key in ("from_worker", "to_worker"):
            worker = _optional_text(record.content.get(key))
            if worker is not None:
                names.add(worker)
    return sorted(names)


def _record_worker_name(record: MemoryRecord) -> str | None:
    for container in (record.provenance, record.content):
        for key in ("worker_id", "worker_name", "worker", "name"):
            worker = _optional_text(container.get(key))
            if worker is not None:
                return worker
    return None


def _is_worker_event_record(record: MemoryRecord) -> bool:
    return record.content.get("kind") == WORKER_EVENT_KIND


def _event_belongs_to_worker(record: MemoryRecord, *, worker: str) -> bool:
    content = record.content
    return (
        content.get("from_worker") == worker
        or content.get("to_worker") == worker
        or content.get("to_worker") is None
    )


def _is_capacity_call(record: MemoryRecord) -> bool:
    content = record.content
    provenance = record.provenance
    return (
        content.get("kind") in CAPACITY_KINDS
        or provenance.get("action_type") in CAPACITY_KINDS
    )


def _capacity_id(record: MemoryRecord) -> str | None:
    content = record.content
    capacity = _optional_text(content.get("capacity_id"))
    if capacity is not None:
        return capacity
    selection = content.get("selection")
    if isinstance(selection, dict):
        return _optional_text(selection.get("capacity_id"))
    return None


def _recent_memory_preview(records: list[MemoryRecord]) -> dict[str, Any] | None:
    record = _latest_record(records)
    if record is None:
        return None
    return {
        "record_id": record.memory_id,
        "scope": record.scope,
        "summary": record.summary,
        "created_at": record.created_at,
        "quality": record.quality,
    }


def _recent_event_preview(records: list[MemoryRecord]) -> dict[str, Any] | None:
    record = _latest_record(records)
    if record is None:
        return None
    content = record.content
    return {
        "record_id": record.memory_id,
        "channel": content.get("channel", DEFAULT_CHANNEL),
        "event_type": content.get("event_type", "message"),
        "from_worker": content.get("from_worker"),
        "to_worker": content.get("to_worker"),
        "message": content.get("message", ""),
        "created_at": record.created_at,
        "summary": record.summary,
        "quality": record.quality,
    }


def _latest_record(records: list[MemoryRecord]) -> MemoryRecord | None:
    if not records:
        return None
    return max(records, key=lambda record: (record.created_at, record.memory_id))


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None
