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

def test_codex_supervisor_llm_action_prompt_scopes_to_active_goal_over_old_session(
    tmp_path,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    goal = "推进目标队列里的新功能。"
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="stale-session",
                cwd=str(workspace),
                source_path="/home/lumber/.codex/sessions/stale.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=900,
                status="stale",
                reason="旧普通会话长时间没有新事件。",
            ),
        ),
    )
    active_goals = [
        {
            "goal_id": "goal-001",
            "goal": goal,
            "cwd": str(workspace),
            "target_name": "goal-worker",
        }
    ]
    suggestions = _advice_payload(
        report,
        include_all_managed=True,
        active_goals=active_goals,
    )["command_suggestions"]

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            payload = json.loads(messages[1]["content"])
            assert payload["active_goals"][0]["target_name"] == "goal-worker"
            assert payload["candidate_targets"] == []
            assert "stale-session" not in payload["resumable_session_ids"]
            assert not any(
                suggestion.get("kind") == "resume_session"
                for suggestion in payload["command_suggestions"]
            )
            return json.dumps(
                {
                    "kind": "launch_session",
                    "target_name": "goal-worker",
                    "reason": "优先消费 active goal。",
                },
                ensure_ascii=False,
            )

    decision = generate_llm_action_decision(
        report,
        suggestions,
        DeterministicProvider(),
        active_goals=active_goals,
    )

    assert decision["kind"] == "launch_session"
    assert decision["target_name"] == "goal-worker"
    assert decision["prompt"] == goal



def test_codex_supervisor_llm_action_rejects_old_resume_with_active_goal(
    tmp_path,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    goal = "推进目标队列里的新功能。"
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="stale-session",
                cwd=str(workspace),
                source_path="/home/lumber/.codex/sessions/stale.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=900,
                status="stale",
                reason="旧普通会话长时间没有新事件。",
            ),
        ),
    )
    active_goals = [
        {
            "goal_id": "goal-001",
            "goal": goal,
            "cwd": str(workspace),
            "target_name": "goal-worker",
        }
    ]
    suggestions = _advice_payload(
        report,
        include_all_managed=True,
        active_goals=active_goals,
    )["command_suggestions"]

    class DeterministicProvider:
        def summarize(self, _messages: list[dict[str, str]]) -> str:
            return json.dumps(
                {
                    "kind": "resume_session",
                    "session_id": "stale-session",
                    "prompt_kind": "send_continue",
                    "reason": "错误地恢复旧普通会话。",
                },
                ensure_ascii=False,
            )

    with pytest.raises(ValueError, match="no command suggestion"):
        generate_llm_action_decision(
            report,
            suggestions,
            DeterministicProvider(),
            active_goals=active_goals,
        )



def test_codex_supervisor_llm_action_messages_include_whitelist_and_commands():
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
                managed_terminal_ready=True,
                managed_bell=True,
                supervisor_status="done",
                supervisor_summary="上一轮任务已完成。",
                supervisor_next="可以继续下一步。",
            ),
        ),
    )
    suggestions = _advice_payload(report, include_all_managed=True)["command_suggestions"]

    messages = build_llm_action_messages(report, suggestions)

    assert messages[0]["role"] == "system"
    assert "LLM planner" in messages[0]["content"]
    assert "执行协议" in messages[0]["content"]
    for term in ("guardrail", "护栏", "只能", "不得", "只输出"):
        assert term not in messages[0]["content"]
    assert (
        '"allowed_kinds": ["monitor", "send_status", "send_continue", '
        '"resume_session", "launch_session", "request_context", "ask_user", '
        '"delete_worktree", "call_capacity"]'
        in messages[1]["content"]
    )
    assert '"context_capability"' in messages[1]["content"]
    assert '"decision_gate"' in messages[1]["content"]
    assert '"kind": "send_continue"' in messages[1]["content"]
    assert '"target_name": "lane-a"' in messages[1]["content"]
    assert '"managed_terminal_ready": true' in messages[1]["content"]
    assert '"managed_bell": true' in messages[1]["content"]
    assert '"supervisor_status": "done"' in messages[1]["content"]



def test_codex_supervisor_llm_action_user_prompt_uses_execution_protocol_language():
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(),
    )

    messages = build_llm_action_messages(report, [])
    content = messages[1]["content"]

    assert "执行路径" in content
    for term in (
        "不得",
        "不要",
        "只允许",
        "才允许",
        "不是自动合并授权",
        "只提供",
    ):
        assert term not in content



