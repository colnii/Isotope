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

def test_codex_supervisor_plain_report_is_human_readable(tmp_path):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-attention.jsonl",
        session_id="attention-session",
        cwd="/home/lumber/Github/isotope",
        events=[
            _user_message("2026-05-16T11:50:00Z", "好，下一步"),
            _assistant_message("2026-05-16T11:58:00Z", "需要你确认是否继续。"),
        ],
    )

    flow = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW)
    text = render_plain_report(flow.scan(limit=5))

    assert "[Codex Supervisor]" in text
    assert "attention-session" in text
    assert "状态：等待用户" in text
    assert "最近用户：好，下一步" in text
    assert "依据：文本命中等待用户 - 最近回复包含确认类表达" in text
    assert "建议：先处理等待用户确认的窗口。" in text



def test_codex_supervisor_report_includes_structured_action_recommendation(tmp_path):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-attention.jsonl",
        session_id="attention-session",
        cwd="/home/lumber/Github/isotope",
        events=[
            _assistant_message("2026-05-16T11:58:00Z", "需要你确认是否继续。"),
        ],
    )

    report = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW).scan(limit=5)
    payload = report.to_dict()

    assert payload["recommendation"] == {
        "action": "review_user_prompt",
        "label": "先处理等待用户确认的窗口。",
        "priority": "high",
        "reason": "最近回复像是在等待用户确认",
        "target_name": None,
        "target_session_id": "attention-session",
        "send_text": None,
    }
    assert render_plain_report(report).endswith("建议：先处理等待用户确认的窗口。")



def test_codex_supervisor_report_recommends_monitor_when_no_attention(tmp_path):
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

    payload = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW).scan().to_dict()

    assert payload["recommendation"] == {
        "action": "monitor",
        "label": "当前没有明显需要介入的窗口。",
        "priority": "low",
        "reason": None,
        "target_name": None,
        "target_session_id": None,
        "send_text": None,
    }



def test_codex_supervisor_report_serializes_to_json_shape(tmp_path):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-active.jsonl",
        session_id="active-session",
        cwd="/home/lumber/Github/isotope",
        events=[
            _assistant_message("2026-05-16T11:59:20Z", "正在读文件。")
        ],
    )

    payload = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW).scan().to_dict()

    assert payload["status"] == "ok"
    assert payload["summary"]["total"] == 1
    assert payload["sessions"][0]["session_id"] == "active-session"
    assert payload["sessions"][0]["status_label"] == "工作中"
    assert payload["sessions"][0]["status_evidence"]["source"] == "recent_event"



def test_codex_supervisor_scan_parses_supervisor_status_protocol(tmp_path):
    codex_home = tmp_path / ".codex"
    session_path = _write_session(
        codex_home,
        "2026/05/16/rollout-status.jsonl",
        session_id="status-session",
        cwd="/home/lumber/Github/isotope",
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "\n".join(
                    [
                        "已完成这一步。",
                        "SUPERVISOR_STATUS: done",
                        "SUPERVISOR_SUMMARY: 测试已经通过，等待用户审阅。",
                        "SUPERVISOR_NEXT: 等待用户确认后继续状态协议下一片。",
                    ]
                ),
            )
        ],
    )

    report = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW).scan()
    session = report.sessions[0]

    assert session.supervisor_status == "done"
    assert session.supervisor_summary == "测试已经通过，等待用户审阅。"
    assert session.supervisor_next == "等待用户确认后继续状态协议下一片。"
    assert session.source_size_bytes == session_path.stat().st_size
    assert session.to_dict()["source_size_bytes"] == session_path.stat().st_size
    assert session.to_dict()["supervisor_status"] == "done"
    assert "Supervisor 状态：done" in render_plain_report(report)
    messages = build_llm_summary_messages(report)
    assert '"supervisor_status": "done"' in messages[1]["content"]
    assert '"source": "supervisor_protocol"' in messages[1]["content"]
    assert "等待用户确认后继续状态协议下一片" in messages[1]["content"]



