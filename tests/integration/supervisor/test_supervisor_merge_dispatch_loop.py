from __future__ import annotations

import json
import sys

from isotope.features.notifications.flow import NotificationFlow
from isotope.features.supervisor.planner.goal_queue import record_supervisor_goal
from isotope.features.supervisor.merge.merge_dispatch import DEFAULT_TARGET_NAME
from isotope.features.supervisor.runner import main as supervisor_main


def test_supervisor_loop_dispatches_merge_worker_for_ready_integration(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    captured: list[list[str]] = []

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: _integration_review_payload(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._prepare_launch_worktree",
        lambda *, cwd, target_name: {
            "enabled": True,
            "source_cwd": str(cwd),
            "cwd": str(workspace),
            "worktree_root": str(workspace),
            "branch": f"supervisor/{target_name}-test",
        },
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            raise AssertionError("merge dispatch should not wait for planner LLM")

    class StubProcess:
        pid = 45678

    def stub_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        captured.append(command)
        return StubProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )
    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)

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
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["merge_dispatch"]["launch_spec"]["target_name"] == DEFAULT_TARGET_NAME
    assert payload["worker_lifecycle_decision"]["action"] == "dispatch_merge"
    assert payload["worker_lifecycle_decision"]["source"] == "integration_review"
    assert payload["worker_lifecycle_decision"]["summary"]["ready_to_integrate"] == 1
    assert payload["worker_lifecycle_execution"]["kind"] == "merge_dispatch"
    assert payload["worker_lifecycle_execution"]["next_step"] == "launch_merge_worker"
    assert payload["worker_lifecycle_execution"]["status"] == "ready_to_launch"
    assert payload["llm_action"]["kind"] == "launch_session"
    assert payload["llm_action"]["source"] == "integration_review"
    assert payload["executed"]["kind"] == "launch_session"
    assert payload["executed"]["managed"]["name"] == DEFAULT_TARGET_NAME
    assert payload["worker_lifecycle_decision"]["execution"]["kind"] == "launch_session"
    assert (
        payload["worker_lifecycle_decision"]["execution"]["display_kind"]
        == "merge_dispatch"
    )
    assert len(captured) == 1
    assert any(
        "source: supervisor integration-review payload" in item for item in captured[0]
    )
    prompt = captured[0][-1]
    assert "只允许按本工单要求推送当前工作分支，用于远端 CI 验证" in prompt
    assert "不主动推送远端" not in prompt
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    managed_records = [
        json.loads(line) for line in registry_path.read_text(encoding="utf-8").splitlines()
    ]
    assert managed_records[0]["worker_role"] == "merge_dispatch"
    assert payload["executed"]["managed"]["worker_role"] == "merge_dispatch"