def test_codex_supervisor_llm_action_messages_include_worker_review_context():
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="managed:managed-001",
                cwd=EXISTING_WORKSPACE,
                source_path="/home/lumber/.codex/supervisor/logs/managed-001.log",
                last_event_at=NOW.isoformat(),
                age_seconds=30,
                status="done",
                reason="worker 已完成",
                managed=True,
                managed_name="worker-a",
                managed_backend="process",
                supervisor_status="done",
                supervisor_summary="worker 已完成入口和测试。",
                supervisor_next="主控 Codex 审查 diff 后合并。",
            ),
        ),
    )
    suggestions = _advice_payload(report, include_all_managed=True)["command_suggestions"]
    worker_reviews = {
        "status": "ok",
        "decision_summary": {
            "merge_candidates": 1,
            "continue_or_split_tasks": 0,
            "missing_worktrees": 0,
            "needs_fresh_review": 1,
        },
        "automation_candidates": {
            "review_then_merge": [
                {
                    "record_id": "managed-001",
                    "name": "worker-a",
                    "cwd": EXISTING_WORKSPACE,
                    "branch": "worker/a",
                    "recommendation": "review_then_merge_candidate",
                    "risk_level": "medium",
                    "reason": "worker 已完成且有本地改动；建议先复查 diff。",
                    "next_actions": ["review_diff", "run_tests"],
                    "validation_commands": ["pytest tests -q"],
                    "reviewer_command": "codex exec -C /repo 'review'",
                }
            ],
        },
        "workers": [
            {
                "name": "worker-a",
                "cwd": EXISTING_WORKSPACE,
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

    messages = build_llm_action_messages(
        report,
        suggestions,
        worker_reviews=worker_reviews,
    )
    payload = json.loads(messages[1]["content"])

    assert payload["worker_reviews"]["workers"][0]["next_decision"][
        "recommendation"
    ] == "review_then_merge_candidate"
    assert payload["worker_reviews"]["automation_candidates"]["review_then_merge"][
        0
    ]["record_id"] == "managed-001"
    assert payload["worker_reviews"]["safety"]["auto_merge"] is False
    assert "merge" not in payload["allowed_kinds"]
    assert "worker_reviews 提供下一轮决策上下文" in "".join(
        payload["action_rules"]
    )



def test_codex_supervisor_generate_llm_action_rejects_merge_even_with_worker_review_context():
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="done-session",
                cwd=EXISTING_WORKSPACE,
                source_path="/home/lumber/.codex/sessions/done.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=30,
                status="done",
                reason="worker 已完成",
                supervisor_status="done",
            ),
        ),
    )
    suggestions = _advice_payload(report, include_all_managed=True)["command_suggestions"]
    worker_reviews = {
        "status": "ok",
        "decision_summary": {"merge_candidates": 1},
        "workers": [
            {
                "name": "worker-a",
                "next_decision": {
                    "recommendation": "review_then_merge_candidate",
                    "merge_suitable": True,
                },
            }
        ],
        "safety": {"auto_merge": False},
    }

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"worker_reviews"' in content
            assert '"merge_suitable": true' in content
            return json.dumps(
                {
                    "kind": "merge_worker",
                    "target_name": "worker-a",
                    "reason": "模型错误地把 review context 当成合并授权。",
                },
                ensure_ascii=False,
            )

    with pytest.raises(ValueError, match="unsupported LLM action"):
        generate_llm_action_decision(
            report,
            suggestions,
            DeterministicProvider(),
            worker_reviews=worker_reviews,
        )



def test_codex_supervisor_llm_action_messages_include_resume_context_size_hint():
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="active-session",
                cwd=EXISTING_WORKSPACE,
                source_path="/home/lumber/.codex/sessions/active.jsonl",
                source_size_bytes=92178,
                last_event_at=NOW.isoformat(),
                age_seconds=30,
                status="working",
                reason="仍在处理 Supervisor 任务",
            ),
        ),
    )
    suggestions = _advice_payload(report, include_all_managed=True)["command_suggestions"]

    messages = build_llm_action_messages(report, suggestions)

    assert '"source_size_bytes": 92178' in messages[1]["content"]
    assert '"resume_context_hint": "large_session_file"' in messages[1]["content"]
    assert "恢复前优先考虑 request_context 或 launch_session" in messages[1]["content"]



def test_codex_supervisor_llm_action_skips_done_resume_candidates():
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="done-session",
                cwd=EXISTING_WORKSPACE,
                source_path="/home/lumber/.codex/sessions/done.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=30,
                status="done",
                reason="上一批工作已完成",
                supervisor_status="done",
                supervisor_summary="已完成。",
                supervisor_next="等待归档。",
            ),
            CodexSessionSummary(
                session_id="stale-session",
                cwd=EXISTING_WORKSPACE,
                source_path="/home/lumber/.codex/sessions/stale.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=900,
                status="stale",
                reason="超过 10 分钟没有新事件",
            ),
        ),
    )

    suggestions = _advice_payload(report, include_all_managed=True)["command_suggestions"]
    messages = build_llm_action_messages(report, suggestions)

    suggestion_text = json.dumps(suggestions, ensure_ascii=False)
    assert "done-session" not in suggestion_text
    assert "stale-session" in suggestion_text
    assert '"session_id": "done-session"' not in messages[1]["content"]
    assert '"session_id": "stale-session"' in messages[1]["content"]



def test_codex_supervisor_llm_action_offers_workspace_actions_after_done_session():
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="done-session",
                cwd=EXISTING_WORKSPACE,
                source_path="/home/lumber/.codex/sessions/done.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=30,
                status="done",
                reason="上一批工作已完成",
                supervisor_status="done",
                supervisor_summary="测试已通过。",
                supervisor_next="可以继续下一步。",
            ),
        ),
    )

    suggestions = _advice_payload(report, include_all_managed=True)["command_suggestions"]
    messages = build_llm_action_messages(report, suggestions)

    kinds = [suggestion["kind"] for suggestion in suggestions]
    assert "resume_session" not in kinds
    assert "request_context" in kinds
    assert "launch_session" in kinds
    assert '"kind": "request_context"' in messages[1]["content"]
    assert '"kind": "launch_session"' in messages[1]["content"]



