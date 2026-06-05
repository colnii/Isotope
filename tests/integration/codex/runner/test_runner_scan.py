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

def test_codex_supervisor_runner_scan_prints_json(tmp_path, capsys):
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
        ["scan", "--codex-home", str(codex_home), "--limit", "1", "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["sessions"][0]["session_id"] == "active-session"



def test_codex_supervisor_runner_dashboard_json_groups_lanes(tmp_path, capsys):
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
    _write_session(
        codex_home,
        "2026/05/16/rollout-done.jsonl",
        session_id="done-session",
        cwd="/home/lumber/Github/isotope",
        events=[
            _assistant_message(
                "2026-05-16T11:58:20Z",
                "\n".join(
                    [
                        "SUPERVISOR_STATUS: done",
                        "SUPERVISOR_SUMMARY: 文档已完成。",
                    ]
                ),
            )
        ],
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-active.jsonl",
        session_id="active-session",
        cwd="/home/lumber/Github/isotope",
        events=[
            _event(
                "2026-05-16T11:57:20Z",
                "event_msg",
                {"type": "agent_reasoning", "message": "running tests"},
            )
        ],
    )

    exit_code = supervisor_main(
        [
            "dashboard",
            "--codex-home",
            str(codex_home),
            "--limit",
            "10",
            "--stale-after",
            NON_STALE_SECONDS,
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["recommendation"]["action"] == "inspect_blocked"
    assert payload["counts"] == {
        "needs_attention": 1,
        "done": 1,
        "working": 1,
    }
    assert [item["session_id"] for item in payload["groups"]["needs_attention"]] == [
        "blocked-session"
    ]
    assert [item["session_id"] for item in payload["groups"]["done"]] == ["done-session"]
    assert [item["session_id"] for item in payload["groups"]["working"]] == [
        "active-session"
    ]
    assert payload["groups"]["needs_attention"][0]["supervisor_summary"] == (
        "测试环境缺少 tmux。"
    )
    assert payload["groups"]["needs_attention"][0]["status_evidence"] == {
        "source": "supervisor_protocol",
        "label": "主动状态协议",
        "detail": "SUPERVISOR_STATUS: blocked",
    }



def test_codex_supervisor_runner_dashboard_json_reads_persisted_worker_lifecycle(
    tmp_path,
    capsys,
):
    codex_home = tmp_path / ".codex"
    record_worker_lifecycle_decision(
        codex_home=codex_home,
        worker_lifecycle_decision={
            "stage": "archived",
            "next_step": "cleanup_worktree",
            "policy": {
                "policy_status": "program_resolved",
                "program_action": "archive_integrated",
                "remaining_step": "cleanup_worktree",
                "blocked_reason": None,
            },
            "timeline": [
                {
                    "stage": "archived",
                    "action": "archive_integrated",
                    "source": "cleanup",
                    "status": "executed",
                    "executed": True,
                }
            ],
        },
        worker_lifecycle_execution={
            "kind": "cleanup_worktree",
            "source": "worker_lifecycle",
            "next_step": "cleanup_worktree",
            "status": "ready_to_delete",
            "delete_worktree_actions": [
                {
                    "kind": "delete_worktree",
                    "target_name": "source-worker",
                    "record_id": "managed-source",
                    "confirm_delete_worktree": True,
                    "base_ref": "main",
                    "source": "worker_lifecycle",
                }
            ],
        },
        worker_lifecycle_execution_result={
            "kind": "cleanup_worktree",
            "source": "worker_lifecycle",
            "skipped": True,
            "reason": "lifecycle cleanup execution requires --lifecycle-cleanup-execute",
            "count": 1,
        },
    )

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
    payload = json.loads(capsys.readouterr().out)
    assert payload["worker_lifecycle"]["stage"] == "archived"
    assert payload["worker_lifecycle"]["next_step"] == "cleanup_worktree"
    assert payload["worker_lifecycle"]["policy_status"] == "program_resolved"
    assert payload["worker_lifecycle_execution"] == {
        "status": "ready_to_delete",
        "kind": "cleanup_worktree",
        "next_step": "cleanup_worktree",
        "source": "worker_lifecycle",
        "action_count": 1,
        "execution_status": "skipped",
        "execution_reason": "lifecycle cleanup execution requires --lifecycle-cleanup-execute",
        "summary": {
            "archivable": 0,
            "delete_ready": 1,
            "delete_blocked": 0,
            "result_actions": 0,
        },
        "recommended_next_step": "delete_ready",
        "decision_source": "worker_lifecycle_execution",
        "routing_reason": (
            "program-owned lifecycle execution recommended delete_ready"
        ),
        "execute_hint": "--lifecycle-cleanup-execute",
        "execute_command": "isotope-supervisor loop --iterations 1 --lifecycle-cleanup-execute",
    }
    assert payload["state_snapshot"]["worker_lifecycle"] == payload["worker_lifecycle"]
    assert payload["state_snapshot"]["worker_lifecycle_execution"]["kind"] == "cleanup_worktree"



def test_codex_supervisor_runner_dashboard_json_includes_notifications(
    tmp_path,
    capsys,
):
    from isotope.features.notifications.flow import NotificationFlow

    codex_home = tmp_path / ".codex"
    created = NotificationFlow.in_process(codex_home).create_notification(
        notification_type="approval",
        title="Worker needs approval",
        source_ref={"ref_type": "supervisor_run", "run_id": "run_123"},
    )
    status = NotificationFlow.in_process(codex_home).create_notification(
        notification_type="worker_status",
        title="Worker finished tests",
        source_ref={"ref_type": "session", "session_id": "session_456"},
    )
    marked = NotificationFlow.in_process(codex_home).mark_read(status.notification_id)
    unsafe = NotificationFlow.in_process(codex_home).create_notification(
        notification_type="worker_status",
        title="Worker source check",
        source_ref={
            "ref_type": "supervisor_run",
            "run_id": "run_unsafe",
            "prompt": "RAW_PROMPT_SHOULD_NOT_LEAK",
            "api_key": "sk-test-secret",
            "log_path": "/tmp/raw.log",
        },
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
    assert payload["notifications"][:2] == [created.to_dict(), marked.to_dict()]
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
    assert payload["notifications"][2] == {
        **unsafe.to_dict(),
        "source_ref": {"ref_type": "supervisor_run", "run_id": "run_unsafe"},
    }
    raw_payload = json.dumps(payload, ensure_ascii=False)
    assert "RAW_PROMPT_SHOULD_NOT_LEAK" not in raw_payload
    assert "sk-test-secret" not in raw_payload
    assert "/tmp/raw.log" not in raw_payload
    assert payload["notification_counts"] == {"total": 3, "unread": 2}



def test_codex_supervisor_runner_dashboard_notification_counts_use_snapshot_total(
    tmp_path,
    capsys,
):
    from isotope.features.notifications.flow import NotificationFlow

    codex_home = tmp_path / ".codex"
    flow = NotificationFlow.in_process(codex_home)
    for index in range(22):
        flow.create_notification(
            notification_type="worker_status",
            title=f"Worker update {index}",
            source_ref={"ref_type": "supervisor_run", "run_id": f"run_{index}"},
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
    assert len(payload["notifications"]) == 20
    assert payload["notification_counts"] == {"total": 22, "unread": 22}
    assert payload["state_snapshot"]["summary"]["notifications"] == 22



def test_codex_supervisor_runner_dashboard_plain_is_grouped(tmp_path, capsys):
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
                    ]
                ),
            )
        ],
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-done.jsonl",
        session_id="done-session",
        cwd="/home/lumber/Github/isotope",
        events=[
            _assistant_message(
                "2026-05-16T11:58:20Z",
                "\n".join(
                    [
                        "SUPERVISOR_STATUS: done",
                        "SUPERVISOR_SUMMARY: 文档已完成。",
                    ]
                ),
            )
        ],
    )

    exit_code = supervisor_main(["dashboard", "--codex-home", str(codex_home)])

    assert exit_code == 0
    text = capsys.readouterr().out
    assert "[Codex Supervisor dashboard]" in text
    assert "建议：先查看主动汇报阻塞的窗口。" in text
    assert "需要看：1" in text
    assert "已完成：1" in text
    assert "工作中：0" in text
    assert "blocked-session 阻塞 / 测试环境缺少 tmux。" in text
    assert "done-session 已完成 / 文档已完成。" in text



