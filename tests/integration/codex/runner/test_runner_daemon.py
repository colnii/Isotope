from __future__ import annotations

import argparse
import http.client
import json
import os
import signal
import shlex
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ..helpers import (
    CONTINUE_REQUEST_TEXT,
    EXISTING_WORKSPACE,
    NON_STALE_SECONDS,
    NOW,
    STATUS_REQUEST_TEXT,
    _add_supervisor_goal,
    _append_supervisor_goal_status,
    _assistant_message,
    _codex_operation_context_result,
    _event,
    _record_cleanup_lifecycle_execution,
    _runner_args,
    _supervisor_send_command,
    _tmux_send_calls,
    _user_message,
    _write_managed_tmux_record,
    _write_session,
    _write_session_index,
    _write_state_threads,
)
from isotope.features.notifications.flow import NotificationFlow
from isotope.features.supervisor import flow as supervisor_flow
from isotope.features.supervisor import runner as supervisor_runner
from isotope.features.supervisor.flow import (
    CodexSessionSummary,
    CodexSupervisorFlow,
    CodexSupervisorReport,
    render_plain_report,
)
from isotope.features.supervisor.llm_action.llm_summary import (
    PoolEntry,
    PooledSummaryProvider,
    build_llm_action_messages,
    build_llm_summary_messages,
    generate_llm_action_decision,
    generate_llm_summary,
    resolve_summary_provider_from_env,
)
from isotope.features.supervisor.merge.merge_dispatch import DEFAULT_TARGET_NAME
from isotope.features.supervisor.notifications.context import (
    read_recent_context_results,
    request_project_context,
)
from isotope.features.supervisor.runner import (
    EXECUTABLE_ADVICE_TEXT,
    _advice_payload,
    _dashboard_payload,
    _execute_context_action,
    _execute_llm_action,
    _print_dashboard_plain,
    _report_fingerprint,
    _supervise_payload,
    main as supervisor_main,
)
from isotope.features.supervisor.state.worker_lifecycle import (
    record_worker_lifecycle_decision,
)

def test_codex_supervisor_daemon_activity_plain_includes_degraded_snapshot_reason(
    capsys,
):
    supervisor_runner._print_daemon_activity_plain(
        {
            "state_snapshot": {
                "status": "ok",
                "kind": "supervisor_state_snapshot",
                "summary": {},
            }
        }
    )

    text = capsys.readouterr().out
    assert "状态快照：supervisor_state_snapshot degraded / missing schema_version" in text



