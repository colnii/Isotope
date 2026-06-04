from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from isotope.features.supervisor.planner.goal_queue import (
    record_supervisor_goal,
    record_supervisor_goal_status,
)
from isotope.features.supervisor.registry import (
    default_registry_path,
    read_managed_records,
)
from isotope.features.supervisor.runner import main as supervisor_main


class LowWaterClosedLoopProvider:
    def summarize(self, messages: list[dict[str, str]]) -> str:
        payload = json.loads(messages[1]["content"])
        assert payload["planning_trigger"] == "low_water"
        return json.dumps(
            {
                "plan_summary": "自动闭环验收：补两个 worker 目标。",
                "goals": [
                    {
                        "goal": "完成自动闭环验收 worker A。",
                        "target_name": "auto-loop-worker-a",
                        "reason": "验证低水位补任务能进入 fanout。",
                    },
                    {
                        "goal": "完成自动闭环验收 worker B。",
                        "target_name": "auto-loop-worker-b",
                        "reason": "验证多个 active goals 能并行启动。",
                    },
                ],
            },
            ensure_ascii=False,
        )


def test_supervisor_loop_replenishes_done_workers_and_dispatches_merge_e2e(
    tmp_path: Path,
    capsys: Any,
    monkeypatch: Any,
) -> None:
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_current_docs(workspace)
    launched_commands: list[list[str]] = []

    class StubProcess:
        def __init__(self, pid: int) -> None:
            self.pid = pid

    def stub_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        del cwd, stdin, stdout, stderr, start_new_session
        launched_commands.append(command)
        return StubProcess(51000 + len(launched_commands))

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: LowWaterClosedLoopProvider(),
    )
    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: _ready_done_worker_reviews(
            codex_home=Path(codex_home),
            base_ref=base_ref,
        ),
    )

    first_payload = _run_loop(
        codex_home=codex_home,
        workspace=workspace,
        capsys=capsys,
        extra_args=[
            "--goal-low-water",
            "2",
            "--goal-replenish-limit",
            "2",
        ],
    )

    assert first_payload["goal_replenishment"]["written_count"] == 2
    assert first_payload["llm_action"]["kind"] == "fanout_launch_sessions"
    assert first_payload["executed"]["summary"]["launched"] == 2
    assert first_payload["executed"]["summary"]["skipped"] == 0
    assert [item["managed"]["name"] for item in first_payload["executed"]["results"]] == [
        "auto-loop-worker-a",
        "auto-loop-worker-b",
    ]

    _write_done_worker_logs(codex_home)

    second_payload = _run_loop(
        codex_home=codex_home,
        workspace=workspace,
        capsys=capsys,
        extra_args=[],
    )

    assert [item["status"] for item in second_payload["goal_updates"]] == [
        "done",
        "done",
    ]
    assert second_payload["active_goals"] == []
    assert second_payload["merge_dispatch"]["integration_review"]["summary"][
        "ready_to_integrate"
    ] == 2
    assert second_payload["llm_action"]["kind"] == "launch_session"
    assert second_payload["llm_action"]["source"] == "integration_review"
    assert second_payload["executed"]["display_kind"] == "merge_dispatch"
    assert second_payload["executed"]["managed"]["name"] == "supervisor-merge-dispatch"
    assert "cleanup_archived" not in second_payload
    assert len(launched_commands) == 3
    assert any(
        "source: supervisor integration-review payload" in part
        for part in launched_commands[-1]
    )


def test_supervisor_loop_dispatches_merge_before_launching_more_fanout(
    tmp_path: Path,
    capsys: Any,
    monkeypatch: Any,
) -> None:
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_current_docs(workspace)
    launched_commands: list[list[str]] = []

    class StubProcess:
        def __init__(self, pid: int) -> None:
            self.pid = pid

    def stub_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        del cwd, stdin, stdout, stderr, start_new_session
        launched_commands.append(command)
        return StubProcess(52000 + len(launched_commands))

    done_goal = record_supervisor_goal(
        codex_home=codex_home,
        cwd=workspace,
        goal="完成等待合并的 worker。",
        target_name="done-worker",
    )
    record_supervisor_goal_status(
        codex_home=codex_home,
        goal_id=done_goal.goal_id,
        status="done",
        target_name="done-worker",
        summary="worker 已完成。",
        next_step="等待 merge worker 合入。",
    )
    record_supervisor_goal(
        codex_home=codex_home,
        cwd=workspace,
        goal="继续执行后续 worker A。",
        target_name="pending-worker-a",
    )
    record_supervisor_goal(
        codex_home=codex_home,
        cwd=workspace,
        goal="继续执行后续 worker B。",
        target_name="pending-worker-b",
    )

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda **kwargs: _ready_payload_for_names(
            base_ref=kwargs["base_ref"],
            names=["done-worker"],
        ),
    )

    payload = _run_loop(
        codex_home=codex_home,
        workspace=workspace,
        capsys=capsys,
        extra_args=[
            "--max-fanout-launches",
            "3",
        ],
    )

    assert "fanout_plan" not in payload
    assert payload["merge_dispatch"]["integration_review"]["summary"][
        "ready_to_integrate"
    ] == 1
    assert payload["llm_action"]["kind"] == "launch_session"
    assert payload["llm_action"]["source"] == "integration_review"
    assert payload["executed"]["display_kind"] == "merge_dispatch"
    assert payload["executed"]["managed"]["name"] == "supervisor-merge-dispatch"
    assert len(launched_commands) == 1
    assert any(
        "source: supervisor integration-review payload" in part
        for part in launched_commands[0]
    )


