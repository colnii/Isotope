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

def test_codex_supervisor_dashboard_fallback_snapshot_keeps_schema_meta():
    report = CodexSupervisorReport(generated_at=NOW.isoformat(), sessions=())

    payload = _dashboard_payload(
        report,
        active_goals=[
            {
                "goal_id": "goal-001",
                "goal": "keep fallback snapshot versioned",
                "target_name": "fallback-meta",
                "last_status": "blocked",
            }
        ],
    )

    assert payload["state_snapshot"]["kind"] == "supervisor_state_snapshot"
    assert payload["state_snapshot"]["schema_version"] == 1
    assert payload["state_snapshot_meta"] == {
        "kind": "supervisor_state_snapshot",
        "schema_version": 1,
        "schema_label": "supervisor_state_snapshot v1",
        "schema_status": "ok",
        "schema_reason": None,
        "source_label": (
            "goal queue / decision requests / lane state / "
            "worker events / notifications / memory records / artifact summaries / "
            "agent groups / worker lifecycle"
        ),
    }



def test_codex_supervisor_dashboard_snapshot_meta_marks_legacy_snapshot_degraded():
    report = CodexSupervisorReport(generated_at=NOW.isoformat(), sessions=())

    payload = _dashboard_payload(
        report,
        state_snapshot={
            "status": "ok",
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
            },
            "active_goals": [],
            "active_decisions": [],
            "failed_lanes": [],
            "recent_worker_events": [],
            "notifications": {"total": 0, "unread": 0, "recent": []},
        },
    )

    assert payload["state_snapshot_meta"] == {
        "kind": None,
        "schema_version": None,
        "schema_label": "degraded snapshot schema",
        "schema_status": "degraded",
        "schema_reason": "missing kind",
        "source_label": (
            "goal queue / decision requests / lane state / "
            "worker events / notifications / memory records / artifact summaries / "
            "agent groups / worker lifecycle"
        ),
    }



