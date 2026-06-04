from __future__ import annotations

import json
from dataclasses import asdict

from isotope.memory.views import (
    build_memory_query_payload,
    build_memory_status_payload,
    build_multi_worker_status_payload,
    render_memory_query_plain,
)
import isotope.platform.state.multi_worker as platform_multi_worker
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


def test_memory_views_build_memory_query_payload_without_content(tmp_path):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem-match",
            scope="run",
            content={"secret": "raw memory content must not leak"},
            summary="Resume from the memory integration boundary.",
            source_refs=[{"ref_type": "artifact", "artifact_id": "artifact_001"}],
            provenance={
                "run_id": "run_001",
                "execution_id": "exec_001",
                "action_type": "write_memory",
            },
            created_at="2026-05-22T01:00:00Z",
            supersedes=[],
            quality="candidate",
        ),
    )
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem-other",
            scope="session",
            content={"secret": "another raw memory payload"},
            summary="Unrelated session note.",
            source_refs=[],
            provenance={
                "run_id": "run_002",
                "execution_id": "exec_002",
                "action_type": "write_memory",
            },
            created_at="2026-05-22T02:00:00Z",
            supersedes=[],
            quality="verified",
        ),
    )

    payload = build_memory_query_payload(root=tmp_path, query="integration boundary")

    assert payload["status"] == "ok"
    assert payload["content_policy"] == "memory_record_refs_expandable"
    assert payload["query"] == "integration boundary"
    assert payload["summary"] == {"total": 2, "matched": 1, "hidden_records": 0}
    assert payload["results"] == [
        {
            "record_id": "mem-match",
            "scope": "run",
            "summary": "Resume from the memory integration boundary.",
            "source_refs": [{"ref_type": "artifact", "artifact_id": "artifact_001"}],
            "provenance": {
                "run_id": "run_001",
                "execution_id": "exec_001",
                "action_type": "write_memory",
            },
            "quality": "candidate",
        }
    ]
    assert '"secret"' not in json.dumps(payload)
    assert "raw memory" not in json.dumps(payload)


def test_memory_query_plain_output_shows_materialized_controlled_expand_metadata():
    output = render_memory_query_plain(
        {
            "status": "ok",
            "query": "controlled expand metadata",
            "scope": "run",
            "run_id": "run_001",
            "summary": {"matched": 1, "hidden_records": 0},
            "controlled_expand": {
                "status": "materialized",
                "budget": 20,
                "used": 5,
                "content_policy": "controlled_expand_memory_record_content_only",
                "materialized_results": [
                    {
                        "record_id": "mem_preview",
                        "encoding": "json",
                        "truncated": False,
                    }
                ],
            },
            "results": [
                {
                    "record_id": "mem_preview",
                    "scope": "run",
                    "quality": "candidate",
                    "summary": "Preview only.",
                }
            ],
        }
    )

    assert "controlled_expand: materialized" in output
    assert "controlled_expand_budget: 20" in output
    assert "controlled_expand_used: 5" in output
    assert (
        "controlled_expand_content_policy: controlled_expand_memory_record_content_only"
        in output
    )
    assert "controlled_expand_result_count: 1" in output


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


def test_multi_worker_status_can_be_built_from_memory_records():
    records = [
        MemoryRecord(
            memory_id="mem-worker-record-input",
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
        MemoryRecord(
            memory_id="worker-event-record-input",
            scope="session",
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
                "execution_id": "worker-event-record-input",
                "action_type": "publish_worker_event",
            },
            created_at="2026-05-22T01:10:00Z",
            supersedes=[],
            quality="verified",
        ),
    ]

    payload = platform_multi_worker.build_multi_worker_status_from_records(records=records)

    assert payload["summary"]["worker_count"] == 2
    assert payload["summary"]["memory_records_total"] == 1
    assert payload["summary"]["worker_events_total"] == 1
    workers = {worker["name"]: worker for worker in payload["workers"]}
    assert workers["worker-a"]["capacity_ids"] == ["artifact.review"]
    assert workers["worker-b"]["incoming_events_total"] == 1
    assert "PRIVATE" not in json.dumps(payload)


def _write_memory_record(memory_dir, record: MemoryRecord) -> None:
    (memory_dir / f"{record.memory_id}.json").write_text(
        json.dumps(asdict(record), sort_keys=True),
        encoding="utf-8",
    )
