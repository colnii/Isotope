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

def test_codex_supervisor_runner_web_print_url_exits(tmp_path, capsys):
    codex_home = tmp_path / ".codex"

    exit_code = supervisor_main(
        [
            "web",
            "--codex-home",
            str(codex_home),
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
            "--print-url",
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "http://127.0.0.1:8765/"



def test_codex_supervisor_runner_advise_prints_json_command_suggestion(tmp_path, capsys):
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
            "advise",
            "--codex-home",
            str(codex_home),
            "--limit",
            "1",
            "--stale-after",
            NON_STALE_SECONDS,
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["recommendation"]["action"] == "monitor"
    assert payload["command_suggestion"] == {
        "command": "isotope-supervisor watch --interval 180 --changes-only",
        "kind": "watch_changes",
        "label": "继续监控变化",
    }



def test_codex_supervisor_runner_advise_plain_is_short(tmp_path, capsys):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-attention.jsonl",
        session_id="attention-session",
        cwd=EXISTING_WORKSPACE,
        events=[
            _assistant_message("2026-05-16T11:58:00Z", "需要你确认是否继续。"),
        ],
    )

    exit_code = supervisor_main(["advise", "--codex-home", str(codex_home)])

    assert exit_code == 0
    text = capsys.readouterr().out
    assert "[Codex Supervisor 建议]" in text
    assert "建议：先处理等待用户确认的窗口。" in text
    assert "动作：review_user_prompt" in text
    assert "命令：isotope-supervisor resume --name resume-attention-session" in text



def test_codex_supervisor_advise_suggests_managed_tmux_commands():
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="managed:managed-001",
                cwd="/home/lumber/Github/isotope",
                source_path="/home/lumber/.codex/supervisor/managed_sessions.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=30,
                status="working",
                reason="Supervisor 托管 tmux 会话仍在运行",
                managed=True,
                managed_name="lane-a",
                managed_backend="tmux",
                managed_tmux_session="isotope-lane-a",
            ),
        ),
    )

    payload = _advice_payload(report)

    assert payload["command_suggestion"] == {
        "command": "tmux attach -t isotope-lane-a",
        "kind": "tmux_attach",
        "label": "打开托管 tmux 窗口",
    }
    assert payload["command_suggestions"] == [
        {
            "command": "tmux attach -t isotope-lane-a",
            "kind": "tmux_attach",
            "label": "打开托管 tmux 窗口",
        },
        {
            "command": _supervisor_send_command("lane-a", STATUS_REQUEST_TEXT),
            "kind": "send_status",
            "label": "让托管 Codex 汇报状态",
        },
        {
            "command": _supervisor_send_command("lane-a", CONTINUE_REQUEST_TEXT),
            "kind": "send_continue",
            "label": "让托管 Codex 继续推进",
        },
        {
            "command": "isotope-supervisor archive --name lane-a",
            "kind": "archive",
            "label": "归档托管记录",
        },
        {
            "command": "isotope-supervisor watch --interval 180 --changes-only",
            "kind": "watch_changes",
            "label": "继续监控变化",
        },
    ]