def test_codex_supervisor_llm_action_messages_explain_done_sessions_are_not_resumable():
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="done-session",
                cwd="/home/lumber/Github/isotope",
                source_path="/home/lumber/.codex/sessions/done.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=30,
                status="done",
                reason="上一批工作已完成",
                supervisor_status="done",
                supervisor_summary="测试已通过。",
                supervisor_next="可以继续下一步。",
            ),
        ),
    )
    suggestions = _advice_payload(report, include_all_managed=True)["command_suggestions"]

    messages = build_llm_action_messages(report, suggestions)

    content = messages[1]["content"]
    assert '"resumable_session_ids": []' in content
    assert '"completed_session_ids": ["done-session"]' in content
    assert "recommendation.target_session_id 是状态线索" in content
    assert "resumable_session_ids；列表为空时选择 request_context" in content



def test_codex_supervisor_llm_action_messages_resumable_ids_follow_command_whitelist():
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="working-session",
                cwd="/home/lumber/Github/isotope",
                source_path="/home/lumber/.codex/sessions/working.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=30,
                status="working",
                reason="当前窗口仍在工作，但本轮没有 resume 白名单命令。",
            ),
        ),
    )
    suggestions = [
        {
            "kind": "request_context",
            "cwd": "/home/lumber/Github/isotope",
            "query": "Supervisor 目标队列",
            "command": "isotope-supervisor context --cwd /home/lumber/Github/isotope --query 'Supervisor 目标队列'",
        }
    ]

    messages = build_llm_action_messages(report, suggestions)

    content = messages[1]["content"]
    assert '"resumable_session_ids": []' in content
    assert '"session_id": "working-session"' not in content



def test_codex_supervisor_generate_llm_action_rejects_missing_workspace_not_in_whitelist(
    tmp_path,
):
    missing_workspace = tmp_path / "deleted-worktree"
    valid_workspace = tmp_path / "workspace"
    valid_workspace.mkdir()
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="stale-session",
                cwd=str(missing_workspace),
                source_path="/home/lumber/.codex/sessions/stale.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=900,
                status="stale",
                reason="历史 worktree 已删除。",
            ),
        ),
    )
    suggestions = [
        {
            "kind": "request_context",
            "cwd": str(valid_workspace),
            "query": "Supervisor 目标队列",
            "command": f"isotope-supervisor context --cwd {valid_workspace} --query 'Supervisor 目标队列'",
        }
    ]

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert str(missing_workspace) not in content
            return json.dumps(
                {
                    "kind": "request_context",
                    "cwd": str(missing_workspace),
                    "query": "错误旧路径",
                    "reason": "模型误选已删除 worktree。",
                },
                ensure_ascii=False,
            )

    with pytest.raises(ValueError, match="unknown workspace"):
        generate_llm_action_decision(report, suggestions, DeterministicProvider())



def test_codex_supervisor_llm_action_messages_explain_recent_context_should_not_repeat():
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="done-session",
                cwd="/home/lumber/Github/isotope",
                source_path="/home/lumber/.codex/sessions/done.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=30,
                status="done",
                reason="上一批工作已完成",
                supervisor_status="done",
            ),
        ),
    )
    suggestions = _advice_payload(report, include_all_managed=True)["command_suggestions"]

    messages = build_llm_action_messages(
        report,
        suggestions,
        recent_context_results=[
            {
                "cwd": "/home/lumber/Github/isotope",
                "query": "Supervisor 当前状态",
                "items": [{"path": "docs/current/status.md", "text": "已有状态"}],
            }
        ],
    )

    content = messages[1]["content"]
    assert '"context_request_history"' in content
    assert '"Supervisor 当前状态"' in content
    assert "context_request_history 记录已查过的 cwd/query 组合" in content
    assert "已有上下文足够时优先选择 launch_session、send_continue、send_status、ask_user 或 monitor" in content



def test_codex_supervisor_llm_action_messages_mark_active_goal_running_worker():
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="managed:managed-001",
                cwd="/home/lumber/Github/isotope/.worktrees/supervisor/goal-a-12345678",
                source_path="/home/lumber/.codex/supervisor/logs/managed-001.log",
                last_event_at=NOW.isoformat(),
                age_seconds=15,
                status="working",
                reason="Supervisor 托管进程已启动",
                managed=True,
                managed_name="goal-a",
                managed_backend="process",
            ),
        ),
    )
    active_goals = [
        {
            "goal_id": "goal-a",
            "goal": "只读检查 Supervisor 日常入口。",
            "cwd": "/home/lumber/Github/isotope",
            "target_name": "goal-a",
        }
    ]

    advice = _advice_payload(
        report,
        include_all_managed=True,
        active_goals=active_goals,
    )
    messages = build_llm_action_messages(
        report,
        advice["command_suggestions"],
        active_goals=active_goals,
    )
    payload = json.loads(messages[1]["content"])

    assert payload["active_goals"][0]["target_name"] == "goal-a"
    assert payload["active_goals"][0]["worker_status"] == "working"
    assert payload["active_goals"][0]["worker_session_id"] == "managed:managed-001"
    assert "同名 worker 已在运行时，根据 worker_status 选择" in "".join(
        payload["action_rules"]
    )
    assert not any(
        suggestion.get("kind") == "launch_session"
        and suggestion.get("target_name") == "goal-a"
        for suggestion in advice["command_suggestions"]
    )



