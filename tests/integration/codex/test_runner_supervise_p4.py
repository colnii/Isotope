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


def test_codex_supervisor_runner_supervise_auto_waits_without_protocol_while_running(
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
        lambda session: "",
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
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "monitor",
        "reason": "managed lane is running without ready signal",
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "managed lane is running without ready signal",
    }
    assert calls == []




def test_codex_supervisor_runner_supervise_auto_prefers_busy_terminal_over_old_done_link(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    prompt = "Supervisor 真实使用验收：检查 loop 行为，不要修改文件。"
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "lane-a",
                "cwd": str(workspace),
                "prompt": prompt,
                "command": ["tmux", "new-session", "-d", "-s", "isotope-lane-a"],
                "pid": 0,
                "started_at": NOW.isoformat(),
                "log_path": str(codex_home / "supervisor" / "logs" / "managed-001.log"),
                "status": "launched",
                "backend": "tmux",
                "tmux_session": "isotope-lane-a",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-old-done.jsonl",
        session_id="old-done-session",
        cwd=str(workspace),
        events=[
            _user_message("2026-05-16T11:40:00Z", prompt),
            _assistant_message(
                "2026-05-16T11:45:00Z",
                "SUPERVISOR_STATUS: done\n"
                "SUPERVISOR_SUMMARY: 旧窗口已完成。\n"
                "SUPERVISOR_NEXT: 等待 Supervisor 归档。",
            ),
        ],
    )
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
        lambda session: (
            "› Supervisor 真实使用验收：检查 loop 行为，不要修改文件。\n\n"
            "◦ Working (12s • esc to interrupt)\n\n"
            "› Implement {feature}\n"
            "  gpt-5.5 xhigh · main"
        ),
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
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "monitor",
        "reason": "managed lane is running without ready signal",
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "managed lane is running without ready signal",
    }
    assert calls == []




def test_codex_supervisor_runner_supervise_auto_requests_status_when_terminal_ready(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    _write_session(
        codex_home,
        "2026/05/16/rollout-working.jsonl",
        session_id="working-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:30Z",
                "SUPERVISOR_STATUS: working\n"
                "SUPERVISOR_SUMMARY: 正在执行上一条任务。\n"
                "SUPERVISOR_NEXT: 等待完成。",
            )
        ],
    )
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
        lambda session: (
            "To continue this session, run codex resume working-session\n"
            "• SUPERVISOR_STATUS: working\n"
            "  SUPERVISOR_SUMMARY: 正在执行上一条任务。\n"
            "  SUPERVISOR_NEXT: 等待完成。\n"
            "› Improve documentation in @filename\n"
            "  gpt-5.5 xhigh · Context 96% left · ~/Github/isotope · main"
        ),
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
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "send_status",
        "reason": "managed terminal is ready for input",
    }
    assert payload["executed"]["kind"] == "send_status"
    assert payload["executed"]["text"] == STATUS_REQUEST_TEXT
    assert calls == _tmux_send_calls(STATUS_REQUEST_TEXT)




