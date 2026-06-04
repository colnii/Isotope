from __future__ import annotations

import argparse
import json
from dataclasses import asdict

import isotope.features.supervisor.state.multi_worker as supervisor_multi_worker
import isotope.platform.state.multi_worker as platform_multi_worker
from isotope.features.supervisor import runner
from isotope.features.supervisor.commands.handlers import capacity as capacity_command
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
                "agent_loop_result": {
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
    assert workers["worker-a"]["recent_capacity_result"] == {
        "record_id": "mem_worker_a_capacity",
        "capacity_id": "artifact.review",
        "summary": "Worker A selected artifact.review.",
        "agent_loop_result": {
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


def test_supervisor_worker_manager_plain_output_shows_supervised_capacity_runs(
    tmp_path,
    capsys,
):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
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
                "agent_loop_result": {
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
    capsys.readouterr()

    assert runner.main(["worker-manager", "--root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "supervised_capacity_runs: 1" in output
    assert (
        "capacity_run: worker-a / artifact.review / tick=executed / "
        "step=call_capability / artifact=artifact_safe_summary"
    ) in output
    assert "Worker A selected artifact.review." in output
    assert "tick_result" not in output
    assert "PRIVATE_" not in output


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
                "agent_loop_result": {
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
    assert workers["worker-a"]["recent_capacity_result"] == {
        "record_id": "mem_worker_a_capacity",
        "capacity_id": "artifact.review",
        "summary": "Worker A selected artifact.review.",
        "agent_loop_result": {
            "agent_loop_executed": True,
            "agent_loop_tick_status": "executed",
            "agent_loop_tick_after_stop_reason": "tick_budget_exhausted",
            "agent_loop_artifact_id": "artifact_safe_summary",
        },
    }
    assert workers["worker-b"]["incoming_events_total"] == 1
    assert "step_result" not in output
    assert "PRIVATE_" not in output


def test_supervisor_dashboard_plain_shows_capacity_result(tmp_path, capsys):
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
                "agent_loop_result": {
                    "agent_loop_executed": True,
                    "agent_loop_planner_selected_step": "call_capability",
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
    capsys.readouterr()

    assert (
        runner.main(
            [
                "dashboard",
                "--codex-home",
                str(codex_home),
                "--stale-after",
                "999999",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "能力调用：1" in output
    assert "受监督执行：workers=1 agent_loop_calls=1 recent=1" in output
    assert "- worker-a artifact.review tick=executed step=call_capability" in output
    assert "artifact=artifact_safe_summary" in output
    assert "Worker A selected artifact.review." in output
    assert "step_result" not in output
    assert "PRIVATE_" not in output


def test_capacity_action_record_flows_into_dashboard_multi_worker_status(
    tmp_path,
    monkeypatch,
    capsys,
):
    codex_home = tmp_path / ".codex"
    agent_loop = {
        "handoff": {
            "initial_next_tick_kind": "planner_step",
            "post_step_phase": "ready",
            "post_step_should_continue": True,
            "post_step_stop_reason": None,
        },
        "planner_output": {
            "selected_step": "call_capability",
            "capability_id": "artifact.review",
        },
        "tick_result": {
            "tick_status": "executed",
            "after_policy": {"must_stop_reason": "tick_budget_exhausted"},
            "planner_result": {
                "step_result": {
                    "action_result": {
                        "artifact_ref": {"artifact_id": "artifact_safe_summary"},
                        "raw": "PRIVATE_ACTION_PAYLOAD",
                    }
                }
            },
        },
    }

    def stub_execute_agent_loop_capacity_step(**kwargs):
        return agent_loop

    monkeypatch.setattr(
        capacity_command,
        "_execute_agent_loop_capacity_step",
        stub_execute_agent_loop_capacity_step,
    )
    result = capacity_command.execute_capacity_action(
        argparse.Namespace(codex_home=str(codex_home), name="capa"),
        {
            "kind": "call_capacity",
            "capacity_id": "artifact.review",
            "reason": "ready",
        },
        {
            "capacity_call_specs": [
                {
                    "capacity_id": "artifact.review",
                    "goal": "检查 artifact review 能力。",
                    "inputs": {},
                }
            ],
            "capacity_decisions": [
                {
                    "kind": "supervisor_capacity_decision",
                    "next_action": "call_capacity",
                    "reason": "ready",
                    "capacity_id": "artifact.review",
                    "can_execute_agent_loop": True,
                    "missing_inputs": [],
                    "blocking_reasons": [],
                }
            ],
        },
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
    assert payload["multi_worker"]["summary"]["capacity_calls_total"] == 1
    workers = {worker["name"]: worker for worker in payload["multi_worker"]["workers"]}
    recent_capacity = workers["capa"]["recent_capacity_result"]
    assert workers["capa"]["recent_capacity_result"] == {
        "record_id": recent_capacity["record_id"],
        "capacity_id": "artifact.review",
        "summary": "capa called artifact.review via agent loop.",
        "agent_loop_result": result["agent_loop_result"],
    }
    supervised = payload["multi_worker"]["supervised_execution"]
    assert supervised == {
        "status": "ok",
        "capacity_workers_total": 1,
        "capacity_agent_loop_calls_total": 1,
        "recent_capacity_runs": [
            {
                "worker": "capa",
                "record_id": recent_capacity["record_id"],
                "capacity_id": "artifact.review",
                "summary": "capa called artifact.review via agent loop.",
                "agent_loop_result": result["agent_loop_result"],
            }
        ],
    }
    assert recent_capacity["record_id"].startswith("mem_capacity_")
    assert "tick_result" not in output
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