def test_supervisor_loop_does_not_dispatch_merge_worker_inside_merge_worker_workspace(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = codex_home / "supervisor" / "logs" / "merge.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("merge worker 正在运行自己的 loop。\n", encoding="utf-8")
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-merge",
                "name": DEFAULT_TARGET_NAME,
                "cwd": str(workspace),
                "prompt": "合并 ready workers。",
                "command": ["codex", "exec", "-C", str(workspace), "合并 ready workers。"],
                "pid": 0,
                "started_at": "2026-05-20T00:00:00+00:00",
                "log_path": str(log_path),
                "status": "launched",
                "backend": "process",
                "worker_role": "merge_dispatch",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    def stub_collect_integration_reviews(**kwargs: object) -> dict[str, object]:
        raise AssertionError("merge worker workspace must not recursively review/dispatch")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        stub_collect_integration_reviews,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

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
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "merge_dispatch" not in payload
    assert payload["llm_action"]["kind"] == "monitor"
    assert payload["llm_action"]["reason"] == "当前工作区是 merge worker，跳过 merge dispatch。"


def test_supervisor_loop_does_not_dispatch_merge_worker_inside_repair_workspace(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = codex_home / "supervisor" / "logs" / "repair.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("repair worker 正在修复 promotion 失败。\n", encoding="utf-8")
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-repair",
                "name": "supervisor-merge-dispatch-repair",
                "cwd": str(workspace),
                "prompt": "修复 merge promotion 失败。",
                "command": ["codex", "exec", "-C", str(workspace), "修复 promotion。"],
                "pid": 0,
                "started_at": "2026-05-20T00:00:00+00:00",
                "log_path": str(log_path),
                "status": "launched",
                "backend": "process",
                "worker_role": "merge_repair",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    def stub_collect_integration_reviews(**kwargs: object) -> dict[str, object]:
        raise AssertionError("repair worker workspace must not recursively review/dispatch")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        stub_collect_integration_reviews,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

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
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "merge_dispatch" not in payload
    assert payload["llm_action"]["kind"] == "monitor"
    assert payload["llm_action"]["reason"] == "当前工作区是 merge_repair worker，跳过递归调度。"


def test_supervisor_daemon_status_surfaces_merge_dispatch_activity(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = codex_home / "supervisor" / "logs" / "daemon.log"
    state_path = codex_home / "supervisor" / "daemon.json"

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: _integration_review_payload(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._prepare_launch_worktree",
        lambda *, cwd, target_name: {
            "enabled": True,
            "source_cwd": str(cwd),
            "cwd": str(workspace),
            "worktree_root": str(workspace),
            "branch": f"supervisor/{target_name}-test",
        },
    )

    class StubProcess:
        pid = 45678

    def stub_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        return StubProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )
    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)

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
        ]
    )
    assert exit_code == 0
    loop_output = capsys.readouterr().out
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(loop_output, encoding="utf-8")
    state_path.write_text(
        json.dumps(
            {
                "pid": 45678,
                "status": "running",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": None,
                "command": [
                    sys.executable,
                    "-u",
                    "-m",
                    "isotope.features.supervisor.runner",
                    "loop",
                ],
                "codex_home": str(codex_home),
                "log_path": str(log_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda pid: pid == 45678,
    )

    exit_code = supervisor_main(
        ["daemon", "status", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    activity = payload["daemon"]["activity"]
    assert activity["recent_supervisor_action"]["kind"] == "merge_dispatch"
    assert activity["recent_supervisor_action"]["reason"] == (
        "ready_to_integrate workers require merge dispatch"
    )
    assert activity["recent_llm_action"]["kind"] == "merge_dispatch"
    assert activity["recent_llm_action"]["reason"] == (
        "ready_to_integrate workers require merge dispatch"
    )
    assert activity["recent_execution"] == {
        "status": "skipped",
        "detail": "merge_dispatch / merge dispatch launch adapter required",
    }


def test_supervisor_loop_waits_when_merge_worker_is_already_running(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = codex_home / "supervisor" / "logs" / "merge.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("merge worker 正在运行。\n", encoding="utf-8")
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-merge",
                "name": DEFAULT_TARGET_NAME,
                "cwd": str(workspace),
                "prompt": "合并 ready workers。",
                "command": ["codex", "exec", "-C", str(workspace), "合并 ready workers。"],
                "pid": 45678,
                "started_at": "2026-05-20T00:00:00+00:00",
                "log_path": str(log_path),
                "status": "launched",
                "backend": "process",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: _integration_review_payload(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._pid_is_running",
        lambda pid: pid == 45678,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._pid_is_running",
        lambda pid: pid == 45678,
        raising=False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            payload = json.loads(messages[1]["content"])
            assert payload["planner_priority"][0]["reason"] == "running_merge_worker"
            assert payload["command_suggestions"] == []
            return json.dumps(
                {
                    "kind": "monitor",
                    "reason": "merge worker 正在运行，等待下一轮。",
                },
                ensure_ascii=False,
            )

    def stub_launch_managed_codex(*args: object, **kwargs: object) -> object:
        raise AssertionError("running merge worker should not be relaunched")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.launch_managed_codex",
        stub_launch_managed_codex,
    )

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
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "merge_dispatch" not in payload
    assert payload["llm_action"]["kind"] == "monitor"
    assert payload["llm_action"]["reason"] == "merge worker 正在运行，等待下一轮。"


def test_supervisor_loop_auto_archives_done_merge_worker_after_integrated_review(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    merge_workspace = tmp_path / "merge-workspace"
    merge_workspace.mkdir()
    log_path = codex_home / "supervisor" / "logs" / "merge.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: merge worker 已完成并确认已集成。\n"
        "SUPERVISOR_NEXT: 等待 Supervisor 归档。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
                {
                    "record_id": "managed-merge",
                    "name": DEFAULT_TARGET_NAME,
                    "cwd": str(merge_workspace),
                "prompt": (
                    "WORK ORDER\n"
                    "source: supervisor integration-review payload\n"
                    "merge_candidates:\n"
                    "- ready-one / managed-ready\n"
                ),
                "command": ["codex", "exec", "-C", str(merge_workspace), "merge"],
                "pid": 0,
                "started_at": "2026-05-20T00:00:00+00:00",
                "log_path": str(log_path),
                "status": "launched",
                "backend": "process",
                "worker_role": "merge_dispatch",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    goal = record_supervisor_goal(
        codex_home=codex_home,
        cwd=workspace,
        goal="归档 merge worker。",
        target_name=DEFAULT_TARGET_NAME,
    )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: {
            "status": "ok",
            "base_ref": "main",
            "summary": {
                "total": 2,
                "merge_workers": 1,
                "ready_to_integrate": 0,
                "already_integrated": 1,
                "needs_review": 0,
                "conflict_risk": 0,
            },
            "groups": {
                "merge_workers": [
                    {
                        "record_id": "managed-merge",
                        "name": DEFAULT_TARGET_NAME,
                        "cwd": str(merge_workspace),
                        "supervisor_protocol": {"status": "done"},
                        "merge_worker": True,
                        "merge_worker_source": "worker_role",
                        "group": "merge_workers",
                    }
                ],
                "ready_to_integrate": [],
                "already_integrated": [{"record_id": "managed-ready"}],
                "needs_review": [],
                "conflict_risk": [],
            },
        },
    )

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
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["cleanup_archived"][0]["kind"] == "merge_worker"
    assert payload["cleanup_archived"][0]["managed"]["status"] == "archived"
    assert payload["cleanup_archived"][0]["goal"]["goal_id"] == goal.goal_id
    assert payload["worker_lifecycle_decision"]["action"] == "archive_integrated"
    assert payload["worker_lifecycle_decision"]["source"] == "cleanup"
    assert (
        payload["worker_lifecycle_decision"]["execution"]
        == payload["cleanup_archived"]
    )
    assert merge_workspace.exists() is True

    registry_events = [
        json.loads(line)
        for line in registry_path.read_text(encoding="utf-8").splitlines()
    ]
    assert registry_events[-1]["record_id"] == "managed-merge"
    assert registry_events[-1]["status"] == "archived"
    goal_events = [
        json.loads(line)
        for line in (codex_home / "supervisor" / "goals.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert goal_events[-1]["event"] == "supervisor_goal_archive"
    assert goal_events[-1]["goal_id"] == goal.goal_id
    notifications = NotificationFlow.in_process(codex_home).list_notifications()
    assert len(notifications) == 1
    assert notifications[0].notification_type == "supervisor_merge_worker_archive"
    assert notifications[0].source_ref == {
        "ref_type": "supervisor_merge_worker_archive",
        "record_id": "managed-merge",
        "status": "done",
        "group": "already_integrated",
    }


def test_supervisor_loop_keeps_done_merge_worker_when_candidates_not_integrated(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = codex_home / "supervisor" / "logs" / "merge.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("SUPERVISOR_STATUS: done\n", encoding="utf-8")
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-merge",
                "name": DEFAULT_TARGET_NAME,
                "cwd": str(workspace),
                "prompt": "merge_candidates:\n- ready-one / managed-ready\n",
                "command": ["codex", "exec", "-C", str(workspace), "merge"],
                "pid": 0,
                "started_at": "2026-05-20T00:00:00+00:00",
                "log_path": str(log_path),
                "status": "launched",
                "backend": "process",
                "worker_role": "merge_dispatch",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: {
            "status": "ok",
            "base_ref": "main",
            "summary": {
                "total": 2,
                "merge_workers": 1,
                "ready_to_integrate": 0,
                "already_integrated": 0,
                "needs_review": 0,
                "conflict_risk": 0,
            },
            "groups": {
                "merge_workers": [
                    {
                        "record_id": "managed-merge",
                        "name": DEFAULT_TARGET_NAME,
                        "cwd": str(workspace),
                        "supervisor_protocol": {"status": "done"},
                        "merge_worker": True,
                        "merge_worker_source": "worker_role",
                        "group": "merge_workers",
                    }
                ],
                "ready_to_integrate": [],
                "already_integrated": [],
                "needs_review": [],
                "conflict_risk": [],
            },
        },
    )

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
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "cleanup_archived" not in payload
    registry_events = [
        json.loads(line)
        for line in registry_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [item["status"] for item in registry_events] == ["launched"]


def _integration_review_payload() -> dict[str, object]:
    return {
        "status": "ok",
        "base_ref": "main",
        "summary": {
            "total": 1,
            "ready_to_integrate": 1,
            "already_integrated": 0,
            "needs_review": 0,
            "conflict_risk": 0,
        },
        "groups": {
            "ready_to_integrate": [
                {
                    "record_id": "managed-ready",
                    "name": "ready-one",
                    "cwd": "/repo/.worktrees/supervisor/ready-12345678",
                    "branch": "supervisor/ready-12345678",
                    "worker_commit": "ready111",
                    "base_ref": "main",
                    "reason": "worker 已完成、分支干净、main 尚未包含且未检测到 merge conflict。",
                    "dirty": False,
                    "merge_conflict": False,
                }
            ],
            "conflict_risk": [],
            "needs_review": [],
            "already_integrated": [],
        },
    }