def test_codex_supervisor_dashboard_json_includes_display_title_and_short_hash(
    tmp_path,
    capsys,
):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-titled.jsonl",
        session_id="019e2e4f-d541-72f1-9269-471aa50bc2f2",
        cwd="/home/lumber/Github/isotope",
        events=[
            _event(
                "2026-05-16T11:58:20Z",
                "event_msg",
                {
                    "type": "thread_name_updated",
                    "thread_name": "Supervisor页面",
                },
            ),
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {"type": "agent_reasoning", "message": "running tests"},
            ),
        ],
    )

    exit_code = supervisor_main(
        [
            "dashboard",
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
    item = payload["groups"]["working"][0]
    assert item["display_title"] == "Supervisor页面"
    assert item["thread_name"] == "Supervisor页面"
    assert item["short_session_id"] == "019e2e4f"
    assert item["resume_command"] == "codex resume 019e2e4f-d541-72f1-9269-471aa50bc2f2"



def test_codex_supervisor_dashboard_json_includes_managed_control_commands(
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
        lambda session: "python版本升级评估\nrunning checks",
    )

    exit_code = supervisor_main(
        [
            "dashboard",
            "--codex-home",
            str(codex_home),
            "--limit",
            "1",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    item = payload["groups"]["working"][0]
    assert item["name"] == "lane-a"
    assert item["control_commands"] == [
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
    ]



def test_codex_supervisor_dashboard_omits_exited_managed_tmux_lanes():
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="managed:closed",
                cwd="/home/lumber/Github/isotope",
                source_path="/home/lumber/.codex/supervisor/managed_sessions.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=120,
                status="exited",
                reason="Supervisor 托管 tmux 会话已退出",
                managed=True,
                managed_name="closed-lane",
                managed_backend="tmux",
                managed_tmux_session="closed-session",
            ),
            CodexSessionSummary(
                session_id="managed:live",
                cwd="/home/lumber/Github/isotope",
                source_path="/home/lumber/.codex/supervisor/managed_sessions.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=30,
                status="working",
                reason="Supervisor 托管 tmux 会话仍在运行",
                managed=True,
                managed_name="live-lane",
                managed_backend="tmux",
                managed_tmux_session="live-session",
            ),
        ),
    )

    payload = _dashboard_payload(report)

    all_items = [
        item
        for items in payload["groups"].values()
        for item in items
    ]
    assert [item["name"] for item in all_items] == ["live-lane"]
    assert payload["counts"] == {
        "needs_attention": 0,
        "done": 0,
        "working": 1,
    }



def test_codex_supervisor_dashboard_merges_managed_lane_with_real_session(
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
        "2026/05/16/rollout-real-codex.jsonl",
        session_id="019e3205-b9cc-7012-804c-ca2ac38e0d32",
        cwd=str(workspace),
        events=[
            _event(
                "2026-05-16T11:58:20Z",
                "event_msg",
                {
                    "type": "thread_name_updated",
                    "thread_name": "python版本升级评估",
                },
            ),
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {"type": "agent_reasoning", "message": "running checks"},
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
        lambda session: "python版本升级评估\nrunning checks",
    )

    exit_code = supervisor_main(
        [
            "dashboard",
            "--codex-home",
            str(codex_home),
            "--limit",
            "5",
            "--stale-after",
            "999999",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    working = payload["groups"]["working"]
    assert len(working) == 1
    item = working[0]
    assert item["name"] == "lane-a"
    assert item["display_title"] == "python版本升级评估"
    assert item["managed_display_title"] == "lane-a"
    assert item["session_id"] == "managed:managed-001"
    assert item["linked_session_id"] == "019e3205-b9cc-7012-804c-ca2ac38e0d32"
    assert item["linked_resume_command"] == (
        "codex resume 019e3205-b9cc-7012-804c-ca2ac38e0d32"
    )
    assert item["resume_command"] == item["linked_resume_command"]
    assert item["thread_name"] == "python版本升级评估"
    assert item["status_evidence"] == {
        "source": "managed_tmux",
        "label": "托管 tmux 状态",
        "detail": "tmux 会话仍在运行",
    }



def test_codex_supervisor_dashboard_uses_tmux_pane_text_to_link_managed_lane(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    _write_session(
        codex_home,
        "2026/05/16/rollout-unrelated.jsonl",
        session_id="019e3205-b9cc-7012-804c-ca2ac38e0d33",
        cwd=str(workspace),
        events=[
            _event(
                "2026-05-16T11:59:50Z",
                "event_msg",
                {"type": "thread_name_updated", "thread_name": "另一个同目录窗口"},
            ),
            _event(
                "2026-05-16T11:59:50Z",
                "event_msg",
                {"type": "agent_reasoning", "message": "running unrelated checks"},
            ),
        ],
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-target.jsonl",
        session_id="019e3205-b9cc-7012-804c-ca2ac38e0d32",
        cwd=str(workspace),
        events=[
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {"type": "thread_name_updated", "thread_name": "python版本升级评估"},
            ),
            _user_message("2026-05-16T11:59:20Z", "评估一下，项目能否升级到 Python 3.14"),
        ],
    )

    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
        tmux_session_checker=lambda session: session == "isotope-lane-a",
        tmux_bell_checker=lambda session: False,
        tmux_pane_reader=lambda session: "当前窗口：python版本升级评估\n评估一下，项目能否升级到 Python 3.14",
    ).scan(limit=5, stale_after_seconds=999999)
    payload = _dashboard_payload(report)

    managed_item = next(
        item for item in payload["groups"]["working"] if item["name"] == "lane-a"
    )
    assert managed_item["display_title"] == "python版本升级评估"
    assert managed_item["linked_session_id"] == "019e3205-b9cc-7012-804c-ca2ac38e0d32"
    assert any(
        item["display_title"] == "另一个同目录窗口"
        for item in payload["groups"]["working"]
    )



def test_codex_supervisor_dashboard_links_stale_protocol_session_from_tmux_pane(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    _write_session(
        codex_home,
        "2026/05/16/rollout-done.jsonl",
        session_id="019e3205-b9cc-7012-804c-ca2ac38e0d32",
        cwd=str(workspace),
        events=[
            _event(
                "2026-05-16T11:40:00Z",
                "event_msg",
                {"type": "thread_name_updated", "thread_name": "python版本升级评估"},
            ),
            _assistant_message(
                "2026-05-16T11:40:00Z",
                "\n".join(
                    [
                        "SUPERVISOR_STATUS: done",
                        "SUPERVISOR_SUMMARY: 当前 main 与 origin/main 同步。",
                        "SUPERVISOR_NEXT: 建议进入下一项明确任务。",
                    ]
                ),
            ),
        ],
    )

    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
        tmux_session_checker=lambda session: session == "isotope-lane-a",
        tmux_bell_checker=lambda session: False,
        tmux_pane_reader=lambda session: (
            "python版本升级评估\n"
            "SUPERVISOR_STATUS: done\n"
            "SUPERVISOR_SUMMARY: 当前 main 与 origin/main 同步。"
        ),
    ).scan(limit=5, stale_after_seconds=600)
    payload = _dashboard_payload(report)

    assert payload["counts"]["done"] == 1
    item = payload["groups"]["done"][0]
    assert item["name"] == "lane-a"
    assert item["display_title"] == "python版本升级评估"
    assert item["linked_session_id"] == "019e3205-b9cc-7012-804c-ca2ac38e0d32"
    assert item["supervisor_status"] == "done"



def test_codex_supervisor_dashboard_matches_managed_lanes_without_stealing_links(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    isotope_workspace = tmp_path / "isotope"
    repo_workspace = tmp_path / "repo"
    isotope_workspace.mkdir()
    repo_workspace.mkdir()
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True)
    records = [
        {
            "record_id": "managed-project",
            "name": "项目重新整理",
            "cwd": str(isotope_workspace),
            "prompt": "接管已有 tmux 会话",
            "command": ["tmux", "attach", "-t", "iso_dev"],
            "pid": 0,
            "started_at": "2026-05-16T12:00:02+00:00",
            "log_path": str(codex_home / "supervisor" / "logs" / "managed-project.log"),
            "status": "adopted",
            "backend": "tmux",
            "tmux_session": "iso_dev",
        },
        {
            "record_id": "managed-python",
            "name": "test",
            "cwd": str(isotope_workspace),
            "prompt": "接管已有 tmux 会话",
            "command": ["tmux", "attach", "-t", "test"],
            "pid": 0,
            "started_at": "2026-05-16T12:00:01+00:00",
            "log_path": str(codex_home / "supervisor" / "logs" / "managed-python.log"),
            "status": "adopted",
            "backend": "tmux",
            "tmux_session": "test",
        },
    ]
    registry_path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-python.jsonl",
        session_id="019e3205-b9cc-7012-804c-ca2ac38e0d32",
        cwd=str(isotope_workspace),
        events=[
            _event(
                "2026-05-16T11:40:00Z",
                "event_msg",
                {"type": "thread_name_updated", "thread_name": "python版本升级评估"},
            ),
            _assistant_message(
                "2026-05-16T11:40:00Z",
                "\n".join(
                    [
                        "SUPERVISOR_STATUS: done",
                        "SUPERVISOR_SUMMARY: Python 版本升级评估已完成。",
                        "SUPERVISOR_NEXT: 等待下一项任务。",
                    ]
                ),
            ),
        ],
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-project.jsonl",
        session_id="019e3210-b9cc-7012-804c-ca2ac38e0d99",
        cwd=str(repo_workspace),
        events=[
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {"type": "thread_name_updated", "thread_name": "项目重新整理"},
            ),
            _assistant_message("2026-05-16T11:59:20Z", "正在整理项目目录。"),
        ],
    )

    def pane_text(session: str) -> str:
        if session == "iso_dev":
            return "test -> python版本升级评估\n项目重新整理\n正在整理项目目录"
        if session == "test":
            return "python版本升级评估\nSUPERVISOR_STATUS: done"
        return ""

    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
        tmux_session_checker=lambda session: session in {"iso_dev", "test"},
        tmux_bell_checker=lambda session: False,
        tmux_pane_reader=pane_text,
    ).scan(limit=10, stale_after_seconds=600)
    payload = _dashboard_payload(report)

    done_item = payload["groups"]["done"][0]
    assert done_item["display_title"] == "python版本升级评估"
    assert done_item["name"] == "test"
    assert done_item["managed_tmux_session"] == "test"
    assert done_item["linked_session_id"] == "019e3205-b9cc-7012-804c-ca2ac38e0d32"
    assert done_item["resume_command"] == (
        "codex resume 019e3205-b9cc-7012-804c-ca2ac38e0d32"
    )

    working_item = next(
        item for item in payload["groups"]["working"] if item["name"] == "项目重新整理"
    )
    assert working_item["display_title"] == "项目重新整理"
    assert working_item["managed_tmux_session"] == "iso_dev"
    assert working_item["linked_session_id"] == "019e3210-b9cc-7012-804c-ca2ac38e0d99"
    assert working_item["resume_command"] == (
        "codex resume 019e3210-b9cc-7012-804c-ca2ac38e0d99"
    )