def test_codex_supervisor_llm_action_messages_prefer_monitor_for_running_active_goal(
    tmp_path,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    goal = "推进已经启动的 active goal。"
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="managed:goal-a",
                cwd=str(workspace),
                source_path="/home/lumber/.codex/supervisor/logs/goal-a.log",
                last_event_at=NOW.isoformat(),
                age_seconds=15,
                status="working",
                reason="active goal worker 正在运行",
                managed=True,
                managed_name="goal-a",
                managed_backend="process",
            ),
        ),
    )
    messages = build_llm_action_messages(
        report,
        [
            {
                "kind": "request_context",
                "cwd": str(workspace),
                "query": goal,
                "command": f"isotope-supervisor context --cwd {workspace} --query {shlex.quote(goal)}",
            },
            {
                "kind": "launch_session",
                "target_name": "goal-a",
                "cwd": str(workspace),
                "prompt": goal,
                "command": f"isotope-supervisor launch --name goal-a --cwd {workspace} --prompt {shlex.quote(goal)}",
            },
        ],
        active_goals=[
            {
                "goal_id": "goal-a",
                "goal": goal,
                "cwd": str(workspace),
                "target_name": "goal-a",
            }
        ],
    )
    payload = json.loads(messages[1]["content"])

    assert payload["planner_priority"][0]["kind"] == "monitor"
    assert payload["planner_priority"][0]["reason"] == "running_worker"
    assert payload["command_suggestions"] == []
    assert "已有 active goal worker 正在运行时优先 monitor 或等待下一轮" in "".join(
        payload["action_rules"]
    )



def test_codex_supervisor_llm_action_messages_prioritize_context_for_blocked_goal(
    tmp_path,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    goal = "修复 blocked goal 的上下文优先级。"
    messages = build_llm_action_messages(
        CodexSupervisorReport(generated_at=NOW.isoformat(), sessions=()),
        [
            {
                "kind": "request_context",
                "cwd": str(workspace),
                "query": goal,
                "command": (
                    f"isotope-supervisor context --cwd {workspace} "
                    f"--query {shlex.quote(goal)}"
                ),
            },
            {
                "kind": "launch_session",
                "target_name": "blocked-worker",
                "cwd": str(workspace),
                "prompt": goal,
                "command": (
                    f"isotope-supervisor launch --name blocked-worker "
                    f"--cwd {workspace} --prompt {shlex.quote(goal)}"
                ),
            },
        ],
        active_goals=[
            {
                "goal_id": "goal-blocked",
                "goal": goal,
                "cwd": str(workspace),
                "target_name": "blocked-worker",
                "last_status": "blocked",
                "last_summary": "worker 缺少上下文。",
                "last_next": "先查相关文档。",
            }
        ],
    )
    payload = json.loads(messages[1]["content"])

    assert payload["blocked_context_priority"] == [
        {
            "kind": "request_context",
            "reason": "context_first_for_blocked_goal",
            "goal_id": "goal-blocked",
            "target_name": "blocked-worker",
            "cwd": str(workspace),
            "query": goal,
            "message": "blocked/needs_user 目标缺上下文时先检索，再判断是否 ask_user。",
        }
    ]
    assert "blocked/needs_user 目标缺少上下文时优先 request_context" in "".join(
        payload["action_rules"]
    )



def test_codex_supervisor_llm_action_messages_include_capacity_decisions(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    decision = {
        "kind": "supervisor_capacity_decision",
        "next_action": "request_input",
        "reason": "needs_input",
        "capacity_id": "supervisor.request_context",
        "can_execute_agent_loop": False,
        "missing_inputs": ["state_root", "cwd", "query"],
        "blocking_reasons": [],
    }

    messages = build_llm_action_messages(
        CodexSupervisorReport(generated_at=NOW.isoformat(), sessions=()),
        [
            {
                "kind": "request_context",
                "cwd": str(workspace),
                "query": "补齐上下文输入",
                "command": (
                    f"isotope-supervisor context --cwd {workspace} "
                    "--query 补齐上下文输入"
                ),
            }
        ],
        capacity_decisions=[decision],
    )
    payload = json.loads(messages[1]["content"])

    assert payload["capacity_decisions"] == [decision]
    assert "capacity_decisions" in "".join(payload["action_rules"])



def test_codex_supervisor_llm_action_messages_prefer_monitor_for_running_merge_worker(
    tmp_path,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="managed:merge",
                cwd=str(workspace),
                source_path="/home/lumber/.codex/supervisor/logs/merge.log",
                last_event_at=NOW.isoformat(),
                age_seconds=15,
                status="working",
                reason="merge dispatch worker 正在运行",
                managed=True,
                managed_name=DEFAULT_TARGET_NAME,
                managed_backend="process",
            ),
        ),
    )
    messages = build_llm_action_messages(
        report,
        [
            {
                "kind": "request_context",
                "cwd": str(workspace),
                "query": "integration review",
                "command": f"isotope-supervisor context --cwd {workspace} --query 'integration review'",
            },
            {
                "kind": "launch_session",
                "target_name": DEFAULT_TARGET_NAME,
                "cwd": str(workspace),
                "prompt": "合并 ready workers。",
                "command": f"isotope-supervisor launch --name {DEFAULT_TARGET_NAME} --cwd {workspace} --prompt '合并 ready workers。'",
            },
        ],
    )
    payload = json.loads(messages[1]["content"])

    assert payload["planner_priority"][0]["kind"] == "monitor"
    assert payload["planner_priority"][0]["reason"] == "running_merge_worker"
    assert payload["command_suggestions"] == []
    assert "已有 merge dispatch worker 正在运行时优先 monitor 或等待下一轮" in "".join(
        payload["action_rules"]
    )