def test_codex_supervisor_protocol_status_overrides_stale_scan_status(tmp_path):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-done-status.jsonl",
        session_id="done-status-session",
        cwd="/home/lumber/Github/isotope",
        events=[
            _assistant_message(
                "2026-05-16T11:00:00Z",
                "\n".join(
                    [
                        "SUPERVISOR_STATUS: done",
                        "SUPERVISOR_SUMMARY: 测试已经通过，等待用户审阅。",
                        "SUPERVISOR_NEXT: 等待用户确认下一步。",
                    ]
                ),
            )
        ],
    )

    report = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW).scan()
    payload = report.to_dict()
    session = payload["sessions"][0]

    assert session["status"] == "done"
    assert session["status_label"] == "已完成"
    assert session["reason"] == "测试已经通过，等待用户审阅。"
    assert session["status_evidence"] == {
        "source": "supervisor_protocol",
        "label": "主动状态协议",
        "detail": "SUPERVISOR_STATUS: done",
    }
    assert payload["summary"]["counts"]["done"] == 1
    assert payload["summary"]["counts"]["stale"] == 0



def test_codex_supervisor_scan_ignores_status_protocol_template_in_event_output(tmp_path):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-template.jsonl",
        session_id="template-session",
        cwd="/home/lumber/Github/isotope",
        events=[
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {
                    "type": "agent_reasoning",
                    "message": "\n".join(
                        [
                            "提示模板：",
                            "SUPERVISOR_STATUS: working|done|blocked|needs_user",
                        ]
                    ),
                },
            )
        ],
    )

    report = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW).scan()
    session = report.sessions[0]

    assert session.supervisor_status is None
    assert session.status_evidence["source"] == "recent_event"



def test_codex_supervisor_scan_parses_thread_title_and_agent_name(tmp_path):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-titled.jsonl",
        session_id="019e2e4f-d541-72f1-9269-471aa50bc2f2",
        cwd="/home/lumber/Github/isotope",
        meta={
            "agent_nickname": "Curie",
            "agent_role": "worker",
        },
        events=[
            _event(
                "2026-05-16T11:58:20Z",
                "event_msg",
                {
                    "type": "thread_name_updated",
                    "thread_id": "019e2e4f-d541-72f1-9269-471aa50bc2f2",
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

    report = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW).scan()
    session = report.sessions[0]
    payload = session.to_dict()

    assert session.thread_name == "Supervisor页面"
    assert session.agent_nickname == "Curie"
    assert session.agent_role == "worker"
    assert session.short_session_id == "019e2e4f"
    assert session.display_title == "Supervisor页面"
    assert payload["thread_name"] == "Supervisor页面"
    assert payload["agent_nickname"] == "Curie"
    assert payload["agent_role"] == "worker"
    assert payload["display_title"] == "Supervisor页面"
    assert payload["short_session_id"] == "019e2e4f"



def test_codex_supervisor_scan_uses_session_index_title_when_jsonl_has_no_rename(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    session_id = "019e274b-d20a-7400-8502-d3923d5167c6"
    _write_session_index(codex_home, session_id=session_id, thread_name="项目重新整理")
    _write_session(
        codex_home,
        "2026/05/16/rollout-index-title.jsonl",
        session_id=session_id,
        cwd="/home/lumber/Github/isotope",
        events=[
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {"type": "agent_reasoning", "message": "running tests"},
            ),
        ],
    )

    report = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW).scan()
    session = report.sessions[0]

    assert session.thread_name == "项目重新整理"
    assert session.display_title == "项目重新整理"
    assert session.to_dict()["display_title"] == "项目重新整理"


def test_codex_supervisor_scan_prefers_session_index_title_over_jsonl_rename(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    session_id = "019dcdca-1d58-7f53-817d-003b9247b881"
    _write_session_index(codex_home, session_id=session_id, thread_name="RNA训练")
    _write_session(
        codex_home,
        "2026/04/27/rollout-rna-training.jsonl",
        session_id=session_id,
        cwd="/home/lumber/Github/AI_Camp_RNA_2026",
        events=[
            _event(
                "2026-05-16T11:58:20Z",
                "event_msg",
                {
                    "type": "thread_name_updated",
                    "thread_id": session_id,
                    "thread_name": "自动生成的很长研究任务标题",
                },
            ),
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {"type": "agent_reasoning", "message": "running tests"},
            ),
        ],
    )

    session = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW).scan().sessions[0]

    assert session.thread_name == "RNA训练"
    assert session.display_title == "RNA训练"