def test_codex_supervisor_dashboard_uses_launch_prompt_to_disambiguate_similar_lanes():
    long_prompt = (
        "Supervisor 双窗口真实托管验证，长任务 lane。请只读，不要修改文件。"
        "第一阶段：运行 sleep 55，然后运行 git rev-parse --abbrev-ref HEAD。"
    )
    short_prompt = (
        "Supervisor 双窗口真实托管验证，短任务 lane。请只读，不要修改文件。"
        "第一阶段：运行 sleep 8，然后运行 git rev-parse --abbrev-ref HEAD。"
    )
    common_terminal = "\n".join(
        [
            "SUPERVISOR_STATUS: done",
            "SUPERVISOR_SUMMARY: 第一阶段完成。",
            "SUPERVISOR_NEXT: 等待 Supervisor 继续指令。",
        ]
    )
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="managed:short",
                cwd=EXISTING_WORKSPACE,
                source_path="/home/lumber/.codex/supervisor/managed_sessions.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=20,
                status="working",
                reason="Supervisor 托管 tmux 会话仍在运行",
                last_user_message=short_prompt,
                managed=True,
                managed_name="e2e-short",
                managed_backend="tmux",
                managed_tmux_session="supervisor-e2e-short",
                managed_terminal_excerpt=common_terminal,
            ),
            CodexSessionSummary(
                session_id="managed:long",
                cwd=EXISTING_WORKSPACE,
                source_path="/home/lumber/.codex/supervisor/managed_sessions.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=20,
                status="working",
                reason="Supervisor 托管 tmux 会话仍在运行",
                last_user_message=long_prompt,
                managed=True,
                managed_name="e2e-long",
                managed_backend="tmux",
                managed_tmux_session="supervisor-e2e-long",
                managed_terminal_excerpt=common_terminal,
            ),
            CodexSessionSummary(
                session_id="real-long",
                cwd=EXISTING_WORKSPACE,
                source_path="/home/lumber/.codex/sessions/long.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=10,
                status="done",
                reason="long 第一阶段完成。",
                initial_user_title=long_prompt,
                last_user_message=long_prompt,
                last_assistant_message=common_terminal,
                supervisor_status="done",
                supervisor_summary="long 第一阶段完成。",
            ),
            CodexSessionSummary(
                session_id="real-short",
                cwd=EXISTING_WORKSPACE,
                source_path="/home/lumber/.codex/sessions/short.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=10,
                status="done",
                reason="short 第一阶段完成。",
                initial_user_title=short_prompt,
                last_user_message=short_prompt,
                last_assistant_message=common_terminal,
                supervisor_status="done",
                supervisor_summary="short 第一阶段完成。",
            ),
        ),
    )

    payload = _dashboard_payload(report)

    short_item = next(
        item for item in payload["groups"]["done"] if item["name"] == "e2e-short"
    )
    long_item = next(
        item for item in payload["groups"]["done"] if item["name"] == "e2e-long"
    )
    assert short_item["linked_session_id"] == "real-short"
    assert short_item["display_title"] == short_prompt[:47] + "…"
    assert long_item["linked_session_id"] == "real-long"
    assert long_item["display_title"] == long_prompt[:47] + "…"



