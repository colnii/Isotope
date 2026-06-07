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


def test_codex_supervisor_runner_loop_fanout_launches_parallel_active_goals(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    goals = [
        ("实现 worker A。", "worker-a"),
        ("实现 worker B。", "worker-b"),
        ("实现 worker C。", "worker-c"),
        ("实现 worker D。", "worker-d"),
    ]
    for goal, target_name in goals:
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
    running_log = codex_home / "supervisor" / "logs" / "managed-running.log"
    running_log.parent.mkdir(parents=True, exist_ok=True)
    running_log.write_text("worker B still running\n", encoding="utf-8")
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-running",
                "name": "worker-b",
                "cwd": str(workspace),
                "prompt": "实现 worker B。",
                "command": ["codex", "exec", "-C", str(workspace), "WORK ORDER"],
                "pid": 4242,
                "started_at": NOW.isoformat(),
                "log_path": str(running_log),
                "status": "launched",
                "backend": "process",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    running_pids = {4242}
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._pid_is_running",
        lambda pid: pid in running_pids,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._pid_is_running",
        lambda pid: pid in running_pids,
        raising=False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            raise AssertionError("fanout should execute without a single-action LLM pick")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )
    captured: list[list[str]] = []

    class StubProcess:
        def __init__(self, pid: int) -> None:
            self.pid = pid

    def stub_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        captured.append(command)
        pid = 45690 + len(captured)
        running_pids.add(pid)
        return StubProcess(pid)

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
            "--max-fanout-launches",
            "2",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["supervisor_action"] == {
        "kind": "fanout_launch_sessions",
        "target_name": None,
        "reason": "多个 active goals 可并行启动受控 worker。",
        "command_suggestion": None,
    }
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["fanout_plan"]["summary"] == {
        "launchable": 1,
        "skipped": 3,
        "limit": 2,
    }
    assert [item["target_name"] for item in payload["fanout_plan"]["launch_specs"]] == [
        "worker-a",
    ]
    assert all(
        item["review"]["requires_human_review"] is False
        for item in payload["fanout_plan"]["launch_specs"]
    )
    assert payload["fanout_plan"]["skipped"] == [
        {
            "target_name": "worker-b",
            "reason": "worker_already_running",
            "batch": "active_goals",
        },
        {
            "target_name": "worker-c",
            "reason": "global_running_limit_reached",
            "batch": "active_goals",
        },
        {
            "target_name": "worker-d",
            "reason": "global_running_limit_reached",
            "batch": "active_goals",
        },
    ]
    assert payload["executed"]["kind"] == "fanout_launch_sessions"
    assert payload["executed"]["summary"] == {
        "launched": 1,
        "skipped": 0,
        "limit": 2,
    }
    assert [item["managed"]["name"] for item in payload["executed"]["results"]] == [
        "worker-a",
    ]
    assert len(captured) == 1
    assert all(command[9].startswith("WORK ORDER") for command in captured)
    assert all("completion_template:" in command[9] for command in captured)
    assert all(
        "integration-review 会自动归入 already_integrated" in command[9]
        for command in captured
    )
    assert all("SUPERVISOR_STATUS: done" not in command[9] for command in captured)
    assert sorted(
        worker["name"] for worker in payload["current_batch"]["managed_workers"]
    ) == [
        "worker-a",
        "worker-b",
    ]
    assert payload["current_batch"]["target_names"] == [
        "worker-a",
        "worker-b",
        "worker-c",
        "worker-d",
    ]

    exit_code = supervisor_main(
        [
            "dashboard",
            "--codex-home",
            str(codex_home),
            "--limit",
            "10",
            "--json",
        ]
    )

    assert exit_code == 0
    dashboard_payload = json.loads(capsys.readouterr().out)
    assert sorted(
        worker["name"] for worker in dashboard_payload["current"]["managed_workers"]
    ) == [
        "worker-a",
        "worker-b",
    ]
    assert dashboard_payload["current"]["target_names"] == [
        "worker-a",
        "worker-b",
        "worker-c",
        "worker-d",
    ]