def test_codex_supervisor_scan_uses_state_thread_title_before_first_user_message(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    session_id = "019de9a7-3b74-7a33-a237-788ee37aff27"
    _write_state_threads(codex_home, session_id=session_id, title="Isotope Review")
    _write_session(
        codex_home,
        "2026/05/16/rollout-state-title.jsonl",
        session_id=session_id,
        cwd="/home/lumber/Github/isotope",
        events=[
            _event(
                "2026-05-16T11:45:00Z",
                "event_msg",
                {
                    "type": "thread_name_updated",
                    "thread_id": "019dcdd1-4845-77e0-ac0c-f6d36a9196e9",
                    "thread_name": "别的窗口标题",
                },
            ),
            _user_message("2026-05-16T11:50:00Z", "好，下一步"),
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {"type": "agent_reasoning", "message": "reading files"},
            ),
        ],
    )

    session = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW).scan().sessions[0]

    assert session.thread_name == "Isotope Review"
    assert session.display_title == "Isotope Review"



def test_codex_supervisor_display_title_shortens_long_state_title(tmp_path):
    codex_home = tmp_path / ".codex"
    session_id = "019e2dec-c400-70e1-ac70-abfa76dbd204"
    long_title = (
        "我的笔记本电脑在关机拔掉电源去公司或者回家再打开，有概率启动时电脑风扇不转动，"
        "导致电脑快速积热，CPU降频，能否帮我解决这个问题"
    )
    _write_state_threads(codex_home, session_id=session_id, title=long_title)
    _write_session(
        codex_home,
        "2026/05/16/rollout-long-title.jsonl",
        session_id=session_id,
        cwd="/home/lumber",
        events=[
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {"type": "agent_reasoning", "message": "reading files"},
            ),
        ],
    )

    payload = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW).scan().sessions[
        0
    ].to_dict()

    assert payload["thread_name"] == long_title
    assert payload["display_title"].endswith("…")
    assert len(payload["display_title"]) <= 48



def test_codex_supervisor_scan_uses_first_user_message_title_before_hash(tmp_path):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-first-message.jsonl",
        session_id="019e2dec-c400-70e1-ac70-abfa76dbd204",
        cwd="/home/lumber",
        events=[
            _user_message(
                "2026-05-16T11:50:00Z",
                "请继续整理项目结构，并先检查当前分支状态。",
            ),
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {"type": "agent_reasoning", "message": "reading files"},
            ),
        ],
    )

    session = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW).scan().sessions[0]

    assert session.display_title == "请继续整理项目结构，并先检查当前分支状态。"
    assert session.to_dict()["initial_user_title"] == "请继续整理项目结构，并先检查当前分支状态。"



def test_codex_supervisor_first_user_title_skips_context_noise(tmp_path):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-context-noise.jsonl",
        session_id="019e2ded-c400-70e1-ac70-abfa76dbd204",
        cwd="/home/lumber",
        events=[
            _user_message(
                "2026-05-16T11:45:00Z",
                "# AGENTS.md instructions for /home/lumber/Github/isotope\n<INSTRUCTIONS>...",
            ),
            _user_message("2026-05-16T11:50:00Z", "继续检查多个 Codex 窗口。"),
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {"type": "agent_reasoning", "message": "reading files"},
            ),
        ],
    )

    session = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW).scan().sessions[0]

    assert session.display_title == "继续检查多个 Codex 窗口。"