def test_codex_supervisor_dashboard_json_separates_current_batch_from_deleted_worktree_history(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    current_workspace = tmp_path / "current-worktree"
    deleted_workspace = tmp_path / "deleted-worktree"
    current_workspace.mkdir()
    target_name = "supervisor-current-batch-dashboard"
    goals_path = codex_home / "supervisor" / "goals.jsonl"
    goals_path.parent.mkdir(parents=True, exist_ok=True)
    goals_path.write_text(
        json.dumps(
            {
                "event": "supervisor_goal",
                "goal_id": "goal-current",
                "created_at": NOW.isoformat(),
                "cwd": str(current_workspace),
                "goal": "改进当前批次 dashboard 视图",
                "target_name": target_name,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_managed_tmux_record(
        codex_home,
        workspace=current_workspace,
        name=target_name,
        record_id="managed-current",
        tmux_session="isotope-current-batch",
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-deleted-worktree.jsonl",
        session_id="historical-deleted-worktree",
        cwd=str(deleted_workspace),
        events=[
            _event(
                "2026-05-16T11:40:00Z",
                "event_msg",
                {"type": "thread_name_updated", "thread_name": target_name},
            ),
            _assistant_message(
                "2026-05-16T11:40:00Z",
                "\n".join(
                    [
                        "SUPERVISOR_STATUS: done",
                        "SUPERVISOR_SUMMARY: 旧 worktree 里的任务已完成。",
                        "SUPERVISOR_NEXT: 等待 Supervisor 归档。",
                    ]
                ),
            ),
        ],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_session_exists",
        lambda session: session == "isotope-current-batch",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_window_has_bell",
        lambda session: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._tmux_capture_pane",
        lambda session: "当前批次正在运行 pytest",
    )

    exit_code = supervisor_main(
        [
            "dashboard",
            "--codex-home",
            str(codex_home),
            "--limit",
            "5",
            "--stale-after",
            "600",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert [goal["goal_id"] for goal in payload["current"]["active_goals"]] == [
        "goal-current"
    ]
    assert payload["current"]["active_goals"][0]["cwd_exists"] is True
    assert [worker["name"] for worker in payload["current"]["managed_workers"]] == [
        target_name
    ]
    assert payload["current"]["managed_workers"][0]["cwd_exists"] is True
    assert payload["current"]["managed_workers"][0]["current"] is True

    historical = next(
        item
        for items in payload["groups"].values()
        for item in items
        if item["session_id"] == "historical-deleted-worktree"
    )
    assert historical["cwd_exists"] is False
    assert historical["current"] is False
    assert "historical-deleted-worktree" not in {
        worker.get("linked_session_id")
        for worker in payload["current"]["managed_workers"]
    }



def test_codex_supervisor_dashboard_does_not_raise_attention_for_missing_worktree_blocked_history(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    missing_workspace = tmp_path / "repo" / ".worktrees" / "supervisor" / "missing-merge-worktree"
    _write_session(
        codex_home,
        "2026/05/16/rollout-missing-blocked.jsonl",
        session_id="missing-blocked",
        cwd=str(missing_workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:40:00Z",
                "\n".join(
                    [
                        "SUPERVISOR_STATUS: blocked",
                        "SUPERVISOR_SUMMARY: 旧合并 worktree 发生冲突。",
                        "SUPERVISOR_NEXT: 需要人工复查旧 worktree。",
                    ]
                ),
            ),
        ],
    )

    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
    ).scan(limit=5, stale_after_seconds=600, active_within_seconds=180)
    payload = _dashboard_payload(report)

    assert payload["counts"]["needs_attention"] == 0
    assert [item["session_id"] for item in payload["groups"]["done"]] == [
        "missing-blocked"
    ]
    assert payload["groups"]["done"][0]["cwd_exists"] is False



def test_codex_supervisor_dashboard_current_batch_excludes_done_managed_worker(
    tmp_path,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    done_worker = CodexSessionSummary(
        session_id="managed:done-worker",
        cwd=str(workspace),
        source_path=str(tmp_path / "done.log"),
        last_event_at=NOW.isoformat(),
        age_seconds=20,
        status="done",
        reason="Supervisor 托管进程已完成",
        managed=True,
        managed_name="done-worker",
        managed_backend="process",
        supervisor_status="done",
        supervisor_summary="worker 已完成。",
        supervisor_next="等待 Supervisor 归档。",
    )
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(done_worker,),
    )

    payload = _dashboard_payload(report)

    assert payload["groups"]["done"][0]["name"] == "done-worker"
    assert payload["groups"]["done"][0]["current"] is False
    assert payload["current"]["managed_workers"] == []



def test_codex_supervisor_dashboard_current_batch_uses_projection_filters(
    tmp_path,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    stale_workspace = tmp_path / "stale-workspace"
    stale_workspace.mkdir()
    done_workspace = tmp_path / "done-workspace"
    done_workspace.mkdir()
    active_goals = [
        {
            "goal_id": "goal-current",
            "target_name": "current-worker",
            "goal": "推进当前批次。",
            "cwd": str(workspace),
            "last_status": "working",
        },
        {
            "goal_id": "goal-stale",
            "target_name": "stale-worker",
            "goal": "历史 stale 目标。",
            "cwd": str(stale_workspace),
            "last_status": "stale",
        },
        {
            "goal_id": "goal-done",
            "target_name": "done-worker",
            "goal": "历史 done 目标。",
            "cwd": str(done_workspace),
            "last_status": "done",
        },
    ]
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="managed:current-worker",
                cwd=str(workspace),
                source_path=str(tmp_path / "current.log"),
                last_event_at=NOW.isoformat(),
                age_seconds=20,
                status="working",
                reason="Supervisor 托管进程正在运行",
                managed=True,
                managed_name="current-worker",
                managed_backend="process",
                supervisor_status="working",
            ),
            CodexSessionSummary(
                session_id="managed:stale-worker",
                cwd=str(stale_workspace),
                source_path=str(tmp_path / "stale.log"),
                last_event_at=NOW.isoformat(),
                age_seconds=7200,
                status="stale",
                reason="历史托管 worker 已 stale",
                managed=True,
                managed_name="stale-worker",
                managed_backend="process",
                supervisor_status="stale",
            ),
            CodexSessionSummary(
                session_id="managed:done-worker",
                cwd=str(done_workspace),
                source_path=str(tmp_path / "done.log"),
                last_event_at=NOW.isoformat(),
                age_seconds=20,
                status="done",
                reason="历史托管 worker 已完成",
                managed=True,
                managed_name="done-worker",
                managed_backend="process",
                supervisor_status="done",
            ),
        ),
    )

    payload = _dashboard_payload(report, active_goals=active_goals)

    assert [goal["goal_id"] for goal in payload["current"]["active_goals"]] == [
        "goal-current"
    ]
    assert [worker["name"] for worker in payload["current"]["managed_workers"]] == [
        "current-worker"
    ]
    assert payload["current"]["counts"] == {
        "active_goals": 1,
        "managed_workers": 1,
        "worker_reviews": 0,
        "automation_candidates": 0,
        "total": 2,
    }
    assert payload["current"]["target_names"] == ["current-worker"]



def test_codex_supervisor_loop_payload_includes_current_batch_projection(
    tmp_path,
    monkeypatch,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    stale_workspace = tmp_path / "stale-workspace"
    stale_workspace.mkdir()
    active_goals = [
        {
            "goal_id": "goal-current",
            "target_name": "current-worker",
            "goal": "推进当前批次。",
            "cwd": str(workspace),
            "last_status": "working",
        },
        {
            "goal_id": "goal-stale",
            "target_name": "stale-worker",
            "goal": "历史 stale 目标。",
            "cwd": str(stale_workspace),
            "last_status": "stale",
        },
    ]

    monkeypatch.setattr(
        "isotope.features.supervisor.runner._active_goal_dicts",
        lambda args, **kwargs: active_goals,
    )
    args = argparse.Namespace(
        codex_home=str(tmp_path / ".codex"),
        command="loop",
        name=None,
        all_workspaces=True,
        workspace_root=None,
        goal=None,
        llm_action=False,
        llm_execute=False,
        llm_summary=False,
        auto_execute=False,
        execute=False,
        prompt_cooldown=0,
        max_continue_count=0,
        max_run_minutes=0,
        max_fanout_launches=2,
    )
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="managed:current-worker",
                cwd=str(workspace),
                source_path=str(tmp_path / "current.log"),
                last_event_at=NOW.isoformat(),
                age_seconds=20,
                status="working",
                reason="Supervisor 托管进程正在运行",
                managed=True,
                managed_name="current-worker",
                managed_backend="process",
                supervisor_status="working",
            ),
            CodexSessionSummary(
                session_id="managed:stale-worker",
                cwd=str(stale_workspace),
                source_path=str(tmp_path / "stale.log"),
                last_event_at=NOW.isoformat(),
                age_seconds=7200,
                status="stale",
                reason="历史托管 worker 已 stale",
                managed=True,
                managed_name="stale-worker",
                managed_backend="process",
                supervisor_status="stale",
            ),
        ),
    )

    payload = _supervise_payload(args, report, iteration=1)

    assert [goal["goal_id"] for goal in payload["current_batch"]["active_goals"]] == [
        "goal-current"
    ]
    assert [
        worker["name"] for worker in payload["current_batch"]["managed_workers"]
    ] == ["current-worker"]
    assert payload["current_batch"]["target_names"] == ["current-worker"]
    assert payload["current_batch"]["dependency_batch"]["summary"]["limit"] == 2



def test_codex_supervisor_dashboard_follows_new_session_in_same_tmux_lane(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "isotope"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    old_session_id = "019e3205-b9cc-7012-804c-ca2ac38e0d32"
    new_session_id = "019e35a2-e442-75e2-84ab-3761a685a736"
    _write_session(
        codex_home,
        "2026/05/16/rollout-python.jsonl",
        session_id=old_session_id,
        cwd=str(workspace),
        events=[
            _event(
                "2026-05-16T11:40:00Z",
                "event_msg",
                {"type": "thread_name_updated", "thread_name": "python版本升级评估"},
            ),
            _assistant_message(
                "2026-05-16T11:40:00Z",
                "\n".join(
                    [
                        "SUPERVISOR_STATUS: done",
                        "SUPERVISOR_SUMMARY: Python 版本升级评估已完成。",
                        "SUPERVISOR_NEXT: 等待下一项任务。",
                    ]
                ),
            ),
        ],
    )
    _write_session(
        codex_home,
        "2026/05/17/rollout-new-test.jsonl",
        session_id=new_session_id,
        cwd=str(workspace),
        events=[
            _event(
                "2026-05-16T11:40:20Z",
                "event_msg",
                {"type": "thread_name_updated", "thread_name": "测试"},
            ),
            _user_message(
                "2026-05-16T11:40:20Z",
                "这是 Supervisor 前端功能测试窗口。后续会反复请求测试 "
                "Isotope 的 feature/supervisor 前端、dashboard 刷新、"
                "resume/attach 绑定、状态按钮和托管输出展示。"
                "请不要继续 python版本升级评估。",
            ),
        ],
    )

    pane_text = "\n".join(
        [
            "SUPERVISOR_STATUS: done",
            "SUPERVISOR_SUMMARY: 当前 main 与 origin/main 同步。",
            f"To continue this session, run codex resume {old_session_id}",
            "╭────────────────────────╮",
            "│ >_ OpenAI Codex        │",
            "╰────────────────────────╯",
            "• Thread renamed to 测试, to resume this thread run codex resume '测试'",
            "› 这是 Supervisor 前端功能测试窗口。后续会反复请求测试 Isotope 的",
            "  feature/supervisor 前端、dashboard 刷新、resume/",
            "  attach 绑定、状态按钮和托管输出展示。请不要继续 python版本升级评估。",
        ]
    )
    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
        tmux_session_checker=lambda session: session == "isotope-lane-a",
        tmux_bell_checker=lambda session: False,
        tmux_pane_reader=lambda session: pane_text,
    ).scan(limit=10, stale_after_seconds=600)
    payload = _dashboard_payload(report)

    managed_item = next(
        item for item in payload["groups"]["working"] if item["name"] == "lane-a"
    )
    assert managed_item["display_title"] == "测试"
    assert managed_item["linked_session_id"] == new_session_id
    assert managed_item["resume_command"] == f"codex resume {new_session_id}"
    assert managed_item["linked_match"] == {
        "label": "活跃终端片段命中 Thread renamed 标题、最近消息片段",
        "reasons": [
            {
                "kind": "thread_marker",
                "label": "活跃终端片段命中 Thread renamed 标题",
                "weight": 250,
            },
            {
                "kind": "message_snippet",
                "label": "活跃终端片段命中最近消息片段",
                "weight": 160,
            },
        ],
        "scope": "active_terminal",
        "score": 410,
    }
    assert any(
        item["display_title"] == "python版本升级评估"
        for item in payload["groups"]["done"]
    )



def test_codex_supervisor_dashboard_keeps_new_thread_marker_in_long_terminal_tail(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "isotope"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    old_session_id = "019e3205-b9cc-7012-804c-ca2ac38e0d32"
    new_session_id = "019e35a2-e442-75e2-84ab-3761a685a736"
    _write_session(
        codex_home,
        "2026/05/16/rollout-python.jsonl",
        session_id=old_session_id,
        cwd=str(workspace),
        events=[
            _event(
                "2026-05-16T11:40:00Z",
                "event_msg",
                {"type": "thread_name_updated", "thread_name": "python版本升级评估"},
            ),
            _assistant_message(
                "2026-05-16T11:40:00Z",
                "\n".join(
                    [
                        "SUPERVISOR_STATUS: done",
                        "SUPERVISOR_SUMMARY: Python 版本升级评估已完成。",
                    ]
                ),
            ),
        ],
    )
    _write_session(
        codex_home,
        "2026/05/17/rollout-new-test.jsonl",
        session_id=new_session_id,
        cwd=str(workspace),
        events=[
            _event(
                "2026-05-16T11:40:20Z",
                "event_msg",
                {"type": "thread_name_updated", "thread_name": "测试"},
            ),
            _user_message(
                "2026-05-16T11:40:20Z",
                "这是 Supervisor 前端功能测试窗口。后续会反复请求测试 dashboard 刷新。",
            ),
        ],
    )
    pane_text = "\n".join(
        [
            "SUPERVISOR_STATUS: done",
            f"To continue this session, run codex resume {old_session_id}",
            "╭────────────────────────╮",
            "│ >_ OpenAI Codex        │",
            "╰────────────────────────╯",
            "• Thread renamed to 测试, to resume this thread run codex resume '测试'",
            "› 这是 Supervisor 前端功能测试窗口。后续会反复请求测试 dashboard 刷新。",
        ]
        + [f"后续输出 {index}" for index in range(1, 60)]
        + [f"To continue this session, run codex resume {old_session_id}"]
    )

    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
        tmux_session_checker=lambda session: session == "isotope-lane-a",
        tmux_bell_checker=lambda session: False,
        tmux_pane_reader=lambda session: pane_text,
    ).scan(limit=10, stale_after_seconds=600)
    payload = _dashboard_payload(report)

    managed_item = next(
        item for item in payload["groups"]["working"] if item["name"] == "lane-a"
    )
    assert managed_item["display_title"] == "测试"
    assert managed_item["linked_session_id"] == new_session_id
    assert "Thread renamed to 测试" in managed_item["managed_terminal_excerpt"]



def test_codex_supervisor_dashboard_ignores_old_resume_id_after_new_context(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "isotope"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    old_session_id = "019e3205-b9cc-7012-804c-ca2ac38e0d32"
    new_session_id = "019e35a2-e442-75e2-84ab-3761a685a736"
    status_prompt = (
        "请汇报当前状态，回复时严格输出三行： 第一行 "
        "`SUPERVISOR_STATUS: working|done|blocked|needs_user`； 第二行 "
        "`SUPERVISOR_SUMMARY: 用一句中文说明当前进展`； 第三行 "
        "`SUPERVISOR_NEXT: 用一句中文说明建议下一步`。"
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-python.jsonl",
        session_id=old_session_id,
        cwd=str(workspace),
        events=[
            _event(
                "2026-05-16T11:40:00Z",
                "event_msg",
                {"type": "thread_name_updated", "thread_name": "python版本升级评估"},
            ),
            _user_message("2026-05-16T11:41:00Z", status_prompt),
            _assistant_message(
                "2026-05-16T11:42:00Z",
                "SUPERVISOR_STATUS: done\n"
                "SUPERVISOR_SUMMARY: Python 版本升级评估已完成。\n"
                "SUPERVISOR_NEXT: 等待下一项任务。",
            ),
        ],
    )
    _write_session(
        codex_home,
        "2026/05/17/rollout-new-test.jsonl",
        session_id=new_session_id,
        cwd=str(workspace),
        events=[
            _event(
                "2026-05-16T11:43:00Z",
                "event_msg",
                {"type": "thread_name_updated", "thread_name": "测试"},
            ),
            _user_message(
                "2026-05-16T11:43:00Z",
                "这是 Supervisor 前端功能测试窗口。后续会反复请求测试 "
                "Isotope 的 feature/supervisor 前端、dashboard 刷新、"
                "resume/attach 绑定、状态按钮和托管输出展示。"
                "请不要继续 python版本升级评估。",
            ),
            _assistant_message(
                "2026-05-16T11:44:00Z",
                "SUPERVISOR_STATUS: needs_user\n"
                "SUPERVISOR_SUMMARY: 当前没有正在执行的 Supervisor 前端测试任务。\n"
                "SUPERVISOR_NEXT: 请给出具体测试目标。",
            ),
        ],
    )
    pane_text = "\n".join(
        [
            "╭────────────────────────╮",
            "│ >_ OpenAI Codex        │",
            "╰────────────────────────╯",
            "› 这是 Supervisor 前端功能测试窗口。后续会反复请求测试 Isotope 的",
            "  feature/supervisor 前端、dashboard 刷新、resume/attach 绑定、状态按钮和托管输出展示。",
            "  请不要继续 python版本升级评估。",
            "• SUPERVISOR_STATUS: 已切换到 Supervisor 前端功能测试语境。",
            f"To continue this session, run codex resume {old_session_id}",
            f"› {status_prompt}",
            "• SUPERVISOR_STATUS: needs_user",
            "  SUPERVISOR_SUMMARY: 当前没有正在执行的 Supervisor 前端测试任务。",
            "  SUPERVISOR_NEXT: 请给出具体测试目标。",
            "› Improve documentation in @filename",
        ]
    )

    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
        tmux_session_checker=lambda session: session == "isotope-lane-a",
        tmux_bell_checker=lambda session: False,
        tmux_pane_reader=lambda session: pane_text,
    ).scan(limit=10, stale_after_seconds=600)
    payload = _dashboard_payload(report)

    test_item = next(
        item
        for group in payload["groups"].values()
        for item in group
        if item["name"] == "lane-a"
    )
    assert test_item["display_title"] == "测试", test_item["linked_match"]
    assert test_item["linked_session_id"] == new_session_id
    assert test_item["supervisor_status"] == "needs_user"



def test_codex_supervisor_dashboard_does_not_let_manager_lane_steal_by_session_id_only(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "isotope"
    repo_workspace = tmp_path / "repo"
    workspace.mkdir()
    repo_workspace.mkdir()
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True)
    new_session_id = "019e35a2-e442-75e2-84ab-3761a685a736"
    registry_path.write_text(
        "\n".join(
            json.dumps(record, ensure_ascii=False)
            for record in [
                {
                    "record_id": "managed-project",
                    "name": "项目重新整理",
                    "cwd": str(workspace),
                    "prompt": "接管已有 tmux 会话",
                    "command": ["tmux", "attach", "-t", "iso_dev"],
                    "pid": 0,
                    "started_at": "2026-05-16T12:00:02+00:00",
                    "log_path": str(codex_home / "supervisor" / "logs" / "project.log"),
                    "status": "adopted",
                    "backend": "tmux",
                    "tmux_session": "iso_dev",
                },
                {
                    "record_id": "managed-test",
                    "name": "test",
                    "cwd": str(workspace),
                    "prompt": "接管已有 tmux 会话",
                    "command": ["tmux", "attach", "-t", "test"],
                    "pid": 0,
                    "started_at": "2026-05-16T12:00:01+00:00",
                    "log_path": str(codex_home / "supervisor" / "logs" / "test.log"),
                    "status": "adopted",
                    "backend": "tmux",
                    "tmux_session": "test",
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-project.jsonl",
        session_id="019e274b-d20a-7400-8502-d3923d5167c6",
        cwd=str(repo_workspace),
        events=[
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {"type": "thread_name_updated", "thread_name": "项目重新整理"},
            ),
            _assistant_message("2026-05-16T11:59:20Z", "正在整理项目。"),
        ],
    )
    _write_session(
        codex_home,
        "2026/05/17/rollout-new-test.jsonl",
        session_id=new_session_id,
        cwd=str(workspace),
        events=[
            _event(
                "2026-05-16T11:40:20Z",
                "event_msg",
                {"type": "thread_name_updated", "thread_name": "测试"},
            ),
            _user_message(
                "2026-05-16T11:40:20Z",
                "这是 Supervisor 前端功能测试窗口。后续会反复请求测试 "
                "dashboard 刷新和 resume/attach 绑定。",
            ),
        ],
    )

    def pane_text(session: str) -> str:
        if session == "iso_dev":
            return (
                "正在排查 test 绑定问题。\n"
                f"页面里出现了 {new_session_id}，但这只是管理窗口在讨论别人的 id。"
            )
        if session == "test":
            return "\n".join(
                [
                    "╭────────────────────────╮",
                    "│ >_ OpenAI Codex        │",
                    "╰────────────────────────╯",
                    "• Thread renamed to 测试, to resume this thread run codex resume '测试'",
                    "› 这是 Supervisor 前端功能测试窗口。后续会反复请求测试 dashboard 刷新和 resume/attach 绑定。",
                ]
            )
        return ""

    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
        tmux_session_checker=lambda session: session in {"iso_dev", "test"},
        tmux_bell_checker=lambda session: False,
        tmux_pane_reader=pane_text,
    ).scan(limit=10, stale_after_seconds=600)
    payload = _dashboard_payload(report)

    test_item = next(
        item for item in payload["groups"]["working"] if item["name"] == "test"
    )
    assert test_item["display_title"] == "测试"
    assert test_item["linked_session_id"] == new_session_id
    assert test_item["linked_match"]["score"] == 410

    project_item = next(
        item for item in payload["groups"]["working"] if item["name"] == "项目重新整理"
    )
    assert project_item["display_title"] == "项目重新整理"
    assert project_item["linked_session_id"] == "019e274b-d20a-7400-8502-d3923d5167c6"



def test_codex_supervisor_dashboard_does_not_link_zero_score_same_cwd_session(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    _write_session(
        codex_home,
        "2026/05/16/rollout-unrelated.jsonl",
        session_id="019e3205-b9cc-7012-804c-ca2ac38e0d32",
        cwd=str(workspace),
        events=[
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {"type": "thread_name_updated", "thread_name": "Isotope loop"},
            ),
            _assistant_message("2026-05-16T11:59:20Z", "已完成下一步。"),
        ],
    )

    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
        tmux_session_checker=lambda session: session == "isotope-lane-a",
        tmux_bell_checker=lambda session: False,
        tmux_pane_reader=lambda session: "python版本升级评估\nSUPERVISOR_STATUS: done",
    ).scan(limit=5, stale_after_seconds=999999)
    payload = _dashboard_payload(report)

    managed_item = next(
        item for item in payload["groups"]["working"] if item["name"] == "lane-a"
    )
    assert managed_item["display_title"] == "lane-a"
    assert managed_item["linked_session_id"] is None
    assert any(
        item["display_title"] == "Isotope loop"
        for item in payload["groups"]["working"]
    )



def test_codex_supervisor_dashboard_uses_linked_protocol_for_managed_lane(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    _write_session(
        codex_home,
        "2026/05/16/rollout-target.jsonl",
        session_id="019e3205-b9cc-7012-804c-ca2ac38e0d32",
        cwd=str(workspace),
        events=[
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {"type": "thread_name_updated", "thread_name": "依赖升级卡住"},
            ),
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "\n".join(
                    [
                        "SUPERVISOR_STATUS: blocked",
                        "SUPERVISOR_SUMMARY: 依赖解析失败。",
                        "SUPERVISOR_NEXT: 需要确认是否降级依赖。",
                    ]
                ),
            ),
        ],
    )

    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
        tmux_session_checker=lambda session: session == "isotope-lane-a",
        tmux_bell_checker=lambda session: False,
        tmux_pane_reader=lambda session: "依赖升级卡住\nSUPERVISOR_STATUS: blocked",
    ).scan(limit=5, stale_after_seconds=999999)
    payload = _dashboard_payload(report)

    assert payload["counts"]["needs_attention"] == 1
    item = payload["groups"]["needs_attention"][0]
    assert item["name"] == "lane-a"
    assert item["display_title"] == "依赖升级卡住"
    assert item["linked_session_id"] == "019e3205-b9cc-7012-804c-ca2ac38e0d32"
    assert item["supervisor_status"] == "blocked"
    assert item["supervisor_summary"] == "依赖解析失败。"
    assert item["supervisor_next"] == "需要确认是否降级依赖。"
    assert item["status_evidence"] == {
        "source": "supervisor_protocol",
        "label": "主动状态协议",
        "detail": "SUPERVISOR_STATUS: blocked",
    }