def test_codex_supervisor_generate_llm_action_decision_accepts_whitelisted_json():
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
    suggestions = _advice_payload(report, include_all_managed=True)["command_suggestions"]

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            assert "send_continue" in messages[1]["content"]
            return json.dumps(
                {
                    "kind": "send_continue",
                    "target_name": "lane-a",
                    "reason": "托管窗口还在运行，可以继续推进。",
                },
                ensure_ascii=False,
            )

    decision = generate_llm_action_decision(report, suggestions, DeterministicProvider())

    assert decision == {
        "kind": "send_continue",
        "target_name": "lane-a",
        "reason": "托管窗口还在运行，可以继续推进。",
        "command_suggestion": {
            "command": _supervisor_send_command("lane-a", CONTINUE_REQUEST_TEXT),
            "kind": "send_continue",
            "label": "让托管 Codex 继续推进",
        },
    }



def test_codex_supervisor_generate_llm_action_decision_accepts_resume_session():
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="019e35a2-e442-75e2-84ab-3761a685a736",
                cwd=EXISTING_WORKSPACE,
                source_path="/home/lumber/.codex/sessions/rollout.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=900,
                status="stale",
                reason="超过 10 分钟没有新事件",
            ),
        ),
    )
    suggestions = _advice_payload(report, include_all_managed=True)["command_suggestions"]

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"can_resume": true' in content
            assert '"session_id": "019e35a2-e442-75e2-84ab-3761a685a736"' in content
            return json.dumps(
                {
                        "kind": "resume_session",
                        "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
                        "prompt_kind": "send_continue",
                        "reason": "历史会话长时间没有新事件，恢复后继续推进。",
                },
                ensure_ascii=False,
            )

    decision = generate_llm_action_decision(report, suggestions, DeterministicProvider())

    assert decision == {
        "kind": "resume_session",
        "target_name": "resume-019e35a2",
        "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
        "prompt_kind": "send_continue",
        "reason": "历史会话长时间没有新事件，恢复后继续推进。",
        "command_suggestion": {
            "command": (
                "isotope-supervisor resume --name resume-019e35a2 "
                f"--cwd {EXISTING_WORKSPACE} "
                "--session-id 019e35a2-e442-75e2-84ab-3761a685a736 "
                f"--prompt {shlex.quote(CONTINUE_REQUEST_TEXT)}"
            ),
            "kind": "resume_session",
            "label": "恢复 Codex 历史会话并继续推进",
            "prompt_kind": "send_continue",
            "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
            "target_name": "resume-019e35a2",
        },
    }



def test_codex_supervisor_generate_llm_action_decision_accepts_launch_session():
    launch_prompt = (
        "请阅读 docs/current/status.md，继续梳理 Supervisor 下一步，并在完成后"
        "按 SUPERVISOR_STATUS/SUMMARY/NEXT 汇报。"
    )
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="019e35a2-e442-75e2-84ab-3761a685a736",
                cwd=EXISTING_WORKSPACE,
                source_path="/home/lumber/.codex/sessions/rollout.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=30,
                status="done",
                reason="已有窗口已完成",
            ),
        ),
    )
    suggestions = _advice_payload(report, include_all_managed=True)["command_suggestions"]

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"kind": "launch_session"' in content
            assert f'"available_workspaces": ["{EXISTING_WORKSPACE}"]' in content
            return json.dumps(
                {
                    "kind": "launch_session",
                    "target_name": "planner-docs",
                    "cwd": EXISTING_WORKSPACE,
                    "prompt": launch_prompt,
                    "reason": "需要单独开新会话推进文档整理。",
                },
                ensure_ascii=False,
            )

    decision = generate_llm_action_decision(report, suggestions, DeterministicProvider())

    assert decision == {
        "kind": "launch_session",
        "target_name": "planner-docs",
        "cwd": EXISTING_WORKSPACE,
        "prompt": launch_prompt,
        "reason": "需要单独开新会话推进文档整理。",
        "command_suggestion": {
            "command": (
                "isotope-supervisor launch --name planner-docs "
                f"--cwd {EXISTING_WORKSPACE} "
                f"--prompt {shlex.quote(launch_prompt)}"
            ),
            "kind": "launch_session",
            "label": "启动新的 Codex 托管会话",
            "target_name": "planner-docs",
            "cwd": EXISTING_WORKSPACE,
            "prompt": launch_prompt,
        },
    }



