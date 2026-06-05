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

from helpers import (
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


def test_codex_supervisor_runner_loop_auto_executes_even_when_report_unchanged(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_session_exists",
        lambda session: session == "isotope-lane-a",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_window_has_bell",
        lambda session: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._tmux_capture_pane",
        lambda session: "› Improve documentation in @filename\n  gpt-5.5 xhigh · main",
    )
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)
    calls: list[list[str]] = []

    def stub_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["git", "-C"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", stub_run)

    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "2",
            "--interval",
            "1",
            "--no-auto-adopt",
            "--rule-execute",
            "--prompt-cooldown",
            "0",
            "--json",
        ]
    )

    assert exit_code == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 2
    assert [json.loads(line)["executed"]["kind"] for line in lines] == [
        "send_status",
        "send_status",
    ]
    assert calls == _tmux_send_calls(STATUS_REQUEST_TEXT) + _tmux_send_calls(
        STATUS_REQUEST_TEXT
    )




def test_codex_supervisor_runner_loop_defaults_to_llm_driver(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_session_exists",
        lambda session: session == "isotope-lane-a",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_window_has_bell",
        lambda session: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._tmux_capture_pane",
        lambda session: "› 等待输入\n  gpt-5.5 xhigh · main",
    )
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"allowed_kinds"' in content
            assert '"managed_terminal_ready": true' in content
            return '{"kind":"send_status","target_name":"lane-a","reason":"让 LLM 决定本轮节奏。"}'

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )
    calls: list[list[str]] = []

    def stub_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["git", "-C"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", stub_run)

    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "2",
            "--interval",
            "1",
            "--no-auto-adopt",
            "--prompt-cooldown",
            "0",
            "--json",
        ]
    )

    assert exit_code == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 2
    payloads = [json.loads(line) for line in lines]
    assert [payload["supervisor_action"]["kind"] for payload in payloads] == [
        "send_status",
        "send_status",
    ]
    assert all(
        payload["llm_action"] == payload["supervisor_action"] for payload in payloads
    )
    assert [payload["executed"]["kind"] for payload in payloads] == [
        "send_status",
        "send_status",
    ]
    assert "auto_action" not in payloads[0]
    assert calls == _tmux_send_calls(STATUS_REQUEST_TEXT) + _tmux_send_calls(
        STATUS_REQUEST_TEXT
    )




def test_codex_supervisor_runner_loop_reports_process_backend_as_managed(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-process-001",
                "name": "process-lane",
                "cwd": str(workspace),
                "prompt": "后台继续推进 Supervisor。",
                "command": [
                    "codex",
                    "exec",
                    "-C",
                    str(workspace),
                    "--skip-git-repo-check",
                    "后台继续推进 Supervisor。",
                ],
                "pid": 4242,
                "started_at": NOW.isoformat(),
                "log_path": str(
                    codex_home / "supervisor" / "logs" / "managed-process-001.log"
                ),
                "status": "launched",
                "backend": "process",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._pid_is_running",
        lambda pid: pid == 4242,
    )
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert f'"available_workspaces": ["{workspace}"]' in content
            assert "process-lane" in content
            return '{"kind":"monitor","reason":"后台 process lane 正在运行，继续观察。"}'

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
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
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["automation"]["ready"] is True
    assert payload["automation"]["managed_process_count"] == 1
    assert payload["automation"]["managed_tmux_count"] == 0
    assert payload["automation"]["managed_names"] == ["process-lane"]
    assert "tmux lane" not in payload["automation"]["reason"]
    assert "后台托管 Codex 进程" in payload["automation"]["reason"]
    assert payload["supervisor_action"] == {
        "kind": "monitor",
        "target_name": None,
        "reason": "后台 process lane 正在运行，继续观察。",
        "command_suggestion": None,
    }
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["executed"] == {
        "kind": "monitor",
        "reason": "后台 process lane 正在运行，继续观察。",
        "skipped": True,
    }