def test_codex_supervisor_scan_limits_recent_candidate_reads(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    recent_session_id = "019e2fff-0000-7000-8000-000000000000"
    for index in range(80):
        session_id = f"019e2f{index:02x}-0000-7000-8000-000000000000"
        _write_session_index(
            codex_home,
            session_id=session_id,
            thread_name=f"旧窗口 {index}",
            updated_at=f"2026-05-16T10:{index % 60:02d}:00Z",
        )
        path = _write_session(
            codex_home,
            f"2026/05/16/rollout-{index:02d}-{session_id}.jsonl",
            session_id=session_id,
            cwd="/home/lumber/Github/isotope",
            events=[_assistant_message("2026-05-16T10:00:00Z", "旧消息。")],
        )
        os.utime(path, (1_768_900_000 + index, 1_768_900_000 + index))
    _write_session_index(
        codex_home,
        session_id=recent_session_id,
        thread_name="最近窗口",
        updated_at="2026-05-16T11:59:20Z",
    )
    recent_path = _write_session(
        codex_home,
        f"2026/05/16/rollout-recent-{recent_session_id}.jsonl",
        session_id=recent_session_id,
        cwd="/home/lumber/Github/isotope",
        events=[
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {"type": "agent_reasoning", "message": "running tests"},
            )
        ],
    )
    os.utime(recent_path, (1_768_999_999, 1_768_999_999))
    calls: list[Path] = []
    original = supervisor_flow._read_session_summary

    def spy_read_session_summary(path: Path, **kwargs: object):
        calls.append(path)
        return original(path, **kwargs)

    monkeypatch.setattr(supervisor_flow, "_read_session_summary", spy_read_session_summary)

    report = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW).scan(limit=1)

    assert report.sessions[0].session_id == recent_session_id
    assert report.sessions[0].display_title == "最近窗口"
    assert len(calls) < 81



def test_codex_supervisor_recommendation_prioritizes_blocked_status(tmp_path):
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

    payload = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW).scan().to_dict()

    assert payload["recommendation"] == {
        "action": "inspect_blocked",
        "label": "先查看主动汇报阻塞的窗口。",
        "priority": "high",
        "reason": "测试环境缺少 tmux。",
        "target_name": None,
        "target_session_id": "blocked-session",
        "send_text": None,
    }



def test_codex_supervisor_recommendation_surfaces_done_status(tmp_path):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-done.jsonl",
        session_id="done-session",
        cwd="/home/lumber/Github/isotope",
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "\n".join(
                    [
                        "SUPERVISOR_STATUS: done",
                        "SUPERVISOR_SUMMARY: 文档和测试都已完成。",
                        "SUPERVISOR_NEXT: 建议用户审阅结果。",
                    ]
                ),
            )
        ],
    )

    payload = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW).scan().to_dict()

    assert payload["recommendation"] == {
        "action": "review_done",
        "label": "先审阅已完成的窗口。",
        "priority": "medium",
        "reason": "文档和测试都已完成。",
        "target_name": None,
        "target_session_id": "done-session",
        "send_text": None,
    }



def test_codex_supervisor_avoids_broad_attention_words_and_caps_json_text(tmp_path):
    codex_home = tmp_path / ".codex"
    long_reply = "建议先等待 1 分钟再开机。" * 20
    _write_session(
        codex_home,
        "2026/05/16/rollout-idle.jsonl",
        session_id="idle-session",
        cwd="/home/lumber/Github/isotope",
        events=[_assistant_message("2026-05-16T11:56:00Z", long_reply)],
    )

    payload = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW).scan().to_dict()

    assert payload["sessions"][0]["status"] == "idle"
    assert len(payload["sessions"][0]["last_assistant_message"]) <= 120



def test_codex_supervisor_avoids_broad_error_words(tmp_path):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-idle.jsonl",
        session_id="idle-session",
        cwd="/home/lumber/Github/isotope",
        events=[_assistant_message("2026-05-16T11:56:00Z", "缺 key 时会明确报错。")],
    )

    report = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW).scan()

    assert report.sessions[0].status == "idle"