def test_codex_supervisor_generate_llm_action_decision_passes_capacity_decisions():
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(),
    )
    suggestions = [
        {
            "kind": "request_context",
            "cwd": EXISTING_WORKSPACE,
            "query": "补齐 capacity 输入",
            "command": (
                "isotope-supervisor context "
                f"--cwd {EXISTING_WORKSPACE} --query 补齐 capacity 输入"
            ),
        }
    ]
    decision = {
        "kind": "supervisor_capacity_decision",
        "next_action": "request_input",
        "reason": "needs_input",
        "capacity_id": "supervisor.request_context",
        "can_execute_agent_loop": False,
        "missing_inputs": ["state_root", "cwd", "query"],
        "blocking_reasons": [],
    }

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"capacity_decisions"' in content
            assert '"next_action": "request_input"' in content
            return json.dumps(
                {
                    "kind": "request_context",
                    "cwd": EXISTING_WORKSPACE,
                    "query": "补齐 capacity 输入",
                    "reason": "capacity decision 缺少输入，先检索上下文。",
                },
                ensure_ascii=False,
            )

    result = generate_llm_action_decision(
        report,
        suggestions,
        DeterministicProvider(),
        capacity_decisions=[decision],
    )

    assert result["kind"] == "request_context"
    assert result["query"] == "补齐 capacity 输入"



def test_codex_supervisor_parser_accepts_capacity_decisions_for_loop_and_supervise():
    parser = supervisor_runner._build_parser()

    loop_args = parser.parse_args(["loop", "--capacity-decisions"])
    supervise_args = parser.parse_args(["supervise", "--capacity-decisions"])

    assert loop_args.capacity_decisions is True
    assert supervise_args.capacity_decisions is True



def test_codex_supervisor_generate_llm_action_decision_accepts_call_capacity(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    report = CodexSupervisorReport(generated_at=NOW.isoformat(), sessions=())
    suggestions = [
        {
            "kind": "request_context",
            "cwd": str(workspace),
            "query": "capacity",
            "command": f"isotope-supervisor context --cwd {workspace} --query capacity",
        }
    ]
    decision = {
        "kind": "supervisor_capacity_decision",
        "next_action": "call_capacity",
        "reason": "ready",
        "capacity_id": "artifact.review",
        "can_execute_agent_loop": True,
        "missing_inputs": [],
        "blocking_reasons": [],
    }

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"call_capacity"' in content
            assert '"capacity_id": "artifact.review"' in content
            return json.dumps(
                {
                    "kind": "call_capacity",
                    "capacity_id": "artifact.review",
                    "reason": "capacity plan 已 ready，调用能力。",
                },
                ensure_ascii=False,
            )

    result = generate_llm_action_decision(
        report,
        suggestions,
        DeterministicProvider(),
        capacity_decisions=[decision],
    )

    assert result == {
        "kind": "call_capacity",
        "target_name": None,
        "capacity_id": "artifact.review",
        "reason": "capacity plan 已 ready，调用能力。",
        "command_suggestion": None,
    }



def test_codex_supervisor_execute_llm_action_dispatches_call_capacity(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    report = CodexSupervisorReport(generated_at=NOW.isoformat(), sessions=())
    action = {
        "kind": "call_capacity",
        "capacity_id": "artifact.review",
        "reason": "capacity plan 已 ready，调用能力。",
        "command_suggestion": None,
    }
    payload = {
        "llm_action": action,
        "capacity_call_specs": [
            {
                "capacity_id": "artifact.review",
                "goal": "检查 artifact review 能力。",
                "inputs": {},
            }
        ],
    }
    captured: dict[str, object] = {}

    def stub_execute_capacity_action(args: object, action: dict[str, object], payload):
        captured["action"] = action
        captured["payload"] = payload
        return {
            "kind": "call_capacity",
            "capacity_id": "artifact.review",
            "agent_loop": {"executed": True},
        }

    monkeypatch.setattr(
        "isotope.features.supervisor.runner._execute_capacity_action",
        stub_execute_capacity_action,
        raising=False,
    )

    result = _execute_llm_action(_runner_args(codex_home), report, payload)

    assert result == {
        "kind": "call_capacity",
        "capacity_id": "artifact.review",
        "agent_loop": {"executed": True},
    }
    assert captured["action"] == action
    assert captured["payload"] == payload



def test_codex_supervisor_generate_llm_action_decision_can_launch_named_suggestion_without_prompt():
    goal = "为 Supervisor 增加目标规划入口，并补测试。"
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(),
    )
    suggestions = _advice_payload(
        report,
        include_all_managed=True,
        active_goals=[
            {
                "goal_id": "goal-123",
                "goal": goal,
                "cwd": EXISTING_WORKSPACE,
                "target_name": "supervisor-goal-planner",
            }
        ],
    )["command_suggestions"]

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert "可以输出 target_name 和 reason" in content
            return json.dumps(
                {
                    "kind": "launch_session",
                    "target_name": "supervisor-goal-planner",
                    "reason": "直接启动目标队列里的 worker。",
                },
                ensure_ascii=False,
            )

    decision = generate_llm_action_decision(report, suggestions, DeterministicProvider())

    assert decision["kind"] == "launch_session"
    assert decision["target_name"] == "supervisor-goal-planner"
    assert decision["cwd"] == EXISTING_WORKSPACE
    assert decision["prompt"] == goal
    assert decision["command_suggestion"]["target_name"] == "supervisor-goal-planner"



def test_codex_supervisor_generate_llm_action_decision_accepts_action_alias_for_kind():
    launch_prompt = "请推进 Search/RAG 检索升级。"
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="source-session",
                cwd=EXISTING_WORKSPACE,
                source_path="/tmp/source.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=60,
                status="working",
                reason="最近仍有事件",
            ),
        ),
    )
    suggestions = _advice_payload(report, include_all_managed=True)["command_suggestions"]

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return json.dumps(
                {
                    "action": "launch_session",
                    "target_name": "search-rag-bm25",
                    "cwd": EXISTING_WORKSPACE,
                    "prompt": launch_prompt,
                    "reason": "检索后继续启动 Search/RAG worker。",
                },
                ensure_ascii=False,
            )

    decision = generate_llm_action_decision(report, suggestions, DeterministicProvider())

    assert decision["kind"] == "launch_session"
    assert decision["target_name"] == "search-rag-bm25"
    assert decision["prompt"] == launch_prompt