def _run_loop(
    *,
    codex_home: Path,
    workspace: Path,
    capsys: Any,
    extra_args: list[str],
) -> dict[str, Any]:
    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--workspace-root",
            str(workspace),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--no-auto-adopt",
            "--json",
            "--merge-dispatch-execute",
            *extra_args,
        ]
    )
    assert exit_code == 0
    return json.loads(capsys.readouterr().out)


def _write_current_docs(root: Path) -> None:
    current = root / "docs" / "current"
    current.mkdir(parents=True)
    (current / "status.md").write_text(
        "Supervisor 需要自动补任务并闭环验收。\n",
        encoding="utf-8",
    )
    (current / "agent-task-queue.md").write_text(
        "- 让 auto loop 从 goal 到 merge dispatch 串起来。\n",
        encoding="utf-8",
    )
    (current / "supervisor-capability-map.md").write_text(
        "- loop 支持 goal replenishment、fanout 和 integration review。\n",
        encoding="utf-8",
    )


def _write_done_worker_logs(codex_home: Path) -> None:
    for record in read_managed_records(default_registry_path(codex_home)):
        if not record.name.startswith("auto-loop-worker-"):
            continue
        Path(record.log_path).write_text(
            "SUPERVISOR_STATUS: done\n"
            f"SUPERVISOR_SUMMARY: {record.name} 已完成并等待合并。\n"
            "SUPERVISOR_NEXT: 等待 Supervisor 归档。\n",
            encoding="utf-8",
        )


def _ready_done_worker_reviews(
    *,
    codex_home: Path,
    base_ref: str,
) -> dict[str, Any]:
    ready = [
        {
            "record_id": record.record_id,
            "name": record.name,
            "cwd": record.cwd,
            "branch": f"supervisor/{record.name}",
            "worker_commit": f"{record.name}-commit",
            "base_ref": base_ref,
            "reason": "worker 已完成、分支干净、main 尚未包含且未检测到 merge conflict。",
            "dirty": False,
            "merge_conflict": False,
        }
        for record in read_managed_records(default_registry_path(codex_home))
        if record.name.startswith("auto-loop-worker-")
        and "SUPERVISOR_STATUS: done" in Path(record.log_path).read_text(encoding="utf-8")
    ]
    return {
        "status": "ok",
        "base_ref": base_ref,
        "summary": {
            "total": len(ready),
            "ready_to_integrate": len(ready),
            "already_integrated": 0,
            "needs_review": 0,
            "conflict_risk": 0,
        },
        "groups": {
            "ready_to_integrate": ready,
            "conflict_risk": [],
            "needs_review": [],
            "already_integrated": [],
        },
        "safety": {"auto_merge": False, "push": False, "delete_branch": False},
    }


def _ready_payload_for_names(*, base_ref: str, names: list[str]) -> dict[str, Any]:
    ready = [
        {
            "record_id": f"managed-{name}",
            "name": name,
            "cwd": f"/tmp/{name}",
            "branch": f"supervisor/{name}",
            "worker_commit": f"{name}-commit",
            "base_ref": base_ref,
            "reason": "worker 已完成、分支干净、main 尚未包含且未检测到 merge conflict。",
            "dirty": False,
            "merge_conflict": False,
        }
        for name in names
    ]
    return {
        "status": "ok",
        "base_ref": base_ref,
        "summary": {
            "total": len(ready),
            "ready_to_integrate": len(ready),
            "already_integrated": 0,
            "needs_review": 0,
            "conflict_risk": 0,
        },
        "groups": {
            "ready_to_integrate": ready,
            "conflict_risk": [],
            "needs_review": [],
            "already_integrated": [],
            "merge_workers": [],
        },
        "safety": {"auto_merge": False, "push": False, "delete_branch": False},
    }
