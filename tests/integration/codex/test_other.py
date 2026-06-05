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

from .helpers import (
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

def test_codex_supervisor_discovers_sessions_and_classifies_attention(tmp_path):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-active.jsonl",
        session_id="active-session",
        cwd="/home/lumber/Github/isotope",
        events=[
            _event(
                "2026-05-16T11:59:00Z",
                "event_msg",
                {"type": "agent_reasoning", "message": "running tests"},
            )
        ],
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-attention.jsonl",
        session_id="attention-session",
        cwd="/home/lumber/Github/x-agent",
        events=[
            _assistant_message(
                "2026-05-16T11:55:00Z",
                "是否继续执行下一步？",
            )
        ],
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-stale.jsonl",
        session_id="stale-session",
        cwd="/home/lumber/Github/med-claw-x",
        events=[
            _event(
                "2026-05-16T11:40:00Z",
                "event_msg",
                {"type": "exec_command", "message": "pytest"},
            )
        ],
    )

    flow = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
        branch_resolver=lambda cwd: {"isotope": "main"}.get(Path(cwd).name),
    )

    report = flow.scan(limit=5, stale_after_seconds=600, active_within_seconds=180)

    assert [session.session_id for session in report.sessions] == [
        "active-session",
        "attention-session",
        "stale-session",
    ]
    assert report.sessions[0].status == "working"
    assert report.sessions[0].git_branch == "main"
    assert report.sessions[0].to_dict()["status_evidence"] == {
        "source": "recent_event",
        "label": "最近仍有事件",
        "detail": "60 秒前有新事件",
    }
    assert report.sessions[1].status == "needs_user"
    assert report.sessions[1].reason == "最近回复像是在等待用户确认"
    assert report.sessions[1].to_dict()["status_evidence"] == {
        "source": "attention_marker",
        "label": "文本命中等待用户",
        "detail": "最近回复包含确认类表达",
    }
    assert report.sessions[2].status == "stale"
    assert report.sessions[2].reason == "超过 10 分钟没有新事件"
    assert report.sessions[2].to_dict()["status_evidence"] == {
        "source": "stale_timeout",
        "label": "超过静默阈值",
        "detail": "1200 秒没有新事件，阈值 600 秒",
    }