def test_codex_supervisor_scan_marks_terminal_ready_for_input(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    pane_text = "\n".join(
        [
            "• SUPERVISOR_STATUS: done",
            "  SUPERVISOR_SUMMARY: 上一批工作已完成。",
            "  SUPERVISOR_NEXT: 等待下一步。",
            "Token usage: total=123",
            "› Improve documentation in @filename",
            "  gpt-5.5 xhigh · Context 96% left · ~/Github/isotope · main",
        ]
    )

    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
        tmux_session_checker=lambda session: session == "isotope-lane-a",
        tmux_bell_checker=lambda session: False,
        tmux_pane_reader=lambda session: pane_text,
    ).scan(limit=5, stale_after_seconds=999999)

    session = report.sessions[0]
    assert session.managed_terminal_ready is True
    assert session.to_dict()["managed_terminal_ready"] is True
    assert "终端=可输入" in render_plain_report(report)
    llm_messages = build_llm_summary_messages(report)
    assert '"managed_terminal_ready": true' in llm_messages[1]["content"]



def test_codex_supervisor_scan_keeps_working_terminal_not_ready(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    pane_text = "\n".join(
        [
            "• Ran PYTHONPATH=src .venv/bin/python -m pytest tests -q",
            "  └ ...................................",
            "",
            "◦ Working (7m 52s • esc to interrupt)",
            "",
            "› *",
            "  tab to queue message · 74% context left",
        ]
    )

    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
        tmux_session_checker=lambda session: session == "isotope-lane-a",
        tmux_bell_checker=lambda session: False,
        tmux_pane_reader=lambda session: pane_text,
    ).scan(limit=5, stale_after_seconds=999999)

    session = report.sessions[0]
    assert session.managed_terminal_ready is False
    assert "终端=运行中" in render_plain_report(report)



def test_codex_supervisor_report_fingerprint_ignores_elapsed_evidence_detail():
    base = {
        "session_id": "stale-session",
        "cwd": "/home/lumber/Github/isotope",
        "source_path": "/home/lumber/.codex/sessions/stale.jsonl",
        "last_event_at": "2026-05-16T11:40:00Z",
        "age_seconds": 1200,
        "status": "stale",
        "reason": "超过 10 分钟没有新事件",
        "status_evidence": {
            "source": "stale_timeout",
            "label": "超过静默阈值",
            "detail": "1200 秒没有新事件，阈值 600 秒",
        },
    }
    later = {
        **base,
        "age_seconds": 1260,
        "status_evidence": {
            "source": "stale_timeout",
            "label": "超过静默阈值",
            "detail": "1260 秒没有新事件，阈值 600 秒",
        },
    }
    first = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(CodexSessionSummary(**base),),
    )
    second = CodexSupervisorReport(
        generated_at=NOW.isoformat(),
        sessions=(CodexSessionSummary(**later),),
    )

    assert _report_fingerprint(first) == _report_fingerprint(second)



def test_codex_supervisor_scan_includes_managed_registry_records(tmp_path):
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
                "prompt": "继续实现 supervisor",
                "command": ["codex", "--cd", str(workspace), "--no-alt-screen", "继续"],
                "pid": 12345,
                "started_at": "2026-05-16T11:59:30+00:00",
                "log_path": str(codex_home / "supervisor" / "logs" / "managed-001.log"),
                "status": "launched",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
        process_checker=lambda pid: pid == 12345,
    ).scan()

    assert len(report.sessions) == 1
    session = report.sessions[0]
    assert session.session_id == "managed:managed-001"
    assert session.status == "working"
    assert session.reason == "Supervisor 托管进程已启动"
    assert session.managed is True
    assert session.managed_name == "lane-a"
    assert session.managed_pid == 12345
    assert session.managed_log_path.endswith("managed-001.log")
    assert session.last_user_message == "继续实现 supervisor"
    assert session.to_dict()["managed"] is True
    text = render_plain_report(report)
    assert "托管：lane-a pid=12345" in text
    llm_messages = build_llm_summary_messages(report)
    assert '"managed": true' in llm_messages[1]["content"]
    assert '"managed_name": "lane-a"' in llm_messages[1]["content"]