def test_codex_supervisor_runner_daemon_start_spawns_background_loop(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    captured: dict[str, object] = {}

    class StubProcess:
        pid = 45678

    def stub_popen(
        command: list[str],
        *,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        captured["command"] = command
        captured["stdin"] = stdin
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return StubProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        stub_popen,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda _: False,
    )

    exit_code = supervisor_main(
        [
            "daemon",
            "start",
            "--codex-home",
            str(codex_home),
            "--interval",
            "7",
            "--limit",
            "3",
            "--worker-codex-model",
            "gpt-5.4-mini",
            "--worker-codex-config",
            'model_reasoning_effort="low"',
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["daemon"]["status"] == "running"
    assert payload["daemon"]["pid"] == 45678
    assert payload["daemon"]["codex_home"] == str(codex_home)
    assert payload["daemon"]["log_path"].endswith("daemon.log")
    assert payload["daemon"]["command"] == [
        sys.executable,
        "-u",
        "-m",
        "isotope.features.supervisor.runner",
        "loop",
        "--codex-home",
        str(codex_home),
        "--interval",
        "7",
        "--limit",
        "3",
        "--worker-codex-model",
        "gpt-5.4-mini",
        "--worker-codex-config",
        'model_reasoning_effort="low"',
    ]
    assert captured["command"] == payload["daemon"]["command"]
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["stderr"] is subprocess.STDOUT
    assert captured["start_new_session"] is True

    state_path = codex_home / "supervisor" / "daemon.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    persisted = dict(payload["daemon"])
    persisted.pop("action")
    assert state == persisted



def test_codex_supervisor_runner_daemon_start_passes_merge_automation_flags(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    captured: dict[str, object] = {}

    class StubProcess:
        pid = 45678

    def stub_popen(
        command: list[str],
        *,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        captured["command"] = command
        return StubProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        stub_popen,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda _: False,
    )

    exit_code = supervisor_main(
        [
            "daemon",
            "start",
            "--codex-home",
            str(codex_home),
            "--merge-dispatch-execute",
            "--auto-merge-promote",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "--merge-dispatch-execute" in payload["daemon"]["command"]
    assert "--auto-merge-promote" in payload["daemon"]["command"]
    assert captured["command"] == payload["daemon"]["command"]



def test_codex_supervisor_runner_daemon_start_passes_lifecycle_archive_execute_flag(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    captured: dict[str, object] = {}

    class StubProcess:
        pid = 45678

    def stub_popen(
        command: list[str],
        *,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        captured["command"] = command
        return StubProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        stub_popen,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda _: False,
    )

    exit_code = supervisor_main(
        [
            "daemon",
            "start",
            "--codex-home",
            str(codex_home),
            "--lifecycle-archive-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "--lifecycle-archive-execute" in payload["daemon"]["command"]
    assert "--lifecycle-cleanup-execute" not in payload["daemon"]["command"]
    assert captured["command"] == payload["daemon"]["command"]



def test_codex_supervisor_runner_daemon_start_defaults_to_strong_worker(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    captured: dict[str, object] = {}

    class StubProcess:
        pid = 45678

    def stub_popen(
        command: list[str],
        *,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        captured["command"] = command
        return StubProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        stub_popen,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda _: False,
    )

    exit_code = supervisor_main(
        [
            "daemon",
            "start",
            "--codex-home",
            str(codex_home),
            "--interval",
            "7",
            "--limit",
            "3",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["daemon"]["command"] == [
        sys.executable,
        "-u",
        "-m",
        "isotope.features.supervisor.runner",
        "loop",
        "--codex-home",
        str(codex_home),
        "--interval",
        "7",
        "--limit",
        "3",
        "--worker-codex-model",
        "gpt-5.5",
        "--worker-codex-config",
        'model_reasoning_effort="high"',
    ]
    assert captured["command"] == payload["daemon"]["command"]



def test_codex_supervisor_runner_daemon_start_passes_max_fanout_launches_to_loop(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    captured: dict[str, object] = {}

    class StubProcess:
        pid = 45679

    def stub_popen(
        command: list[str],
        *,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        captured["command"] = command
        return StubProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        stub_popen,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda _: False,
    )

    exit_code = supervisor_main(
        [
            "daemon",
            "start",
            "--codex-home",
            str(codex_home),
            "--interval",
            "7",
            "--limit",
            "3",
            "--max-fanout-launches",
            "2",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["daemon"]["command"] == [
        sys.executable,
        "-u",
        "-m",
        "isotope.features.supervisor.runner",
        "loop",
        "--codex-home",
        str(codex_home),
        "--interval",
        "7",
        "--limit",
        "3",
        "--max-fanout-launches",
        "2",
        "--worker-codex-model",
        "gpt-5.5",
        "--worker-codex-config",
        'model_reasoning_effort="high"',
    ]
    assert captured["command"] == payload["daemon"]["command"]
    state = json.loads(
        (codex_home / "supervisor" / "daemon.json").read_text(encoding="utf-8")
    )
    assert state["command"] == payload["daemon"]["command"]



def test_codex_supervisor_runner_daemon_start_queues_goal_instead_of_repeating_explicit_goal(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    goal = "持续跟进 isotope 的 Supervisor worker。"
    captured: dict[str, object] = {}

    class StubProcess:
        pid = 45680

    def stub_popen(
        command: list[str],
        *,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        captured["command"] = command
        return StubProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        stub_popen,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda _: False,
    )

    exit_code = supervisor_main(
        [
            "daemon",
            "start",
            "--codex-home",
            str(codex_home),
            "--interval",
            "7",
            "--limit",
            "3",
            "--goal",
            goal,
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "--goal" not in payload["daemon"]["command"]
    assert payload["daemon"]["queued_goal"]["goal"] == goal
    assert payload["daemon"]["queued_goal"]["cwd"] == str(Path.cwd())
    assert payload["daemon"]["command"] == [
        sys.executable,
        "-u",
        "-m",
        "isotope.features.supervisor.runner",
        "loop",
        "--codex-home",
        str(codex_home),
        "--interval",
        "7",
        "--limit",
        "3",
        "--worker-codex-model",
        "gpt-5.5",
        "--worker-codex-config",
        'model_reasoning_effort="high"',
    ]
    assert captured["command"] == payload["daemon"]["command"]



def test_codex_supervisor_runner_daemon_start_uses_goal_queue_dynamically(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    exit_code = supervisor_main(
        [
            "goal",
            "add",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--goal",
            "后台 loop 动态读取目标队列。",
            "--json",
        ]
    )
    assert exit_code == 0
    capsys.readouterr()
    captured: dict[str, object] = {}

    class StubProcess:
        pid = 45682

    def stub_popen(
        command: list[str],
        *,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        captured["command"] = command
        return StubProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        stub_popen,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda _: False,
    )

    exit_code = supervisor_main(
        [
            "daemon",
            "start",
            "--codex-home",
            str(codex_home),
            "--interval",
            "7",
            "--limit",
            "3",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "--goal" not in payload["daemon"]["command"]
    assert captured["command"] == payload["daemon"]["command"]



def test_codex_supervisor_runner_up_starts_daemon_with_strong_worker_defaults(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    captured: dict[str, object] = {}

    class StubProcess:
        pid = 45678

    def stub_popen(
        command: list[str],
        *,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        captured["command"] = command
        captured["stdin"] = stdin
        captured["stderr"] = stderr
        return StubProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        stub_popen,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda _: False,
    )

    exit_code = supervisor_main(
        [
            "up",
            "--codex-home",
            str(codex_home),
            "--interval",
            "7",
            "--limit",
            "3",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["daemon"]["action"] == "started"
    assert payload["daemon"]["command"] == [
        sys.executable,
        "-u",
        "-m",
        "isotope.features.supervisor.runner",
        "loop",
        "--codex-home",
        str(codex_home),
        "--interval",
        "7",
        "--limit",
        "3",
        "--worker-codex-model",
        "gpt-5.5",
        "--worker-codex-config",
        'model_reasoning_effort="high"',
    ]
    assert payload["daemon"]["activity"] == {
        "recent_supervisor_action": None,
        "recent_llm_action": None,
        "recent_ci": None,
        "recent_execution": None,
        "recent_worker": None,
        "state_snapshot": {
            "status": "ok",
            "kind": "supervisor_state_snapshot",
            "schema_version": 1,
            "codex_home": str(codex_home),
            "summary": {
                "active_goals": 0,
                "goals_done": 0,
                "goals_blocked": 0,
                "goals_needs_user": 0,
                "active_decisions": 0,
                "failed_lanes": 0,
                "worker_events": 0,
                "notifications": 0,
                "unread_notifications": 0,
                "memory_records": 0,
                "artifact_summaries": 0,
                "agent_groups": 0,
            },
            "active_goals": [],
            "active_decisions": [],
            "failed_lanes": [],
            "recent_worker_events": [],
            "notifications": {"total": 0, "unread": 0, "recent": []},
            "memory": {
                "total": 0,
                "by_scope": {"thread": 0, "run": 0, "session": 0},
                "recent": [],
            },
            "artifacts": {"total": 0, "recent": []},
            "agent_groups": {"total": 0, "recent": []},
        },
        "night_summary": {
            "active_goals": 0,
            "running_workers": 0,
            "ready_to_integrate": 0,
            "merge_worker_running": False,
            "recent_ci_status": None,
            "recent_ci_detail": None,
            "recent_execution_status": None,
            "recent_execution_detail": None,
            "recent_worker_status": None,
            "recent_worker_name": None,
        },
    }
    assert captured["command"] == payload["daemon"]["command"]



def test_codex_supervisor_runner_up_goal_enters_persistent_queue(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    goal = "用日常入口启动后自动消费目标。"
    captured: dict[str, object] = {}

    class StubProcess:
        pid = 45683

    def stub_popen(
        command: list[str],
        *,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        captured["command"] = command
        return StubProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        stub_popen,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda _: False,
    )

    exit_code = supervisor_main(
        [
            "up",
            "--codex-home",
            str(codex_home),
            "--interval",
            "7",
            "--limit",
            "3",
            "--goal",
            goal,
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "--goal" not in payload["daemon"]["command"]
    assert payload["daemon"]["queued_goal"]["goal"] == goal
    assert payload["daemon"]["queued_goal"]["cwd"] == str(Path.cwd())
    assert payload["daemon"]["activity"]["active_goals"][0]["goal"] == goal
    assert payload["daemon"]["activity"]["active_goals"][0]["cwd"] == str(Path.cwd())
    assert captured["command"] == payload["daemon"]["command"]



def test_codex_supervisor_runner_daemon_status_includes_active_goal_status(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    exit_code = supervisor_main(
        [
            "goal",
            "add",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--goal",
            "daemon status 展示目标状态。",
            "--target-name",
            "goal-supervisor",
            "--json",
        ]
    )
    assert exit_code == 0
    capsys.readouterr()
    log_path = codex_home / "supervisor" / "logs" / "managed-001.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "SUPERVISOR_STATUS: needs_user\n"
        "SUPERVISOR_SUMMARY: 需要确认验收范围。\n"
        "SUPERVISOR_NEXT: 等待用户确认。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "goal-supervisor",
                "cwd": str(workspace),
                "prompt": "daemon status 展示目标状态。",
                "command": ["codex", "exec", "-C", str(workspace), "继续"],
                "pid": 0,
                "started_at": NOW.isoformat(),
                "log_path": str(log_path),
                "status": "launched",
                "backend": "process",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--no-auto-adopt",
            "--rule-execute",
            "--json",
        ]
    )
    assert exit_code == 0
    capsys.readouterr()
    state_path = codex_home / "supervisor" / "daemon.json"
    state_path.write_text(
        json.dumps(
            {
                "pid": 45678,
                "status": "running",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": None,
                "command": [sys.executable, "-m", "isotope.features.supervisor.runner"],
                "codex_home": str(codex_home),
                "log_path": str(codex_home / "supervisor" / "logs" / "daemon.log"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
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
    item = payload["daemon"]["activity"]["active_goals"][0]
    assert item["target_name"] == "goal-supervisor"
    assert item["last_status"] == "needs_user"
    assert item["last_summary"] == "需要确认验收范围。"
    assert item["last_next"] == "等待用户确认。"
    assert payload["daemon"]["activity"]["state_snapshot"]["active_goals"] == [
        item
    ]
    assert payload["daemon"]["activity"]["state_snapshot"]["summary"][
        "goals_needs_user"
    ] == 1



def test_codex_supervisor_runner_daemon_status_marks_existing_loop_running(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    state_path = codex_home / "supervisor" / "daemon.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "pid": 45678,
                "status": "running",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": None,
                "command": ["python", "-m", "isotope.features.supervisor.runner", "loop"],
                "codex_home": str(codex_home),
                "log_path": str(codex_home / "supervisor" / "logs" / "daemon.log"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
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
    assert payload["status"] == "ok"
    assert payload["daemon"]["status"] == "running"
    assert payload["daemon"]["pid"] == 45678
    assert payload["daemon"]["state_path"] == str(state_path)



def test_codex_supervisor_runner_daemon_status_includes_recent_activity(
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
                    "--worker-codex-model",
                    "gpt-5.5",
                    "--worker-codex-config",
                    'model_reasoning_effort="high"',
                ],
                "codex_home": str(codex_home),
                "log_path": str(log_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    log_path.write_text(
        "\n".join(
            [
                "[LLM 白名单动作]",
                "launch_session / 需要启动新会话继续推进。",
                "已执行：isotope-supervisor launch --name planner-session",
                "[LLM 白名单动作]",
                "launch_session / 同名任务仍在冷却。",
                "已跳过：launch prompt cooldown active",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    worker_log_path.write_text(
        "FAKE CODEX worker invoked\n"
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: worker 已完成状态汇报。\n"
        "SUPERVISOR_NEXT: 等待 Supervisor 归档。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "planner-session",
                "cwd": str(workspace),
                "prompt": "继续推进",
                "command": [
                    "codex",
                    "exec",
                    "-m",
                    "gpt-5.5",
                    "-c",
                    'model_reasoning_effort="high"',
                    "-C",
                    str(workspace),
                    "--skip-git-repo-check",
                    "继续推进",
                ],
                "pid": 45679,
                "started_at": "2026-05-18T10:01:00+00:00",
                "log_path": str(worker_log_path),
                "status": "launched",
                "backend": "process",
            },
            ensure_ascii=False,
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
    assert activity["recent_supervisor_action"] == {
        "kind": "launch_session",
        "reason": "同名任务仍在冷却。",
    }
    assert activity["recent_llm_action"] == activity["recent_supervisor_action"]
    assert activity["recent_execution"] == {
        "status": "skipped",
        "detail": "launch prompt cooldown active",
    }
    assert activity["recent_worker"]["name"] == "planner-session"
    assert activity["recent_worker"]["model"] == "gpt-5.5"
    assert activity["recent_worker"]["config"] == ['model_reasoning_effort="high"']
    assert activity["recent_worker"]["status"] == "done"
    assert activity["recent_worker"]["summary"] == "worker 已完成状态汇报。"
    assert activity["recent_worker"]["next"] == "等待 Supervisor 归档。"



def test_codex_supervisor_runner_daemon_status_includes_night_summary(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    exit_code = supervisor_main(
        [
            "goal",
            "add",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--goal",
            "夜间长跑摘要展示关键计数。",
            "--target-name",
            "night-summary",
            "--json",
        ]
    )
    assert exit_code == 0
    capsys.readouterr()

    state_path = codex_home / "supervisor" / "daemon.json"
    log_path = codex_home / "supervisor" / "logs" / "daemon.log"
    worker_log_path = codex_home / "supervisor" / "logs" / "managed-001.log"
    merge_log_path = codex_home / "supervisor" / "logs" / "managed-merge.log"
    done_log_path = codex_home / "supervisor" / "logs" / "managed-done.log"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "CI：success / workflow CI passed\n"
        "已执行：isotope-supervisor integration-review --json\n",
        encoding="utf-8",
    )
    worker_log_path.write_text(
        "SUPERVISOR_STATUS: working\n"
        "SUPERVISOR_SUMMARY: 正在跑夜间任务。\n"
        "SUPERVISOR_NEXT: 继续等待下一轮。\n",
        encoding="utf-8",
    )
    merge_log_path.write_text(
        "SUPERVISOR_STATUS: working\n"
        "SUPERVISOR_SUMMARY: 正在复查 ready worker。\n"
        "SUPERVISOR_NEXT: 跑完测试后汇报。\n",
        encoding="utf-8",
    )
    done_log_path.write_text(
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: 已完成。\n"
        "SUPERVISOR_NEXT: 等待归档。\n",
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
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        "\n".join(
            json.dumps(item, ensure_ascii=False)
            for item in [
                {
                    "record_id": "managed-001",
                    "name": "night-summary",
                    "cwd": str(workspace),
                    "prompt": "夜间长跑摘要展示关键计数。",
                    "command": ["codex", "exec", "-C", str(workspace), "继续"],
                    "pid": 45679,
                    "started_at": NOW.isoformat(),
                    "log_path": str(worker_log_path),
                    "status": "launched",
                    "backend": "process",
                },
                {
                    "record_id": "managed-done",
                    "name": "done-worker",
                    "cwd": str(workspace),
                    "prompt": "已完成 worker。",
                    "command": ["codex", "exec", "-C", str(workspace), "done"],
                    "pid": 45681,
                    "started_at": NOW.isoformat(),
                    "log_path": str(done_log_path),
                    "status": "launched",
                    "backend": "process",
                },
                {
                    "record_id": "managed-merge",
                    "name": "supervisor-merge-dispatch",
                    "cwd": str(workspace),
                    "prompt": "复查 ready worker 后合入。",
                    "command": ["codex", "exec", "-C", str(workspace), "merge"],
                    "pid": 45680,
                    "started_at": NOW.isoformat(),
                    "log_path": str(merge_log_path),
                    "status": "launched",
                    "backend": "process",
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda pid: pid == 45678,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._pid_is_running",
        lambda pid: pid in {45679, 45680},
        raising=False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: {
            "status": "ok",
            "summary": {
                "total": 4,
                "ready_to_integrate": 3,
                "already_integrated": 0,
                "needs_review": 1,
                "conflict_risk": 0,
            },
            "groups": {},
        },
    )

    exit_code = supervisor_main(
        ["daemon", "status", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    summary = payload["daemon"]["activity"]["night_summary"]
    assert summary == {
        "active_goals": 1,
        "running_workers": 2,
        "ready_to_integrate": 3,
        "merge_worker_running": True,
        "recent_ci_status": "success",
        "recent_ci_detail": "workflow CI passed",
        "recent_execution_status": "executed",
        "recent_execution_detail": "isotope-supervisor integration-review --json",
        "recent_worker_status": "working",
        "recent_worker_name": "supervisor-merge-dispatch",
    }

    exit_code = supervisor_main(["daemon", "status", "--codex-home", str(codex_home)])

    assert exit_code == 0
    text = capsys.readouterr().out
    assert (
        "夜间摘要：active goals 1 / running workers 2 / "
        "ready_to_integrate 3 / merge worker 运行中"
    ) in text
    assert "状态快照：supervisor_state_snapshot v1" in text
    assert "CI：success / workflow CI passed" in text
    assert "执行结果：executed / isotope-supervisor integration-review --json" in text



def test_codex_supervisor_runner_daemon_status_marks_exited_worker_not_working(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = codex_home / "supervisor" / "daemon.json"
    worker_log_path = codex_home / "supervisor" / "logs" / "managed-001.log"
    state_path.parent.mkdir(parents=True)
    worker_log_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "pid": 45678,
                "status": "stopped",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": "2026-05-18T10:05:00+00:00",
                "command": [sys.executable, "-m", "isotope.features.supervisor.runner"],
                "codex_home": str(codex_home),
                "log_path": str(codex_home / "supervisor" / "logs" / "daemon.log"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    worker_log_path.write_text(
        "SUPERVISOR_STATUS: working\n"
        "SUPERVISOR_SUMMARY: 正在读取项目状态。\n"
        "SUPERVISOR_NEXT: 继续读取项目状态并判断下一步。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "planner-session",
                "cwd": str(workspace),
                "prompt": "继续推进",
                "command": ["codex", "exec", "-C", str(workspace), "继续推进"],
                "pid": 45679,
                "started_at": "2026-05-18T10:01:00+00:00",
                "log_path": str(worker_log_path),
                "status": "launched",
                "backend": "process",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda pid: False,
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
    assert activity["recent_worker"] is None
    assert activity["night_summary"]["running_workers"] == 0



def test_codex_supervisor_runner_up_reports_existing_daemon_activity(
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
    state_path.write_text(
        json.dumps(
            {
                "pid": 45678,
                "status": "running",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": None,
                "command": ["python", "-u", "-m", "isotope.features.supervisor.runner", "loop"],
                "codex_home": str(codex_home),
                "log_path": str(log_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    log_path.write_text(
        "[LLM 白名单动作]\n"
        "launch_session / 最近启动了托管 worker。\n"
        "已执行：isotope-supervisor launch --name planner-session\n",
        encoding="utf-8",
    )
    worker_log_path.write_text(
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: up 入口活动展示完成。\n"
        "SUPERVISOR_NEXT: 等待归档。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "planner-session",
                "cwd": str(workspace),
                "prompt": "继续推进",
                "command": [
                    "codex",
                    "exec",
                    "-m",
                    "gpt-5.5",
                    "-c",
                    'model_reasoning_effort="high"',
                    "-C",
                    str(workspace),
                    "--skip-git-repo-check",
                    "继续推进",
                ],
                "pid": 45679,
                "started_at": "2026-05-18T10:01:00+00:00",
                "log_path": str(worker_log_path),
                "status": "launched",
                "backend": "process",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda pid: pid == 45678,
    )

    exit_code = supervisor_main(["up", "--codex-home", str(codex_home), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["daemon"]["action"] == "already_running"
    assert payload["daemon"]["activity"]["recent_supervisor_action"] == {
        "kind": "launch_session",
        "reason": "最近启动了托管 worker。",
    }
    assert (
        payload["daemon"]["activity"]["recent_llm_action"]
        == payload["daemon"]["activity"]["recent_supervisor_action"]
    )
    assert payload["daemon"]["activity"]["recent_worker"]["model"] == "gpt-5.5"
    assert payload["daemon"]["activity"]["recent_worker"]["status"] == "done"



def test_codex_supervisor_runner_daemon_stop_terminates_and_marks_stopped(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    state_path = codex_home / "supervisor" / "daemon.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "pid": 45678,
                "status": "running",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": None,
                "command": ["python", "-m", "isotope.features.supervisor.runner", "loop"],
                "codex_home": str(codex_home),
                "log_path": str(codex_home / "supervisor" / "logs" / "daemon.log"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda pid: pid == 45678,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.os.kill",
        lambda pid, signal_number: killed.append((pid, signal_number)),
    )

    exit_code = supervisor_main(
        ["daemon", "stop", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["daemon"]["status"] == "stopped"
    assert payload["daemon"]["pid"] == 45678
    assert payload["daemon"]["state_path"] == str(state_path)
    assert killed == [(45678, signal.SIGTERM)]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "stopped"
    assert state["stopped_at"] is not None



def test_codex_supervisor_runner_daemon_watchdog_restarts_stale_loop(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    state_path = codex_home / "supervisor" / "daemon.json"
    log_path = codex_home / "supervisor" / "logs" / "daemon.log"
    command = [
        sys.executable,
        "-m",
        "isotope.features.supervisor.runner",
        "loop",
        "--codex-home",
        str(codex_home),
        "--interval",
        "7",
    ]
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "pid": 11111,
                "status": "running",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": None,
                "command": command,
                "codex_home": str(codex_home),
                "log_path": str(log_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    class StubProcess:
        pid = 22222

    def stub_popen(
        command_: list[str],
        *,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        captured["command"] = command_
        captured["stdin"] = stdin
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return StubProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda pid: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        stub_popen,
    )

    exit_code = supervisor_main(
        ["daemon", "watchdog", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["daemon"]["action"] == "restarted"
    assert payload["daemon"]["previous_pid"] == 11111
    assert payload["daemon"]["pid"] == 22222
    assert payload["daemon"]["status"] == "running"
    assert payload["daemon"]["command"] == command
    assert captured["command"] == command
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["stderr"] is subprocess.STDOUT
    assert captured["start_new_session"] is True
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["pid"] == 22222
    assert persisted["command"] == command
    assert "action" not in persisted
    assert "previous_pid" not in persisted



def test_codex_supervisor_runner_daemon_watchdog_leaves_live_loop_alone(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    state_path = codex_home / "supervisor" / "daemon.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "pid": 45678,
                "status": "running",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": None,
                "command": ["python", "-m", "isotope.features.supervisor.runner", "loop"],
                "codex_home": str(codex_home),
                "log_path": str(codex_home / "supervisor" / "logs" / "daemon.log"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    def fail_popen(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("watchdog must not restart a live daemon")

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda pid: pid == 45678,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        fail_popen,
    )

    exit_code = supervisor_main(
        ["daemon", "watchdog", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["daemon"]["action"] == "alive"
    assert payload["daemon"]["pid"] == 45678
    assert payload["daemon"]["status"] == "running"



def test_codex_supervisor_runner_daemon_watcher_start_spawns_periodic_watchdog(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    captured: dict[str, object] = {}

    class StubProcess:
        pid = 33333

    def stub_popen(
        command: list[str],
        *,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        captured["command"] = command
        captured["stdin"] = stdin
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return StubProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda _pid: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        stub_popen,
    )

    exit_code = supervisor_main(
        [
            "daemon",
            "watcher",
            "start",
            "--codex-home",
            str(codex_home),
            "--interval",
            "5",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    expected_command = [
        sys.executable,
        "-m",
        "isotope.features.supervisor.runner",
        "daemon",
        "watcher",
        "run",
        "--codex-home",
        str(codex_home),
        "--interval",
        "5",
    ]
    assert payload["status"] == "ok"
    assert payload["watcher"]["action"] == "started"
    assert payload["watcher"]["status"] == "running"
    assert payload["watcher"]["pid"] == 33333
    assert payload["watcher"]["command"] == expected_command
    assert payload["watcher"]["log_path"].endswith("watcher.log")
    assert payload["watcher"]["state_path"].endswith("watcher.json")
    assert captured["command"] == expected_command
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["stderr"] is subprocess.STDOUT
    assert captured["start_new_session"] is True

    state = json.loads(
        (codex_home / "supervisor" / "watcher.json").read_text(encoding="utf-8")
    )
    persisted = dict(payload["watcher"])
    persisted.pop("action")
    assert state == persisted



def test_codex_supervisor_runner_daemon_watcher_run_calls_watchdog_periodically(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    calls: list[str] = []

    def stub_watchdog(*, codex_home: Path) -> dict[str, object]:
        calls.append(str(codex_home))
        return {
            "action": "alive" if len(calls) == 1 else "restarted",
            "pid": 10000 + len(calls),
            "status": "running",
        }

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.watchdog_supervisor_daemon",
        stub_watchdog,
    )
    monkeypatch.setattr("isotope.features.supervisor.daemon._sleep", lambda _seconds: None)

    exit_code = supervisor_main(
        [
            "daemon",
            "watcher",
            "run",
            "--codex-home",
            str(codex_home),
            "--interval",
            "5",
            "--iterations",
            "2",
            "--json",
        ]
    )

    assert exit_code == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert calls == [str(codex_home), str(codex_home)]
    assert [line["watchdog"]["action"] for line in lines] == ["alive", "restarted"]
    assert [line["iteration"] for line in lines] == [1, 2]



def test_codex_supervisor_runner_daemon_watcher_stop_marks_stopped(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    state_path = codex_home / "supervisor" / "watcher.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "pid": 33333,
                "status": "running",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": None,
                "command": [
                    sys.executable,
                    "-m",
                    "isotope.features.supervisor.runner",
                    "daemon",
                    "watcher",
                    "run",
                ],
                "codex_home": str(codex_home),
                "log_path": str(codex_home / "supervisor" / "logs" / "watcher.log"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda pid: pid == 33333,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.os.kill",
        lambda pid, signal_number: killed.append((pid, signal_number)),
    )

    exit_code = supervisor_main(
        ["daemon", "watcher", "stop", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["watcher"]["status"] == "stopped"
    assert payload["watcher"]["pid"] == 33333
    assert killed == [(33333, signal.SIGTERM)]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "stopped"
    assert state["stopped_at"] is not None