def test_codex_supervisor_managed_terminal_excerpt_keeps_recent_tail(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    pane_text = "\n".join(
        [f"old terminal line {index}" for index in range(1, 70)]
        + [
            "SUPERVISOR_STATUS: done",
            "SUPERVISOR_SUMMARY: 文档已完成。",
            "› 好，下一步",
        ]
    )

    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
        tmux_session_checker=lambda session: session == "isotope-lane-a",
        tmux_bell_checker=lambda session: False,
        tmux_pane_reader=lambda session: pane_text,
    ).scan(limit=5, stale_after_seconds=999999)

    excerpt = report.sessions[0].managed_terminal_excerpt
    assert excerpt is not None
    assert "SUPERVISOR_STATUS: done" in excerpt
    assert "› 好，下一步" in excerpt
    assert "old terminal line 1" not in excerpt
    assert "\n" in excerpt
    assert report.sessions[0].to_dict()["managed_terminal_excerpt"] == excerpt



def test_codex_supervisor_dashboard_plain_shows_dependency_batch(tmp_path, capsys):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    active_goals = [
        {
            "goal_id": "goal-a",
            "target_name": "worker-a",
            "goal": "完成基础。",
            "last_status": "done",
            "merged": True,
            "verified": True,
            "cwd": str(workspace),
        },
        {
            "goal_id": "goal-b",
            "target_name": "worker-b",
            "goal": "接入基础。",
            "depends_on": ["worker-a"],
            "cwd": str(workspace),
        },
        {
            "goal_id": "goal-c",
            "target_name": "worker-c",
            "goal": "端到端验证。",
            "depends_on": ["worker-b"],
            "cwd": str(workspace),
        },
    ]
    report = CodexSupervisorReport(generated_at=NOW.isoformat(), sessions=())

    _print_dashboard_plain(_dashboard_payload(report, active_goals=active_goals))

    text = capsys.readouterr().out
    assert "依赖批次：ready" in text
    assert "可启动：worker-b" in text
    assert "等待依赖：worker-c <- worker-b" in text