def test_codex_supervisor_runner_loop_summarizes_completed_fanout_batch(
    tmp_path,
    capsys,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    first_goal = _add_supervisor_goal(
        capsys,
        codex_home=codex_home,
        workspace=workspace,
        goal="完成 fanout worker A。",
        target_name="worker-a",
    )
    second_goal = _add_supervisor_goal(
        capsys,
        codex_home=codex_home,
        workspace=workspace,
        goal="完成 fanout worker B。",
        target_name="worker-b",
    )
    log_dir = codex_home / "supervisor" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    first_log = log_dir / "managed-a.log"
    second_log = log_dir / "managed-b.log"
    first_log.write_text(
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: worker A 已完成并提交。\n"
        "SUPERVISOR_NEXT: 等待 Supervisor 汇总。\n",
        encoding="utf-8",
    )
    second_log.write_text(
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: worker B 已完成并提交。\n"
        "SUPERVISOR_NEXT: 等待 Supervisor 汇总。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "record_id": "managed-a",
                        "name": "worker-a",
                        "cwd": str(workspace),
                        "prompt": "完成 fanout worker A。",
                        "command": ["codex", "exec", "-C", str(workspace), "继续"],
                        "pid": 0,
                        "started_at": NOW.isoformat(),
                        "log_path": str(first_log),
                        "status": "launched",
                        "backend": "process",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "record_id": "managed-b",
                        "name": "worker-b",
                        "cwd": str(workspace),
                        "prompt": "完成 fanout worker B。",
                        "command": ["codex", "exec", "-C", str(workspace), "继续"],
                        "pid": 0,
                        "started_at": NOW.isoformat(),
                        "log_path": str(second_log),
                        "status": "launched",
                        "backend": "process",
                    },
                    ensure_ascii=False,
                ),
            ]
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
    payload = json.loads(capsys.readouterr().out)
    assert [item["status"] for item in payload["goal_updates"]] == ["done", "done"]
    assert payload["active_goals"] == []
    assert payload["fanout_status"]["status"] == "completed"
    assert payload["fanout_status"]["summary"] == {
        "total": 2,
        "done": 2,
        "blocked": 0,
        "needs_user": 0,
        "running": 0,
        "pending": 0,
    }
    assert payload["fanout_status"]["results"] == [
        {
            "goal_id": first_goal["goal_id"],
            "target_name": "worker-a",
            "status": "done",
            "summary": "worker A 已完成并提交。",
            "next": "等待 Supervisor 汇总。",
        },
        {
            "goal_id": second_goal["goal_id"],
            "target_name": "worker-b",
            "status": "done",
            "summary": "worker B 已完成并提交。",
            "next": "等待 Supervisor 汇总。",
        },
    ]
    assert payload["lifecycle_trace"]["summary"]["active_goals"] == 0
    assert payload["lifecycle_trace"]["summary"]["active_managed_workers"] == 2
    assert payload["lifecycle_trace"]["next_attention"] == {
        "kind": "archive_cleanup",
        "target": "worker-a",
    }
    assert [
        item["name"]
        for item in payload["lifecycle_trace"]["stages"]["cleanup"]["candidates"]
        if item["kind"] == "managed_worker"
    ] == ["worker-a", "worker-b"]




