from __future__ import annotations

import json
from dataclasses import asdict

from isotope.features.supervisor import runner
from isotope.platform.schemas.memory import MemoryRecord


def test_supervisor_worker_manager_groups_memory_events_and_capacity_calls(
    tmp_path,
    capsys,
):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem_worker_a_note",
            scope="thread",
            content={
                "kind": "note",
                "worker_id": "worker-a",
                "raw": "PRIVATE_WORKER_A_CONTENT",
            },
            summary="Worker A note.",
            source_refs=[],
            provenance={
                "run_id": "run_a",
                "execution_id": "exec_a",
                "action_type": "write_memory",
                "worker_id": "worker-a",
            },
            created_at="2026-05-22T01:00:00Z",
            supersedes=[],
            quality="candidate",
        ),
    )
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem_worker_a_capacity",
            scope="run",
            content={
                "kind": "capacity_call",
                "worker_id": "worker-a",
                "capacity_id": "artifact.review",
                "arguments": {"secret": "PRIVATE_CAPACITY_ARGUMENT"},
            },
            summary="Worker A selected artifact.review.",
            source_refs=[],
            provenance={
                "run_id": "run_a",
                "execution_id": "exec_capacity",
                "action_type": "capacity_call",
            },
            created_at="2026-05-22T01:10:00Z",
            supersedes=[],
            quality="verified",
        ),
    )
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem_worker_b_note",
            scope="session",
            content={"worker_name": "worker-b", "raw": "PRIVATE_WORKER_B_CONTENT"},
            summary="Worker B note.",
            source_refs=[],
            provenance={
                "run_id": "run_b",
                "execution_id": "exec_b",
                "action_type": "write_memory",
            },
            created_at="2026-05-22T01:20:00Z",
            supersedes=[],
            quality="candidate",
        ),
    )
    _publish_event(
        tmp_path,
        from_worker="worker-a",
        to_worker="worker-b",
        event_type="handoff",
        message="Ready for Worker B.",
    )
    _publish_event(
        tmp_path,
        from_worker="worker-b",
        to_worker=None,
        event_type="status",
        message="Broadcast status.",
    )
    capsys.readouterr()

    assert runner.main(["worker-manager", "--root", str(tmp_path), "--json"]) == 0

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["status"] == "ok"
    assert payload["summary"]["worker_count"] == 2
    assert payload["summary"]["memory_records_total"] == 3
    assert payload["summary"]["worker_events_total"] == 2
    assert payload["summary"]["capacity_calls_total"] == 1

    workers = {worker["name"]: worker for worker in payload["workers"]}
    assert workers["worker-a"]["memory_records_total"] == 2
    assert workers["worker-a"]["capacity_calls_total"] == 1
    assert workers["worker-a"]["capacity_ids"] == ["artifact.review"]
    assert workers["worker-a"]["outgoing_events_total"] == 1
    assert workers["worker-b"]["memory_records_total"] == 1
    assert workers["worker-b"]["incoming_events_total"] == 2
    assert workers["worker-b"]["outgoing_events_total"] == 1
    assert "content" not in workers["worker-a"]
    assert "PRIVATE_" not in output


def test_supervisor_worker_manager_plain_output_is_human_readable(tmp_path, capsys):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    _write_memory_record(
        memory_dir,
        MemoryRecord(
            memory_id="mem_worker_a_note",
            scope="thread",
            content={"worker_id": "worker-a", "raw": "hidden"},
            summary="Worker A note.",
            source_refs=[],
            provenance={
                "run_id": "run_a",
                "execution_id": "exec_a",
                "action_type": "write_memory",
            },
            created_at="2026-05-22T01:00:00Z",
            supersedes=[],
            quality="candidate",
        ),
    )
    _publish_event(
        tmp_path,
        from_worker="worker-a",
        to_worker=None,
        event_type="status",
        message="Still running.",
    )
    capsys.readouterr()

    assert runner.main(["worker-manager", "--root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "Worker manager" in output
    assert "workers: 1" in output
    assert "- worker-a / memory=1 / events in=1 out=1 / capacity_calls=0" in output
    assert "Still running." in output
    assert "hidden" not in output


def _publish_event(
    tmp_path,
    *,
    from_worker: str,
    to_worker: str | None,
    event_type: str,
    message: str,
) -> None:
    args = [
        "worker-event",
        "publish",
        "--root",
        str(tmp_path),
        "--from",
        from_worker,
        "--type",
        event_type,
        "--message",
        message,
    ]
    if to_worker is not None:
        args.extend(["--to", to_worker])
    assert runner.main(args) == 0


def _write_memory_record(memory_dir, record: MemoryRecord) -> None:
    (memory_dir / f"{record.memory_id}.json").write_text(
        json.dumps(asdict(record), sort_keys=True),
        encoding="utf-8",
    )
