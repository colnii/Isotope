from __future__ import annotations

import json
import sys

from isotope.features.supervisor.merge_dispatch import DEFAULT_TARGET_NAME
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
        lambda *, codex_home, base_ref, include_unfinished: _integration_review_payload(),
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

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            raise AssertionError("merge dispatch should not wait for planner LLM")

    class FakeProcess:
        pid = 45678

    def fake_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured.append(command)
        return FakeProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FakeProvider(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )
    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)

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
    assert payload["merge_dispatch"]["launch_spec"]["target_name"] == DEFAULT_TARGET_NAME
    assert payload["llm_action"]["kind"] == "launch_session"
    assert payload["llm_action"]["source"] == "integration_review"
    assert payload["executed"]["kind"] == "launch_session"
    assert payload["executed"]["managed"]["name"] == DEFAULT_TARGET_NAME
    assert len(captured) == 1
    assert any(
        "source: supervisor integration-review payload" in item for item in captured[0]
    )


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
        lambda *, codex_home, base_ref, include_unfinished: _integration_review_payload(),
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

    class FakeProcess:
        pid = 45678

    def fake_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        return FakeProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )
    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)

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
    assert activity["recent_llm_action"]["kind"] == "merge_dispatch"
    assert activity["recent_llm_action"]["reason"] == (
        "ready_to_integrate workers require merge dispatch"
    )
    assert activity["recent_execution"]["status"] == "executed"
    assert activity["recent_execution"]["detail"].startswith("merge_dispatch / ")


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
        lambda *, codex_home, base_ref, include_unfinished: _integration_review_payload(),
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

    class FakeProvider:
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

    def fake_launch_managed_codex(*args: object, **kwargs: object) -> object:
        raise AssertionError("running merge worker should not be relaunched")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FakeProvider(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.launch_managed_codex",
        fake_launch_managed_codex,
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