def test_codex_supervisor_runner_loop_pauses_fanout_on_blocked_worker(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    blocked_goal = _add_supervisor_goal(
        capsys,
        codex_home=codex_home,
        workspace=workspace,
        goal="等待 fanout worker A。",
        target_name="worker-a",
    )
    _add_supervisor_goal(
        capsys,
        codex_home=codex_home,
        workspace=workspace,
        goal="等待 fanout worker B。",
        target_name="worker-b",
    )
    log_path = codex_home / "supervisor" / "logs" / "managed-a.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "SUPERVISOR_STATUS: blocked\n"
        "SUPERVISOR_SUMMARY: worker A 需要外部依赖。\n"
        "SUPERVISOR_NEXT: 等待用户处理依赖。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-a",
                "name": "worker-a",
                "cwd": str(workspace),
                "prompt": "等待 fanout worker A。",
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

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            raise AssertionError("paused fanout should not ask LLM for another action")

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
    assert payload["goal_updates"][0]["goal_id"] == blocked_goal["goal_id"]
    assert payload["fanout_status"]["status"] == "paused"
    assert payload["fanout_status"]["requires_user_attention"] is True
    assert payload["fanout_plan"]["summary"] == {
        "launchable": 0,
        "skipped": 1,
        "limit": 3,
    }
    assert payload["fanout_plan"]["skipped"] == [
        {
            "target_name": "worker-b",
            "reason": "fanout_paused_for_attention",
            "batch": "active_goals",
        }
    ]
    assert payload["supervisor_action"]["kind"] == "monitor"
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["executed"]["kind"] == "monitor"
    notifications = NotificationFlow.in_process(codex_home).list_notifications(
        notification_type="supervisor_goal_status"
    )
    assert notifications[0].source_ref == {
        "ref_type": "supervisor_goal_status",
        "goal_id": blocked_goal["goal_id"],
        "status": "blocked",
    }




def test_codex_supervisor_runner_loop_archives_goal_when_worker_reports_done(
    tmp_path,
    capsys,
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
            "完成目标后自动归档。",
            "--target-name",
            "goal-supervisor",
            "--json",
        ]
    )
    assert exit_code == 0
    goal = json.loads(capsys.readouterr().out)["goal"]
    log_path = codex_home / "supervisor" / "logs" / "managed-001.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: 目标已完成。\n"
        "SUPERVISOR_NEXT: 等待 Supervisor 归档。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "goal-supervisor",
                "cwd": str(workspace),
                "prompt": "完成目标后自动归档。",
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
    payload = json.loads(capsys.readouterr().out)
    assert payload["goal_updates"][0]["goal_id"] == goal["goal_id"]
    assert payload["goal_updates"][0]["status"] == "done"
    assert payload["goal_updates"][0]["archived"]["event"] == "supervisor_goal_archive"
    assert payload["active_goals"] == []

    exit_code = supervisor_main(["goal", "list", "--codex-home", str(codex_home), "--json"])
    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["active_goals"] == []