def test_codex_supervisor_dashboard_json_includes_persisted_decision_requests(
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
                "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
                "target_name": "resume-019e35a2",
                "question": "目录迁移是保留兼容层，还是直接迁移并删除旧入口？",
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
            "dashboard",
            "--codex-home",
            str(codex_home),
            "--limit",
            "5",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision_requests"] == [
        {
            "request_id": "decision-001",
            "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
            "target_name": "resume-019e35a2",
            "goal_id": None,
            "question": "目录迁移是保留兼容层，还是直接迁移并删除旧入口？",
            "reason": "Codex 明确要拍板。",
            "context_status": "conflict",
            "created_at": "2026-05-16T12:00:00+00:00",
        }
    ]
    assert payload["state_snapshot"]["summary"]["active_decisions"] == 1
    assert payload["state_snapshot"]["active_decisions"] == payload["decision_requests"]



def test_codex_supervisor_dashboard_plain_prints_decision_requests(
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

    exit_code = supervisor_main(["dashboard", "--codex-home", str(codex_home)])

    assert exit_code == 0
    text = capsys.readouterr().out
    assert "等待拍板：1" in text
    assert "- 选择保留兼容层还是直接迁移？ context=conflict target=resume-session-a" in text



def test_codex_supervisor_state_plain_includes_degraded_snapshot_reason(capsys):
    supervisor_runner._print_state_plain(
        {
            "status": "ok",
            "codex_home": "/tmp/codex",
            "kind": "supervisor_state_snapshot",
            "summary": {
                "active_goals": 0,
                "active_decisions": 0,
                "failed_lanes": 0,
                "worker_events": 0,
                "notifications": 0,
                "unread_notifications": 0,
            },
        }
    )

    text = capsys.readouterr().out
    assert "状态快照：supervisor_state_snapshot degraded / missing schema_version" in text



def test_codex_supervisor_overnight_plain_includes_degraded_snapshot_reason(capsys):
    supervisor_runner._print_overnight_check_plain(
        {
            "summary": {
                "daemon_status": "not_running",
                "watcher_status": "not_running",
                "active_goals": 0,
                "integration_review": {
                    "total": 0,
                    "ready_to_integrate": 0,
                    "already_integrated": 0,
                    "needs_review": 0,
                    "conflict_risk": 0,
                },
                "cleanup_candidates": 0,
            },
            "daemon": {
                "activity": {
                    "state_snapshot": {
                        "status": "ok",
                        "summary": {},
                    }
                }
            },
        }
    )

    text = capsys.readouterr().out
    assert "状态快照：degraded snapshot schema / missing kind" in text



def test_codex_supervisor_loop_payload_produces_capacity_decisions_for_llm(
    tmp_path,
    monkeypatch,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    codex_home = tmp_path / ".codex"
    goal = "补齐当前目标需要的上下文。"
    decision = {
        "kind": "supervisor_capacity_decision",
        "next_action": "call_capacity",
        "reason": "ready",
        "capacity_id": "supervisor.request_context",
        "can_execute_agent_loop": True,
        "missing_inputs": [],
        "blocking_reasons": [],
    }
    provider = object()

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_capacity_calling_provider_from_env",
        lambda: provider,
    )

    def stub_build_capacity_plan(**kwargs: object) -> dict[str, object]:
        assert kwargs["goal"] == goal
        assert kwargs["provider"] is provider
        assert kwargs["execute_agent_loop"] is False
        return {
            "kind": "supervisor_capacity_plan",
            "status": "ok",
            "status_reason": "ready",
            "selection": {
                "capacity_id": "supervisor.request_context",
                "arguments": {"query": "补齐上下文输入"},
            },
            "agent_loop_result": {"agent_loop_executed": False},
            "supervisor_decision": decision,
        }

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.build_supervisor_capacity_plan",
        stub_build_capacity_plan,
    )
    captured: dict[str, object] = {}

    def stub_decide_action(args: object, report: object, payload: dict[str, object]):
        captured["capacity_decisions"] = payload.get("capacity_decisions")
        return {
            "kind": "monitor",
            "target_name": None,
            "reason": "只检查 capacity decision 输入。",
            "command_suggestion": None,
        }

    monkeypatch.setattr(
        "isotope.features.supervisor.runner._decide_action_with_llm",
        stub_decide_action,
    )

    args = argparse.Namespace(
        codex_home=str(codex_home),
        command="loop",
        name=None,
        all_workspaces=False,
        workspace_root=str(workspace),
        goal=goal,
        llm_action=True,
        llm_execute=False,
        llm_summary=False,
        capacity_decisions=True,
        auto_execute=False,
        execute=False,
        prompt_cooldown=0,
        max_continue_count=0,
        max_context_requests=0,
        max_run_minutes=0,
        max_fanout_launches=2,
        max_worker_retry_count=0,
        merge_dispatch_execute=False,
        auto_merge_promote=False,
    )
    report = CodexSupervisorReport(generated_at=NOW.isoformat(), sessions=())

    payload = _supervise_payload(args, report, iteration=1)

    assert payload["capacity_decisions"] == [decision]
    assert captured["capacity_decisions"] == [decision]
    assert payload["capacity_call_specs"] == [
        {
            "capacity_id": "supervisor.request_context",
            "goal": goal,
            "inputs": {"query": "补齐上下文输入"},
        }
    ]
    assert payload["capacity_decision_status"]["agent_loop_result"] == {
        "agent_loop_executed": False
    }



def test_codex_supervisor_dashboard_keeps_finished_process_with_protocol(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = codex_home / "supervisor" / "logs" / "managed-001.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: 已完成后台 smoke。\n"
        "SUPERVISOR_NEXT: 等待归档。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "lane-a",
                "cwd": str(workspace),
                "prompt": "继续实现 supervisor",
                "command": ["codex", "exec", "-C", str(workspace), "继续"],
                "pid": 12345,
                "started_at": "2026-05-16T11:59:30+00:00",
                "log_path": str(log_path),
                "status": "launched",
                "backend": "process",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
        process_checker=lambda pid: False,
    ).scan()
    payload = _dashboard_payload(report)

    assert payload["counts"]["done"] == 1
    item = payload["groups"]["done"][0]
    assert item["name"] == "lane-a"
    assert item["status"] == "done"
    assert item["supervisor_summary"] == "已完成后台 smoke。"