def test_codex_supervisor_runner_loop_does_not_reprompt_completed_process_worker(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = codex_home / "supervisor" / "logs" / "managed-process-001.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: worker 已完成实现和验证。\n"
        "SUPERVISOR_NEXT: 建议主控复查 diff 后进入合并流程。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-process-001",
                "name": "process-lane",
                "cwd": str(workspace),
                "prompt": "后台继续推进 Supervisor。",
                "command": ["codex", "exec", "-C", str(workspace), "后台继续推进。"],
                "pid": 4242,
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
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._pid_is_running",
        lambda pid: False,
    )
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    class FailingProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            raise AssertionError("completed process worker should not be reprompted")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FailingProvider(),
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
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["supervisor_action"] == {
        "kind": "monitor",
        "target_name": None,
        "reason": "当前没有可控的 Supervisor 目标，先继续监控。",
        "command_suggestion": None,
    }
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "当前没有可控的 Supervisor 目标，先继续监控。",
    }




def test_codex_supervisor_runner_loop_retries_exited_process_worker(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = codex_home / "supervisor" / "logs" / "managed-process-001.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "SUPERVISOR_STATUS: working\n"
        "SUPERVISOR_SUMMARY: worker 正在写代码但进程退出。\n"
        "SUPERVISOR_NEXT: 继续推进当前任务。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-process-001",
                "name": "process-lane",
                "cwd": str(workspace),
                "prompt": "后台继续推进 Supervisor。",
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
                    "后台继续推进 Supervisor。",
                ],
                "pid": 4242,
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
    monkeypatch.setattr("isotope.features.supervisor.flow._pid_is_running", lambda _: False)
    monkeypatch.setattr("isotope.features.supervisor.runner._pid_is_running", lambda _: False)
    monkeypatch.setattr("isotope.features.supervisor.flow._git_branch_for", lambda _: None)
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    class StubProcess:
        pid = 5252

    captured: dict[str, object] = {}

    def stub_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        captured["command"] = command
        captured["cwd"] = cwd
        captured["stdin"] = stdin
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return StubProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)

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
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_retried_workers"] == [
        {
            "name": "process-lane",
            "previous_record_id": "managed-process-001",
            "record_id": payload["auto_retried_workers"][0]["record_id"],
            "pid": 5252,
            "retry_count": 1,
            "max_retries": 2,
        }
    ]
    assert captured["command"][:7] == [
        "codex",
        "exec",
        "-m",
        "gpt-5.5",
        "-c",
        'model_reasoning_effort="high"',
        "-C",
    ]
    assert captured["cwd"] == str(workspace)
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["stderr"] is subprocess.STDOUT
    assert captured["start_new_session"] is True
    lane_state = json.loads(
        (codex_home / "supervisor" / "lane_state.json").read_text(encoding="utf-8")
    )
    assert lane_state["process-lane"]["worker_retry_count"] == 1