def test_codex_supervisor_runner_loop_does_not_auto_archive_plain_done_managed_worker(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    missing_workspace = tmp_path / "missing-workspace"
    exit_code = supervisor_main(
        [
            "goal",
            "add",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--goal",
            "完成目标后等待显式 cleanup 归档 worker。",
            "--target-name",
            "done-worker",
            "--json",
        ]
    )
    assert exit_code == 0
    goal = json.loads(capsys.readouterr().out)["goal"]
    log_dir = codex_home / "supervisor" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    done_log_path = log_dir / "managed-done.log"
    done_log_path.write_text(
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: worker 已完成。\n"
        "SUPERVISOR_NEXT: 等待 Supervisor 归档。\n",
        encoding="utf-8",
    )
    active_log_path = log_dir / "managed-active.log"
    active_log_path.write_text(
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: worker 正在收尾。\n"
        "SUPERVISOR_NEXT: 等待 Supervisor 归档。\n"
        "◦ Working (esc to interrupt)\n",
        encoding="utf-8",
    )
    missing_log_path = log_dir / "managed-missing.log"
    missing_log_path.write_text(
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: worker 已完成但 worktree 不存在。\n"
        "SUPERVISOR_NEXT: 等待人工确认。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "record_id": "managed-done",
                        "name": "done-worker",
                        "cwd": str(workspace),
                        "prompt": "完成目标后等待显式 cleanup 归档 worker。",
                        "command": ["codex", "exec", "-C", str(workspace), "继续"],
                        "pid": 0,
                        "started_at": NOW.isoformat(),
                        "log_path": str(done_log_path),
                        "status": "launched",
                        "backend": "process",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                json.dumps(
                    {
                        "record_id": "managed-active",
                        "name": "active-worker",
                        "cwd": str(workspace),
                        "prompt": "仍在工作。",
                        "command": ["codex", "exec", "-C", str(workspace), "继续"],
                        "pid": 0,
                        "started_at": NOW.isoformat(),
                        "log_path": str(active_log_path),
                        "status": "launched",
                        "backend": "process",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                json.dumps(
                    {
                        "record_id": "managed-missing",
                        "name": "missing-worker",
                        "cwd": str(missing_workspace),
                        "prompt": "worktree 不存在。",
                        "command": [
                            "codex",
                            "exec",
                            "-C",
                            str(missing_workspace),
                            "继续",
                        ],
                        "pid": 0,
                        "started_at": NOW.isoformat(),
                        "log_path": str(missing_log_path),
                        "status": "launched",
                        "backend": "process",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: {
            "status": "ok",
            "base_ref": base_ref,
            "include_unfinished": include_unfinished,
            "summary": {
                "total": 1,
                "merge_workers": 0,
                "ready_to_integrate": 1,
                "already_integrated": 0,
                "needs_review": 0,
                "conflict_risk": 0,
            },
            "groups": {
                "merge_workers": [],
                "ready_to_integrate": [
                    {
                        "record_id": "managed-done",
                        "name": "done-worker",
                        "group": "ready_to_integrate",
                        "base_ref": base_ref,
                    }
                ],
                "already_integrated": [],
                "needs_review": [],
                "conflict_risk": [],
            },
            "workers": [
                {
                    "record_id": "managed-done",
                    "name": "done-worker",
                    "group": "ready_to_integrate",
                    "base_ref": base_ref,
                }
            ],
            "safety": {
                "auto_merge": False,
                "push": False,
                "delete_branch": False,
            },
        },
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
    payload = json.loads(capsys.readouterr().out)
    assert payload["goal_updates"][0]["goal_id"] == goal["goal_id"]
    assert payload["goal_updates"][0]["status"] == "done"
    assert payload["active_goals"] == []
    assert "cleanup_archived" not in payload
    registry_events = [
        json.loads(line)
        for line in registry_path.read_text(encoding="utf-8").splitlines()
    ]
    archived_names = [
        item["name"] for item in registry_events if item.get("status") == "archived"
    ]
    assert archived_names == []




def test_codex_supervisor_runner_loop_cleans_worktree_after_merge_worker_archive(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    worktree = workspace / ".worktrees" / "supervisor" / "merge-worker-abcd1234"
    merge_log_path = codex_home / "supervisor" / "logs" / "managed-merge.log"
    merge_log_path.parent.mkdir(parents=True, exist_ok=True)
    merge_log_path.write_text(
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: ready worker 已合入 main。\n"
        "SUPERVISOR_NEXT: 等待 Supervisor 归档。\n",
        encoding="utf-8",
    )
    source_log_path = codex_home / "supervisor" / "logs" / "managed-source.log"
    source_log_path.write_text(
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: source worker 已完成。\n"
        "SUPERVISOR_NEXT: 等待 merge worker 合入。\n",
        encoding="utf-8",
    )
    source_worktree = workspace / ".worktrees" / "supervisor" / "source-worker-abcd1234"
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "record_id": "managed-source",
                        "name": "source-worker",
                        "cwd": str(source_worktree),
                        "prompt": "完成 source worker。",
                        "command": [
                            "codex",
                            "exec",
                            "-C",
                            str(source_worktree),
                            "source",
                        ],
                        "pid": 0,
                        "started_at": NOW.isoformat(),
                        "log_path": str(source_log_path),
                        "status": "launched",
                        "backend": "process",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                json.dumps(
                    {
                        "record_id": "managed-merge",
                        "name": DEFAULT_TARGET_NAME,
                        "cwd": str(worktree),
                        "prompt": "合并 managed-source 的改动。",
                        "command": [
                            "codex",
                            "exec",
                            "-C",
                            str(worktree),
                            "managed-source",
                        ],
                        "pid": 0,
                        "started_at": NOW.isoformat(),
                        "log_path": str(merge_log_path),
                        "status": "launched",
                        "backend": "process",
                        "worker_role": "merge_dispatch",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    review_payload = {
        "status": "ok",
        "base_ref": "main",
        "include_unfinished": False,
        "summary": {
            "total": 2,
            "merge_workers": 1,
            "ready_to_integrate": 0,
            "already_integrated": 1,
            "needs_review": 0,
            "conflict_risk": 0,
        },
        "groups": {
            "merge_workers": [
                {
                    "record_id": "managed-merge",
                    "name": DEFAULT_TARGET_NAME,
                    "group": "merge_workers",
                    "supervisor_protocol": {
                        "status": "done",
                        "summary": "ready worker 已合入 main。",
                        "next": "等待 Supervisor 归档。",
                    },
                }
            ],
            "ready_to_integrate": [],
            "already_integrated": [
                {
                    "record_id": "managed-source",
                    "name": "source-worker",
                    "group": "already_integrated",
                }
            ],
            "needs_review": [],
            "conflict_risk": [],
        },
        "workers": [],
        "safety": {"auto_merge": False, "push": False, "delete_branch": False},
    }
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: review_payload,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._delete_worktree_candidate_payloads",
        lambda args: [
            {
                "name": "source-worker",
                "target_name": "source-worker",
                "record_id": "managed-source",
                "cwd": str(source_worktree),
                "archived": True,
                "integration_group": "already_integrated",
            },
            {
                "name": DEFAULT_TARGET_NAME,
                "target_name": DEFAULT_TARGET_NAME,
                "record_id": "managed-merge",
                "cwd": str(worktree),
                "archived": True,
                "integration_group": "already_integrated",
            }
        ],
    )
    deleted_actions: list[dict[str, Any]] = []

    def stub_delete(args: Any, action: dict[str, Any]) -> dict[str, Any]:
        deleted_actions.append(action)
        deleted_worktree = (
            str(source_worktree)
            if action["record_id"] == "managed-source"
            else str(worktree)
        )
        return {
            "kind": "delete_worktree",
            "target_name": action["target_name"],
            "record_id": action["record_id"],
            "deleted_worktree": deleted_worktree,
        }

    monkeypatch.setattr(
        "isotope.features.supervisor.runner._execute_delete_worktree_action",
        stub_delete,
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
    payload = json.loads(capsys.readouterr().out)
    assert [item["record_id"] for item in payload["cleanup_archived"]] == [
        "managed-source",
        "managed-merge",
    ]
    assert payload["cleanup_deleted_worktrees"] == [
        {
            "kind": "delete_worktree",
            "target_name": "source-worker",
            "record_id": "managed-source",
            "deleted_worktree": str(source_worktree),
        },
        {
            "kind": "delete_worktree",
            "target_name": DEFAULT_TARGET_NAME,
            "record_id": "managed-merge",
            "deleted_worktree": str(worktree),
        }
    ]
    assert payload["worker_lifecycle_decision"]["action"] == "cleanup_worktree"
    assert payload["worker_lifecycle_decision"]["source"] == "cleanup"
    assert (
        payload["worker_lifecycle_decision"]["execution"]
        == payload["cleanup_deleted_worktrees"]
    )
    assert deleted_actions == [
        {
            "kind": "delete_worktree",
            "target_name": "source-worker",
            "record_id": "managed-source",
            "confirm_delete_worktree": True,
            "base_ref": "main",
            "source": "cleanup_auto",
        },
        {
            "kind": "delete_worktree",
            "target_name": DEFAULT_TARGET_NAME,
            "record_id": "managed-merge",
            "confirm_delete_worktree": True,
            "base_ref": "main",
            "source": "cleanup_auto",
        }
    ]
    registry_events = [
        json.loads(line)
        for line in registry_path.read_text(encoding="utf-8").splitlines()
    ]
    archived_names = [
        item["name"] for item in registry_events if item.get("status") == "archived"
    ]
    assert archived_names == ["source-worker", DEFAULT_TARGET_NAME]




def test_codex_supervisor_runner_loop_keeps_blocked_goal_active(
    tmp_path,
    capsys,
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
            "阻塞时等待用户处理。",
            "--target-name",
            "goal-supervisor",
            "--json",
        ]
    )
    assert exit_code == 0
    goal = json.loads(capsys.readouterr().out)["goal"]
    log_path = codex_home / "supervisor" / "logs" / "managed-001.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "SUPERVISOR_STATUS: blocked\n"
        "SUPERVISOR_SUMMARY: 缺少产品决策。\n"
        "SUPERVISOR_NEXT: 请求用户拍板。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "goal-supervisor",
                "cwd": str(workspace),
                "prompt": "阻塞时等待用户处理。",
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
    payload = json.loads(capsys.readouterr().out)
    assert payload["goal_updates"][0]["goal_id"] == goal["goal_id"]
    assert payload["goal_updates"][0]["status"] == "blocked"
    assert "archived" not in payload["goal_updates"][0]
    assert payload["active_goals"][0]["goal_id"] == goal["goal_id"]
    assert payload["active_goals"][0]["last_status"] == "blocked"

    exit_code = supervisor_main(["goal", "list", "--codex-home", str(codex_home), "--json"])
    assert exit_code == 0
    listed_goal = json.loads(capsys.readouterr().out)["active_goals"][0]
    assert listed_goal["goal_id"] == goal["goal_id"]
    assert listed_goal["last_status"] == "blocked"




def test_codex_supervisor_runner_loop_replans_blocked_goal_with_llm_context(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("Supervisor 目标阻塞后要重新规划。\n", encoding="utf-8")
    exit_code = supervisor_main(
        [
            "goal",
            "add",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--goal",
            "重新规划阻塞目标。",
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
        "SUPERVISOR_STATUS: blocked\n"
        "SUPERVISOR_SUMMARY: 需要重新确认项目上下文。\n"
        "SUPERVISOR_NEXT: 先查询 docs/current。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "goal-supervisor",
                "cwd": str(workspace),
                "prompt": "重新规划阻塞目标。",
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
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    class DeterministicProvider:
        def __init__(self) -> None:
            self.calls = 0

        def summarize(self, messages: list[dict[str, str]]) -> str:
            self.calls += 1
            content = messages[1]["content"]
            assert '"active_goals"' in content
            assert '"last_status": "blocked"' in content
            assert "blocked/needs_user" in content
            if self.calls == 1:
                return json.dumps(
                    {
                        "kind": "request_context",
                        "cwd": str(workspace),
                        "query": "Supervisor 目标阻塞后如何继续推进",
                        "reason": "阻塞目标需要先查项目上下文。",
                    },
                    ensure_ascii=False,
                )
            return json.dumps(
                {
                    "kind": "monitor",
                    "reason": "上下文已查询，本轮先记录结果。",
                },
                ensure_ascii=False,
            )

    provider = DeterministicProvider()
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: provider,
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
    assert payload["active_goals"][0]["last_status"] == "blocked"
    assert payload["supervisor_action"]["kind"] == "request_context"
    assert payload["llm_action"] == payload["supervisor_action"]
    context = _codex_operation_context_result(payload["executed"])
    assert context["query"] == "Supervisor 目标阻塞后如何继续推进"
    assert payload["supervisor_followup_action"]["kind"] == "monitor"
    assert payload["llm_followup_action"] == payload["supervisor_followup_action"]




def test_codex_supervisor_runner_loop_records_goal_level_decision_request(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    docs_dir = workspace / "docs" / "current"
    docs_dir.mkdir(parents=True)
    (docs_dir / "status.md").write_text(
        "阻塞目标的文档和代码现状冲突，需要用户拍板。\n",
        encoding="utf-8",
    )
    exit_code = supervisor_main(
        [
            "goal",
            "add",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--goal",
            "处理阻塞目标拍板。",
            "--target-name",
            "goal-supervisor",
            "--json",
        ]
    )
    assert exit_code == 0
    goal = json.loads(capsys.readouterr().out)["goal"]
    log_path = codex_home / "supervisor" / "logs" / "managed-001.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "SUPERVISOR_STATUS: needs_user\n"
        "SUPERVISOR_SUMMARY: 文档和代码现状冲突。\n"
        "SUPERVISOR_NEXT: 请用户拍板保留兼容层还是直接迁移。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "goal-supervisor",
                "cwd": str(workspace),
                "prompt": "处理阻塞目标拍板。",
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
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    class DeterministicProvider:
        def __init__(self) -> None:
            self.calls = 0

        def summarize(self, messages: list[dict[str, str]]) -> str:
            self.calls += 1
            content = messages[1]["content"]
            assert goal["goal_id"] in content
            assert '"last_status": "needs_user"' in content
            if self.calls == 1:
                return json.dumps(
                    {
                        "kind": "request_context",
                        "cwd": str(workspace),
                        "query": "阻塞目标 拍板 冲突",
                        "reason": "先查上下文再决定是否问用户。",
                    },
                    ensure_ascii=False,
                )
            assert "阻塞目标的文档和代码现状冲突" in content
            return json.dumps(
                {
                    "kind": "ask_user",
                    "goal_id": goal["goal_id"],
                    "question": "这个目标保留兼容层，还是直接迁移并删除旧入口？",
                    "codex_requested_decision": True,
                    "instructions_exhausted": True,
                    "context_status": "conflict",
                    "reason": "目标明确请求拍板，既有指示不足，文档和现状冲突。",
                },
                ensure_ascii=False,
            )

    provider = DeterministicProvider()
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: provider,
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
    assert payload["supervisor_action"]["kind"] == "request_context"
    assert payload["llm_action"] == payload["supervisor_action"]
    _codex_operation_context_result(payload["executed"])
    assert payload["supervisor_followup_action"]["kind"] == "ask_user"
    assert payload["llm_followup_action"] == payload["supervisor_followup_action"]
    followup = payload["followup_executed"]
    assert followup["kind"] == "ask_user"
    assert followup["requires_user"] is True
    assert followup["goal_id"] == goal["goal_id"]
    assert followup["target_name"] == "goal-supervisor"
    assert followup["question"] == "这个目标保留兼容层，还是直接迁移并删除旧入口？"
    decision_request = followup["decision_request"]
    assert decision_request["goal_id"] == goal["goal_id"]
    assert decision_request["target_name"] == "goal-supervisor"
    assert decision_request["context_status"] == "conflict"
    assert decision_request["gate"] == {
        "codex_requested_decision": True,
        "instructions_exhausted": True,
        "context_status": "conflict",
    }
    records = [
        json.loads(line)
        for line in (codex_home / "supervisor" / "decision_requests.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert records[0]["goal_id"] == goal["goal_id"]
    assert provider.calls == 2




def test_codex_supervisor_runner_loop_goal_provider_resolution_failure_is_visible(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: (_ for _ in ()).throw(ValueError("No LLM pool entries found")),
    )

    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--workspace-root",
            str(workspace),
            "--goal",
            "继续推进 Supervisor。",
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
        "reason": "LLM 动作无效，已跳过执行：No LLM pool entries found",
        "command_suggestion": None,
        "error": "No LLM pool entries found",
    }
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "LLM 动作无效，已跳过执行：No LLM pool entries found",
    }




def test_codex_supervisor_runner_loop_can_continue_multiple_lanes_with_default_budgets(
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
    lane_state_path = codex_home / "supervisor" / "lane_state.json"
    lane_state_path.parent.mkdir(parents=True, exist_ok=True)
    lane_state_path.write_text(
        json.dumps(
            {
                "lane-a": {
                    "name": "lane-a",
                    "tmux_session": "isotope-lane-a",
                    "last_status": "done",
                    "last_prompted_at": "2026-05-16T11:58:00+00:00",
                    "prompt_count": 8,
                    "last_prompt_kind": "send_continue",
                    "continue_count": 8,
                },
                "lane-b": {
                    "name": "lane-b",
                    "tmux_session": "isotope-lane-b",
                    "last_status": "done",
                    "last_prompted_at": "2026-05-16T11:58:00+00:00",
                    "prompt_count": 6,
                    "last_prompt_kind": "send_continue",
                    "continue_count": 6,
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
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
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    class DeterministicProvider:
        calls = 0

        def summarize(self, messages: list[dict[str, str]]) -> str:
            self.calls += 1
            content = messages[1]["content"]
            assert '"target_name": "lane-a"' in content
            assert '"target_name": "lane-b"' in content
            target = "lane-a" if self.calls == 1 else "lane-b"
            return json.dumps(
                {
                    "kind": "send_continue",
                    "target_name": target,
                    "reason": f"{target} 已完成上一段，继续推进。",
                },
                ensure_ascii=False,
            )

    provider = DeterministicProvider()
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: provider,
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
    assert [payload["supervisor_action"]["target_name"] for payload in payloads] == [
        "lane-a",
        "lane-b",
    ]
    assert all(
        payload["llm_action"] == payload["supervisor_action"] for payload in payloads
    )
    assert [payload["executed"]["kind"] for payload in payloads] == [
        "send_continue",
        "send_continue",
    ]
    assert [payload["executed"]["managed"]["name"] for payload in payloads] == [
        "lane-a",
        "lane-b",
    ]
    assert calls == _tmux_send_calls(CONTINUE_REQUEST_TEXT) + _tmux_send_calls(
        CONTINUE_REQUEST_TEXT,
        buffer_name="isotope-supervisor-managed-002",
        target="isotope-lane-b",
    )
    assert provider.calls == 2