def test_codex_supervisor_context_request_uses_bm25_backend_without_rg(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    (workspace / "docs" / "current").mkdir(parents=True)
    (workspace / ".worktrees" / "old").mkdir(parents=True)
    (workspace / "docs" / "current" / "status.md").write_text(
        "Supervisor 下一步节奏：由 LLM 主导。\n",
        encoding="utf-8",
    )
    (workspace / ".worktrees" / "old" / "status.md").write_text(
        "Supervisor 下一步节奏：旧工作树内容不应该参与。\n",
        encoding="utf-8",
    )

    def stub_run(
        command: list[str],
        *,
        cwd: str,
        text: bool,
        capture_output: bool,
        check: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        del command, cwd, text, capture_output, check, timeout
        raise AssertionError("request_context should use the BM25 backend, not rg")

    result = request_project_context(
        codex_home=codex_home,
        cwd=workspace,
        query="Supervisor 下一步节奏",
        run=stub_run,
        rg_bin="rg",
    )

    assert result.backend == "bm25"
    assert result.items[0].path == "docs/current/status.md"
    assert "LLM 主导" in result.items[0].text



def test_codex_supervisor_context_request_returns_ranked_evidence(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    (workspace / "docs" / "current").mkdir(parents=True)
    (workspace / "src" / "isotope" / "features" / "supervisor").mkdir(parents=True)
    (workspace / "docs" / "current" / "status.md").write_text(
        "# Codex Supervisor Status\n\n"
        "request_context ranked evidence 会给 LLM "
        "title path snippet score match_reason。\n",
        encoding="utf-8",
    )
    (workspace / "src" / "isotope" / "features" / "supervisor" / "context.py").write_text(
        "def request_project_context():\n"
        "    return 'context only'\n",
        encoding="utf-8",
    )

    result = request_project_context(
        codex_home=codex_home,
        cwd=workspace,
        query="request_context ranked evidence",
        max_results=2,
    )

    first = result.items[0]
    assert result.backend == "bm25"
    assert [item.score for item in result.items] == sorted(
        (item.score for item in result.items),
        reverse=True,
    )
    assert {item.path for item in result.items[:2]} == {
        "docs/current/status.md",
        "src/isotope/features/supervisor/context.py",
    }
    assert first.path == "docs/current/status.md"
    assert first.title == "Codex Supervisor Status"
    assert first.snippet == first.text
    assert "title path snippet score match_reason" in first.snippet
    assert first.score > result.items[1].score
    assert "request_context" in first.match_reason
    assert "ranked" in first.match_reason
    assert first.to_dict() == {
        "path": "docs/current/status.md",
        "line": 3,
        "title": "Codex Supervisor Status",
        "text": first.text,
        "snippet": first.snippet,
        "score": first.score,
        "match_reason": first.match_reason,
        "source_group": "docs/current",
    }

    recent = read_recent_context_results(codex_home=codex_home, cwd=workspace)
    assert recent[0].items[0].title == "Codex Supervisor Status"
    assert recent[0].items[0].snippet == first.snippet
    assert recent[0].items[0].match_reason == first.match_reason
    assert recent[0].items[0].source_group == "docs/current"



def test_codex_supervisor_context_request_bm25_top_two_keeps_keyword_baseline_hits(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    (workspace / "docs").mkdir(parents=True)
    (workspace / "src").mkdir(parents=True)
    (workspace / "docs" / "approval.md").write_text(
        "approval resume context gate keeps restart evidence current.\n",
        encoding="utf-8",
    )
    (workspace / "src" / "resume_context.py").write_text(
        "def approval_resume_context():\n"
        "    return 'restart evidence'\n",
        encoding="utf-8",
    )
    (workspace / "docs" / "noise.md").write_text(
        "approval approval approval approval unrelated note.\n",
        encoding="utf-8",
    )

    result = request_project_context(
        codex_home=codex_home,
        cwd=workspace,
        query="approval resume context",
        max_results=2,
    )

    assert result.backend == "bm25"
    assert {item.path for item in result.items[:2]} == {
        "docs/approval.md",
        "src/resume_context.py",
    }



def test_codex_supervisor_context_request_surfaces_project_context_anchors(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    (workspace / "docs" / "current").mkdir(parents=True)
    (workspace / "src" / "isotope" / "features" / "supervisor").mkdir(parents=True)
    (workspace / "docs" / "current" / "status.md").write_text(
        "# Isotope 当前状态\n\n当前主线要求 AI-first，避免把产品能力降级成诊断。\n",
        encoding="utf-8",
    )
    (workspace / "docs" / "current" / "supervisor-capability-map.md").write_text(
        "# Codex Supervisor 能力地图\n\n"
        "上下文能力层登记 context 和 request_context，给 planner 提供排序证据。\n",
        encoding="utf-8",
    )
    (workspace / "docs" / "current" / "docs-map.md").write_text(
        "# 当前文档地图\n\n先读 status、任务队列和 Supervisor 能力地图。\n",
        encoding="utf-8",
    )
    (workspace / "src" / "isotope" / "features" / "supervisor" / "context.py").write_text(
        "def request_project_context():\n"
        "    return 'ranked evidence'\n",
        encoding="utf-8",
    )
    (workspace / "src" / "isotope" / "features" / "supervisor" / "llm_summary.py").write_text(
        "def generate_llm_action_decision():\n"
        "    return 'planner entry'\n",
        encoding="utf-8",
    )

    def stub_run(
        command: list[str],
        *,
        cwd: str,
        text: bool,
        capture_output: bool,
        check: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, text, capture_output, check, timeout
        return subprocess.CompletedProcess(command, 1, "", "")

    result = request_project_context(
        codex_home=codex_home,
        cwd=workspace,
        query="Supervisor request_context docs/current 能力图 状态文档 代码入口",
        run=stub_run,
        rg_bin="rg",
        max_results=5,
    )

    paths = [item.path for item in result.items]
    assert result.backend == "bm25"
    assert "docs/current/supervisor-capability-map.md" in paths
    assert "docs/current/status.md" in paths
    assert "docs/current/docs-map.md" in paths
    assert "src/isotope/features/supervisor/context.py" in paths
    assert all(len(item.snippet) <= 240 for item in result.items)
    assert any("project context anchor" in item.match_reason for item in result.items)



def test_codex_supervisor_context_request_groups_current_docs_and_supervisor_code(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    (workspace / "docs" / "current").mkdir(parents=True)
    (workspace / "src" / "isotope" / "features" / "supervisor").mkdir(parents=True)
    (workspace / "docs" / "current" / "status.md").write_text(
        "# Isotope 当前状态\n\n"
        "`request_context` 会返回结构化 ranked evidence，供 LLM planner 判断下一步。\n",
        encoding="utf-8",
    )
    (workspace / "docs" / "current" / "supervisor-capability-map.md").write_text(
        "# Codex Supervisor 能力地图\n\n"
        "上下文能力层包含 context、request_context 和结果记录。\n",
        encoding="utf-8",
    )
    (workspace / "src" / "isotope" / "features" / "supervisor" / "context.py").write_text(
        "def request_project_context():\n"
        "    return 'ranked evidence'\n",
        encoding="utf-8",
    )

    def stub_run(
        command: list[str],
        *,
        cwd: str,
        text: bool,
        capture_output: bool,
        check: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, text, capture_output, check, timeout
        return subprocess.CompletedProcess(command, 1, "", "")

    result = request_project_context(
        codex_home=codex_home,
        cwd=workspace,
        query="Supervisor request_context docs/current 状态文档 代码入口",
        run=stub_run,
        rg_bin="rg",
        max_results=4,
    )

    by_path = {item.path: item for item in result.items}
    status = by_path["docs/current/status.md"].to_dict()
    context_py = by_path["src/isotope/features/supervisor/context.py"].to_dict()

    assert status["source_group"] == "docs/current"
    assert context_py["source_group"] == "supervisor feature code"
    assert "group: docs/current" in status["match_reason"]
    assert "matched aliases:" in status["match_reason"]
    assert "group: supervisor feature code" in context_py["match_reason"]
    assert "matched aliases:" in context_py["match_reason"]



def test_codex_supervisor_context_request_falls_back_without_rg(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    (workspace / "docs").mkdir(parents=True)
    (workspace / "docs" / "note.md").write_text(
        "request_context 可以使用 Python 兜底检索。\n",
        encoding="utf-8",
    )

    result = request_project_context(
        codex_home=codex_home,
        cwd=workspace,
        query="request_context Python",
        rg_bin=None,
    )

    assert result.backend == "bm25"
    assert result.items[0].path == "docs/note.md"



def test_codex_supervisor_start_here_prints_human_first_workflow(
    tmp_path,
    capsys,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    exit_code = supervisor_main(
        [
            "start-here",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--goal",
            "让 Supervisor 帮我推进当前项目。",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["workflow"]["cwd"] == str(workspace)
    assert payload["workflow"]["goal"] == "让 Supervisor 帮我推进当前项目。"
    assert payload["recommended_order"] == [
        "start",
        "open_web",
        "check_status",
        "send_feedback",
    ]
    assert payload["commands"]["start"] == (
        "cd "
        + shlex.quote(str(workspace))
        + " && isotope-supervisor up --codex-home "
        + shlex.quote(str(codex_home))
        + " --goal '让 Supervisor 帮我推进当前项目。' --goal-low-water 2"
        + " --goal-replenish-limit 2 --max-fanout-launches 2"
        + " --merge-dispatch-execute --lifecycle-archive-execute"
        + " --auto-merge-promote"
    )
    assert payload["commands"]["open_web"] == (
        "isotope-supervisor web --codex-home "
        + shlex.quote(str(codex_home))
        + " --host 127.0.0.1 --port 8765"
    )
    assert payload["commands"]["trace"] == (
        "isotope-supervisor trace --codex-home "
        + shlex.quote(str(codex_home))
        + " --json"
    )
    assert payload["feedback_prompts"] == [
        "页面是否能看出哪些 worker 正在跑？",
        "lifecycle_trace.next_attention 是否符合你的直觉？",
        "如果它停住了，停在 goal、worker、decision、merge 还是 cleanup？",
    ]