def test_codex_supervisor_runner_advice_plain_prints_ask_user_question(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    docs_dir = workspace / "docs" / "current"
    docs_dir.mkdir(parents=True)
    (docs_dir / "status.md").write_text(
        "目录迁移文档和现状冲突，需要用户拍板兼容策略。\n",
        encoding="utf-8",
    )
    request_project_context(
        codex_home=codex_home,
        cwd=workspace,
        query="目录迁移 兼容策略",
        rg_bin=None,
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-needs-user.jsonl",
        session_id="019e35a2-e442-75e2-84ab-3761a685a736",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "\n".join(
                    [
                        "SUPERVISOR_STATUS: needs_user",
                        "SUPERVISOR_SUMMARY: 目录迁移有两种不可兼容方案。",
                        "SUPERVISOR_NEXT: 请用户拍板选择保留兼容层还是直接迁移。",
                    ]
                ),
            )
        ],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert "目录迁移文档和现状冲突" in content
            return json.dumps(
                {
                    "kind": "ask_user",
                    "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
                    "question": "目录迁移是保留兼容层，还是直接迁移并删除旧入口？",
                    "codex_requested_decision": True,
                    "instructions_exhausted": True,
                    "context_status": "conflict",
                    "reason": "Codex 明确要拍板，既有指示不足，文档和现状冲突。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )

    exit_code = supervisor_main(
        [
            "advise",
            "--codex-home",
            str(codex_home),
            "--limit",
            "5",
            "--stale-after",
            "999999",
            "--llm-action",
        ]
    )

    assert exit_code == 0
    text = capsys.readouterr().out
    assert "Supervisor 动作：ask_user" in text
    assert "等待拍板：目录迁移是保留兼容层，还是直接迁移并删除旧入口？" in text
    assert "上下文状态：conflict" in text



def test_codex_supervisor_runner_advise_can_add_supervisor_action(
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

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            assert "command_suggestions" in messages[1]["content"]
            return '{"kind":"send_status","target_name":"lane-a","reason":"先看进度。"}'

    captured: dict[str, object] = {}

    def stub_resolver(**kwargs: object) -> DeterministicProvider:
        captured.update(kwargs)
        return DeterministicProvider()

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        stub_resolver,
    )

    exit_code = supervisor_main(
        [
            "advise",
            "--codex-home",
            str(codex_home),
            "--limit",
            "1",
            "--llm-action",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["supervisor_action"] == {
        "kind": "send_status",
            "target_name": "lane-a",
            "reason": "先看进度。",
            "command_suggestion": {
                "command": _supervisor_send_command("lane-a", STATUS_REQUEST_TEXT),
                "kind": "send_status",
                "label": "让托管 Codex 汇报状态",
            },
    }
    assert payload["llm_action"] == payload["supervisor_action"]
    assert captured["agent_name"] == "supervisor"



def test_codex_supervisor_runner_advise_execute_send_status(
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
        assert check is True
        assert text is True
        assert capture_output is True
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", stub_run)

    exit_code = supervisor_main(
        [
            "advise",
            "--codex-home",
            str(codex_home),
            "--execute",
            "send_status",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["executed"] == {
        "command": _supervisor_send_command("lane-a", STATUS_REQUEST_TEXT),
        "kind": "send_status",
        "managed": {
            "name": "lane-a",
            "record_id": "managed-001",
            "tmux_session": "isotope-lane-a",
        },
        "text": STATUS_REQUEST_TEXT,
    }
    assert calls == _tmux_send_calls(STATUS_REQUEST_TEXT)



def test_codex_supervisor_runner_advise_name_targets_managed_lane(
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
            "advise",
            "--codex-home",
            str(codex_home),
            "--name",
            "lane-b",
            "--execute",
            "send_status",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    send_status = next(
        item
        for item in payload["command_suggestions"]
        if item["kind"] == "send_status"
    )
    assert send_status["command"] == _supervisor_send_command("lane-b", STATUS_REQUEST_TEXT)
    assert payload["executed"]["managed"]["name"] == "lane-b"
    assert calls == _tmux_send_calls(
        STATUS_REQUEST_TEXT,
        buffer_name="isotope-supervisor-managed-b",
        target="session-b",
    )



def test_codex_supervisor_runner_advise_name_missing_does_not_fallback(
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
            "advise",
            "--codex-home",
            str(codex_home),
            "--name",
            "missing",
            "--execute",
            "send_status",
            "--json",
        ]
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "codex_supervisor_runner_error"
    assert payload["error"]["message"] == "managed lane not found: missing"
    assert calls == []



def test_codex_supervisor_runner_advise_execute_rejects_non_send_kind(
    tmp_path,
    capsys,
):
    codex_home = tmp_path / ".codex"

    exit_code = supervisor_main(
        [
            "advise",
            "--codex-home",
            str(codex_home),
            "--execute",
            "tmux_attach",
            "--json",
        ]
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "codex_supervisor_runner_error"
    assert "send_status" in payload["error"]["message"]
    assert "send_continue" in payload["error"]["message"]