def test_codex_supervisor_runner_check_json_summarizes_projection_surfaces(
    tmp_path,
    capsys,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    goal = _add_supervisor_goal(
        capsys,
        codex_home=codex_home,
        workspace=workspace,
        goal="早上检查 Supervisor 状态。",
        target_name="morning-check",
    )

    exit_code = supervisor_main(["check", "--codex-home", str(codex_home), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["summary"] == {
        "daemon_status": "not_running",
        "watcher_status": "not_running",
        "active_goals": 1,
        "integration_review": {
            "total": 0,
            "ready_to_integrate": 0,
            "already_integrated": 0,
            "needs_review": 0,
            "conflict_risk": 0,
        },
        "cleanup_candidates": 0,
    }
    assert payload["daemon"]["status"] == "not_running"
    assert payload["watcher"]["status"] == "not_running"
    assert payload["goals"]["active_goals"][0]["goal_id"] == goal["goal_id"]
    assert payload["integration_review"]["include_unfinished"] is True
    assert payload["cleanup"]["candidates"] == []



def test_codex_supervisor_runner_overnight_check_plain_is_compact_summary(
    tmp_path,
    capsys,
):
    codex_home = tmp_path / ".codex"

    exit_code = supervisor_main(["overnight-check", "--codex-home", str(codex_home)])

    assert exit_code == 0
    text = capsys.readouterr().out
    assert "[Codex Supervisor overnight check]" in text
    assert "daemon：not_running" in text
    assert "watcher：not_running" in text
    assert "活跃目标：0" in text
    assert "状态快照：supervisor_state_snapshot v1" in text
    assert "integration-review：total=0 ready=0 integrated=0 review=0 conflict=0" in text
    assert "可归档项：0" in text



def test_codex_supervisor_runner_scan_can_add_llm_summary(
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
            return "窗口 A 正在读文件，暂时不用介入。"

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
            "scan",
            "--codex-home",
            str(codex_home),
            "--limit",
            "1",
            "--llm-summary",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["llm_summary"] == "窗口 A 正在读文件，暂时不用介入。"
    assert captured["agent_name"] == "supervisor"



