from __future__ import annotations

import json
from dataclasses import asdict

import isotope.features.supervisor.state.multi_worker as supervisor_multi_worker
import isotope.platform.state.multi_worker as platform_multi_worker
from isotope.features.supervisor import runner
from isotope.platform.schemas.memory import MemoryRecord


def test_multi_worker_status_uses_platform_state_implementation():
    assert (
        supervisor_multi_worker.build_multi_worker_status_payload
        is platform_multi_worker.build_multi_worker_status_payload
    )
    assert (
        supervisor_multi_worker.render_multi_worker_status_plain
        is platform_multi_worker.render_multi_worker_status_plain
    )


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
                "agent_loop_summary": {
                    "agent_loop_executed": True,
                    "agent_loop_planner_selected_step": "call_capability",
                    "agent_loop_tick_status": "executed",
                    "agent_loop_artifact_id": "artifact_safe_summary",
                    "tick_result": {"raw": "PRIVATE_TICK_PAYLOAD"},
                },
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
    assert workers["worker-a"]["recent_capacity_summary"] == {
        "record_id": "mem_worker_a_capacity",
        "capacity_id": "artifact.review",
        "summary": "Worker A selected artifact.review.",
        "agent_loop_summary": {
            "agent_loop_executed": True,
            "agent_loop_planner_selected_step": "call_capability",
            "agent_loop_tick_status": "executed",
            "agent_loop_artifact_id": "artifact_safe_summary",
        },
    }
    assert workers["worker-a"]["outgoing_events_total"] == 1
    assert workers["worker-b"]["memory_records_total"] == 1
    assert workers["worker-b"]["incoming_events_total"] == 2
    assert workers["worker-b"]["outgoing_events_total"] == 1
    assert "content" not in workers["worker-a"]
    assert "tick_result" not in output
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


def test_supervisor_dashboard_json_includes_multi_worker_status(tmp_path, capsys):
    codex_home = tmp_path / ".codex"
    memory_dir = codex_home / "memory"
    memory_dir.mkdir(parents=True)
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
                "agent_loop_summary": {
                    "agent_loop_executed": True,
                    "agent_loop_tick_status": "executed",
                    "agent_loop_tick_after_stop_reason": "tick_budget_exhausted",
                    "agent_loop_artifact_id": "artifact_safe_summary",
                    "step_result": {"raw": "PRIVATE_STEP_PAYLOAD"},
                },
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
    _publish_event(
        codex_home,
        from_worker="worker-a",
        to_worker="worker-b",
        event_type="handoff",
        message="Ready for Worker B.",
    )
    capsys.readouterr()

    assert (
        runner.main(
            [
                "dashboard",
                "--codex-home",
                str(codex_home),
                "--stale-after",
                "999999",
                "--json",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["multi_worker"]["summary"]["worker_count"] == 2
    assert payload["multi_worker"]["summary"]["capacity_calls_total"] == 1
    workers = {worker["name"]: worker for worker in payload["multi_worker"]["workers"]}
    assert workers["worker-a"]["capacity_ids"] == ["artifact.review"]
    assert workers["worker-a"]["recent_capacity_summary"] == {
        "record_id": "mem_worker_a_capacity",
        "capacity_id": "artifact.review",
        "summary": "Worker A selected artifact.review.",
        "agent_loop_summary": {
            "agent_loop_executed": True,
            "agent_loop_tick_status": "executed",
            "agent_loop_tick_after_stop_reason": "tick_budget_exhausted",
            "agent_loop_artifact_id": "artifact_safe_summary",
        },
    }
    assert workers["worker-b"]["incoming_events_total"] == 1
    assert "step_result" not in output
    assert "PRIVATE_" not in output


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
