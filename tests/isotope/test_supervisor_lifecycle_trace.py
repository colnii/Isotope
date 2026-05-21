from __future__ import annotations

import json
from datetime import datetime, timezone

from isotope.features.supervisor.decision_requests import record_decision_request
from isotope.features.supervisor.goal_queue import record_supervisor_goal
from isotope.features.supervisor.registry import (
    ManagedCodexRecord,
    append_managed_record,
    default_registry_path,
)
from isotope.features.supervisor.runner import main as supervisor_main


NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def test_supervisor_trace_projects_lifecycle_ledgers(tmp_path, capsys):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    goal = record_supervisor_goal(
        codex_home=codex_home,
        cwd=workspace,
        goal="继续推进 Supervisor 长跑能力。",
        target_name="trace-target",
        now=lambda: NOW,
    )
    record_decision_request(
        codex_home=codex_home,
        action={
            "session_id": f"goal:{goal.goal_id}",
            "goal_id": goal.goal_id,
            "target_name": "trace-target",
            "question": "是否继续合并 worker？",
            "reason": "merge promotion failed",
            "context_status": "conflict",
            "gate": {
                "codex_requested_decision": True,
                "instructions_exhausted": True,
                "context_status": "conflict",
            },
        },
        now=lambda: NOW,
    )
    _append_record(
        codex_home,
        workspace=workspace,
        record_id="managed-worker",
        name="worker-a",
        worker_role="worker",
        protocol_status="working",
    )
    _append_record(
        codex_home,
        workspace=workspace,
        record_id="managed-repair",
        name="repair-a",
        worker_role="merge_repair",
        protocol_status="done",
    )
    _append_record(
        codex_home,
        workspace=workspace,
        record_id="managed-archived",
        name="archived-a",
        worker_role="merge_dispatch",
        protocol_status="done",
        status="archived",
    )

    exit_code = supervisor_main(
        [
            "trace",
            "--codex-home",
            str(codex_home),
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["summary"] == {
        "active_goals": 1,
        "active_managed_workers": 2,
        "active_decisions": 1,
        "merge_workers": 0,
        "repair_workers": 1,
        "archived_workers": 1,
    }
    assert payload["next_attention"]["kind"] == "answer_decision"
    assert payload["stages"]["goal_queue"]["active"][0]["target_name"] == "trace-target"
    assert payload["stages"]["workers"]["active"][0]["name"] == "worker-a"
    assert payload["stages"]["merge"]["repair_workers"][0]["name"] == "repair-a"
    assert payload["stages"]["cleanup"]["archived_workers"][0]["name"] == "archived-a"
    assert payload["stages"]["decisions"]["active"][0]["target_name"] == "trace-target"


def _append_record(
    codex_home,
    *,
    workspace,
    record_id: str,
    name: str,
    worker_role: str,
    protocol_status: str,
    status: str = "launched",
) -> None:
    log_path = codex_home / "supervisor" / "logs" / f"{record_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(
            [
                f"SUPERVISOR_STATUS: {protocol_status}",
                f"SUPERVISOR_SUMMARY: {name} summary",
                "SUPERVISOR_NEXT: 等待下一步",
            ]
        ),
        encoding="utf-8",
    )
    append_managed_record(
        default_registry_path(codex_home),
        ManagedCodexRecord(
            record_id=record_id,
            name=name,
            cwd=str(workspace),
            prompt=f"prompt for {name}",
            command=("codex", "exec", "-C", str(workspace), "prompt"),
            pid=0,
            started_at=NOW.isoformat(),
            log_path=str(log_path),
            status=status,
            backend="process",
            worker_role=worker_role,
        ),
    )
