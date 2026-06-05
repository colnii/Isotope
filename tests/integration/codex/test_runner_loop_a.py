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


def test_codex_supervisor_runner_loop_marks_stale_decision_request_timeout(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    decision_path = codex_home / "supervisor" / "decision_requests.jsonl"
    decision_path.parent.mkdir(parents=True)
    decision_path.write_text(
        json.dumps(
            {
                "event": "decision_request",
                "request_id": "decision-001",
                "created_at": "2026-05-20T12:00:00+00:00",
                "session_id": "goal:goal-001",
                "goal_id": "goal-001",
                "target_name": "goal-supervisor",
                "question": "保留兼容层还是直接迁移？",
                "reason": "目标明确请求拍板。",
                "context_status": "conflict",
                "gate": {
                    "codex_requested_decision": True,
                    "instructions_exhausted": True,
                    "context_status": "conflict",
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.planner.decision_requests._utc_now",
        lambda: datetime(2026, 5, 20, 12, 2, tzinfo=timezone.utc),
    )
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--decision-timeout",
            "60",
            "--no-auto-adopt",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision_timeout_alerts"] == [
        {
            "request_id": "decision-001",
            "goal_id": "goal-001",
            "target_name": "goal-supervisor",
            "lane_name": "goal-supervisor",
            "timeout_seconds": 60,
        }
    ]
    lane_state = json.loads(
        (codex_home / "supervisor" / "lane_state.json").read_text(encoding="utf-8")
    )
    assert lane_state["goal-supervisor"]["decision_timeout_request_id"] == "decision-001"
    assert lane_state["goal-supervisor"]["decision_timeout_seconds"] == 60
    notifications = NotificationFlow.in_process(codex_home).list_notifications(
        notification_type="supervisor_decision_timeout"
    )
    assert len(notifications) == 1
    assert notifications[0].source_ref == {
        "ref_type": "supervisor_decision_timeout",
        "request_id": "decision-001",
        "goal_id": "goal-001",
        "target_name": "goal-supervisor",
        "timeout_seconds": "60",
    }

    exit_code = supervisor_main(
        [
            "decision",
            "archive",
            "--codex-home",
            str(codex_home),
            "--request-id",
            "decision-001",
            "--json",
        ]
    )

    assert exit_code == 0
    capsys.readouterr()
    lane_state = json.loads(
        (codex_home / "supervisor" / "lane_state.json").read_text(encoding="utf-8")
    )
    assert lane_state["goal-supervisor"]["decision_timeout_request_id"] is None
    assert lane_state["goal-supervisor"]["decision_timeout_alerted_at"] is None
    assert lane_state["goal-supervisor"]["decision_timeout_seconds"] is None




def test_codex_supervisor_runner_loop_ignores_answered_decision_request_timeout(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    decision_path = codex_home / "supervisor" / "decision_requests.jsonl"
    decision_path.parent.mkdir(parents=True)
    decision_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event": "decision_request",
                        "request_id": "decision-001",
                        "created_at": "2026-05-20T12:00:00+00:00",
                        "session_id": "goal:goal-001",
                        "goal_id": "goal-001",
                        "target_name": "goal-supervisor",
                        "question": "保留兼容层还是直接迁移？",
                        "reason": "目标明确请求拍板。",
                        "context_status": "conflict",
                        "gate": {
                            "codex_requested_decision": True,
                            "instructions_exhausted": True,
                            "context_status": "conflict",
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "event": "decision_answer",
                        "request_id": "decision-001",
                        "created_at": "2026-05-20T12:01:00+00:00",
                        "session_id": "goal:goal-001",
                        "goal_id": "goal-001",
                        "target_name": "goal-supervisor",
                        "question": "保留兼容层还是直接迁移？",
                        "answer": "保留兼容层。",
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.planner.decision_requests._utc_now",
        lambda: datetime(2026, 5, 20, 12, 2, tzinfo=timezone.utc),
    )
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--decision-timeout",
            "60",
            "--no-auto-adopt",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision_timeout_alerts"] == []
    assert not (codex_home / "supervisor" / "lane_state.json").exists()
    notifications = NotificationFlow.in_process(codex_home).list_notifications(
        notification_type="supervisor_decision_timeout"
    )
    assert notifications == []




def test_codex_supervisor_runner_loop_uses_decision_answer_to_continue_goal(
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
            "按用户拍板继续推进目录迁移。",
            "--target-name",
            "goal-supervisor",
            "--json",
        ]
    )
    assert exit_code == 0
    goal = json.loads(capsys.readouterr().out)["goal"]
    decision_path = codex_home / "supervisor" / "decision_requests.jsonl"
    decision_path.parent.mkdir(parents=True, exist_ok=True)
    decision_path.write_text(
        json.dumps(
            {
                "event": "decision_request",
                "request_id": "decision-001",
                "created_at": "2026-05-20T12:00:00+00:00",
                "session_id": f"goal:{goal['goal_id']}",
                "goal_id": goal["goal_id"],
                "target_name": "goal-supervisor",
                "question": "保留兼容层还是直接迁移？",
                "reason": "目标明确请求拍板。",
                "context_status": "conflict",
                "gate": {
                    "codex_requested_decision": True,
                    "instructions_exhausted": True,
                    "context_status": "conflict",
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    exit_code = supervisor_main(
        [
            "decision",
            "answer",
            "--codex-home",
            str(codex_home),
            "--request-id",
            "decision-001",
            "--answer",
            "保留兼容层，先保证旧入口可用。",
            "--json",
        ]
    )
    assert exit_code == 0
    capsys.readouterr()
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"recent_decision_answers"' in content
            assert "保留兼容层，先保证旧入口可用。" in content
            assert goal["goal_id"] in content
            return json.dumps(
                {
                    "kind": "launch_session",
                    "target_name": "goal-supervisor",
                    "cwd": str(workspace),
                    "prompt": "用户已拍板保留兼容层，请按该方向继续推进目录迁移。",
                    "reason": "已有用户拍板答案，可以继续启动 worker。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )
    captured: dict[str, object] = {}

    class StubProcess:
        pid = 45683

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
    assert payload["decision_requests"] == []
    assert payload["recent_decision_answers"][0]["answer"] == "保留兼容层，先保证旧入口可用。"
    assert payload["llm_action"]["kind"] == "launch_session"
    assert payload["executed"]["kind"] == "launch_session"
    assert captured["command"][9].startswith("WORK ORDER")
    assert "用户已拍板保留兼容层" in captured["command"][9]




def test_codex_supervisor_runner_loop_suggests_all_active_goals(
    tmp_path,
    capsys,
):
    codex_home = tmp_path / ".codex"
    workspace_a = tmp_path / "workspace-a"
    workspace_b = tmp_path / "workspace-b"
    workspace_a.mkdir()
    workspace_b.mkdir()

    for workspace, goal, target_name in (
        (workspace_a, "推进第一个功能目标。", "goal-a"),
        (workspace_b, "推进第二个功能目标。", "goal-b"),
    ):
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
                target_name,
                "--json",
            ]
        )
        assert exit_code == 0
        capsys.readouterr()

    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--workspace-root",
            str(tmp_path),
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
    payload = json.loads(capsys.readouterr().out)
    launch_suggestions = [
        suggestion
        for suggestion in payload["command_suggestions"]
        if suggestion["kind"] == "launch_session"
    ]
    assert [
        (suggestion["target_name"], suggestion["cwd"], suggestion["prompt"])
        for suggestion in launch_suggestions
    ] == [
        ("goal-a", str(workspace_a), "推进第一个功能目标。"),
        ("goal-b", str(workspace_b), "推进第二个功能目标。"),
    ]
    assert [
        goal["goal_id"] for goal in payload["state_snapshot"]["active_goals"]
    ] == [goal["goal_id"] for goal in payload["active_goals"]]
    assert payload["state_snapshot"]["summary"]["active_goals"] == 2




def test_codex_supervisor_runner_loop_prioritizes_active_goals_over_stale_resume(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    goal = "推进目标队列里的新功能。"
    _write_session(
        codex_home,
        "2026/05/16/rollout-stale.jsonl",
        session_id="stale-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:45:00Z",
                "旧会话已经长时间没有新事件。",
            )
        ],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

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
            "goal-worker",
            "--json",
        ]
    )
    assert exit_code == 0
    capsys.readouterr()

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return json.dumps(
                {
                    "kind": "monitor",
                    "reason": "只检查候选排序。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
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
    assert [
        suggestion["kind"] for suggestion in payload["command_suggestions"][:2]
    ] == ["request_context", "launch_session"]
    assert payload["command_suggestions"][0]["query"] == goal
    assert payload["command_suggestions"][1]["target_name"] == "goal-worker"




def test_codex_supervisor_runner_loop_does_not_launch_after_terminal_done_goals(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = codex_home / "supervisor" / "logs" / "managed-done.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: 已完成只读目标。\n"
        "SUPERVISOR_NEXT: 等待 Supervisor 归档。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-done",
                "name": "terminal-goal",
                "cwd": str(workspace),
                "prompt": "完成后等待归档。",
                "command": ["codex", "exec", "-C", str(workspace), "完成后等待归档。"],
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

    class ForbiddenProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            raise AssertionError("terminal done goals should not call the LLM planner")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: ForbiddenProvider(),
    )

    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--workspace-root",
            str(tmp_path),
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
    assert payload["command_suggestions"] == []
    assert payload["llm_action"] == {
        "kind": "monitor",
        "target_name": None,
        "reason": "当前没有可控的 Supervisor 目标，先继续监控。",
        "command_suggestion": None,
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "当前没有可控的 Supervisor 目标，先继续监控。",
    }




def test_codex_supervisor_runner_loop_ignores_exited_managed_process_without_active_goals(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = codex_home / "supervisor" / "logs" / "managed-exited.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("worker exited before reporting terminal status\n", encoding="utf-8")
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-exited",
                "name": "old-cleanup-worker",
                "cwd": str(workspace),
                "prompt": "历史清理任务。",
                "command": ["codex", "exec", "-C", str(workspace), "历史清理任务。"],
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

    class ForbiddenProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            raise AssertionError("exited historical workers should not call the LLM planner")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: ForbiddenProvider(),
    )

    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--workspace-root",
            str(tmp_path),
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
    assert payload["llm_action"] == {
        "kind": "monitor",
        "target_name": None,
        "reason": "当前没有可控的 Supervisor 目标，先继续监控。",
        "command_suggestion": None,
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "当前没有可控的 Supervisor 目标，先继续监控。",
    }




def test_codex_supervisor_runner_loop_with_goal_context_request_feeds_next_planner_call(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    docs_dir = workspace / "docs" / "current"
    docs_dir.mkdir(parents=True)
    (docs_dir / "status.md").write_text(
        "Supervisor 自主节奏：先查上下文，再选择继续、开新会话或询问用户。\n",
        encoding="utf-8",
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-source.jsonl",
        session_id="source-session",
        cwd=str(workspace),
        events=[_assistant_message("2026-05-16T11:59:20Z", "上一轮已完成。")],
    )
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)
    seen_context_on_second_call = False

    class DeterministicProvider:
        calls = 0

        def summarize(self, messages: list[dict[str, str]]) -> str:
            nonlocal seen_context_on_second_call
            self.calls += 1
            content = messages[1]["content"]
            if self.calls == 1:
                assert '"recent_context_results": []' in content
                return json.dumps(
                    {
                        "kind": "request_context",
                        "cwd": str(workspace),
                        "query": "Supervisor 自主节奏",
                        "reason": "缺少项目当前上下文。",
                    },
                    ensure_ascii=False,
                )
            assert '"recent_context_results"' in content
            assert "Supervisor 自主节奏" in content
            assert "docs/current/status.md" in content
            seen_context_on_second_call = True
            return '{"kind":"monitor","reason":"已读到上下文，等待下一轮决策。"}'

    provider = DeterministicProvider()
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: provider,
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
            "--goal",
            "继续推进 Supervisor 自主节奏验证。",
            "--iterations",
            "2",
            "--interval",
            "1",
            "--no-auto-adopt",
            "--json",
        ]
    )

    assert exit_code == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1
    _codex_operation_context_result(json.loads(lines[0])["executed"])
    assert seen_context_on_second_call is True




def test_codex_supervisor_runner_loop_without_active_goal_idles(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_session(
        codex_home,
        "2026/05/16/rollout-source.jsonl",
        session_id="source-session",
        cwd=str(workspace),
        events=[_assistant_message("2026-05-16T11:59:20Z", "上一轮已完成。")],
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            raise AssertionError("loop without active goals should not ask LLM to invent work")

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
    assert payload["active_goals"] == []
    assert payload["llm_action"] == {
        "kind": "monitor",
        "target_name": None,
        "reason": "当前没有可控的 Supervisor 目标，先继续监控。",
        "command_suggestion": None,
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "当前没有可控的 Supervisor 目标，先继续监控。",
    }




def test_codex_supervisor_runner_loop_uses_daily_defaults(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "2",
            "--interval",
            "1",
            "--json",
        ]
    )

    assert exit_code == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["automation"]["ready"] is False
    assert payload["llm_action"] == {
        "kind": "monitor",
        "target_name": None,
        "reason": "当前没有可控的 Supervisor 目标，先继续监控。",
        "command_suggestion": None,
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "reason": "当前没有可控的 Supervisor 目标，先继续监控。",
        "skipped": True,
    }




def test_codex_supervisor_runner_loop_auto_adopts_discovered_tmux_candidate(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls: list[list[str]] = []

    def stub_run(
        command: list[str],
        *,
        check: bool = False,
        text: bool = True,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert text is True
        assert capture_output is True
        if command[:3] == ["tmux", "list-sessions", "-F"]:
            return subprocess.CompletedProcess(command, 0, "iso_dev\t0\t1\n", "")
        if command[:3] == ["tmux", "capture-pane", "-p"]:
            return subprocess.CompletedProcess(
                command,
                0,
                "Working ... esc to interrupt\n  gpt-5.5 xhigh · Context 80% left\n",
                "",
            )
        if command[:3] == ["tmux", "display-message", "-p"]:
            return subprocess.CompletedProcess(command, 0, str(workspace) + "\n", "")
        if command[:3] == ["tmux", "has-session", "-t"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:4] == ["tmux", "set-hook", "-t", "iso_dev"]:
            assert check is True
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:2] == ["git", "-C"]:
            return subprocess.CompletedProcess(command, 0, "main\n", "")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", stub_run)
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_session_exists",
        lambda session: session == "iso_dev",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_window_has_bell",
        lambda session: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._tmux_capture_pane",
        lambda session: "Working ... esc to interrupt\n  gpt-5.5 xhigh · main",
    )

    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--rule-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_adopted"] == [
        {
            "name": "iso-dev",
            "tmux_session": "iso_dev",
            "cwd": str(workspace),
            "status": "adopted",
        }
    ]
    assert payload["automation"]["ready"] is True
    assert payload["auto_action"] == {
        "kind": "monitor",
        "reason": "managed lane is running without ready signal",
    }
    records = [
        json.loads(line)
        for line in (codex_home / "supervisor" / "managed_sessions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert records[0]["name"] == "iso-dev"
    assert records[0]["tmux_session"] == "iso_dev"
    assert records[0]["cwd"] == str(workspace)