def test_codex_supervisor_generate_llm_action_decision_rejects_running_target_launch():
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="managed:managed-001",
                cwd="/home/lumber/Github/isotope/.worktrees/supervisor/goal-a-12345678",
                source_path="/home/lumber/.codex/supervisor/logs/managed-001.log",
                last_event_at=NOW.isoformat(),
                age_seconds=15,
                status="working",
                reason="Supervisor 托管进程已启动",
                managed=True,
                managed_name="goal-a",
                managed_backend="process",
            ),
        ),
    )
    active_goals = [
        {
            "goal_id": "goal-a",
            "goal": "只读检查 Supervisor 日常入口。",
            "cwd": "/home/lumber/Github/isotope",
            "target_name": "goal-a",
        }
    ]
    suggestions = _advice_payload(
        report,
        include_all_managed=True,
        active_goals=active_goals,
    )["command_suggestions"]

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return json.dumps(
                {
                    "kind": "launch_session",
                    "target_name": "goal-a",
                    "cwd": "/home/lumber/Github/isotope",
                    "prompt": "继续做同一个目标。",
                    "reason": "错误地重复启动同名 worker。",
                },
                ensure_ascii=False,
            )

    with pytest.raises(ValueError, match="running managed worker"):
        generate_llm_action_decision(
            report,
            suggestions,
            DeterministicProvider(),
            active_goals=active_goals,
        )



def test_codex_supervisor_generate_llm_action_decision_accepts_launch_worker_profile():
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="019e35a2-e442-75e2-84ab-3761a685a736",
                cwd=EXISTING_WORKSPACE,
                source_path="/home/lumber/.codex/sessions/rollout.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=30,
                status="done",
                reason="已有窗口已完成",
            ),
        ),
    )
    suggestions = _advice_payload(report, include_all_managed=True)["command_suggestions"]

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"worker_profiles"' in content
            assert '"light"' in content
            return json.dumps(
                {
                    "kind": "launch_session",
                    "target_name": "quick-smoke",
                    "cwd": EXISTING_WORKSPACE,
                    "prompt": "只读检查当前状态并输出三行状态协议。",
                    "worker_profile": "light",
                    "reason": "只读 smoke 不需要高推理代码档。",
                },
                ensure_ascii=False,
            )

    decision = generate_llm_action_decision(report, suggestions, DeterministicProvider())

    assert decision["kind"] == "launch_session"
    assert decision["target_name"] == "quick-smoke"
    assert decision["worker_profile"] == "light"
    assert decision["command_suggestion"]["worker_profile"] == "light"



def test_codex_supervisor_generate_llm_action_decision_accepts_request_context():
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="019e35a2-e442-75e2-84ab-3761a685a736",
                cwd=EXISTING_WORKSPACE,
                source_path="/home/lumber/.codex/sessions/rollout.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=30,
                status="done",
                reason="已有窗口已完成",
            ),
        ),
    )
    suggestions = _advice_payload(report, include_all_managed=True)["command_suggestions"]

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"context_capability"' in content
            assert '"kind": "request_context"' in content
            return json.dumps(
                {
                    "kind": "request_context",
                    "cwd": EXISTING_WORKSPACE,
                    "query": "Supervisor 下一步节奏",
                    "reason": "需要先查项目当前说明再决定。",
                },
                ensure_ascii=False,
            )

    decision = generate_llm_action_decision(report, suggestions, DeterministicProvider())

    assert decision == {
        "kind": "request_context",
        "target_name": None,
        "cwd": EXISTING_WORKSPACE,
        "query": "Supervisor 下一步节奏",
        "reason": "需要先查项目当前说明再决定。",
        "command_suggestion": {
            "command": (
                f"isotope-supervisor context --cwd {EXISTING_WORKSPACE} "
                "--query 'Supervisor 下一步节奏'"
            ),
            "kind": "request_context",
            "label": "检索项目上下文",
            "cwd": EXISTING_WORKSPACE,
            "query": "Supervisor 下一步节奏",
        },
    }



def test_codex_supervisor_generate_llm_action_decision_rejects_ask_user_without_codex_request():
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="019e35a2-e442-75e2-84ab-3761a685a736",
                cwd=EXISTING_WORKSPACE,
                source_path="/home/lumber/.codex/sessions/rollout.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=30,
                status="done",
                reason="已有窗口已完成",
                supervisor_status="done",
                supervisor_summary="测试已通过。",
                supervisor_next="可以继续下一步。",
            ),
        ),
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return json.dumps(
                {
                    "kind": "ask_user",
                    "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
                    "question": "是否继续下一步？",
                    "codex_requested_decision": True,
                    "instructions_exhausted": True,
                    "context_status": "missing",
                    "reason": "测试 gate。",
                },
                ensure_ascii=False,
            )

    with pytest.raises(ValueError, match="ask_user requires a Codex decision request"):
        generate_llm_action_decision(
            report,
            _advice_payload(report)["command_suggestions"],
            DeterministicProvider(),
            recent_context_results=[
                {
                    "cwd": "/home/lumber/Github/isotope",
                    "query": "是否继续下一步",
                    "items": [],
                }
            ],
        )



