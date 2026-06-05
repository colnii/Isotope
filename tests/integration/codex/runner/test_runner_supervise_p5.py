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


def test_codex_supervisor_runner_supervise_bell_rings_for_human_attention(
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
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda _: None)

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "2",
            "--interval",
            "1",
            "--auto-execute",
            "--bell",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == "\a"




def test_codex_supervisor_runner_supervise_bell_ignores_unmanaged_attention_when_lane_runs(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    other_workspace = tmp_path / "other"
    workspace.mkdir()
    other_workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    _write_session(
        codex_home,
        "2026/05/16/rollout-unmanaged-attention.jsonl",
        session_id="unmanaged-attention-session",
        cwd=str(other_workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:30Z",
                "需要你确认是否继续。",
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
        lambda session: "",
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
            "--bell",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["auto_action"] == {
        "kind": "monitor",
        "reason": "managed lane is running without ready signal",
    }




def test_codex_supervisor_runner_supervise_bell_skips_auto_handled_continue(
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
            "--bell",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert calls == _tmux_send_calls(CONTINUE_REQUEST_TEXT)




def test_codex_supervisor_runner_execute_skips_repeated_prompt_in_cooldown(
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
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "lane-a",
                "cwd": str(workspace),
                "prompt": "等待输入",
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
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_session_exists",
        lambda session: session == "isotope-lane-a",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_window_has_bell",
        lambda session: False,
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

    first_exit = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--execute",
            "send_status",
            "--json",
        ]
    )
    first_payload = json.loads(capsys.readouterr().out)
    second_exit = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--execute",
            "send_status",
            "--json",
        ]
    )
    second_payload = json.loads(capsys.readouterr().out)

    assert first_exit == 0
    assert first_payload["executed"]["kind"] == "send_status"
    assert second_exit == 0
    assert second_payload["executed"]["skipped"] is True
    assert second_payload["executed"]["reason"] == "lane prompt cooldown active"
    assert second_payload["executed"]["lane_state"]["name"] == "lane-a"
    assert second_payload["executed"]["lane_state"]["prompt_count"] == 1
    assert calls == _tmux_send_calls(STATUS_REQUEST_TEXT)




def test_codex_supervisor_runner_supervise_auto_skips_cooldown_lane_for_next_action(
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
                    "prompt": "刚被催过",
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
                    "prompt": "等待继续",
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
    lane_state_path = codex_home / "supervisor" / "lane_state.json"
    lane_state_path.write_text(
        json.dumps(
            {
                "lane-a": {
                    "name": "lane-a",
                    "tmux_session": "session-a",
                    "last_status": "working",
                    "last_prompted_at": "2099-01-01T00:00:00+00:00",
                    "prompt_count": 1,
                }
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-lane-b.jsonl",
        session_id="lane-b-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:30Z",
                "SUPERVISOR_STATUS: done\n"
                "SUPERVISOR_SUMMARY: lane-b 已完成。\n"
                "SUPERVISOR_NEXT: 等待继续。",
            )
        ],
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
            "› Improve documentation in @filename\n  gpt-5.5 xhigh · main"
            if session == "session-a"
            else "SUPERVISOR_STATUS: done\n"
            "SUPERVISOR_SUMMARY: lane-b 已完成。\n"
            "SUPERVISOR_NEXT: 等待继续。"
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
        "target_name": "lane-b",
    }
    assert payload["executed"]["managed"]["name"] == "lane-b"
    assert calls == _tmux_send_calls(
        CONTINUE_REQUEST_TEXT,
        buffer_name="isotope-supervisor-managed-b",
        target="session-b",
    )




def test_codex_supervisor_runner_execute_can_disable_prompt_cooldown(
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
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "lane-a",
                "cwd": str(workspace),
                "prompt": "等待输入",
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
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_session_exists",
        lambda session: session == "isotope-lane-a",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_window_has_bell",
        lambda session: False,
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

    for _ in range(2):
        exit_code = supervisor_main(
            [
                "supervise",
                "--codex-home",
                str(codex_home),
                "--iterations",
                "1",
                "--interval",
                "1",
                "--execute",
                "send_status",
                "--prompt-cooldown",
                "0",
                "--json",
            ]
        )
        payload = json.loads(capsys.readouterr().out)
        assert exit_code == 0
        assert payload["executed"]["kind"] == "send_status"
        assert "skipped" not in payload["executed"]

    assert calls == _tmux_send_calls(STATUS_REQUEST_TEXT) + _tmux_send_calls(
        STATUS_REQUEST_TEXT
    )




def test_codex_supervisor_runner_supervise_plain_reports_skipped_prompt(
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
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "lane-a",
                "cwd": str(workspace),
                "prompt": "等待输入",
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
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_session_exists",
        lambda session: session == "isotope-lane-a",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_window_has_bell",
        lambda session: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.subprocess.run",
        lambda command, *, check, text, capture_output: subprocess.CompletedProcess(
            command, 0, "", ""
        ),
    )

    for _ in range(2):
        exit_code = supervisor_main(
            [
                "supervise",
                "--codex-home",
                str(codex_home),
                "--iterations",
                "1",
                "--interval",
                "1",
                "--execute",
                "send_status",
            ]
        )
        assert exit_code == 0
        output = capsys.readouterr().out

    assert "已跳过：lane prompt cooldown active" in output
    assert "已执行：" not in output




def test_codex_supervisor_runner_llm_summary_reports_missing_key(
    tmp_path,
    capsys,
    monkeypatch,
):
    # Point the TOML path to a non-existent file so the resolver has zero entries
    monkeypatch.setenv(
        "SUPERVISOR_LLM_POOL_TOML_FILES",
        str(tmp_path / "nonexistent.toml"),
    )
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-active.jsonl",
        session_id="active-session",
        cwd="/home/lumber/Github/isotope",
        events=[
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {"type": "agent_reasoning", "message": "reading files"},
            )
        ],
    )

    exit_code = supervisor_main(
        [
            "scan",
            "--codex-home",
            str(codex_home),
            "--llm-summary",
            "--json",
        ]
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "codex_supervisor_runner_error"
    assert "LLM pool" in payload["error"]["message"]




def test_codex_supervisor_runner_watch_changes_only_suppresses_unchanged_reports(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-active.jsonl",
        session_id="active-session",
        cwd="/home/lumber/Github/isotope",
        events=[
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {"type": "agent_reasoning", "message": "reading files"},
            )
        ],
    )
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda _: None)

    exit_code = supervisor_main(
        [
            "watch",
            "--codex-home",
            str(codex_home),
            "--interval",
            "1",
            "--iterations",
            "2",
            "--changes-only",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert output.count("[Codex Supervisor]") == 1




def test_codex_supervisor_runner_watch_changes_only_prints_changed_reports(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-active.jsonl",
        session_id="active-session",
        cwd="/home/lumber/Github/isotope",
        events=[
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {"type": "agent_reasoning", "message": "reading files"},
            )
        ],
    )

    def change_session(_: int) -> None:
        _write_session(
            codex_home,
            "2026/05/16/rollout-active.jsonl",
            session_id="active-session",
            cwd="/home/lumber/Github/isotope",
            events=[_assistant_message("2026-05-16T11:59:40Z", "正在运行测试。")],
        )

    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", change_session)

    exit_code = supervisor_main(
        [
            "watch",
            "--codex-home",
            str(codex_home),
            "--interval",
            "1",
            "--iterations",
            "2",
            "--changes-only",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert output.count("[Codex Supervisor]") == 2
    assert "正在运行测试" in output




def test_codex_supervisor_runner_watch_bell_rings_for_attention(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-blocked.jsonl",
        session_id="blocked-session",
        cwd="/home/lumber/Github/isotope",
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "\n".join(
                    [
                        "SUPERVISOR_STATUS: blocked",
                        "SUPERVISOR_SUMMARY: 测试环境缺少 tmux。",
                        "SUPERVISOR_NEXT: 需要人工查看环境。",
                    ]
                ),
            )
        ],
    )
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda _: None)

    exit_code = supervisor_main(
        [
            "watch",
            "--codex-home",
            str(codex_home),
            "--interval",
            "1",
            "--iterations",
            "2",
            "--bell",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == "\a"
    assert captured.out.count("[Codex Supervisor]") == 2
    assert "先查看主动汇报阻塞的窗口" in captured.out




def test_codex_supervisor_runner_supervise_resume_respects_prompt_cooldown(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_session(
        codex_home,
        "2026/05/16/rollout-resume-cooldown.jsonl",
        session_id="019e35a2-e442-75e2-84ab-3761a685a736",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:50:00Z",
                "正在整理 Supervisor 验收结果。",
            )
        ],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return json.dumps(
                {
                    "kind": "resume_session",
                    "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
                    "prompt_kind": "send_status",
                    "reason": "先恢复会话汇报状态。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )
    popen_calls: list[list[str]] = []

    class StubProcess:
        pid = 34567

    def stub_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        popen_calls.append(command)
        return StubProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "2",
            "--interval",
            "1",
            "--llm-execute",
            "--prompt-cooldown",
            "300",
            "--json",
        ]
    )

    assert exit_code == 0
    payloads = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip()
    ]
    assert [payload["executed"]["kind"] for payload in payloads] == [
        "resume_session",
        "resume_session",
    ]
    assert payloads[0]["executed"]["managed"]["name"] == "resume-019e35a2"
    assert payloads[1]["executed"]["skipped"] is True
    assert payloads[1]["executed"]["reason"] == "resume prompt cooldown active"
    assert len(popen_calls) == 1




def test_codex_supervisor_runner_supervise_invalid_llm_action_falls_back_to_monitor(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_session(
        codex_home,
        "2026/05/16/rollout-done.jsonl",
        session_id="done-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "SUPERVISOR_STATUS: done\nSUPERVISOR_SUMMARY: 已完成。\nSUPERVISOR_NEXT: 可以继续下一步。",
            )
        ],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return json.dumps(
                {
                    "kind": "resume_session",
                    "session_id": "done-session",
                    "prompt_kind": "send_status",
                    "reason": "模型误选了已完成会话。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
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
            "--llm-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["llm_action"] == {
        "kind": "monitor",
        "target_name": None,
        "reason": "LLM 动作无效，已跳过执行：unknown resumable session for LLM action: done-session",
        "command_suggestion": None,
        "error": "unknown resumable session for LLM action: done-session",
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "LLM 动作无效，已跳过执行：unknown resumable session for LLM action: done-session",
    }




def test_codex_supervisor_runner_supervise_llm_provider_failure_falls_back_to_monitor(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_session(
        codex_home,
        "2026/05/16/rollout-working.jsonl",
        session_id="working-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "正在整理 Supervisor 验收结果。",
            )
        ],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    class FailingProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            raise ValueError(
                "All LLM pool entries failed: pool:ValueError(empty model response)"
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FailingProvider(),
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
            "--llm-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["llm_action"] == {
        "kind": "monitor",
        "target_name": None,
        "reason": (
            "LLM 动作无效，已跳过执行：All LLM pool entries failed: "
            "pool:ValueError(empty model response)"
        ),
        "command_suggestion": None,
        "error": "All LLM pool entries failed: pool:ValueError(empty model response)",
    }
    assert payload["executed"]["kind"] == "monitor"
    assert payload["executed"]["skipped"] is True




