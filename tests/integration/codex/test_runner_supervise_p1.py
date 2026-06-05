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


def test_codex_supervisor_send_status_text_requires_protocol_report():
    text = EXECUTABLE_ADVICE_TEXT["send_status"]

    assert "\n" not in text
    assert "SUPERVISOR_STATUS:" in text
    assert "SUPERVISOR_SUMMARY:" in text
    assert "SUPERVISOR_NEXT:" in text
    assert "working|done|blocked|needs_user" in text




def test_codex_supervisor_send_continue_text_requires_protocol_report():
    text = EXECUTABLE_ADVICE_TEXT["send_continue"]

    assert "\n" not in text
    assert "SUPERVISOR_STATUS:" in text
    assert "SUPERVISOR_SUMMARY:" in text
    assert "SUPERVISOR_NEXT:" in text




def test_codex_supervisor_runner_supervisor_action_becomes_primary_command_suggestion(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session_path = _write_session(
        codex_home,
        "2026/05/16/rollout-large-resume.jsonl",
        session_id="large-resume-session",
        cwd=str(workspace),
        events=[
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {"type": "agent_reasoning", "message": "working"},
            )
        ],
    )
    with session_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                _event(
                    "2026-05-16T11:59:30Z",
                    "event_msg",
                    {"type": "agent_reasoning", "message": "x" * 70000},
                ),
                ensure_ascii=False,
            )
            + "\n"
        )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"resume_context_hint": "large_session_file"' in content
            return json.dumps(
                {
                    "kind": "request_context",
                    "cwd": str(workspace),
                    "query": "Supervisor 下一步",
                    "reason": "大会话先查上下文。",
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
            "--workspace-root",
            str(workspace),
            "--limit",
            "1",
            "--stale-after",
            "999999",
            "--llm-action",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["supervisor_action"]["kind"] == "request_context"
    assert (
        payload["command_suggestion"]
        == payload["supervisor_action"]["command_suggestion"]
    )
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["command_suggestion"]["kind"] == "request_context"
    assert payload["rule_command_suggestion"]["kind"] == "resume_session"




def test_codex_supervisor_runner_supervise_supervisor_action_passes_worker_reviews(
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
        events=[_assistant_message("2026-05-16T11:59:20Z", "上一轮 worker 已完成。")],
    )
    worker_reviews = {
        "status": "ok",
        "decision_summary": {
            "merge_candidates": 1,
            "continue_or_split_tasks": 0,
            "missing_worktrees": 0,
            "needs_fresh_review": 1,
        },
        "workers": [
            {
                "record_id": "managed-001",
                "name": "worker-a",
                "cwd": str(workspace),
                "cwd_exists": True,
                "next_decision": {
                    "recommendation": "review_then_merge_candidate",
                    "summary": "worker 已完成且有本地改动；建议先复查 diff 并跑验证，通过后再人工合并。",
                    "merge_suitable": True,
                    "continue_or_split_task": False,
                    "risk_level": "medium",
                },
            }
        ],
        "safety": {"auto_merge": False, "delete_branch": False},
    }

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            payload = json.loads(messages[1]["content"])
            assert payload["worker_reviews"]["workers"][0]["name"] == "worker-a"
            assert payload["worker_reviews"]["workers"][0]["next_decision"][
                "merge_suitable"
            ] is True
            assert payload["worker_reviews"]["safety"]["auto_merge"] is False
            assert "merge" not in payload["allowed_kinds"]
            return json.dumps(
                {
                    "kind": "request_context",
                    "cwd": str(workspace),
                    "query": "worker-a diff review next_decision",
                    "reason": "worker review 指向 fresh review，先检索上下文。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_worker_reviews",
        lambda *, codex_home, **kwargs: worker_reviews,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
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
            "--llm-action",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["worker_reviews"] == worker_reviews
    assert payload["supervisor_action"]["kind"] == "request_context"
    assert payload["supervisor_action"]["query"] == "worker-a diff review next_decision"
    assert payload["llm_action"] == payload["supervisor_action"]




def test_codex_supervisor_runner_supervisor_action_scopes_to_workspace_root(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "isotope"
    workspace.mkdir()
    external_workspace = tmp_path / "other"
    external_workspace.mkdir()
    _write_session(
        codex_home,
        "2026/05/16/rollout-external.jsonl",
        session_id="external-session",
        cwd=str(external_workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:50Z",
                "正在另一个项目里工作。",
            )
        ],
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-isotope.jsonl",
        session_id="isotope-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "正在整理 Isotope Supervisor。",
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
            assert "external-session" not in content
            assert "isotope-session" in content
            assert f'"available_workspaces": ["{workspace}"]' in content
            return '{"kind":"monitor","reason":"只监控当前项目工作区。"}'

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
            "--workspace-root",
            str(workspace),
            "--llm-action",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["supervisor_action"]["kind"] == "monitor"
    assert payload["llm_action"] == payload["supervisor_action"]
    suggestion_text = json.dumps(payload["command_suggestions"], ensure_ascii=False)
    assert "external-session" not in suggestion_text
    assert "isotope-session" in suggestion_text




def test_codex_supervisor_runner_supervise_json_includes_llm_summary_and_advice(
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

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            assert "active-session" in messages[1]["content"]
            assert "recommendation" in messages[1]["content"]
            return "窗口 A 正在读文件，建议继续监控。"

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
            "supervise",
            "--codex-home",
            str(codex_home),
            "--limit",
            "1",
            "--stale-after",
            NON_STALE_SECONDS,
            "--iterations",
            "1",
            "--interval",
            "1",
            "--llm-summary",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["iteration"] == 1
    assert payload["report"]["sessions"][0]["session_id"] == "active-session"
    assert payload["recommendation"]["action"] == "monitor"
    assert payload["command_suggestions"] == [
        {
            "command": "isotope-supervisor watch --interval 180 --changes-only",
            "kind": "watch_changes",
            "label": "继续监控变化",
        }
    ]
    assert payload["llm_summary"] == "窗口 A 正在读文件，建议继续监控。"
    assert captured["agent_name"] == "supervisor"




def test_codex_supervisor_runner_supervise_can_execute_send_status(
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
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["executed"]["kind"] == "send_status"
    assert payload["executed"]["text"] == STATUS_REQUEST_TEXT
    assert calls == _tmux_send_calls(STATUS_REQUEST_TEXT)




def test_codex_supervisor_runner_supervise_llm_execute_sends_whitelisted_action(
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
        lambda session: "› 这是可输入的托管窗口\n  gpt-5.5 xhigh · main",
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert (
                '"allowed_kinds": ["monitor", "send_status", "send_continue", '
                '"resume_session", "launch_session", "request_context", "ask_user", '
                '"delete_worktree", "call_capacity"]'
            ) in content
            assert '"managed_terminal_ready": true' in content
            return '{"kind":"send_status","target_name":"lane-a","reason":"先看进度。"}'

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
    assert payload["supervisor_action"]["kind"] == "send_status"
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["executed"]["kind"] == "send_status"
    assert payload["executed"]["managed"]["name"] == "lane-a"
    assert payload["executed"]["text"] == STATUS_REQUEST_TEXT
    assert calls == _tmux_send_calls(STATUS_REQUEST_TEXT)


@pytest.mark.parametrize(
    ("kind", "request_text"),
    [
        ("send_status", STATUS_REQUEST_TEXT),
        ("send_continue", CONTINUE_REQUEST_TEXT),
    ],
)


def test_codex_supervisor_runner_supervise_llm_execute_blocks_busy_tmux_send(
    tmp_path,
    capsys,
    monkeypatch,
    kind,
    request_text,
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
        lambda session: "\n".join(
            [
                "• Running tests",
                "◦ Working (esc to interrupt)",
            ]
        ),
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"managed_terminal_ready": false' in content
            return json.dumps(
                {"kind": kind, "target_name": "lane-a", "reason": "直接追问。"},
                ensure_ascii=False,
            )

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
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--llm-execute",
            "--prompt-cooldown",
            "0",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["supervisor_action"]["kind"] == kind
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "managed lane is running without ready signal",
        "blocked_kind": kind,
        "command": _supervisor_send_command("lane-a", request_text),
    }
    assert calls == []




def test_codex_supervisor_runner_supervise_llm_execute_uses_selected_target_command(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    _write_managed_tmux_record(
        codex_home,
        workspace=workspace,
        append=True,
        name="lane-b",
        record_id="managed-002",
        tmux_session="isotope-lane-b",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_session_exists",
        lambda session: session in {"isotope-lane-a", "isotope-lane-b"},
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_window_has_bell",
        lambda session: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._tmux_capture_pane",
        lambda session: "› 等待输入\n  gpt-5.5 xhigh · main",
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"target_name": "lane-a"' in content
            assert '"target_name": "lane-b"' in content
            return (
                '{"kind":"send_continue","target_name":"lane-b",'
                '"reason":"lane-b 已完成上一轮，可以继续。"}'
            )

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
    assert payload["executed"]["managed"]["name"] == "lane-b"
    assert (
        "--name lane-b"
        in payload["supervisor_action"]["command_suggestion"]["command"]
    )
    assert payload["llm_action"] == payload["supervisor_action"]
    assert "--name lane-b" in payload["executed"]["command"]
    assert calls == _tmux_send_calls(
        CONTINUE_REQUEST_TEXT,
        buffer_name="isotope-supervisor-managed-002",
        target="isotope-lane-b",
    )




def test_codex_supervisor_runner_supervise_llm_execute_skips_monitor(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-active.jsonl",
        session_id="active-session",
        cwd=EXISTING_WORKSPACE,
        events=[
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {"type": "agent_reasoning", "message": "reading files"},
            )
        ],
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
    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"can_resume": true' in content
            return '{"kind":"monitor","reason":"仍在工作，先观察。"}'

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
    assert payload["supervisor_action"] == {
        "kind": "monitor",
        "target_name": None,
        "reason": "仍在工作，先观察。",
        "command_suggestion": None,
    }
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "仍在工作，先观察。",
    }
    assert calls == []