def test_codex_supervisor_scan_marks_managed_process_exited(tmp_path):
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
                "prompt": "继续实现 supervisor",
                "command": ["codex", "--cd", str(workspace), "--no-alt-screen", "继续"],
                "pid": 12345,
                "started_at": "2026-05-16T11:59:30+00:00",
                "log_path": str(codex_home / "supervisor" / "logs" / "managed-001.log"),
                "status": "launched",
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

    assert report.sessions[0].status == "exited"
    assert report.sessions[0].status_label == "已退出"
    assert report.sessions[0].reason == "Supervisor 托管进程已退出"



def test_codex_supervisor_scan_parses_managed_process_log_protocol(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = codex_home / "supervisor" / "logs" / "managed-001.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        "\n".join(
            [
                "OpenAI Codex v0.130.0",
                "exec",
                "/bin/bash -lc 'git status --short --branch'",
                "codex",
                "SUPERVISOR_STATUS: done",
                "SUPERVISOR_SUMMARY: process 后端 smoke 已完成。",
                "SUPERVISOR_NEXT: 等待 Supervisor 归档。",
            ]
        ),
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

    session = report.sessions[0]
    assert session.status == "done"
    assert session.status_label == "已完成"
    assert session.reason == "process 后端 smoke 已完成。"
    assert session.supervisor_status == "done"
    assert session.supervisor_summary == "process 后端 smoke 已完成。"
    assert session.supervisor_next == "等待 Supervisor 归档。"
    assert session.status_evidence == {
        "source": "supervisor_protocol",
        "label": "主动状态协议",
        "detail": "SUPERVISOR_STATUS: done",
    }
    assert session.managed_terminal_excerpt is not None
    assert "SUPERVISOR_STATUS: done" in session.managed_terminal_excerpt



def test_codex_supervisor_scan_keeps_exited_process_when_log_says_working(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = codex_home / "supervisor" / "logs" / "managed-001.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        "SUPERVISOR_STATUS: working\n"
        "SUPERVISOR_SUMMARY: 正在读取项目状态。\n"
        "SUPERVISOR_NEXT: 继续读取项目状态并判断下一步。\n",
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

    session = report.sessions[0]
    assert session.status == "exited"
    assert session.reason == "Supervisor 托管进程已退出"
    assert session.supervisor_status == "working"
    assert session.supervisor_summary == "正在读取项目状态。"



def test_codex_supervisor_scan_marks_tmux_managed_session_running(tmp_path):
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
                "prompt": "继续实现 supervisor",
                "command": ["tmux", "new-session", "-d", "-s", "isotope-lane-a"],
                "pid": 0,
                "started_at": "2026-05-16T11:59:30+00:00",
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

    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
        tmux_session_checker=lambda session: session == "isotope-lane-a",
    ).scan()

    assert report.sessions[0].status == "working"
    assert report.sessions[0].reason == "Supervisor 托管 tmux 会话仍在运行"
    assert report.sessions[0].managed_backend == "tmux"
    assert report.sessions[0].managed_tmux_session == "isotope-lane-a"
    assert report.sessions[0].to_dict()["managed_tmux_session"] == "isotope-lane-a"
    text = render_plain_report(report)
    assert "托管：lane-a backend=tmux tmux=isotope-lane-a" in text
    llm_messages = build_llm_summary_messages(report)
    assert '"managed_backend": "tmux"' in llm_messages[1]["content"]



def test_codex_supervisor_scan_marks_tmux_managed_bell_signal(tmp_path):
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
                "prompt": "继续实现 supervisor",
                "command": ["tmux", "new-session", "-d", "-s", "isotope-lane-a"],
                "pid": 0,
                "started_at": "2026-05-16T11:59:30+00:00",
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

    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
        tmux_session_checker=lambda session: session == "isotope-lane-a",
        tmux_bell_checker=lambda session: session == "isotope-lane-a",
    ).scan()

    session = report.sessions[0]
    assert session.managed_bell is True
    assert session.to_dict()["managed_bell"] is True
    assert "bell=响过" in render_plain_report(report)
    llm_messages = build_llm_summary_messages(report)
    assert '"managed_bell": true' in llm_messages[1]["content"]