def test_codex_supervisor_runner_supervise_auto_name_targets_ready_lane(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        "\n".join(
            json.dumps(record, ensure_ascii=False)
            for record in [
                {
                    "record_id": "managed-a",
                    "name": "lane-a",
                    "cwd": str(workspace),
                    "prompt": "等待输入",
                    "command": ["tmux", "attach", "-t", "session-a"],
                    "pid": 0,
                    "started_at": NOW.isoformat(),
                    "log_path": str(codex_home / "supervisor" / "logs" / "a.log"),
                    "status": "adopted",
                    "backend": "tmux",
                    "tmux_session": "session-a",
                },
                {
                    "record_id": "managed-b",
                    "name": "lane-b",
                    "cwd": str(workspace),
                    "prompt": "等待输入",
                    "command": ["tmux", "attach", "-t", "session-b"],
                    "pid": 0,
                    "started_at": NOW.isoformat(),
                    "log_path": str(codex_home / "supervisor" / "logs" / "b.log"),
                    "status": "adopted",
                    "backend": "tmux",
                    "tmux_session": "session-b",
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_session_exists",
        lambda session: session in {"session-a", "session-b"},
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_window_has_bell",
        lambda session: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._tmux_capture_pane",
        lambda session: (
            "◦ Working (7m 52s • esc to interrupt)"
            if session == "session-a"
            else "› Improve documentation in @filename\n  gpt-5.5 xhigh · main"
        ),
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
            "supervise",
            "--codex-home",
            str(codex_home),
            "--name",
            "lane-b",
            "--iterations",
            "1",
            "--interval",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "send_status",
        "reason": "managed terminal is ready for input",
    }
    assert payload["executed"]["managed"]["name"] == "lane-b"
    assert calls == _tmux_send_calls(
        STATUS_REQUEST_TEXT,
        buffer_name="isotope-supervisor-managed-b",
        target="session-b",
    )




def test_codex_supervisor_runner_supervise_auto_finds_ready_lane_after_running_lane(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        "\n".join(
            json.dumps(record, ensure_ascii=False)
            for record in [
                {
                    "record_id": "managed-a",
                    "name": "lane-a",
                    "cwd": str(workspace),
                    "prompt": "仍在运行",
                    "command": ["tmux", "attach", "-t", "session-a"],
                    "pid": 0,
                    "started_at": NOW.isoformat(),
                    "log_path": str(codex_home / "supervisor" / "logs" / "a.log"),
                    "status": "adopted",
                    "backend": "tmux",
                    "tmux_session": "session-a",
                },
                {
                    "record_id": "managed-b",
                    "name": "lane-b",
                    "cwd": str(workspace),
                    "prompt": "等待输入",
                    "command": ["tmux", "attach", "-t", "session-b"],
                    "pid": 0,
                    "started_at": NOW.isoformat(),
                    "log_path": str(codex_home / "supervisor" / "logs" / "b.log"),
                    "status": "adopted",
                    "backend": "tmux",
                    "tmux_session": "session-b",
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_session_exists",
        lambda session: session in {"session-a", "session-b"},
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_window_has_bell",
        lambda session: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._tmux_capture_pane",
        lambda session: (
            "◦ Working (7m 52s • esc to interrupt)"
            if session == "session-a"
            else "› Improve documentation in @filename\n  gpt-5.5 xhigh · main"
        ),
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
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "send_status",
        "reason": "managed terminal is ready for input",
        "target_name": "lane-b",
    }
    assert payload["executed"]["managed"]["name"] == "lane-b"
    assert calls == _tmux_send_calls(
        STATUS_REQUEST_TEXT,
        buffer_name="isotope-supervisor-managed-b",
        target="session-b",
    )




def test_codex_supervisor_runner_supervise_auto_continues_done_lane(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    _write_session(
        codex_home,
        "2026/05/16/rollout-done.jsonl",
        session_id="done-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:30Z",
                "SUPERVISOR_STATUS: done\n"
                "SUPERVISOR_SUMMARY: 当前任务已完成。\n"
                "SUPERVISOR_NEXT: 可以继续下一步。",
            )
        ],
    )
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
        lambda session: (
            "SUPERVISOR_STATUS: done\n"
            "SUPERVISOR_SUMMARY: 当前任务已完成。\n"
            "SUPERVISOR_NEXT: 可以继续下一步。"
        ),
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
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "send_continue",
        "reason": "managed lane reported done",
    }
    assert payload["executed"]["kind"] == "send_continue"
    assert payload["executed"]["text"] == CONTINUE_REQUEST_TEXT
    assert calls == _tmux_send_calls(CONTINUE_REQUEST_TEXT)




def test_codex_supervisor_runner_supervise_auto_respects_max_continue_count(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    lane_state_path = codex_home / "supervisor" / "lane_state.json"
    lane_state_path.write_text(
        json.dumps(
            {
                "lane-a": {
                    "name": "lane-a",
                    "tmux_session": "isotope-lane-a",
                    "last_status": "done",
                    "last_prompted_at": "2026-05-16T11:59:00+00:00",
                    "prompt_count": 3,
                    "last_prompt_kind": "send_continue",
                    "continue_count": 3,
                }
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-done.jsonl",
        session_id="done-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:30Z",
                "SUPERVISOR_STATUS: done\n"
                "SUPERVISOR_SUMMARY: 当前任务已完成。\n"
                "SUPERVISOR_NEXT: 可以继续下一步。",
            )
        ],
    )
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
        lambda session: (
            "SUPERVISOR_STATUS: done\n"
            "SUPERVISOR_SUMMARY: 当前任务已完成。\n"
            "SUPERVISOR_NEXT: 可以继续下一步。"
        ),
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
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--prompt-cooldown",
            "0",
            "--max-continue-count",
            "3",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "monitor",
        "reason": "lane continue budget exhausted",
        "target_name": "lane-a",
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "lane continue budget exhausted",
    }
    assert calls == []




def test_codex_supervisor_runner_supervise_auto_respects_max_run_minutes(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    _write_session(
        codex_home,
        "2026/05/16/rollout-done.jsonl",
        session_id="done-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:30Z",
                "SUPERVISOR_STATUS: done\n"
                "SUPERVISOR_SUMMARY: 当前任务已完成。\n"
                "SUPERVISOR_NEXT: 可以继续下一步。",
            )
        ],
    )
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
        lambda session: (
            "SUPERVISOR_STATUS: done\n"
            "SUPERVISOR_SUMMARY: 当前任务已完成。\n"
            "SUPERVISOR_NEXT: 可以继续下一步。"
        ),
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
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--prompt-cooldown",
            "0",
            "--max-run-minutes",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "monitor",
        "reason": "lane run budget exhausted",
        "target_name": "lane-a",
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "lane run budget exhausted",
    }
    assert calls == []




def test_codex_supervisor_runner_supervise_default_allows_long_continue_lane(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    lane_state_path = codex_home / "supervisor" / "lane_state.json"
    lane_state_path.write_text(
        json.dumps(
            {
                "lane-a": {
                    "name": "lane-a",
                    "tmux_session": "isotope-lane-a",
                    "last_status": "done",
                    "last_prompted_at": "2026-05-16T11:59:00+00:00",
                    "prompt_count": 8,
                    "last_prompt_kind": "send_continue",
                    "continue_count": 8,
                }
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-done.jsonl",
        session_id="done-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:30Z",
                "SUPERVISOR_STATUS: done\n"
                "SUPERVISOR_SUMMARY: 长任务阶段完成。\n"
                "SUPERVISOR_NEXT: 可以继续下一段。",
            )
        ],
    )
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
        lambda session: (
            "SUPERVISOR_STATUS: done\n"
            "SUPERVISOR_SUMMARY: 长任务阶段完成。\n"
            "SUPERVISOR_NEXT: 可以继续下一段。"
        ),
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
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--prompt-cooldown",
            "0",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "send_continue",
        "reason": "managed lane reported done",
    }
    assert payload["executed"]["kind"] == "send_continue"
    assert payload["executed"]["text"] == CONTINUE_REQUEST_TEXT
    assert calls == _tmux_send_calls(CONTINUE_REQUEST_TEXT)




def test_codex_supervisor_runner_supervise_auto_stops_terminal_done_lane(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    _write_session(
        codex_home,
        "2026/05/16/rollout-terminal-done.jsonl",
        session_id="terminal-done-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:30Z",
                "SUPERVISOR_STATUS: done\n"
                "SUPERVISOR_SUMMARY: 本次任务已经完成。\n"
                "SUPERVISOR_NEXT: 等待 Supervisor 归档或下发新任务。",
            )
        ],
    )
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
        lambda session: (
            "SUPERVISOR_STATUS: done\n"
            "SUPERVISOR_SUMMARY: 本次任务已经完成。\n"
            "SUPERVISOR_NEXT: 等待 Supervisor 归档或下发新任务。"
        ),
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
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "monitor",
        "reason": "managed lane reported terminal done",
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "managed lane reported terminal done",
    }
    assert calls == []




def test_codex_supervisor_runner_supervise_auto_waits_on_blocked_lane(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    _write_session(
        codex_home,
        "2026/05/16/rollout-blocked.jsonl",
        session_id="blocked-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:30Z",
                "SUPERVISOR_STATUS: blocked\n"
                "SUPERVISOR_SUMMARY: 需要用户提供 API key。\n"
                "SUPERVISOR_NEXT: 等待用户处理。",
            )
        ],
    )
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
        lambda session: (
            "SUPERVISOR_STATUS: blocked\n"
            "SUPERVISOR_SUMMARY: 需要用户提供 API key。\n"
            "SUPERVISOR_NEXT: 等待用户处理。"
        ),
    )
    calls: list[list[str]] = []

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.subprocess.run",
        lambda command, *, check, text, capture_output: subprocess.CompletedProcess(
            command, 0, "", ""
        )
        if command[:2] == ["git", "-C"]
        else calls.append(command) or subprocess.CompletedProcess(command, 0, "", ""),
    )

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "monitor",
        "reason": "lane needs human attention",
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "lane needs human attention",
    }
    assert calls == []