def test_codex_supervisor_generate_llm_action_decision_rejects_ask_user_before_context_check():
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="019e35a2-e442-75e2-84ab-3761a685a736",
                cwd="/home/lumber/Github/isotope",
                source_path="/home/lumber/.codex/sessions/rollout.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=30,
                status="needs_user",
                reason="等待用户确认",
                supervisor_status="needs_user",
                supervisor_summary="实现路径有 A/B 两种。",
                supervisor_next="请用户拍板选择 A 还是 B。",
            ),
        ),
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return json.dumps(
                {
                    "kind": "ask_user",
                    "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
                    "question": "选择 A 还是 B？",
                    "codex_requested_decision": True,
                    "instructions_exhausted": True,
                    "context_status": "missing",
                    "reason": "上下文还没查。",
                },
                ensure_ascii=False,
            )

    with pytest.raises(ValueError, match="ask_user requires a context check"):
        generate_llm_action_decision(
            report,
            _advice_payload(report)["command_suggestions"],
            DeterministicProvider(),
            recent_context_results=[],
        )



def test_codex_supervisor_generate_llm_action_decision_accepts_ask_user_after_gate():
    report = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(
            CodexSessionSummary(
                session_id="019e35a2-e442-75e2-84ab-3761a685a736",
                cwd="/home/lumber/Github/isotope",
                source_path="/home/lumber/.codex/sessions/rollout.jsonl",
                last_event_at=NOW.isoformat(),
                age_seconds=30,
                status="needs_user",
                reason="等待用户确认",
                supervisor_status="needs_user",
                supervisor_summary="目录迁移有两种不可兼容方案。",
                supervisor_next="请用户拍板选择先兼容还是直接迁移。",
            ),
        ),
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"decision_gate"' in content
            assert '"recent_context_results"' in content
            return json.dumps(
                {
                    "kind": "ask_user",
                    "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
                    "question": "目录迁移是先保留兼容层，还是直接迁移并删除旧入口？",
                    "codex_requested_decision": True,
                    "instructions_exhausted": True,
                    "context_status": "conflict",
                    "reason": "Codex 明确要拍板，既有指示无法覆盖，文档与现状冲突。",
                },
                ensure_ascii=False,
            )

    decision = generate_llm_action_decision(
        report,
        _advice_payload(report)["command_suggestions"],
        DeterministicProvider(),
        recent_context_results=[
            {
                "cwd": "/home/lumber/Github/isotope",
                "query": "目录迁移 兼容层",
                "items": [
                    {
                        "path": "docs/current/status.md",
                        "line": 1,
                        "text": "旧文档要求保留兼容层，但现有代码已删除旧入口。",
                        "score": 10,
                    }
                ],
            }
        ],
    )

    assert decision == {
        "kind": "ask_user",
        "target_name": "resume-019e35a2",
        "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
        "question": "目录迁移是先保留兼容层，还是直接迁移并删除旧入口？",
        "context_status": "conflict",
        "codex_requested_decision": True,
        "instructions_exhausted": True,
        "reason": "Codex 明确要拍板，既有指示无法覆盖，文档与现状冲突。",
        "command_suggestion": None,
    }



def test_codex_supervisor_generate_llm_action_decision_extracts_noisy_json():
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
    suggestions = _advice_payload(report)["command_suggestions"]

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return (
                "我会按这个格式返回：{\"kind\":\"monitor\"}\n"
                "```json\n"
                "{\"kind\":\"send_status\",\"target_name\":\"lane-a\",\"reason\":\"先让它按协议汇报。\"}\n"
                "```"
            )

    decision = generate_llm_action_decision(report, suggestions, DeterministicProvider())

    assert decision["kind"] == "send_status"
    assert decision["target_name"] == "lane-a"
    assert decision["reason"] == "先让它按协议汇报。"



def test_codex_supervisor_generate_llm_action_decision_reports_raw_excerpt_for_non_json():
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
    suggestions = _advice_payload(report)["command_suggestions"]

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return "我需要更多上下文，暂时不能决定。"

    with pytest.raises(ValueError, match="raw=我需要更多上下文"):
        generate_llm_action_decision(report, suggestions, DeterministicProvider())



def test_codex_supervisor_generate_llm_action_decision_rejects_unsupported_action():
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
    suggestions = _advice_payload(report)["command_suggestions"]

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return '{"kind":"delete_branch","reason":"危险动作"}'

    with pytest.raises(ValueError, match="unsupported LLM action"):
        generate_llm_action_decision(report, suggestions, DeterministicProvider())



def test_codex_supervisor_generate_llm_action_decision_falls_back_without_targets():
    report = CodexSupervisorReport(generated_at=NOW.isoformat(), sessions=())

    class FailingProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            raise AssertionError("LLM should not be called without managed targets")

    decision = generate_llm_action_decision(report, [], FailingProvider())

    assert decision == {
        "kind": "monitor",
        "target_name": None,
        "reason": "当前没有可控的 Supervisor 目标，先继续监控。",
        "command_suggestion": None,
    }