def test_codex_supervisor_scan_reports_tmux_bell_hook_health(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)

    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
        tmux_session_checker=lambda session: session == "isotope-lane-a",
        tmux_bell_checker=lambda session: False,
        tmux_bell_hook_checker=lambda session: session == "isotope-lane-a",
    ).scan()

    session = report.sessions[0]
    assert session.managed_bell_hook_installed is True
    assert session.to_dict()["managed_bell_hook_installed"] is True
    assert "bell hook=已安装" in render_plain_report(report)
    llm_messages = build_llm_summary_messages(report)
    assert '"managed_bell_hook_installed": true' in llm_messages[1]["content"]



def test_codex_supervisor_scan_highlights_tmux_bell_hook_event(tmp_path):
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
                "prompt": "继续实现 supervisor",
                "command": ["tmux", "attach", "-t", "isotope-lane-a"],
                "pid": 0,
                "started_at": "2026-05-16T11:59:30+00:00",
                "log_path": str(codex_home / "supervisor" / "logs" / "managed-001.log"),
                "status": "adopted",
                "backend": "tmux",
                "tmux_session": "isotope-lane-a",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    bell_path = codex_home / "supervisor" / "bell_events.jsonl"
    bell_path.write_text(
        json.dumps(
            {
                "event": "bell",
                "name": "lane-a",
                "tmux_session": "isotope-lane-a",
                "created_at": "2026-05-16T11:59:50+00:00",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    report = CodexSupervisorFlow(
        codex_home=codex_home,
        now=lambda: NOW,
        tmux_session_checker=lambda session: session == "isotope-lane-a",
        tmux_bell_checker=lambda session: False,
    ).scan()

    session = report.sessions[0]
    assert session.managed_bell is True
    assert session.managed_bell_event_at == "2026-05-16T11:59:50+00:00"
    assert session.to_dict()["managed_bell_event_at"] == "2026-05-16T11:59:50+00:00"
    plain = render_plain_report(report)
    assert "bell=响过" in plain
    assert "bell 事件：2026-05-16T11:59:50+00:00" in plain
    llm_messages = build_llm_summary_messages(report)
    assert '"managed_bell_event_at": "2026-05-16T11:59:50+00:00"' in llm_messages[1]["content"]



def test_codex_supervisor_recommendation_surfaces_tmux_bell_event(tmp_path):
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
                "prompt": "继续实现 supervisor",
                "command": ["tmux", "attach", "-t", "isotope-lane-a"],
                "pid": 0,
                "started_at": "2026-05-16T11:59:30+00:00",
                "log_path": str(codex_home / "supervisor" / "logs" / "managed-001.log"),
                "status": "adopted",
                "backend": "tmux",
                "tmux_session": "isotope-lane-a",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    bell_path = codex_home / "supervisor" / "bell_events.jsonl"
    bell_path.write_text(
        json.dumps(
            {
                "event": "bell",
                "name": "lane-a",
                "tmux_session": "isotope-lane-a",
                "created_at": "2026-05-16T11:59:50+00:00",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = (
        CodexSupervisorFlow(
            codex_home=codex_home,
            now=lambda: NOW,
            tmux_session_checker=lambda session: session == "isotope-lane-a",
            tmux_bell_checker=lambda session: False,
        )
        .scan()
        .to_dict()
    )

    assert payload["recommendation"] == {
        "action": "inspect_bell",
        "label": "查看刚响铃的托管窗口。",
        "priority": "medium",
        "reason": "tmux bell event at 2026-05-16T11:59:50+00:00",
        "target_name": "lane-a",
        "target_session_id": "managed:managed-001",
        "send_text": None,
    }


