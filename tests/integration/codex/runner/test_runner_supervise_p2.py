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


def test_codex_supervisor_runner_supervise_llm_execute_can_resume_session(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_session(
        codex_home,
        "2026/05/16/rollout-resume.jsonl",
        session_id="019e35a2-e442-75e2-84ab-3761a685a736",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "正在整理 Supervisor 验收结果，尚未输出最终状态。",
            )
        ],
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"can_resume": true' in content
            assert '"kind": "resume_session"' in content
            return json.dumps(
                {
                        "kind": "resume_session",
                        "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
                        "prompt_kind": "send_continue",
                        "reason": "旧会话长时间未更新，可以恢复后继续。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )
    captured: dict[str, object] = {}

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
        captured["command"] = command
        captured["cwd"] = cwd
        captured["stdin"] = stdin
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return StubProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)

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
    assert payload["supervisor_action"]["kind"] == "resume_session"
    assert payload["supervisor_action"]["target_name"] == "resume-019e35a2"
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["executed"]["kind"] == "resume_session"
    assert payload["executed"]["managed"]["name"] == "resume-019e35a2"
    assert payload["executed"]["managed"]["pid"] == 34567
    assert payload["executed"]["text"] == CONTINUE_REQUEST_TEXT
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
    assert captured["command"][9] == "resume"
    assert captured["command"][10] == "019e35a2-e442-75e2-84ab-3761a685a736"
    assert captured["command"][11].startswith("继续推进当前任务。")
    assert captured["cwd"] == str(workspace)
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["stderr"] is subprocess.STDOUT




def test_codex_supervisor_llm_execute_blocks_old_resume_when_active_goal_exists(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="old-session",
                cwd=str(workspace),
                source_path=str(codex_home / "sessions/old.jsonl"),
                last_event_at=NOW.isoformat(),
                age_seconds=900,
                status="stale",
                reason="旧普通会话长时间没有新事件。",
            ),
        ),
    )
    payload = {
        "active_goals": [
            {
                "goal_id": "goal-001",
                "goal": "推进目标队列里的新功能。",
                "cwd": str(workspace),
                "target_name": "goal-worker",
            }
        ],
        "command_suggestions": [
            {
                "kind": "request_context",
                "cwd": str(workspace),
                "query": "推进目标队列里的新功能。",
                "command": "isotope-supervisor context",
            },
            {
                "kind": "launch_session",
                "target_name": "goal-worker",
                "cwd": str(workspace),
                "prompt": "推进目标队列里的新功能。",
                "command": "isotope-supervisor launch --name goal-worker",
            },
        ],
        "supervisor_action": {
            "kind": "resume_session",
            "session_id": "old-session",
            "prompt_kind": "send_continue",
            "target_name": "resume-old",
            "reason": "错误地恢复旧普通会话。",
            "command_suggestion": {
                "kind": "resume_session",
                "session_id": "old-session",
                "prompt_kind": "send_continue",
                "target_name": "resume-old",
                "command": "isotope-supervisor resume --name resume-old",
            },
        },
    }

    def stub_resume_managed_codex(*args: object, **kwargs: object) -> object:
        raise AssertionError("old session must not be resumed while active goals exist")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resume_managed_codex",
        stub_resume_managed_codex,
    )

    result = _execute_llm_action(
        _runner_args(codex_home),
        report,
        payload,
    )

    assert result == {
        "kind": "resume_session",
        "skipped": True,
        "reason": "resume session outside active goals",
        "session_id": "old-session",
    }




