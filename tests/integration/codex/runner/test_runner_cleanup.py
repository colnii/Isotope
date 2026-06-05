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

def test_codex_supervisor_runner_decision_list_prints_active_requests(
    tmp_path,
    capsys,
):
    codex_home = tmp_path / ".codex"
    decision_path = codex_home / "supervisor" / "decision_requests.jsonl"
    decision_path.parent.mkdir(parents=True)
    decision_path.write_text(
        json.dumps(
            {
                "event": "decision_request",
                "request_id": "decision-001",
                "created_at": "2026-05-16T12:00:00+00:00",
                "session_id": "session-a",
                "target_name": "resume-session-a",
                "question": "选择保留兼容层还是直接迁移？",
                "reason": "Codex 明确要拍板。",
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

    exit_code = supervisor_main(["decision", "list", "--codex-home", str(codex_home)])

    assert exit_code == 0
    text = capsys.readouterr().out
    assert "等待拍板：1" in text
    assert "decision-001 选择保留兼容层还是直接迁移？" in text
    assert (
        "归档：isotope-supervisor decision archive --request-id decision-001"
        in text
    )



def test_codex_supervisor_runner_decision_archive_removes_active_request(
    tmp_path,
    capsys,
):
    codex_home = tmp_path / ".codex"
    decision_path = codex_home / "supervisor" / "decision_requests.jsonl"
    decision_path.parent.mkdir(parents=True)
    decision_path.write_text(
        json.dumps(
            {
                "event": "decision_request",
                "request_id": "decision-001",
                "created_at": "2026-05-16T12:00:00+00:00",
                "session_id": "session-a",
                "target_name": "resume-session-a",
                "question": "选择保留兼容层还是直接迁移？",
                "reason": "Codex 明确要拍板。",
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
            "archive",
            "--codex-home",
            str(codex_home),
            "--request-id",
            "decision-001",
            "--json",
        ]
    )

    assert exit_code == 0
    archive_payload = json.loads(capsys.readouterr().out)
    assert archive_payload["status"] == "ok"
    assert archive_payload["archived"]["event"] == "decision_archive"
    assert archive_payload["archived"]["request_id"] == "decision-001"

    exit_code = supervisor_main(
        ["dashboard", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    dashboard_payload = json.loads(capsys.readouterr().out)
    assert dashboard_payload["decision_requests"] == []



def test_codex_supervisor_runner_decision_answer_records_user_decision(
    tmp_path,
    capsys,
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

    exit_code = supervisor_main(
        [
            "decision",
            "answer",
            "--codex-home",
            str(codex_home),
            "--request-id",
            "decision-001",
            "--answer",
            "保留兼容层，后续再清理旧入口。",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["answered"] == {
        "event": "decision_answer",
        "request_id": "decision-001",
        "created_at": payload["answered"]["created_at"],
        "session_id": "goal:goal-001",
        "goal_id": "goal-001",
        "target_name": "goal-supervisor",
        "question": "保留兼容层还是直接迁移？",
        "answer": "保留兼容层，后续再清理旧入口。",
        "reason": "目标明确请求拍板。",
        "context_status": "conflict",
        "gate": {
            "codex_requested_decision": True,
            "instructions_exhausted": True,
            "context_status": "conflict",
        },
    }
    assert payload["decision_requests"] == []

    records = [
        json.loads(line)
        for line in decision_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["event"] for record in records] == [
        "decision_request",
        "decision_answer",
    ]

    exit_code = supervisor_main(
        ["decision", "list", "--codex-home", str(codex_home), "--json"]
    )
    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["decision_requests"] == []



def test_codex_supervisor_runner_goal_add_list_and_archive(
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
            "持续推进 Supervisor 目标队列。",
            "--target-name",
            "goal-supervisor",
            "--json",
        ]
    )

    assert exit_code == 0
    add_payload = json.loads(capsys.readouterr().out)
    goal = add_payload["goal"]
    assert goal["event"] == "supervisor_goal"
    assert goal["goal_id"].startswith("goal-")
    assert goal["cwd"] == str(workspace)
    assert goal["goal"] == "持续推进 Supervisor 目标队列。"
    assert goal["target_name"] == "goal-supervisor"
    assert add_payload["active_goals"] == [goal]

    exit_code = supervisor_main(
        ["goal", "list", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    list_payload = json.loads(capsys.readouterr().out)
    assert list_payload["active_goals"] == [goal]

    exit_code = supervisor_main(
        [
            "goal",
            "archive",
            "--codex-home",
            str(codex_home),
            "--goal-id",
            goal["goal_id"],
            "--status",
            "done",
            "--summary",
            "目标已完成并准备归档。",
            "--next-step",
            "等待下一批 Supervisor 目标。",
            "--json",
        ]
    )

    assert exit_code == 0
    archive_payload = json.loads(capsys.readouterr().out)
    assert archive_payload["archived"]["event"] == "supervisor_goal_archive"
    assert archive_payload["archived"]["goal_id"] == goal["goal_id"]
    assert archive_payload["archived"]["status"] == "done"
    assert archive_payload["archived"]["summary"] == "目标已完成并准备归档。"
    assert archive_payload["archived"]["next"] == "等待下一批 Supervisor 目标。"
    assert archive_payload["active_goals"] == []



def test_codex_supervisor_runner_cleanup_lists_and_archives_only_done_items(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    done_goal = _add_supervisor_goal(
        capsys,
        codex_home=codex_home,
        workspace=workspace,
        goal="已完成后等待清理。",
        target_name="done-worker",
    )
    working_goal = _add_supervisor_goal(
        capsys,
        codex_home=codex_home,
        workspace=workspace,
        goal="还在工作中。",
        target_name="working-worker",
    )
    assert working_goal["goal_id"] != done_goal["goal_id"]

    goals_path = codex_home / "supervisor" / "goals.jsonl"
    with goals_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "event": "supervisor_goal_status",
                    "goal_id": done_goal["goal_id"],
                    "status": "done",
                    "target_name": "done-worker",
                    "summary": "目标已完成。",
                    "next": "等待 Supervisor 归档。",
                    "created_at": NOW.isoformat(),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
    NotificationFlow.in_process(codex_home).create_notification(
        notification_type="supervisor_goal_status",
        title="Supervisor goal status: done",
        source_ref={
            "ref_type": "supervisor_goal_status",
            "goal_id": done_goal["goal_id"],
            "status": "done",
        },
    )

    done_log_path = codex_home / "supervisor" / "logs" / "managed-done.log"
    done_log_path.parent.mkdir(parents=True, exist_ok=True)
    done_log_path.write_text(
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: worker 已完成。\n"
        "SUPERVISOR_NEXT: 等待 Supervisor 归档。\n",
        encoding="utf-8",
    )
    working_log_path = codex_home / "supervisor" / "logs" / "managed-working.log"
    working_log_path.write_text(
        "SUPERVISOR_STATUS: working\n"
        "SUPERVISOR_SUMMARY: worker 仍在执行。\n"
        "SUPERVISOR_NEXT: 继续等待。\n",
        encoding="utf-8",
    )
    done_tmux_log_path = codex_home / "supervisor" / "logs" / "managed-done-tmux.log"
    working_tmux_log_path = codex_home / "supervisor" / "logs" / "managed-working-tmux.log"
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "record_id": "managed-done",
                        "name": "done-worker",
                        "cwd": str(workspace),
                        "prompt": "已完成后等待清理。",
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
                        "record_id": "managed-done-tmux",
                        "name": "done-tmux-worker",
                        "cwd": str(workspace),
                        "prompt": "tmux 已完成后等待清理。",
                        "command": ["tmux", "attach", "-t", "done-tmux"],
                        "pid": 0,
                        "started_at": NOW.isoformat(),
                        "log_path": str(done_tmux_log_path),
                        "status": "launched",
                        "backend": "tmux",
                        "tmux_session": "done-tmux",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                json.dumps(
                    {
                        "record_id": "managed-working-tmux",
                        "name": "working-tmux-worker",
                        "cwd": str(workspace),
                        "prompt": "tmux 仍在工作中。",
                        "command": ["tmux", "attach", "-t", "working-tmux"],
                        "pid": 0,
                        "started_at": NOW.isoformat(),
                        "log_path": str(working_tmux_log_path),
                        "status": "launched",
                        "backend": "tmux",
                        "tmux_session": "working-tmux",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                json.dumps(
                    {
                        "record_id": "managed-working",
                        "name": "working-worker",
                        "cwd": str(workspace),
                        "prompt": "还在工作中。",
                        "command": ["codex", "exec", "-C", str(workspace), "继续"],
                        "pid": 0,
                        "started_at": NOW.isoformat(),
                        "log_path": str(working_log_path),
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
    pane_texts = {
        "done-tmux": (
            "SUPERVISOR_STATUS: done\n"
            "SUPERVISOR_SUMMARY: tmux worker 已完成。\n"
            "SUPERVISOR_NEXT: 等待 Supervisor 归档。\n"
        ),
        "working-tmux": (
            "SUPERVISOR_STATUS: done\n"
            "SUPERVISOR_SUMMARY: tmux worker 正在收尾。\n"
            "SUPERVISOR_NEXT: 等待 Supervisor 归档。\n"
            "◦ Working (esc to interrupt)\n"
        ),
    }
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._tmux_capture_pane",
        lambda session: pane_texts.get(session),
    )
    codex_history_path = _write_session(
        codex_home,
        "2026/05/20/rollout-history.jsonl",
        session_id="history-session",
        cwd=str(workspace),
        events=[_assistant_message("2026-05-20T12:00:00Z", "历史记录")],
    )

    exit_code = supervisor_main(["cleanup", "list", "--codex-home", str(codex_home), "--json"])

    assert exit_code == 0
    list_payload = json.loads(capsys.readouterr().out)
    assert list_payload["status"] == "ok"
    assert [item["kind"] for item in list_payload["candidates"]] == [
        "goal",
        "managed_worker",
        "managed_worker",
        "notification",
    ]
    assert list_payload["candidates"][0]["goal_id"] == done_goal["goal_id"]
    assert list_payload["candidates"][1]["name"] == "done-worker"
    assert list_payload["candidates"][2]["name"] == "done-tmux-worker"
    assert list_payload["candidates"][3]["notification_id"].startswith("notif_")
    assert all("--codex-home" in item["command"] for item in list_payload["candidates"])
    assert all(
        item.get("goal_id") != working_goal["goal_id"]
        and item.get("name") != "working-worker"
        and item.get("name") != "working-tmux-worker"
        for item in list_payload["candidates"]
    )

    exit_code = supervisor_main(
        ["cleanup", "archive", "--codex-home", str(codex_home), "--all", "--json"]
    )

    assert exit_code == 0
    archive_payload = json.loads(capsys.readouterr().out)
    assert archive_payload["status"] == "ok"
    assert [item["kind"] for item in archive_payload["archived"]] == [
        "goal",
        "managed_worker",
        "managed_worker",
        "notification",
    ]
    assert archive_payload["active_goals"] == [working_goal]
    assert codex_history_path.exists()
    assert "history-session" in codex_history_path.read_text(encoding="utf-8")
    registry_events = [
        json.loads(line)
        for line in registry_path.read_text(encoding="utf-8").splitlines()
    ]
    assert registry_events[-2]["record_id"] == "managed-done"
    assert registry_events[-2]["status"] == "archived"
    assert registry_events[-1]["record_id"] == "managed-done-tmux"
    assert registry_events[-1]["status"] == "archived"
    notifications = NotificationFlow.in_process(codex_home).list_notifications(
        notification_type="supervisor_goal_status"
    )
    assert notifications[0].unread is False



def test_codex_supervisor_runner_cleanup_list_includes_worktree_delete_candidates(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    worktree = workspace / ".worktrees" / "supervisor" / "done-worker-abcd1234"
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._delete_worktree_candidate_payloads",
        lambda args: [
            {
                "name": "done-worker",
                "target_name": "done-worker",
                "record_id": "managed-done",
                "cwd": str(worktree),
                "archived": True,
                "integration_group": "already_integrated",
            }
        ],
    )

    exit_code = supervisor_main(["cleanup", "list", "--codex-home", str(codex_home), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["worktree_candidates"] == [
        {
            "name": "done-worker",
            "target_name": "done-worker",
            "record_id": "managed-done",
            "cwd": str(worktree),
            "archived": True,
            "integration_group": "already_integrated",
            "command": (
                "isotope-supervisor cleanup delete-worktree "
                f"--codex-home {codex_home} --name done-worker "
                "--record-id managed-done --confirm-delete-worktree"
            ),
        }
    ]



def test_codex_supervisor_cleanup_list_skips_expensive_worktree_validation(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    worktree = workspace / ".worktrees" / "supervisor" / "done-worker-abcd1234"
    worktree.mkdir(parents=True)
    log_path = codex_home / "supervisor" / "logs" / "managed-done.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: worker 已完成。\n"
        "SUPERVISOR_NEXT: 等待 cleanup。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-done",
                "name": "done-worker",
                "cwd": str(worktree),
                "prompt": "已完成后等待清理。",
                "command": ["codex", "exec", "-C", str(worktree), "继续"],
                "pid": 0,
                "started_at": NOW.isoformat(),
                "log_path": str(log_path),
                "status": "archived",
                "backend": "process",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    captured = {}

    def stub_review(record, **kwargs):
        captured.update(kwargs)
        return {
            "group": "already_integrated",
            "dirty": False,
            "main_contains_worker": False,
            "main_has_worker_patch": True,
            "worker_commit": "abc123",
            "base_ref": kwargs.get("base_ref", "main"),
        }

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.review_managed_record_integration",
        stub_review,
    )

    exit_code = supervisor_main(["cleanup", "list", "--codex-home", str(codex_home), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["worktree_candidates"][0]["record_id"] == "managed-done"
    assert captured["run_test_gate"] is False
    assert captured["run_candidate_validation"] is False



def test_codex_supervisor_runner_cleanup_archives_stale_missing_worker_by_record_id(
    tmp_path,
    capsys,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    missing_worktree = workspace / ".worktrees" / "supervisor" / "same-name-old"
    current_worktree = workspace / ".worktrees" / "supervisor" / "same-name-new"
    current_worktree.mkdir(parents=True)
    old_log = codex_home / "supervisor" / "logs" / "managed-old.log"
    new_log = codex_home / "supervisor" / "logs" / "managed-new.log"
    old_log.parent.mkdir(parents=True, exist_ok=True)
    old_log.write_text(
        "SUPERVISOR_STATUS: blocked\n"
        "SUPERVISOR_SUMMARY: 旧 worktree 已不存在。\n"
        "SUPERVISOR_NEXT: 等待 cleanup 归档。\n",
        encoding="utf-8",
    )
    new_log.write_text(
        "SUPERVISOR_STATUS: working\n"
        "SUPERVISOR_SUMMARY: 新 worker 正在执行。\n"
        "SUPERVISOR_NEXT: 继续等待。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "record_id": "managed-old",
                        "name": "same-name",
                        "cwd": str(missing_worktree),
                        "prompt": "旧 worker。",
                        "command": ["codex", "exec", "-C", str(missing_worktree), "继续"],
                        "pid": 0,
                        "started_at": NOW.isoformat(),
                        "log_path": str(old_log),
                        "status": "launched",
                        "backend": "process",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                json.dumps(
                    {
                        "record_id": "managed-new",
                        "name": "same-name",
                        "cwd": str(current_worktree),
                        "prompt": "新 worker。",
                        "command": ["codex", "exec", "-C", str(current_worktree), "继续"],
                        "pid": 0,
                        "started_at": NOW.isoformat(),
                        "log_path": str(new_log),
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

    exit_code = supervisor_main(["cleanup", "list", "--codex-home", str(codex_home), "--json"])

    assert exit_code == 0
    list_payload = json.loads(capsys.readouterr().out)
    stale = [
        item
        for item in list_payload["candidates"]
        if item.get("record_id") == "managed-old"
    ]
    assert stale == [
        {
            "kind": "managed_worker",
            "name": "same-name",
            "record_id": "managed-old",
            "status": "stale_missing_worktree",
            "summary": "旧 worktree 已不存在。",
            "next": "等待 cleanup 归档。",
            "cwd": str(missing_worktree),
            "backend": "process",
            "command": (
                "isotope-supervisor cleanup archive "
                f"--codex-home {codex_home} --name same-name --record-id managed-old"
            ),
        }
    ]

    exit_code = supervisor_main(
        [
            "cleanup",
            "archive",
            "--codex-home",
            str(codex_home),
            "--name",
            "same-name",
            "--record-id",
            "managed-old",
            "--json",
        ]
    )

    assert exit_code == 0
    archive_payload = json.loads(capsys.readouterr().out)
    assert archive_payload["archived"][0]["managed"]["record_id"] == "managed-old"
    latest_status_by_record_id = {
        item["record_id"]: item["status"]
        for item in (
            json.loads(line)
            for line in registry_path.read_text(encoding="utf-8").splitlines()
        )
    }
    assert latest_status_by_record_id["managed-old"] == "archived"
    assert latest_status_by_record_id["managed-new"] == "launched"



def test_codex_supervisor_runner_cleanup_all_deduplicates_done_missing_worker(
    tmp_path,
    capsys,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    missing_worktree = workspace / ".worktrees" / "supervisor" / "done-missing"
    log_path = codex_home / "supervisor" / "logs" / "managed-done-missing.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: 旧 worker 已完成但 worktree 已删除。\n"
        "SUPERVISOR_NEXT: 等待 cleanup 归档。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-done-missing",
                "name": "done-missing",
                "cwd": str(missing_worktree),
                "prompt": "旧 worker。",
                "command": ["codex", "exec", "-C", str(missing_worktree), "继续"],
                "pid": 0,
                "started_at": NOW.isoformat(),
                "log_path": str(log_path),
                "status": "launched",
                "backend": "process",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = supervisor_main(["cleanup", "list", "--codex-home", str(codex_home), "--json"])

    assert exit_code == 0
    list_payload = json.loads(capsys.readouterr().out)
    matching = [
        item
        for item in list_payload["candidates"]
        if item.get("record_id") == "managed-done-missing"
    ]
    assert len(matching) == 1
    assert matching[0]["command"].endswith("--name done-missing --record-id managed-done-missing")

    exit_code = supervisor_main(
        ["cleanup", "archive", "--codex-home", str(codex_home), "--all", "--json"]
    )

    assert exit_code == 0
    archive_payload = json.loads(capsys.readouterr().out)
    assert [
        item["managed"]["record_id"]
        for item in archive_payload["archived"]
        if item["kind"] == "managed_worker"
    ] == ["managed-done-missing"]



def test_codex_supervisor_runner_cleanup_delete_worktree_uses_guarded_action(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    captured: dict[str, Any] = {}

    def stub_execute(args: Any, action: dict[str, Any]) -> dict[str, Any]:
        captured["action"] = action
        return {
            "kind": "delete_worktree",
            "target_name": action["target_name"],
            "record_id": action["record_id"],
            "deleted_worktree": "/tmp/worktree",
        }

    monkeypatch.setattr(
        "isotope.features.supervisor.runner._execute_delete_worktree_action",
        stub_execute,
    )

    exit_code = supervisor_main(
        [
            "cleanup",
            "delete-worktree",
            "--codex-home",
            str(codex_home),
            "--name",
            "done-worker",
            "--record-id",
            "managed-done",
            "--confirm-delete-worktree",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert captured["action"] == {
        "kind": "delete_worktree",
        "target_name": "done-worker",
        "record_id": "managed-done",
        "confirm_delete_worktree": True,
        "base_ref": "main",
    }
    assert payload["deleted"]["deleted_worktree"] == "/tmp/worktree"



def test_codex_supervisor_runner_cleanup_delete_worktree_plain_reports_deleted(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"

    def stub_execute(args: Any, action: dict[str, Any]) -> dict[str, Any]:
        return {
            "kind": "delete_worktree",
            "target_name": action["target_name"],
            "record_id": action["record_id"],
            "deleted_worktree": "/tmp/worktree",
        }

    monkeypatch.setattr(
        "isotope.features.supervisor.runner._execute_delete_worktree_action",
        stub_execute,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._delete_worktree_candidate_payloads",
        lambda args: [],
    )

    exit_code = supervisor_main(
        [
            "cleanup",
            "delete-worktree",
            "--codex-home",
            str(codex_home),
            "--name",
            "done-worker",
            "--record-id",
            "managed-done",
            "--confirm-delete-worktree",
        ]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "已删除 worktree：done-worker" in out
    assert "cwd：/tmp/worktree" in out



def test_codex_supervisor_runner_decide_action_passes_capacity_decisions(monkeypatch):
    report = CodexSupervisorReport(generated_at=NOW.isoformat(), sessions=())
    decision = {
        "kind": "supervisor_capacity_decision",
        "next_action": "call_capacity",
        "reason": "ready",
        "capacity_id": "artifact.review",
        "can_execute_agent_loop": True,
        "missing_inputs": [],
        "blocking_reasons": [],
    }
    captured: dict[str, object] = {}

    def stub_generate(*args: object, **kwargs: object) -> dict[str, object]:
        captured["capacity_decisions"] = kwargs.get("capacity_decisions")
        return {
            "kind": "monitor",
            "target_name": None,
            "reason": "只检查透传。",
            "command_suggestion": None,
        }

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda agent_name: object(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.generate_llm_action_decision",
        stub_generate,
    )

    result = supervisor_runner._decide_action_with_llm(
        argparse.Namespace(),
        report,
        {
            "command_suggestions": [
                {
                    "kind": "request_context",
                    "cwd": EXISTING_WORKSPACE,
                    "query": "capacity",
                    "command": "isotope-supervisor context --query capacity",
                }
            ],
            "capacity_decisions": [decision],
        },
    )

    assert result["kind"] == "monitor"
    assert captured["capacity_decisions"] == [decision]



def test_codex_supervisor_runner_decide_action_passes_worker_lifecycle_decision(
    monkeypatch,
):
    report = CodexSupervisorReport(generated_at=NOW.isoformat(), sessions=())
    lifecycle_decision = {
        "kind": "worker_lifecycle_decision",
        "action": "archive_integrated",
        "stage": "archived",
        "next_step": "cleanup_worktree",
        "source": "cleanup",
        "execution": [{"kind": "merge_worker", "record_id": "managed-merge"}],
    }
    lifecycle_execution = {
        "kind": "cleanup_worktree",
        "source": "worker_lifecycle",
        "next_step": "cleanup_worktree",
        "status": "ready_to_delete",
        "delete_worktree_actions": [
            {
                "kind": "delete_worktree",
                "target_name": "source-worker",
                "record_id": "managed-source",
            }
        ],
    }
    lifecycle_execution_result = {
        "kind": "cleanup_worktree",
        "source": "worker_lifecycle",
        "skipped": True,
        "reason": "lifecycle cleanup execution requires --lifecycle-cleanup-execute",
        "count": 1,
    }
    captured: dict[str, object] = {}

    def stub_generate(*args: object, **kwargs: object) -> dict[str, object]:
        captured["worker_lifecycle_decision"] = kwargs.get(
            "worker_lifecycle_decision"
        )
        captured["worker_lifecycle_execution"] = kwargs.get(
            "worker_lifecycle_execution"
        )
        captured["worker_lifecycle_execution_result"] = kwargs.get(
            "worker_lifecycle_execution_result"
        )
        return {
            "kind": "monitor",
            "target_name": None,
            "reason": "只检查 lifecycle 透传。",
            "command_suggestion": None,
        }

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda agent_name: object(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.generate_llm_action_decision",
        stub_generate,
    )

    result = supervisor_runner._decide_action_with_llm(
        argparse.Namespace(),
        report,
        {
            "command_suggestions": [
                {
                    "kind": "request_context",
                    "cwd": EXISTING_WORKSPACE,
                    "query": "worker lifecycle",
                    "command": (
                        "isotope-supervisor context --query worker-lifecycle"
                    ),
                }
            ],
            "worker_lifecycle_decision": lifecycle_decision,
            "worker_lifecycle_execution": lifecycle_execution,
            "worker_lifecycle_execution_result": lifecycle_execution_result,
        },
    )

    assert result["kind"] == "monitor"
    assert captured["worker_lifecycle_decision"] == lifecycle_decision
    assert captured["worker_lifecycle_execution"] == lifecycle_execution
    assert captured["worker_lifecycle_execution_result"] == lifecycle_execution_result



def test_codex_supervisor_runner_archive_hides_managed_lane(
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

    archive_exit_code = supervisor_main(
        [
            "archive",
            "--codex-home",
            str(codex_home),
            "--name",
            "lane-a",
            "--json",
        ]
    )

    assert archive_exit_code == 0
    archive_payload = json.loads(capsys.readouterr().out)
    assert archive_payload["status"] == "ok"
    assert archive_payload["managed"]["name"] == "lane-a"
    assert archive_payload["managed"]["status"] == "archived"

    dashboard_exit_code = supervisor_main(
        [
            "dashboard",
            "--codex-home",
            str(codex_home),
            "--limit",
            "5",
            "--json",
        ]
    )

    assert dashboard_exit_code == 0
    dashboard_payload = json.loads(capsys.readouterr().out)
    assert dashboard_payload["counts"] == {
        "needs_attention": 0,
        "done": 0,
        "working": 0,
    }



def test_codex_supervisor_runner_goal_list_shows_latest_blocked_status(
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
            "展示阻塞目标状态。",
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
                "prompt": "展示阻塞目标状态。",
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

    exit_code = supervisor_main(["goal", "list", "--codex-home", str(codex_home), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    item = payload["active_goals"][0]
    assert item["goal_id"] == goal["goal_id"]
    assert item["last_status"] == "blocked"
    assert item["last_summary"] == "缺少产品决策。"
    assert item["last_next"] == "请求用户拍板。"

    exit_code = supervisor_main(["goal", "list", "--codex-home", str(codex_home)])
    assert exit_code == 0
    text = capsys.readouterr().out
    assert "状态：blocked" in text
    assert "摘要：缺少产品决策。" in text
    assert "下一步：请求用户拍板。" in text



def test_codex_supervisor_runner_goal_list_outputs_queue_view_groups(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _add_supervisor_goal(
        capsys,
        codex_home=codex_home,
        workspace=workspace,
        goal="等待启动的目标。",
        target_name="pending-worker",
    )
    _add_supervisor_goal(
        capsys,
        codex_home=codex_home,
        workspace=workspace,
        goal="夜间正在执行的目标。",
        target_name="running-worker",
    )
    blocked_goal = _add_supervisor_goal(
        capsys,
        codex_home=codex_home,
        workspace=workspace,
        goal="被依赖卡住的目标。",
        target_name="blocked-worker",
    )
    needs_user_goal = _add_supervisor_goal(
        capsys,
        codex_home=codex_home,
        workspace=workspace,
        goal="等待用户确认的目标。",
        target_name="needs-user-worker",
    )
    done_goal = _add_supervisor_goal(
        capsys,
        codex_home=codex_home,
        workspace=workspace,
        goal="刚跑完等待归档的目标。",
        target_name="done-worker",
    )
    _append_supervisor_goal_status(
        codex_home,
        goal_id=str(blocked_goal["goal_id"]),
        status="blocked",
        target_name="blocked-worker",
        summary="依赖服务不可用。",
        next_step="等待依赖恢复。",
    )
    _append_supervisor_goal_status(
        codex_home,
        goal_id=str(needs_user_goal["goal_id"]),
        status="needs_user",
        target_name="needs-user-worker",
        summary="需要确认验收范围。",
        next_step="等待用户确认。",
    )
    _append_supervisor_goal_status(
        codex_home,
        goal_id=str(done_goal["goal_id"]),
        status="done",
        target_name="done-worker",
        summary="目标已经完成。",
        next_step="等待 Supervisor 归档。",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "running-worker",
                "cwd": str(workspace),
                "prompt": "夜间正在执行的目标。",
                "command": ["codex", "exec", "-C", str(workspace), "继续"],
                "pid": 4242,
                "started_at": NOW.isoformat(),
                "log_path": str(codex_home / "supervisor" / "logs" / "managed-001.log"),
                "status": "launched",
                "backend": "process",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._pid_is_running",
        lambda pid: pid == 4242,
    )

    exit_code = supervisor_main(["goal", "list", "--codex-home", str(codex_home), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    queue = payload["queue_view"]
    assert [item["target_name"] for item in queue["pending"]] == ["pending-worker"]
    assert [item["target_name"] for item in queue["running"]] == ["running-worker"]
    assert queue["running"][0]["worker_status"] == "running"
    assert [item["target_name"] for item in queue["blocked"]] == ["blocked-worker"]
    assert queue["blocked"][0]["last_summary"] == "依赖服务不可用。"
    assert [item["target_name"] for item in queue["needs_user"]] == [
        "needs-user-worker"
    ]
    assert [item["target_name"] for item in queue["done_recent"]] == ["done-worker"]
    assert queue["done_recent"][0]["last_next"] == "等待 Supervisor 归档。"

    exit_code = supervisor_main(["goal", "list", "--codex-home", str(codex_home)])

    assert exit_code == 0
    text = capsys.readouterr().out
    assert "队列视图：" in text
    assert "- pending: 1" in text
    assert "- running: 1" in text
    assert "- blocked: 1" in text
    assert "- needs_user: 1" in text
    assert "- done-recent: 1" in text
    assert "pending-worker 等待启动的目标。" in text
    assert "done-worker 刚跑完等待归档的目标。" in text



def test_codex_supervisor_runner_goal_list_reads_done_status_from_worker_log(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _add_supervisor_goal(
        capsys,
        codex_home=codex_home,
        workspace=workspace,
        goal="已经由 worker 完成的目标。",
        target_name="done-worker",
    )
    log_path = codex_home / "supervisor" / "logs" / "managed-001.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: worker 已完成并等待合并。\n"
        "SUPERVISOR_NEXT: 等待 Supervisor 触发 merge dispatch。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "done-worker",
                "cwd": str(workspace),
                "prompt": "已经由 worker 完成的目标。",
                "command": ["codex", "exec", "-C", str(workspace), "继续"],
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
        "isotope.features.supervisor.runner._pid_is_running",
        lambda pid: pid == 4242,
    )

    exit_code = supervisor_main(["goal", "list", "--codex-home", str(codex_home), "--json"])

    assert exit_code == 0
    queue = json.loads(capsys.readouterr().out)["queue_view"]
    assert queue["running"] == []
    assert [item["target_name"] for item in queue["done_recent"]] == ["done-worker"]
    assert queue["done_recent"][0]["worker_status"] == "done"
    assert queue["done_recent"][0]["last_summary"] == "worker 已完成并等待合并。"



