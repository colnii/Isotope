from __future__ import annotations

import json
from dataclasses import asdict

from isotope.memory.views import (
    build_memory_status_payload,
    build_multi_worker_status_payload,
)
from isotope.platform.schemas.memory import MemoryRecord


def test_memory_views_build_memory_status_payload(tmp_path):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem-thread",
            scope="thread",
            content={"note": "PRIVATE"},
            summary="Thread memory.",
            source_refs=[],
            provenance={"run_id": "run-a", "execution_id": "exec-a", "action_type": "write"},
            created_at="2026-05-22T01:00:00Z",
            supersedes=[],
            quality="candidate",
        ),
    )

    payload = build_memory_status_payload(root=tmp_path)

    assert payload["summary"]["total"] == 1
    assert payload["summary"]["by_scope"]["thread"] == 1
    assert payload["records"][0]["record_id"] == "mem-thread"
    assert "content" not in payload["records"][0]


def test_memory_views_build_multi_worker_status_payload(tmp_path):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem-worker-a",
            scope="run",
            content={
                "kind": "capacity_call",
                "worker_id": "worker-a",
                "capacity_id": "artifact.review",
                "arguments": {"secret": "PRIVATE"},
            },
            summary="Worker A selected artifact.review.",
            source_refs=[],
            provenance={
                "run_id": "run-a",
                "execution_id": "exec-capacity",
                "action_type": "capacity_call",
            },
            created_at="2026-05-22T01:00:00Z",
            supersedes=[],
            quality="verified",
        ),
    )
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="worker-event-1",
            scope="run",
            content={
                "kind": "worker_event",
                "channel": "supervisor",
                "from_worker": "worker-a",
                "to_worker": "worker-b",
                "event_type": "handoff",
                "message": "Ready.",
            },
            summary="worker-a -> worker-b: Ready.",
            source_refs=[],
            provenance={
                "run_id": "supervisor_worker_event_channel",
                "execution_id": "worker-event-1",
                "action_type": "publish_worker_event",
            },
            created_at="2026-05-22T01:10:00Z",
            supersedes=[],
            quality="verified",
        ),
    )

    payload = build_multi_worker_status_payload(root=tmp_path)

    assert payload["summary"]["worker_count"] == 2
    assert payload["summary"]["capacity_calls_total"] == 1
    workers = {worker["name"]: worker for worker in payload["workers"]}
    assert workers["worker-a"]["capacity_ids"] == ["artifact.review"]
    assert workers["worker-b"]["incoming_events_total"] == 1
    assert "PRIVATE" not in json.dumps(payload)


def _write_memory_record(memory_dir, record: MemoryRecord) -> None:
    (memory_dir / f"{record.memory_id}.json").write_text(
        json.dumps(asdict(record), sort_keys=True),
        encoding="utf-8",
    )