def test_codex_supervisor_runner_loop_stops_process_worker_retry_at_budget(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = codex_home / "supervisor" / "logs" / "managed-process-001.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "SUPERVISOR_STATUS: working\n"
        "SUPERVISOR_SUMMARY: worker 正在写代码但进程退出。\n"
        "SUPERVISOR_NEXT: 继续推进当前任务。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-process-001",
                "name": "process-lane",
                "cwd": str(workspace),
                "prompt": "后台继续推进 Supervisor。",
                "command": ["codex", "exec", "-C", str(workspace), "后台继续推进。"],
                "pid": 4242,
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
    lane_state_path = codex_home / "supervisor" / "lane_state.json"
    lane_state_path.parent.mkdir(parents=True, exist_ok=True)
    lane_state_path.write_text(
        json.dumps(
            {
                "process-lane": {
                    "name": "process-lane",
                    "tmux_session": None,
                    "last_status": "worker_retry",
                    "last_prompted_at": NOW.isoformat(),
                    "prompt_count": 0,
                    "last_prompt_kind": "worker_retry",
                    "continue_count": 0,
                    "worker_retry_count": 2,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("isotope.features.supervisor.flow._pid_is_running", lambda _: False)
    monkeypatch.setattr("isotope.features.supervisor.runner._pid_is_running", lambda _: False)
    monkeypatch.setattr("isotope.features.supervisor.flow._git_branch_for", lambda _: None)
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    def fail_launch(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("worker retry budget is exhausted")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.launch_managed_codex",
        fail_launch,
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
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_retried_workers"] == []
    lane_state = json.loads(lane_state_path.read_text(encoding="utf-8"))
    assert lane_state["process-lane"]["worker_retry_count"] == 2




def test_codex_supervisor_runner_loop_requests_decision_after_worker_retry_budget(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = codex_home / "supervisor" / "logs" / "managed-process-001.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "SUPERVISOR_STATUS: working\n"
        "SUPERVISOR_SUMMARY: worker 正在写代码但进程失败。\n"
        "SUPERVISOR_NEXT: 继续推进当前任务。\n"
        "stderr: AssertionError: regression failed\n"
        "Process exited with code 2\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-process-001",
                "name": "process-lane",
                "cwd": str(workspace),
                "prompt": "后台继续推进 Supervisor。",
                "command": ["codex", "exec", "-C", str(workspace), "后台继续推进。"],
                "pid": 4242,
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
    lane_state_path = codex_home / "supervisor" / "lane_state.json"
    lane_state_path.parent.mkdir(parents=True, exist_ok=True)
    lane_state_path.write_text(
        json.dumps(
            {
                "process-lane": {
                    "name": "process-lane",
                    "tmux_session": None,
                    "last_status": "worker_retry",
                    "last_prompted_at": NOW.isoformat(),
                    "prompt_count": 0,
                    "last_prompt_kind": "worker_retry",
                    "continue_count": 0,
                    "worker_retry_count": 2,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("isotope.features.supervisor.flow._pid_is_running", lambda _: False)
    monkeypatch.setattr("isotope.features.supervisor.runner._pid_is_running", lambda _: False)
    monkeypatch.setattr("isotope.features.supervisor.flow._git_branch_for", lambda _: None)
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    def fail_launch(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("worker retry budget is exhausted")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.launch_managed_codex",
        fail_launch,
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
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_retried_workers"] == []
    assert payload["decision_requests"][0]["target_name"] == "process-lane"
    assert payload["decision_requests"][0]["session_id"] == (
        "failure:worker_retry_failed:process-lane"
    )
    assert payload["decision_requests"][0]["reason"] == (
        "worker retry limit exceeded"
    )




def test_codex_supervisor_runner_loop_retries_timed_out_process_worker(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = codex_home / "supervisor" / "logs" / "managed-process-001.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("worker did not finish within budget\n", encoding="utf-8")
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-process-001",
                "name": "process-lane",
                "cwd": str(workspace),
                "prompt": "后台继续推进 Supervisor。",
                "command": ["codex", "exec", "-C", str(workspace), "后台继续推进。"],
                "pid": 4242,
                "started_at": "2000-01-01T00:00:00+00:00",
                "log_path": str(log_path),
                "status": "launched",
                "backend": "process",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("isotope.features.supervisor.flow._pid_is_running", lambda _: False)
    monkeypatch.setattr("isotope.features.supervisor.runner._pid_is_running", lambda _: False)
    monkeypatch.setattr("isotope.features.supervisor.flow._git_branch_for", lambda _: None)
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    class StubProcess:
        pid = 5252

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.subprocess.Popen",
        lambda *_args, **_kwargs: StubProcess(),
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
            "--max-run-minutes",
            "1",
            "--no-auto-adopt",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_retried_workers"] == [
        {
            "name": "process-lane",
            "previous_record_id": "managed-process-001",
            "record_id": payload["auto_retried_workers"][0]["record_id"],
            "pid": 5252,
            "retry_count": 1,
            "max_retries": 2,
            "failure": {
                "reason": "timeout",
                "exit_code": None,
                "stderr_summary": "worker did not finish within budget",
            },
        }
    ]
    lane_state = json.loads(
        (codex_home / "supervisor" / "lane_state.json").read_text(encoding="utf-8")
    )
    assert lane_state["process-lane"]["last_failure_reason"] == "timeout"
    assert lane_state["process-lane"]["worker_retry_count"] == 1




def test_codex_supervisor_runner_loop_does_not_retry_process_worker_without_working_protocol(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = codex_home / "supervisor" / "logs" / "managed-process-001.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("worker exited before protocol report\n", encoding="utf-8")
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-process-001",
                "name": "process-lane",
                "cwd": str(workspace),
                "prompt": "后台继续推进 Supervisor。",
                "command": ["codex", "exec", "-C", str(workspace), "后台继续推进。"],
                "pid": 4242,
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
    monkeypatch.setattr("isotope.features.supervisor.flow._pid_is_running", lambda _: False)
    monkeypatch.setattr("isotope.features.supervisor.runner._pid_is_running", lambda _: False)
    monkeypatch.setattr("isotope.features.supervisor.flow._git_branch_for", lambda _: None)
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    def fail_launch(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("worker without working protocol should not be retried")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.launch_managed_codex",
        fail_launch,
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
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_retried_workers"] == []




def test_codex_supervisor_runner_loop_goal_can_launch_first_worker(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    goal = "实现 Supervisor goal 入口，并补最小测试。"
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert f'"available_workspaces": ["{workspace}"]' in content
            assert goal in content
            assert '"kind": "launch_session"' in content
            return json.dumps(
                {
                    "kind": "launch_session",
                    "target_name": "goal-worker",
                    "cwd": str(workspace),
                    "prompt": goal,
                    "reason": "用户给了明确目标，启动新 worker 推进。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )
    captured: dict[str, object] = {}

    class StubProcess:
        pid = 45679

    def stub_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        captured["command"] = command
        captured["cwd"] = cwd
        captured["stdin"] = stdin
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return StubProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)

    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--workspace-root",
            str(workspace),
            "--goal",
            goal,
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
    assert payload["supervisor_action"]["kind"] == "launch_session"
    assert payload["supervisor_action"]["prompt"] == goal
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["executed"]["kind"] == "launch_session"
    assert payload["executed"]["managed"]["name"] == "goal-worker"
    assert payload["executed"]["managed"]["pid"] == 45679
    assert payload["executed"]["worktree"] == {
        "enabled": False,
        "source_cwd": str(workspace),
        "cwd": str(workspace),
        "reason": "not_git_repo",
    }
    assert captured["command"][:9] == [
        "codex",
        "exec",
        "-m",
        "gpt-5.5",
        "-c",
        'model_reasoning_effort="high"',
        "-C",
        str(workspace),
        "--skip-git-repo-check",
    ]
    assert captured["command"][9].startswith("WORK ORDER")
    assert f"goal: {goal}" in captured["command"][9]
    assert "必须在本 worktree 内提交一个 Conventional Commits 提交" in captured[
        "command"
    ][9]
    assert captured["cwd"] == str(workspace)
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["stderr"] is subprocess.STDOUT
    assert captured["start_new_session"] is True




def test_codex_supervisor_runner_loop_uses_persisted_goal_queue(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    goal = "让 Supervisor 自动消费持久目标队列。"
    exit_code = supervisor_main(
        [
            "goal",
            "add",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--goal",
            goal,
            "--target-name",
            "goal-supervisor",
            "--json",
        ]
    )
    assert exit_code == 0
    add_payload = json.loads(capsys.readouterr().out)
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert f'"available_workspaces": ["{workspace}"]' in content
            assert goal in content
            assert '"target_name": "goal-supervisor"' in content
            return json.dumps(
                {
                    "kind": "launch_session",
                    "target_name": "goal-supervisor",
                    "cwd": str(workspace),
                    "prompt": goal,
                    "reason": "队列里有活跃目标，启动 worker 推进。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )
    captured: dict[str, object] = {}

    class StubProcess:
        pid = 45681

    def stub_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        captured["command"] = command
        captured["cwd"] = cwd
        return StubProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)

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
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["active_goals"] == add_payload["active_goals"]
    assert payload["supervisor_action"]["kind"] == "launch_session"
    assert payload["supervisor_action"]["target_name"] == "goal-supervisor"
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["executed"]["managed"]["name"] == "goal-supervisor"
    assert payload["executed"]["worktree"]["cwd"] == str(workspace)
    assert captured["command"][9].startswith("WORK ORDER")
    assert f"goal: {goal}" in captured["command"][9]
    assert "必须在本 worktree 内提交一个 Conventional Commits 提交" in captured[
        "command"
    ][9]




