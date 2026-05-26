from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from isotope.features.supervisor.flow import CodexSupervisorFlow
from isotope.features.supervisor.planner.decision_requests import read_active_decision_requests
from isotope.features.supervisor.state.lane_state import (
    default_lane_state_path,
    read_lane_states,
)
from isotope.features.supervisor.runner import (
    _auto_retry_exited_process_workers,
    _execute_launch_action,
    main as supervisor_main,
)


def test_supervisor_daemon_status_records_nonzero_worker_failure(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = codex_home / "supervisor" / "daemon.json"
    log_path = codex_home / "supervisor" / "logs" / "daemon.log"
    worker_log_path = codex_home / "supervisor" / "logs" / "managed-001.log"
    state_path.parent.mkdir(parents=True)
    log_path.parent.mkdir(parents=True)
    worker_log_path.write_text(
        "running tests\n"
        "stderr: AssertionError: expected clean worker result\n"
        "Process exited with code 2\n",
        encoding="utf-8",
    )
    state_path.write_text(
        json.dumps(
            {
                "pid": 45678,
                "status": "running",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": None,
                "command": [sys.executable, "-m", "isotope.features.supervisor.runner"],
                "codex_home": str(codex_home),
                "log_path": str(log_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    _write_managed_record(
        codex_home,
        workspace=workspace,
        log_path=worker_log_path,
        pid=45679,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda pid: pid == 45678,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._pid_is_running",
        lambda pid: False,
        raising=False,
    )

    exit_code = supervisor_main(
        ["daemon", "status", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    worker = payload["daemon"]["activity"]["recent_worker"]
    assert worker["status"] == "error"
    assert worker["failure"] == {
        "reason": "exit_code",
        "exit_code": 2,
        "stderr_summary": "stderr: AssertionError: expected clean worker result",
        "record_id": "managed-001",
    }
    state = read_lane_states(default_lane_state_path(codex_home))["worker-a"]
    assert state.last_status == "failed"
    assert state.last_failure_reason == "exit_code"
    assert state.last_failure_exit_code == 2
    assert state.last_failure_stderr_summary == (
        "stderr: AssertionError: expected clean worker result"
    )
    assert state.last_failure_record_id == "managed-001"


def test_supervisor_daemon_status_records_usage_limit_worker_failure(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = codex_home / "supervisor" / "daemon.json"
    log_path = codex_home / "supervisor" / "logs" / "daemon.log"
    worker_log_path = codex_home / "supervisor" / "logs" / "managed-001.log"
    state_path.parent.mkdir(parents=True)
    log_path.parent.mkdir(parents=True)
    worker_log_path.write_text(
        "Reading additional input from stdin...\n"
        "ERROR: You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage "
        "to purchase more credits or try again at 5:04 AM.\n",
        encoding="utf-8",
    )
    state_path.write_text(
        json.dumps(
            {
                "pid": 45678,
                "status": "running",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": None,
                "command": [sys.executable, "-m", "isotope.features.supervisor.runner"],
                "codex_home": str(codex_home),
                "log_path": str(log_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    _write_managed_record(
        codex_home,
        workspace=workspace,
        log_path=worker_log_path,
        pid=45679,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda pid: pid == 45678,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._pid_is_running",
        lambda pid: False,
        raising=False,
    )

    exit_code = supervisor_main(
        ["daemon", "status", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    worker = payload["daemon"]["activity"]["recent_worker"]
    assert worker["status"] == "error"
    assert worker["failure"]["reason"] == "usage_limit"
    assert worker["failure"]["exit_code"] is None
    assert "try again at 5:04 AM" in worker["failure"]["stderr_summary"]
    state = read_lane_states(default_lane_state_path(codex_home))["worker-a"]
    assert state.last_status == "failed"
    assert state.last_failure_reason == "usage_limit"
    assert state.last_failure_exit_code is None
    assert "try again at 5:04 AM" in state.last_failure_stderr_summary


def test_supervisor_daemon_status_suppresses_live_activity_when_stopped(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = codex_home / "supervisor" / "daemon.json"
    log_path = codex_home / "supervisor" / "logs" / "daemon.log"
    worker_log_path = codex_home / "supervisor" / "logs" / "managed-001.log"
    state_path.parent.mkdir(parents=True)
    log_path.parent.mkdir(parents=True)
    worker_log_path.write_text("SUPERVISOR_STATUS: working\n", encoding="utf-8")
    log_path.write_text(
        "[LLM 白名单动作]\n"
        "monitor / merge dispatch worker 正在运行，等待下一轮状态变化。\n"
        "已跳过：merge dispatch worker 正在运行，等待下一轮状态变化。\n",
        encoding="utf-8",
    )
    state_path.write_text(
        json.dumps(
            {
                "pid": 45678,
                "status": "stopped",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": "2026-05-18T10:05:00+00:00",
                "command": [sys.executable, "-m", "isotope.features.supervisor.runner"],
                "codex_home": str(codex_home),
                "log_path": str(log_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    _write_managed_record(
        codex_home,
        workspace=workspace,
        log_path=worker_log_path,
        pid=45679,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._pid_is_running",
        lambda pid: False,
        raising=False,
    )

    exit_code = supervisor_main(
        ["daemon", "status", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    activity = payload["daemon"]["activity"]
    assert activity["recent_llm_action"] is None
    assert activity["recent_execution"] is None
    assert activity["recent_worker"] is None
    assert activity["night_summary"]["running_workers"] == 0
    assert activity["night_summary"]["recent_worker_name"] is None


def test_supervisor_launch_action_degrades_after_recorded_worker_failure(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = default_lane_state_path(codex_home)
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "worker-a": {
                    "name": "worker-a",
                    "tmux_session": None,
                    "last_status": "failed",
                    "prompt_count": 0,
                    "last_failure_reason": "timeout",
                    "last_failure_exit_code": None,
                    "last_failure_stderr_summary": "worker exceeded run budget",
                    "last_failure_record_id": "managed-001",
                    "last_failed_at": "2026-05-18T10:05:00+00:00",
                    "failure_count": 1,
                }
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._prepare_launch_worktree",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not relaunch")),
    )

    result = _execute_launch_action(
        _runner_args(codex_home),
        {
            "kind": "launch_session",
            "target_name": "worker-a",
            "cwd": str(workspace),
            "prompt": "继续 worker A",
        },
    )

    assert result["kind"] == "monitor"
    assert result["skipped"] is True
    assert result["reason"] == "worker failure recorded"
    assert result["degraded_from"] == "launch_session"
    assert result["lane_state"]["last_failure_reason"] == "timeout"


def test_supervisor_loop_does_not_auto_retry_usage_limit_worker(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    worker_log_path = codex_home / "supervisor" / "logs" / "managed-001.log"
    worker_log_path.parent.mkdir(parents=True)
    worker_log_path.write_text(
        "ERROR: You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage "
        "to purchase more credits or try again at 5:04 AM.\n",
        encoding="utf-8",
    )
    _write_managed_record(
        codex_home,
        workspace=workspace,
        log_path=worker_log_path,
        pid=45679,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._pid_is_running",
        lambda pid: False,
        raising=False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.launch_managed_codex",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not relaunch")),
    )
    args = _runner_args(codex_home)
    args.max_worker_retry_count = 2

    retried = _auto_retry_exited_process_workers(args)

    assert retried == []
    state = read_lane_states(default_lane_state_path(codex_home))["worker-a"]
    assert state.last_failure_reason == "usage_limit"
    requests = read_active_decision_requests(codex_home=codex_home)
    assert len(requests) == 1
    assert requests[0].reason == "worker retry limit exceeded"
    assert requests[0].target_name == "worker-a"


def test_supervisor_dashboard_marks_recorded_worker_failure(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    worker_log_path = codex_home / "supervisor" / "logs" / "managed-001.log"
    worker_log_path.parent.mkdir(parents=True)
    worker_log_path.write_text("worker exited before status report\n", encoding="utf-8")
    _write_managed_record(
        codex_home,
        workspace=workspace,
        log_path=worker_log_path,
        pid=45679,
    )
    state_path = default_lane_state_path(codex_home)
    state_path.write_text(
        json.dumps(
            {
                "worker-a": {
                    "name": "worker-a",
                    "tmux_session": None,
                    "last_status": "failed",
                    "prompt_count": 0,
                    "last_failure_reason": "exit_code",
                    "last_failure_exit_code": 1,
                    "last_failure_stderr_summary": "stderr: command failed",
                    "last_failure_record_id": "managed-001",
                    "last_failed_at": "2026-05-18T10:05:00+00:00",
                    "failure_count": 1,
                }
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: __import__("datetime").datetime.fromisoformat(
            "2026-05-18T10:06:00+00:00"
        ),
        process_checker=lambda pid: False,
    ).scan()

    session = report.sessions[0]
    assert session.status == "error"
    assert session.reason == "worker failed: exit_code"
    assert session.to_dict()["managed_failure"] == {
        "reason": "exit_code",
        "exit_code": 1,
        "stderr_summary": "stderr: command failed",
        "record_id": "managed-001",
        "failed_at": "2026-05-18T10:05:00+00:00",
    }


def _runner_args(codex_home: Path) -> argparse.Namespace:
    return argparse.Namespace(
        codex_home=str(codex_home),
        max_run_minutes=0,
        prompt_cooldown=0,
        worker_codex_model=None,
        worker_codex_config=[],
        worker_profile="coding",
        max_worker_retry_count=2,
        webhook_url=None,
        webhook_secret=None,
    )


def _write_managed_record(
    codex_home: Path,
    *,
    workspace: Path,
    log_path: Path,
    pid: int,
) -> None:
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "worker-a",
                "cwd": str(workspace),
                "prompt": "继续 worker A",
                "command": ["codex", "exec", "-C", str(workspace), "继续"],
                "pid": pid,
                "started_at": "2026-05-18T10:01:00+00:00",
                "log_path": str(log_path),
                "status": "launched",
                "backend": "process",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