def test_codex_supervisor_runner_supervise_resume_skips_running_process_cwd(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = codex_home / "supervisor" / "logs" / "managed-running.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("worker still running\n", encoding="utf-8")
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-running",
                "name": "planner-session",
                "cwd": str(workspace),
                "prompt": "继续推进 Supervisor。",
                "command": ["codex", "exec", "-C", str(workspace), "WORK ORDER"],
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
    _write_session(
        codex_home,
        "2026/05/16/rollout-active-worker.jsonl",
        session_id="019e4055-c9d9-7c22-87c9-b30bc57875a2",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "SUPERVISOR_STATUS: working\n"
                "SUPERVISOR_SUMMARY: 正在读取项目状态。\n"
                "SUPERVISOR_NEXT: 继续读取项目状态并判断下一步。",
            )
        ],
    )

    monkeypatch.setattr(
        "isotope.features.supervisor.flow._pid_is_running",
        lambda pid: pid == 4242,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._pid_is_running",
        lambda pid: pid == 4242,
        raising=False,
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return json.dumps(
                {
                    "kind": "resume_session",
                    "session_id": "019e4055-c9d9-7c22-87c9-b30bc57875a2",
                    "prompt_kind": "send_status",
                    "reason": "恢复正在运行的 worker 查看状态。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )

    def stub_resume_managed_codex(*args: object, **kwargs: object) -> object:
        raise AssertionError("running worker cwd should not be resumed")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resume_managed_codex",
        stub_resume_managed_codex,
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
    assert payload["supervisor_action"]["kind"] == "resume_session"
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["executed"]["kind"] == "resume_session"
    assert payload["executed"]["skipped"] is True
    assert payload["executed"]["reason"] == "managed process already running"
    assert payload["executed"]["managed"] == {
        "name": "planner-session",
        "record_id": "managed-running",
        "pid": 4242,
        "backend": "process",
    }




def test_codex_supervisor_runner_supervise_resume_skips_missing_cwd(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    missing_workspace = tmp_path / "deleted-worktree"
    _write_session(
        codex_home,
        "2026/05/16/rollout-deleted-worktree.jsonl",
        session_id="019e4055-c9d9-7c22-87c9-b30bc57875a2",
        cwd=str(missing_workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "SUPERVISOR_STATUS: working\n"
                "SUPERVISOR_SUMMARY: 正在读取项目状态。\n"
                "SUPERVISOR_NEXT: 继续读取项目状态并判断下一步。",
            )
        ],
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return json.dumps(
                {
                    "kind": "resume_session",
                    "session_id": "019e4055-c9d9-7c22-87c9-b30bc57875a2",
                    "prompt_kind": "send_status",
                    "reason": "恢复旧 worker 会话查看状态。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )

    def stub_resume_managed_codex(*args: object, **kwargs: object) -> object:
        raise AssertionError("missing cwd should not be passed to codex exec resume")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resume_managed_codex",
        stub_resume_managed_codex,
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
    assert payload["supervisor_action"]["kind"] == "monitor"
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["executed"]["kind"] == "monitor"
    assert payload["executed"]["skipped"] is True
    assert all(
        suggestion.get("cwd") != str(missing_workspace)
        for suggestion in payload["command_suggestions"]
    )




def test_codex_supervisor_runner_supervise_context_rejects_missing_cwd(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    missing_workspace = tmp_path / "deleted-worktree"
    _write_session(
        codex_home,
        "2026/05/16/rollout-deleted-worktree.jsonl",
        session_id="019e4055-c9d9-7c22-87c9-b30bc57875a2",
        cwd=str(missing_workspace),
        events=[_assistant_message("2026-05-16T11:59:20Z", "仍在整理状态。")],
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return json.dumps(
                {
                    "kind": "request_context",
                    "cwd": str(missing_workspace),
                    "query": "Supervisor 当前状态",
                    "reason": "先查上下文。",
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
    assert payload["supervisor_action"]["kind"] == "monitor"
    assert payload["supervisor_action"]["error"] == (
        f"unknown workspace for LLM action: {missing_workspace}"
    )
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["executed"]["skipped"] is True
    assert payload["executed"]["kind"] == "monitor"




def test_codex_supervisor_runner_supervise_llm_execute_can_launch_session(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    launch_prompt = "请根据当前文档继续推进 Supervisor，并按状态协议汇报。"
    _write_session(
        codex_home,
        "2026/05/16/rollout-source.jsonl",
        session_id="source-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "SUPERVISOR_STATUS: done\nSUPERVISOR_SUMMARY: 已完成。\nSUPERVISOR_NEXT: 可开新任务。",
            )
        ],
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"available_workspaces"' in content
            assert '"kind": "launch_session"' in content
            return json.dumps(
                {
                    "kind": "launch_session",
                    "target_name": "new-planner",
                    "cwd": str(workspace),
                    "prompt": launch_prompt,
                    "reason": "需要开新会话并行推进下一批。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )
    captured: dict[str, object] = {}

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
        captured["command"] = command
        captured["cwd"] = cwd
        captured["stdin"] = stdin
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return StubProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)

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
            "--worker-codex-model",
            "gpt-5.4-mini",
            "--worker-codex-config",
            'model_reasoning_effort="low"',
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["supervisor_action"]["kind"] == "launch_session"
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["executed"]["kind"] == "launch_session"
    assert payload["executed"]["managed"]["name"] == "new-planner"
    assert payload["executed"]["managed"]["pid"] == 45678
    assert "WORK ORDER" in payload["executed"]["text"]
    assert f"goal: {launch_prompt}" in payload["executed"]["text"]
    assert f"cwd: {workspace}" in payload["executed"]["text"]
    assert "budget_hint: prompt-only" in payload["executed"]["text"]
    assert "这不是 Supervisor 强制预算控制" in payload["executed"]["text"]
    assert "必须在本 worktree 内提交一个 Conventional Commits 提交" in payload[
        "executed"
    ]["text"]
    assert "commit_exception" in payload["executed"]["text"]
    assert "SUPERVISOR_STATUS" in payload["executed"]["text"]
    assert captured["command"][:9] == [
        "codex",
        "exec",
        "-m",
        "gpt-5.4-mini",
        "-c",
        'model_reasoning_effort="low"',
        "-C",
        str(workspace),
        "--skip-git-repo-check",
    ]
    assert "WORK ORDER" in captured["command"][9]
    assert f"goal: {launch_prompt}" in captured["command"][9]
    assert "budget_hint: prompt-only" in captured["command"][9]
    assert "这不是 Supervisor 强制预算控制" in captured["command"][9]
    assert "必须在本 worktree 内提交一个 Conventional Commits 提交" in captured[
        "command"
    ][9]
    assert "commit_exception" in captured["command"][9]
    assert "SUPERVISOR_STATUS" in captured["command"][9]
    assert captured["cwd"] == str(workspace)
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["stderr"] is subprocess.STDOUT




def test_codex_supervisor_runner_supervise_launch_uses_light_worker_profile(
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
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "SUPERVISOR_STATUS: done\nSUPERVISOR_SUMMARY: 已完成。\nSUPERVISOR_NEXT: 可开新任务。",
            )
        ],
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return json.dumps(
                {
                    "kind": "launch_session",
                    "target_name": "quick-smoke",
                    "cwd": str(workspace),
                    "prompt": "只读检查当前状态并输出三行状态协议。",
                    "worker_profile": "light",
                    "reason": "只读 smoke 不需要高推理代码档。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )
    captured: dict[str, object] = {}

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
        captured["command"] = command
        captured["cwd"] = cwd
        return StubProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)

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
    assert payload["supervisor_action"]["worker_profile"] == "light"
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["executed"]["kind"] == "launch_session"
    assert payload["executed"]["worker_profile"] == "light"
    assert captured["command"][:6] == [
        "codex",
        "exec",
        "-m",
        "gpt-5.5",
        "-c",
        'model_reasoning_effort="low"',
    ]




def test_codex_supervisor_runner_supervise_launch_uses_isolated_worktree(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    launch_prompt = "请在隔离工作区继续推进 Supervisor。"
    _write_session(
        codex_home,
        "2026/05/16/rollout-source.jsonl",
        session_id="source-session",
        cwd=str(repo_root),
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "SUPERVISOR_STATUS: done\nSUPERVISOR_SUMMARY: 已完成。\nSUPERVISOR_NEXT: 可开新任务。",
            )
        ],
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return json.dumps(
                {
                    "kind": "launch_session",
                    "target_name": "new-planner",
                    "cwd": str(repo_root),
                    "prompt": launch_prompt,
                    "reason": "需要隔离工作区推进下一批。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )
    run_calls: list[list[str]] = []

    def stub_run(
        command: list[str],
        *,
        check: bool = False,
        text: bool = False,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        run_calls.append(command)
        if command[:4] == ["git", "-C", str(repo_root), "rev-parse"]:
            return subprocess.CompletedProcess(command, 0, str(repo_root) + "\n", "")
        if command[:6] == ["git", "-C", str(repo_root), "worktree", "add", "-b"]:
            Path(command[-2]).mkdir(parents=True)
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(command, 0, "", "")

    captured: dict[str, object] = {}

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
        captured["command"] = command
        captured["cwd"] = cwd
        return StubProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", stub_run)
    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)

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
    worktree = payload["executed"]["worktree"]
    assert worktree["enabled"] is True
    assert worktree["source_cwd"] == str(repo_root)
    assert worktree["cwd"].startswith(str(repo_root / ".worktrees" / "supervisor"))
    assert worktree["branch"].startswith("supervisor/new-planner-")
    assert ["git", "-C", str(repo_root), "worktree", "add", "-b"] in [
        call[:6] for call in run_calls
    ]
    assert captured["cwd"] == worktree["cwd"]
    assert captured["command"][captured["command"].index("-C") + 1] == worktree["cwd"]
    assert f"cwd: {worktree['cwd']}" in payload["executed"]["text"]




def test_codex_supervisor_runner_supervise_launch_preserves_subdir_in_worktree(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    repo_root = tmp_path / "repo"
    workspace = repo_root / "apps" / "api"
    workspace.mkdir(parents=True)
    _write_session(
        codex_home,
        "2026/05/16/rollout-source.jsonl",
        session_id="source-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "SUPERVISOR_STATUS: done\nSUPERVISOR_SUMMARY: 已完成。\nSUPERVISOR_NEXT: 可开新任务。",
            )
        ],
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return json.dumps(
                {
                    "kind": "launch_session",
                    "target_name": "api-worker",
                    "cwd": str(workspace),
                    "prompt": "继续推进 API 子目录任务。",
                    "reason": "需要隔离子目录任务。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    def stub_run(
        command: list[str],
        *,
        check: bool = False,
        text: bool = False,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        if command[:4] == ["git", "-C", str(workspace), "rev-parse"]:
            return subprocess.CompletedProcess(command, 0, str(repo_root) + "\n", "")
        if command[:4] == ["git", "-C", str(repo_root), "worktree"]:
            worktree_root = Path(command[-2])
            (worktree_root / "apps" / "api").mkdir(parents=True)
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(command, 0, "", "")

    captured: dict[str, object] = {}

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
        captured["command"] = command
        captured["cwd"] = cwd
        return StubProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", stub_run)
    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)

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
    worktree = payload["executed"]["worktree"]
    assert worktree["source_cwd"] == str(workspace)
    assert worktree["cwd"].endswith("/apps/api")
    assert worktree["worktree_root"] in worktree["cwd"]
    assert captured["cwd"] == worktree["cwd"]




def test_codex_supervisor_runner_supervise_launch_respects_prompt_cooldown(
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
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "SUPERVISOR_STATUS: done\nSUPERVISOR_SUMMARY: 已完成。\nSUPERVISOR_NEXT: 可开新任务。",
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
                    "kind": "launch_session",
                    "target_name": "planner-session",
                    "cwd": str(workspace),
                    "prompt": "继续推进 Supervisor 下一步。",
                    "reason": "启动新会话继续推进。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )
    popen_calls: list[list[str]] = []

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
        "launch_session",
        "launch_session",
    ]
    assert payloads[0]["executed"]["managed"]["name"] == "planner-session"
    assert payloads[1]["executed"]["skipped"] is True
    assert payloads[1]["executed"]["reason"] == "launch prompt cooldown active"
    assert len(popen_calls) == 1
    assert popen_calls[0][:9] == [
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




def test_codex_supervisor_runner_supervise_launch_skips_running_named_process(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = codex_home / "supervisor" / "logs" / "managed-running.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("worker still running\n", encoding="utf-8")
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-running",
                "name": "planner-session",
                "cwd": str(workspace),
                "prompt": "继续推进 Supervisor。",
                "command": [
                    "codex",
                    "exec",
                    "-C",
                    str(workspace),
                    "--skip-git-repo-check",
                    "继续推进 Supervisor。",
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

    monkeypatch.setattr(
        "isotope.features.supervisor.flow._pid_is_running",
        lambda pid: pid == 4242,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._pid_is_running",
        lambda pid: pid == 4242,
        raising=False,
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return json.dumps(
                {
                    "kind": "launch_session",
                    "target_name": "planner-session",
                    "cwd": str(workspace),
                    "prompt": "继续推进 Supervisor 下一步。",
                    "reason": "继续开新 worker。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )

    def stub_launch_managed_codex(*args: object, **kwargs: object) -> object:
        raise AssertionError("running planner-session should not be relaunched")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.launch_managed_codex",
        stub_launch_managed_codex,
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
    assert payload["supervisor_action"]["kind"] == "monitor"
    assert payload["supervisor_action"]["error"] == (
        "target already has running managed worker: planner-session"
    )
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": (
            "LLM 动作无效，已跳过执行："
            "target already has running managed worker: planner-session"
        ),
    }



