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

from isotope.features.notifications.flow import NotificationFlow
from isotope.features.supervisor import flow as supervisor_flow
from isotope.features.supervisor.flow import (
    CodexSessionSummary,
    CodexSupervisorFlow,
    CodexSupervisorReport,
    render_plain_report,
)
from isotope.features.supervisor.context import (
    read_recent_context_results,
    request_project_context,
)
from isotope.features.supervisor.llm_summary import (
    PooledSummaryProvider,
    PoolEntry,
    build_llm_action_messages,
    build_llm_summary_messages,
    generate_llm_action_decision,
    generate_llm_summary,
    resolve_summary_provider_from_env,
)
from isotope.features.supervisor.runner import (
    EXECUTABLE_ADVICE_TEXT,
    _advice_payload,
    _dashboard_payload,
    _execute_llm_action,
    _report_fingerprint,
    main as supervisor_main,
)


NOW = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)
STATUS_REQUEST_TEXT = EXECUTABLE_ADVICE_TEXT["send_status"]
CONTINUE_REQUEST_TEXT = EXECUTABLE_ADVICE_TEXT["send_continue"]
EXISTING_WORKSPACE = str(Path(__file__).resolve().parents[2])


def _runner_args(codex_home: Path) -> argparse.Namespace:
    return argparse.Namespace(
        codex_home=str(codex_home),
        max_continue_count=0,
        max_run_minutes=0,
        prompt_cooldown=0,
        worker_codex_model=None,
        worker_codex_config=[],
        worker_profile="coding",
    )


def _supervisor_send_command(name: str, text: str) -> str:
    return shlex.join(["isotope-supervisor", "send", "--name", name, "--text", text])


def _tmux_send_calls(
    text: str,
    *,
    buffer_name: str = "isotope-supervisor-managed-001",
    target: str = "isotope-lane-a",
) -> list[list[str]]:
    return [
        ["tmux", "set-buffer", "-b", buffer_name, "--", text],
        ["tmux", "paste-buffer", "-d", "-b", buffer_name, "-t", target],
        ["tmux", "send-keys", "-t", target, "C-m"],
    ]


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
            "999999",
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
    assert payload["notifications"][2] == {
        **unsafe.to_dict(),
        "source_ref": {"ref_type": "supervisor_run", "run_id": "run_unsafe"},
    }
    raw_payload = json.dumps(payload, ensure_ascii=False)
    assert "RAW_PROMPT_SHOULD_NOT_LEAK" not in raw_payload
    assert "sk-test-secret" not in raw_payload
    assert "/tmp/raw.log" not in raw_payload
    assert payload["notification_counts"] == {"total": 3, "unread": 2}


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
            "999999",
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
            "• Ran PYTHONPATH=src .venv/bin/python -m pytest tests/isotope -q",
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


def test_codex_supervisor_web_serves_dashboard_html_and_json(tmp_path):
    from isotope.features.supervisor.web import create_dashboard_server
    from isotope.features.notifications.flow import NotificationFlow

    codex_home = tmp_path / ".codex"
    notification = NotificationFlow.in_process(codex_home).create_notification(
        notification_type="approval",
        title="Worker needs approval",
        source_ref={"ref_type": "supervisor_run", "run_id": "run_123"},
    )
    unsafe_notification = NotificationFlow.in_process(codex_home).create_notification(
        notification_type="approval",
        title="Worker source check",
        source_ref={
            "ref_type": "supervisor_run",
            "run_id": "run_unsafe",
            "prompt": "RAW_PROMPT_SHOULD_NOT_LEAK",
            "api_key": "sk-test-secret",
            "log_path": "/tmp/raw.log",
        },
    )
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

    server = create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/")
        html_response = conn.getresponse()
        html = html_response.read().decode("utf-8")
        conn.request("GET", "/dashboard.json")
        json_response = conn.getresponse()
        payload = json.loads(json_response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert html_response.status == 200
    assert "text/html" in html_response.getheader("content-type", "")
    assert 'data-group="needs_attention"' in html
    assert "short_session_id" in html
    assert "display_title" in html
    assert "managed_display_title" in html
    assert "copyResumeCommand" in html
    assert "copyControlCommand" in html
    assert "copyControlLabel" in html
    assert "复制状态" in html
    assert "复制继续" in html
    assert "sendManagedCommand" in html
    assert "requestLlmAction" in html
    assert "renderDecisionRequest" in html
    assert "renderDecisionRequests" in html
    assert "renderNotifications" in html
    assert "current-list" in html
    assert "当前批次" in html
    assert "renderCurrentBatch" in html
    assert "current-count" in html
    assert "暂无当前目标" in html
    assert "暂无托管 worker" in html
    assert "notification-list" in html
    assert "通知列表" in html
    assert "source_ref" in html
    assert "submitDecisionAnswer" in html
    assert "/decision/answer" in html
    assert "填写答案" in html
    assert "提交答案" in html
    assert "copyDecisionArchiveCommand" in html
    assert "复制归档拍板" in html
    assert "等待拍板列表" in html
    assert "decision_requests" in html
    assert "等待拍板" in html
    assert "context_status" in html
    assert "renderSupervisorProtocol" in html
    assert "状态汇报" in html
    assert "下一步" in html
    assert "connectSupervisorEvents" in html
    assert "EventSource" in html
    assert "applyLlmActionHighlight" in html
    assert "suggested-action" in html
    assert "data-command-kind" in html
    assert "data-lane-name" in html
    assert "renderCardSource" in html
    assert "卡片来源" in html
    assert "普通历史会话" in html
    assert "renderManagedDetails" in html
    assert "renderLinkedMatch" in html
    assert "linked_match" in html
    assert "绑定依据" in html
    assert "managed_terminal_excerpt" in html
    assert "最近输出" in html
    assert "bell：" in html
    assert "未收到" in html
    assert "bell hook" in html
    assert "终端状态" in html
    assert "scrollTerminalExcerptToBottom" in html
    assert "rememberTerminalExcerptScroll" in html
    assert "restoreTerminalExcerptScroll" in html
    assert "/managed/send" in html
    assert "/llm-action" in html
    assert "/events" in html
    assert "模型建议" in html
    assert "status_evidence" in html
    assert "依据：" in html
    assert "codex resume " in html
    assert '"tmux attach -t " + item.managed_tmux_session' not in html
    assert "Codex Supervisor" in html
    assert "dashboard.json" in html
    assert json_response.status == 200
    assert payload["status"] == "ok"
    assert payload["current"] == {
        "active_goals": [],
        "managed_workers": [],
        "counts": {"active_goals": 0, "managed_workers": 0},
    }
    assert payload["counts"]["needs_attention"] == 1
    assert payload["decision_requests"] == []
    assert payload["notifications"] == [
        notification.to_dict(),
        {
            **unsafe_notification.to_dict(),
            "source_ref": {"ref_type": "supervisor_run", "run_id": "run_unsafe"},
        },
    ]
    raw_payload = json.dumps(payload, ensure_ascii=False)
    assert "RAW_PROMPT_SHOULD_NOT_LEAK" not in raw_payload
    assert "sk-test-secret" not in raw_payload
    assert "/tmp/raw.log" not in raw_payload
    assert payload["notification_counts"] == {"total": 2, "unread": 2}
    assert payload["groups"]["needs_attention"][0]["session_id"] == "blocked-session"
    assert payload["groups"]["needs_attention"][0]["status_evidence"]["source"] == (
        "supervisor_protocol"
    )


def test_codex_supervisor_web_events_stream_bell_changes(tmp_path):
    from isotope.features.supervisor.web import create_dashboard_server

    codex_home = tmp_path / ".codex"
    server = create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/events")
        response = conn.getresponse()
        first_line = response.readline().decode("utf-8").strip()
        event_path = codex_home / "supervisor" / "bell_events.jsonl"
        event_path.parent.mkdir(parents=True)
        event_path.write_text(
            (
                '{"event":"bell","name":"lane-a","tmux_session":"isotope-lane-a",'
                '"created_at":"2026-05-16T12:00:00Z"}\n'
            ),
            encoding="utf-8",
        )
        lines: list[str] = []
        while len(lines) < 4:
            lines.append(response.readline().decode("utf-8").strip())
            if "tmux_session" in lines[-1]:
                break
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    assert response.getheader("content-type") == "text/event-stream; charset=utf-8"
    assert first_line == "event: ready"
    assert "event: bell" in lines
    assert any('"tmux_session": "isotope-lane-a"' in line for line in lines)


def test_codex_supervisor_web_repairs_bell_hooks_on_startup(tmp_path):
    from isotope.features.supervisor.web import create_dashboard_server

    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        text: bool,
        capture_output: bool,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert text is True
        assert capture_output is True
        assert check is (command[:2] == ["tmux", "set-hook"])
        return subprocess.CompletedProcess(command, 0, "", "")

    server = create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        repair_run=fake_run,
    )
    server.server_close()

    assert calls[0] == ["tmux", "has-session", "-t", "isotope-lane-a"]
    assert calls[1][:4] == ["tmux", "set-hook", "-t", "isotope-lane-a"]
    assert calls[1][4] == "alert-bell"
    assert "bell_events.jsonl" in calls[1][5]
    assert "lane-a" in calls[1][5]
    assert [result.to_dict() for result in server.bell_hook_repairs] == [
        {
            "name": "lane-a",
            "tmux_session": "isotope-lane-a",
            "status": "installed",
            "message": None,
        }
    ]


def test_codex_supervisor_web_returns_manual_llm_action_without_sending(
    tmp_path,
    monkeypatch,
):
    from isotope.features.supervisor.web import create_dashboard_server

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
        lambda session: (
            "SUPERVISOR_STATUS: blocked\n"
            "SUPERVISOR_SUMMARY: 需要用户提供 API key。\n"
            "SUPERVISOR_NEXT: 等待用户处理。"
        ),
    )
    send_calls: list[list[str]] = []

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            assert "command_suggestions" in messages[1]["content"]
            return '{"kind":"send_status","target_name":"lane-a","reason":"先看进度。"}'

    def fake_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        send_calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    server = create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        send_run=fake_run,
        llm_action_provider=FakeProvider(),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            "/llm-action",
            b"{}",
            {"content-type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    assert payload["status"] == "ok"
    assert payload["llm_action"] == {
        "kind": "send_status",
        "target_name": "lane-a",
            "reason": "先看进度。",
            "command_suggestion": {
                "command": _supervisor_send_command("lane-a", STATUS_REQUEST_TEXT),
                "kind": "send_status",
                "label": "让托管 Codex 汇报状态",
            },
    }
    assert send_calls == []


def test_codex_supervisor_web_returns_ask_user_after_context_gate(
    tmp_path,
    monkeypatch,
):
    from isotope.features.supervisor.web import create_dashboard_server

    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    docs_dir = workspace / "docs" / "current"
    docs_dir.mkdir(parents=True)
    (docs_dir / "status.md").write_text(
        "目录迁移文档和现状冲突，需要用户拍板兼容策略。\n",
        encoding="utf-8",
    )
    request_project_context(
        codex_home=codex_home,
        cwd=workspace,
        query="目录迁移 兼容策略",
        rg_bin=None,
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-needs-user.jsonl",
        session_id="019e35a2-e442-75e2-84ab-3761a685a736",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "\n".join(
                    [
                        "SUPERVISOR_STATUS: needs_user",
                        "SUPERVISOR_SUMMARY: 目录迁移有两种不可兼容方案。",
                        "SUPERVISOR_NEXT: 请用户拍板选择保留兼容层还是直接迁移。",
                    ]
                ),
            )
        ],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert "目录迁移文档和现状冲突" in content
            return json.dumps(
                {
                    "kind": "ask_user",
                    "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
                    "question": "目录迁移是保留兼容层，还是直接迁移并删除旧入口？",
                    "codex_requested_decision": True,
                    "instructions_exhausted": True,
                    "context_status": "conflict",
                    "reason": "Codex 明确要拍板，既有指示不足，文档和现状冲突。",
                },
                ensure_ascii=False,
            )

    server = create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        llm_action_provider=FakeProvider(),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            "/llm-action",
            b"{}",
            {"content-type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    assert payload["llm_action"] == {
        "kind": "ask_user",
        "target_name": "resume-019e35a2",
        "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
        "question": "目录迁移是保留兼容层，还是直接迁移并删除旧入口？",
        "context_status": "conflict",
        "codex_requested_decision": True,
        "instructions_exhausted": True,
        "reason": "Codex 明确要拍板，既有指示不足，文档和现状冲突。",
        "command_suggestion": None,
    }
    assert payload["recent_context_results"][0]["query"] == "目录迁移 兼容策略"


def test_codex_supervisor_web_can_submit_decision_answer(tmp_path):
    from isotope.features.supervisor.web import create_dashboard_server

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
    server = create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            "/decision/answer",
            json.dumps(
                {
                    "request_id": "decision-001",
                    "answer": "保留兼容层，后续再清理旧入口。",
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            {"content-type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        conn.request("GET", "/dashboard.json")
        dashboard_response = conn.getresponse()
        dashboard_payload = json.loads(dashboard_response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    assert payload["status"] == "ok"
    assert payload["answered"]["event"] == "decision_answer"
    assert payload["answered"]["request_id"] == "decision-001"
    assert payload["answered"]["goal_id"] == "goal-001"
    assert payload["answered"]["answer"] == "保留兼容层，后续再清理旧入口。"
    assert payload["decision_requests"] == []
    assert dashboard_response.status == 200
    assert dashboard_payload["decision_requests"] == []


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
        }
    ]


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

    class FakeProvider:
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
        lambda **_: FakeProvider(),
    )
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 45683

    def fake_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        captured["cwd"] = cwd
        return FakeProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)

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
            "--json",
        ]
    )

    assert exit_code == 0
    archive_payload = json.loads(capsys.readouterr().out)
    assert archive_payload["archived"]["event"] == "supervisor_goal_archive"
    assert archive_payload["archived"]["goal_id"] == goal["goal_id"]
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

    class FakeProvider:
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
        lambda **_: FakeProvider(),
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

    class FakeProvider:
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
        FakeProvider(),
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

    class FakeProvider:
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
            FakeProvider(),
            active_goals=active_goals,
        )


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


def test_codex_supervisor_web_rejects_invalid_manual_llm_action(tmp_path):
    from isotope.features.supervisor.web import create_dashboard_server

    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return '{"kind":"delete_branch","reason":"危险动作"}'

    server = create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        llm_action_provider=FakeProvider(),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            "/llm-action",
            b"{}",
            {"content-type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 400
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "codex_supervisor_web_error"
    assert "unsupported LLM action" in payload["error"]["message"]


def test_codex_supervisor_web_can_send_allowed_managed_command(tmp_path):
    from isotope.features.supervisor.web import create_dashboard_server

    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert check is True
        assert text is True
        assert capture_output is True
        return subprocess.CompletedProcess(command, 0, "", "")

    server = create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        send_run=fake_run,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        body = json.dumps({"name": "lane-a", "kind": "send_status"}).encode("utf-8")
        conn.request(
            "POST",
            "/managed/send",
            body,
            {"content-type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    assert payload["status"] == "ok"
    assert payload["kind"] == "send_status"
    assert payload["text"] == STATUS_REQUEST_TEXT
    assert payload["managed"]["tmux_session"] == "isotope-lane-a"
    assert calls == _tmux_send_calls(STATUS_REQUEST_TEXT)
    lane_state = json.loads(
        (codex_home / "supervisor" / "lane_state.json").read_text(encoding="utf-8")
    )
    assert lane_state["lane-a"]["last_status"] == "send_status"
    assert lane_state["lane-a"]["prompt_count"] == 1


def test_codex_supervisor_web_rejects_unsupported_managed_command(tmp_path):
    from isotope.features.supervisor.web import create_dashboard_server

    codex_home = tmp_path / ".codex"

    server = create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        body = json.dumps({"name": "lane-a", "kind": "tmux_attach"}).encode("utf-8")
        conn.request(
            "POST",
            "/managed/send",
            body,
            {"content-type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 400
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "codex_supervisor_web_error"
    assert "send_status" in payload["error"]["message"]


def test_codex_supervisor_runner_web_print_url_exits(tmp_path, capsys):
    codex_home = tmp_path / ".codex"

    exit_code = supervisor_main(
        [
            "web",
            "--codex-home",
            str(codex_home),
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
            "--print-url",
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "http://127.0.0.1:8765/"


def test_codex_supervisor_runner_advise_prints_json_command_suggestion(tmp_path, capsys):
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
        [
            "advise",
            "--codex-home",
            str(codex_home),
            "--limit",
            "1",
            "--stale-after",
            "999999",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["recommendation"]["action"] == "monitor"
    assert payload["command_suggestion"] == {
        "command": "isotope-supervisor watch --interval 180 --changes-only",
        "kind": "watch_changes",
        "label": "继续监控变化",
    }


def test_codex_supervisor_runner_advise_plain_is_short(tmp_path, capsys):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-attention.jsonl",
        session_id="attention-session",
        cwd=EXISTING_WORKSPACE,
        events=[
            _assistant_message("2026-05-16T11:58:00Z", "需要你确认是否继续。"),
        ],
    )

    exit_code = supervisor_main(["advise", "--codex-home", str(codex_home)])

    assert exit_code == 0
    text = capsys.readouterr().out
    assert "[Codex Supervisor 建议]" in text
    assert "建议：先处理等待用户确认的窗口。" in text
    assert "动作：review_user_prompt" in text
    assert "命令：isotope-supervisor resume --name resume-attention-session" in text


def test_codex_supervisor_advise_suggests_managed_tmux_commands():
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

    payload = _advice_payload(report)

    assert payload["command_suggestion"] == {
        "command": "tmux attach -t isotope-lane-a",
        "kind": "tmux_attach",
        "label": "打开托管 tmux 窗口",
    }
    assert payload["command_suggestions"] == [
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
        {
            "command": "isotope-supervisor watch --interval 180 --changes-only",
            "kind": "watch_changes",
            "label": "继续监控变化",
        },
    ]


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
    assert "guardrail" in messages[0]["content"]
    assert (
        '"allowed_kinds": ["monitor", "send_status", "send_continue", '
        '"resume_session", "launch_session", "request_context", "ask_user"]'
        in messages[1]["content"]
    )
    assert '"context_capability"' in messages[1]["content"]
    assert '"decision_gate"' in messages[1]["content"]
    assert '"kind": "send_continue"' in messages[1]["content"]
    assert '"target_name": "lane-a"' in messages[1]["content"]
    assert '"managed_terminal_ready": true' in messages[1]["content"]
    assert '"managed_bell": true' in messages[1]["content"]
    assert '"supervisor_status": "done"' in messages[1]["content"]


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
                    "validation_commands": ["pytest tests/isotope -q"],
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
    assert "worker_reviews 只提供下一轮决策上下文" in "".join(
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

    class FakeProvider:
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
            FakeProvider(),
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
    assert "recommendation.target_session_id 只是状态线索" in content
    assert "resumable_session_ids 为空时不得输出 resume_session" in content


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

    class FakeProvider:
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
        generate_llm_action_decision(report, suggestions, FakeProvider())


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
    assert "不要重复同一个 cwd/query 的 request_context" in content
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
    assert "同名 worker 已在运行时不得再次 launch_session" in "".join(
        payload["action_rules"]
    )
    assert not any(
        suggestion.get("kind") == "launch_session"
        and suggestion.get("target_name") == "goal-a"
        for suggestion in advice["command_suggestions"]
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

    class FakeProvider:
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

    decision = generate_llm_action_decision(report, suggestions, FakeProvider())

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

    class FakeProvider:
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

    decision = generate_llm_action_decision(report, suggestions, FakeProvider())

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

    class FakeProvider:
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

    decision = generate_llm_action_decision(report, suggestions, FakeProvider())

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

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert "可只输出 target_name" in content
            return json.dumps(
                {
                    "kind": "launch_session",
                    "target_name": "supervisor-goal-planner",
                    "reason": "直接启动目标队列里的 worker。",
                },
                ensure_ascii=False,
            )

    decision = generate_llm_action_decision(report, suggestions, FakeProvider())

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

    class FakeProvider:
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

    decision = generate_llm_action_decision(report, suggestions, FakeProvider())

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

    class FakeProvider:
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
            FakeProvider(),
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

    class FakeProvider:
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

    decision = generate_llm_action_decision(report, suggestions, FakeProvider())

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

    class FakeProvider:
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

    decision = generate_llm_action_decision(report, suggestions, FakeProvider())

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

    class FakeProvider:
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
            FakeProvider(),
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

    class FakeProvider:
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
            FakeProvider(),
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

    class FakeProvider:
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
        FakeProvider(),
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


def test_codex_supervisor_runner_advice_plain_prints_ask_user_question(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    docs_dir = workspace / "docs" / "current"
    docs_dir.mkdir(parents=True)
    (docs_dir / "status.md").write_text(
        "目录迁移文档和现状冲突，需要用户拍板兼容策略。\n",
        encoding="utf-8",
    )
    request_project_context(
        codex_home=codex_home,
        cwd=workspace,
        query="目录迁移 兼容策略",
        rg_bin=None,
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-needs-user.jsonl",
        session_id="019e35a2-e442-75e2-84ab-3761a685a736",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "\n".join(
                    [
                        "SUPERVISOR_STATUS: needs_user",
                        "SUPERVISOR_SUMMARY: 目录迁移有两种不可兼容方案。",
                        "SUPERVISOR_NEXT: 请用户拍板选择保留兼容层还是直接迁移。",
                    ]
                ),
            )
        ],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert "目录迁移文档和现状冲突" in content
            return json.dumps(
                {
                    "kind": "ask_user",
                    "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
                    "question": "目录迁移是保留兼容层，还是直接迁移并删除旧入口？",
                    "codex_requested_decision": True,
                    "instructions_exhausted": True,
                    "context_status": "conflict",
                    "reason": "Codex 明确要拍板，既有指示不足，文档和现状冲突。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FakeProvider(),
    )

    exit_code = supervisor_main(
        [
            "advise",
            "--codex-home",
            str(codex_home),
            "--limit",
            "5",
            "--stale-after",
            "999999",
            "--llm-action",
        ]
    )

    assert exit_code == 0
    text = capsys.readouterr().out
    assert "LLM 动作：ask_user" in text
    assert "等待拍板：目录迁移是保留兼容层，还是直接迁移并删除旧入口？" in text
    assert "上下文状态：conflict" in text


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

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return (
                "我会按这个格式返回：{\"kind\":\"monitor\"}\n"
                "```json\n"
                "{\"kind\":\"send_status\",\"target_name\":\"lane-a\",\"reason\":\"先让它按协议汇报。\"}\n"
                "```"
            )

    decision = generate_llm_action_decision(report, suggestions, FakeProvider())

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

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return "我需要更多上下文，暂时不能决定。"

    with pytest.raises(ValueError, match="raw=我需要更多上下文"):
        generate_llm_action_decision(report, suggestions, FakeProvider())


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

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return '{"kind":"delete_branch","reason":"危险动作"}'

    with pytest.raises(ValueError, match="unsupported LLM action"):
        generate_llm_action_decision(report, suggestions, FakeProvider())


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


def test_codex_supervisor_runner_advise_can_add_llm_action(
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

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            assert "command_suggestions" in messages[1]["content"]
            return '{"kind":"send_status","target_name":"lane-a","reason":"先看进度。"}'

    captured: dict[str, object] = {}

    def fake_resolver(**kwargs: object) -> FakeProvider:
        captured.update(kwargs)
        return FakeProvider()

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        fake_resolver,
    )

    exit_code = supervisor_main(
        [
            "advise",
            "--codex-home",
            str(codex_home),
            "--limit",
            "1",
            "--llm-action",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["llm_action"] == {
        "kind": "send_status",
            "target_name": "lane-a",
            "reason": "先看进度。",
            "command_suggestion": {
                "command": _supervisor_send_command("lane-a", STATUS_REQUEST_TEXT),
                "kind": "send_status",
                "label": "让托管 Codex 汇报状态",
            },
    }
    assert captured["agent_name"] == "supervisor"


def test_codex_supervisor_runner_llm_action_becomes_primary_command_suggestion(
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

    class FakeProvider:
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
        lambda **_: FakeProvider(),
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
    assert payload["llm_action"]["kind"] == "request_context"
    assert payload["command_suggestion"] == payload["llm_action"]["command_suggestion"]
    assert payload["command_suggestion"]["kind"] == "request_context"
    assert payload["rule_command_suggestion"]["kind"] == "resume_session"


def test_codex_supervisor_runner_supervise_llm_action_passes_worker_reviews(
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

    class FakeProvider:
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
        lambda **_: FakeProvider(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_worker_reviews",
        lambda *, codex_home: worker_reviews,
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
    assert payload["llm_action"]["kind"] == "request_context"
    assert payload["llm_action"]["query"] == "worker-a diff review next_decision"


def test_codex_supervisor_runner_llm_action_scopes_to_workspace_root(
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

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert "external-session" not in content
            assert "isotope-session" in content
            assert f'"available_workspaces": ["{workspace}"]' in content
            return '{"kind":"monitor","reason":"只监控当前项目工作区。"}'

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FakeProvider(),
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
    assert payload["llm_action"]["kind"] == "monitor"
    suggestion_text = json.dumps(payload["command_suggestions"], ensure_ascii=False)
    assert "external-session" not in suggestion_text
    assert "isotope-session" in suggestion_text


def test_codex_supervisor_runner_advise_execute_send_status(
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

    def fake_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["git", "-C"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        calls.append(command)
        assert check is True
        assert text is True
        assert capture_output is True
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "advise",
            "--codex-home",
            str(codex_home),
            "--execute",
            "send_status",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["executed"] == {
        "command": _supervisor_send_command("lane-a", STATUS_REQUEST_TEXT),
        "kind": "send_status",
        "managed": {
            "name": "lane-a",
            "record_id": "managed-001",
            "tmux_session": "isotope-lane-a",
        },
        "text": STATUS_REQUEST_TEXT,
    }
    assert calls == _tmux_send_calls(STATUS_REQUEST_TEXT)


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


def test_codex_supervisor_runner_advise_name_targets_managed_lane(
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
        "\n".join(
            json.dumps(record, ensure_ascii=False)
            for record in [
                {
                    "record_id": "managed-a",
                    "name": "lane-a",
                    "cwd": str(workspace),
                    "prompt": "等待输入",
                    "command": ["tmux", "attach", "-t", "session-a"],
                    "pid": 0,
                    "started_at": NOW.isoformat(),
                    "log_path": str(codex_home / "supervisor" / "logs" / "a.log"),
                    "status": "adopted",
                    "backend": "tmux",
                    "tmux_session": "session-a",
                },
                {
                    "record_id": "managed-b",
                    "name": "lane-b",
                    "cwd": str(workspace),
                    "prompt": "等待输入",
                    "command": ["tmux", "attach", "-t", "session-b"],
                    "pid": 0,
                    "started_at": NOW.isoformat(),
                    "log_path": str(codex_home / "supervisor" / "logs" / "b.log"),
                    "status": "adopted",
                    "backend": "tmux",
                    "tmux_session": "session-b",
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_session_exists",
        lambda session: session in {"session-a", "session-b"},
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_window_has_bell",
        lambda session: False,
    )
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "advise",
            "--codex-home",
            str(codex_home),
            "--name",
            "lane-b",
            "--execute",
            "send_status",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    send_status = next(
        item
        for item in payload["command_suggestions"]
        if item["kind"] == "send_status"
    )
    assert send_status["command"] == _supervisor_send_command("lane-b", STATUS_REQUEST_TEXT)
    assert payload["executed"]["managed"]["name"] == "lane-b"
    assert calls == _tmux_send_calls(
        STATUS_REQUEST_TEXT,
        buffer_name="isotope-supervisor-managed-b",
        target="session-b",
    )


def test_codex_supervisor_runner_advise_name_missing_does_not_fallback(
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
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "advise",
            "--codex-home",
            str(codex_home),
            "--name",
            "missing",
            "--execute",
            "send_status",
            "--json",
        ]
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "codex_supervisor_runner_error"
    assert payload["error"]["message"] == "managed lane not found: missing"
    assert calls == []


def test_codex_supervisor_runner_advise_execute_rejects_non_send_kind(
    tmp_path,
    capsys,
):
    codex_home = tmp_path / ".codex"

    exit_code = supervisor_main(
        [
            "advise",
            "--codex-home",
            str(codex_home),
            "--execute",
            "tmux_attach",
            "--json",
        ]
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "codex_supervisor_runner_error"
    assert "send_status" in payload["error"]["message"]
    assert "send_continue" in payload["error"]["message"]


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

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            assert "active-session" in messages[1]["content"]
            assert "recommendation" in messages[1]["content"]
            return "窗口 A 正在读文件，建议继续监控。"

    captured: dict[str, object] = {}

    def fake_resolver(**kwargs: object) -> FakeProvider:
        captured.update(kwargs)
        return FakeProvider()

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        fake_resolver,
    )

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--limit",
            "1",
            "--stale-after",
            "999999",
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

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

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

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert (
                '"allowed_kinds": ["monitor", "send_status", "send_continue", '
                '"resume_session", "launch_session", "request_context", "ask_user"]'
            ) in content
            assert '"managed_terminal_ready": true' in content
            return '{"kind":"send_status","target_name":"lane-a","reason":"先看进度。"}'

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FakeProvider(),
    )
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

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
    assert payload["llm_action"]["kind"] == "send_status"
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

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"managed_terminal_ready": false' in content
            return json.dumps(
                {"kind": kind, "target_name": "lane-a", "reason": "直接追问。"},
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FakeProvider(),
    )
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

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
    assert payload["llm_action"]["kind"] == kind
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

    class FakeProvider:
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
        lambda **_: FakeProvider(),
    )
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

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
    assert "--name lane-b" in payload["llm_action"]["command_suggestion"]["command"]
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

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)
    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"can_resume": true' in content
            return '{"kind":"monitor","reason":"仍在工作，先观察。"}'

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FakeProvider(),
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
    assert payload["llm_action"] == {
        "kind": "monitor",
        "target_name": None,
        "reason": "仍在工作，先观察。",
        "command_suggestion": None,
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "仍在工作，先观察。",
    }
    assert calls == []


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

    class FakeProvider:
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
        lambda **_: FakeProvider(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 34567

    def fake_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        captured["cwd"] = cwd
        captured["stdin"] = stdin
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return FakeProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)

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
    assert payload["llm_action"]["kind"] == "resume_session"
    assert payload["llm_action"]["target_name"] == "resume-019e35a2"
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
        "llm_action": {
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

    def fake_resume_managed_codex(*args: object, **kwargs: object) -> object:
        raise AssertionError("old session must not be resumed while active goals exist")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resume_managed_codex",
        fake_resume_managed_codex,
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

    class FakeProvider:
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
        lambda **_: FakeProvider(),
    )

    def fake_resume_managed_codex(*args: object, **kwargs: object) -> object:
        raise AssertionError("running worker cwd should not be resumed")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resume_managed_codex",
        fake_resume_managed_codex,
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
    assert payload["llm_action"]["kind"] == "resume_session"
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

    class FakeProvider:
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
        lambda **_: FakeProvider(),
    )

    def fake_resume_managed_codex(*args: object, **kwargs: object) -> object:
        raise AssertionError("missing cwd should not be passed to codex exec resume")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resume_managed_codex",
        fake_resume_managed_codex,
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
    assert payload["llm_action"]["kind"] == "monitor"
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

    class FakeProvider:
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
        lambda **_: FakeProvider(),
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
    assert payload["llm_action"]["kind"] == "monitor"
    assert payload["llm_action"]["error"] == (
        f"unknown workspace for LLM action: {missing_workspace}"
    )
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

    class FakeProvider:
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
        lambda **_: FakeProvider(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 45678

    def fake_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        captured["cwd"] = cwd
        captured["stdin"] = stdin
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return FakeProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)

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
    assert payload["llm_action"]["kind"] == "launch_session"
    assert payload["executed"]["kind"] == "launch_session"
    assert payload["executed"]["managed"]["name"] == "new-planner"
    assert payload["executed"]["managed"]["pid"] == 45678
    assert "WORK ORDER" in payload["executed"]["text"]
    assert f"goal: {launch_prompt}" in payload["executed"]["text"]
    assert f"cwd: {workspace}" in payload["executed"]["text"]
    assert "budget_hint: prompt-only" in payload["executed"]["text"]
    assert "这不是 Supervisor 强制预算控制" in payload["executed"]["text"]
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

    class FakeProvider:
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
        lambda **_: FakeProvider(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 45678

    def fake_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        captured["cwd"] = cwd
        return FakeProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)

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
    assert payload["llm_action"]["worker_profile"] == "light"
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

    class FakeProvider:
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
        lambda **_: FakeProvider(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )
    run_calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        check: bool = False,
        text: bool = False,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        run_calls.append(command)
        if command[:4] == ["git", "-C", str(repo_root), "rev-parse"]:
            return subprocess.CompletedProcess(command, 0, str(repo_root) + "\n", "")
        if command[:4] == ["git", "-C", str(repo_root), "worktree"]:
            Path(command[-2]).mkdir(parents=True)
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(command, 0, "", "")

    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 45678

    def fake_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        captured["cwd"] = cwd
        return FakeProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)
    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)

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
    assert ["git", "-C", str(repo_root), "worktree", "add", "-b"] == run_calls[1][:6]
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

    class FakeProvider:
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
        lambda **_: FakeProvider(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    def fake_run(
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

    class FakeProcess:
        pid = 45678

    def fake_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        captured["cwd"] = cwd
        return FakeProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)
    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)

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

    class FakeProvider:
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
        lambda **_: FakeProvider(),
    )
    popen_calls: list[list[str]] = []

    class FakeProcess:
        pid = 45678

    def fake_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        popen_calls.append(command)
        return FakeProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)

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

    class FakeProvider:
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
        lambda **_: FakeProvider(),
    )

    def fake_launch_managed_codex(*args: object, **kwargs: object) -> object:
        raise AssertionError("running planner-session should not be relaunched")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.launch_managed_codex",
        fake_launch_managed_codex,
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
    assert payload["llm_action"]["kind"] == "monitor"
    assert payload["llm_action"]["error"] == (
        "target already has running managed worker: planner-session"
    )
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": (
            "LLM 动作无效，已跳过执行："
            "target already has running managed worker: planner-session"
        ),
    }


def test_codex_supervisor_runner_supervise_llm_execute_can_request_context(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    docs_dir = workspace / "docs" / "current"
    docs_dir.mkdir(parents=True)
    (docs_dir / "status.md").write_text(
        "Supervisor 下一步节奏：由 LLM 主导，规则只做护栏。\n",
        encoding="utf-8",
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-source.jsonl",
        session_id="source-session",
        cwd=str(workspace),
        events=[_assistant_message("2026-05-16T11:59:20Z", "上一轮已完成。")],
    )

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"context_capability"' in content
            return json.dumps(
                {
                    "kind": "request_context",
                    "cwd": str(workspace),
                    "query": "Supervisor 下一步节奏",
                    "reason": "先查项目上下文再决定。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FakeProvider(),
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
            "--llm-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["llm_action"]["kind"] == "request_context"
    assert payload["executed"]["kind"] == "request_context"
    assert payload["executed"]["context"]["query"] == "Supervisor 下一步节奏"
    assert payload["executed"]["context"]["items"][0]["path"] == "docs/current/status.md"
    assert "LLM 主导" in payload["executed"]["context"]["items"][0]["text"]

    context_log = codex_home / "supervisor" / "context_results.jsonl"
    records = [
        json.loads(line)
        for line in context_log.read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["query"] == "Supervisor 下一步节奏"


def test_codex_supervisor_runner_supervise_request_context_replans_same_iteration(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    docs_dir = workspace / "docs" / "current"
    docs_dir.mkdir(parents=True)
    (docs_dir / "status.md").write_text(
        "Supervisor 同轮闭环：查完上下文后可以继续推进。\n",
        encoding="utf-8",
    )
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
        lambda session: "› 等待输入\n  gpt-5.5 xhigh · main",
    )

    class FakeProvider:
        calls = 0

        def summarize(self, messages: list[dict[str, str]]) -> str:
            self.calls += 1
            content = messages[1]["content"]
            if self.calls == 1:
                assert '"recent_context_results": []' in content
                return json.dumps(
                    {
                        "kind": "request_context",
                        "cwd": str(workspace),
                        "query": "Supervisor 同轮闭环",
                        "reason": "先查上下文再决定动作。",
                    },
                    ensure_ascii=False,
                )
            assert "Supervisor 同轮闭环" in content
            assert "docs/current/status.md" in content
            return json.dumps(
                {
                    "kind": "send_status",
                    "target_name": "lane-a",
                    "reason": "读到上下文后，立刻请求托管窗口汇报状态。",
                },
                ensure_ascii=False,
            )

    provider = FakeProvider()
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: provider,
    )
    calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
        timeout: int | None = None,
        cwd: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["git", "-C"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command and command[0].endswith("rg"):
            return subprocess.CompletedProcess(command, 1, "", "")
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

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
    assert payload["llm_action"]["kind"] == "request_context"
    assert payload["executed"]["kind"] == "request_context"
    assert payload["llm_followup_action"]["kind"] == "send_status"
    assert payload["followup_executed"]["kind"] == "send_status"
    assert calls == _tmux_send_calls(STATUS_REQUEST_TEXT)
    assert provider.calls == 2


def test_codex_supervisor_runner_supervise_respects_max_context_requests(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    docs_dir = workspace / "docs" / "current"
    docs_dir.mkdir(parents=True)
    (docs_dir / "status.md").write_text(
        "Supervisor 上下文预算：同一轮只能查一次。\n",
        encoding="utf-8",
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-source.jsonl",
        session_id="source-session",
        cwd=str(workspace),
        events=[_assistant_message("2026-05-16T11:59:20Z", "上一轮已完成。")],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    class FakeProvider:
        calls = 0

        def summarize(self, messages: list[dict[str, str]]) -> str:
            self.calls += 1
            if self.calls == 1:
                return json.dumps(
                    {
                        "kind": "request_context",
                        "cwd": str(workspace),
                        "query": "Supervisor 上下文预算",
                        "reason": "先查当前文档。",
                    },
                    ensure_ascii=False,
                )
            return json.dumps(
                {
                    "kind": "request_context",
                    "cwd": str(workspace),
                    "query": "Supervisor 上下文预算 第二次",
                    "reason": "还想继续查。",
                },
                ensure_ascii=False,
            )

    provider = FakeProvider()
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: provider,
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
            "--max-context-requests",
            "1",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["llm_action"]["kind"] == "request_context"
    assert payload["executed"]["kind"] == "request_context"
    assert payload["llm_followup_action"]["kind"] == "request_context"
    assert payload["followup_executed"] == {
        "kind": "request_context",
        "skipped": True,
        "reason": "context request budget exhausted",
        "context_request_count": 1,
        "max_context_requests": 1,
    }
    context_log = codex_home / "supervisor" / "context_results.jsonl"
    records = [
        json.loads(line)
        for line in context_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["query"] for record in records] == ["Supervisor 上下文预算"]
    assert provider.calls == 2


def test_codex_supervisor_runner_supervise_default_allows_context_followup(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    docs_dir = workspace / "docs" / "current"
    docs_dir.mkdir(parents=True)
    (docs_dir / "status.md").write_text(
        "Supervisor 默认预算要宽松，避免阻碍长任务。\n",
        encoding="utf-8",
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-source.jsonl",
        session_id="source-session",
        cwd=str(workspace),
        events=[_assistant_message("2026-05-16T11:59:20Z", "上一轮已完成。")],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    class FakeProvider:
        calls = 0

        def summarize(self, messages: list[dict[str, str]]) -> str:
            self.calls += 1
            return json.dumps(
                {
                    "kind": "request_context",
                    "cwd": str(workspace),
                    "query": f"默认宽松预算 {self.calls}",
                    "reason": "继续查上下文。",
                },
                ensure_ascii=False,
            )

    provider = FakeProvider()
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: provider,
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
    assert payload["executed"]["kind"] == "request_context"
    assert payload["followup_executed"]["kind"] == "request_context"
    assert "skipped" not in payload["followup_executed"]
    context_log = codex_home / "supervisor" / "context_results.jsonl"
    records = [
        json.loads(line)
        for line in context_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["query"] for record in records] == [
        "默认宽松预算 1",
        "默认宽松预算 2",
    ]
    assert provider.calls == 2


def test_codex_supervisor_runner_supervise_context_followup_can_ask_user_after_gate(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    docs_dir = workspace / "docs" / "current"
    docs_dir.mkdir(parents=True)
    (docs_dir / "status.md").write_text(
        "目录迁移文档和现有代码冲突，需要人工确认兼容策略。\n",
        encoding="utf-8",
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-needs-user.jsonl",
        session_id="019e35a2-e442-75e2-84ab-3761a685a736",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "\n".join(
                    [
                        "SUPERVISOR_STATUS: needs_user",
                        "SUPERVISOR_SUMMARY: 目录迁移有两种不可兼容方案。",
                        "SUPERVISOR_NEXT: 请用户拍板选择保留兼容层还是直接迁移。",
                    ]
                ),
            )
        ],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    class FakeProvider:
        calls = 0

        def summarize(self, messages: list[dict[str, str]]) -> str:
            self.calls += 1
            content = messages[1]["content"]
            if self.calls == 1:
                return json.dumps(
                    {
                        "kind": "request_context",
                        "cwd": str(workspace),
                        "query": "目录迁移 兼容策略",
                        "reason": "先查文档和现状再决定是否问用户。",
                    },
                    ensure_ascii=False,
                )
            assert "目录迁移文档和现有代码冲突" in content
            return json.dumps(
                {
                    "kind": "ask_user",
                    "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
                    "question": "目录迁移是保留兼容层，还是直接迁移并删除旧入口？",
                    "codex_requested_decision": True,
                    "instructions_exhausted": True,
                    "context_status": "conflict",
                    "reason": "Codex 明确要拍板，既有指示不足，文档和现状冲突。",
                },
                ensure_ascii=False,
            )

    provider = FakeProvider()
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: provider,
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
    assert payload["llm_action"]["kind"] == "request_context"
    assert payload["executed"]["kind"] == "request_context"
    assert payload["llm_followup_action"]["kind"] == "ask_user"
    followup = payload["followup_executed"]
    assert followup["kind"] == "ask_user"
    assert followup["requires_user"] is True
    assert followup["session_id"] == "019e35a2-e442-75e2-84ab-3761a685a736"
    assert followup["target_name"] == "resume-019e35a2"
    assert followup["question"] == "目录迁移是保留兼容层，还是直接迁移并删除旧入口？"
    assert followup["reason"] == "Codex 明确要拍板，既有指示不足，文档和现状冲突。"
    assert followup["context_status"] == "conflict"
    assert followup["gate"] == {
        "codex_requested_decision": True,
        "instructions_exhausted": True,
        "context_status": "conflict",
    }
    decision_request = followup["decision_request"]
    assert decision_request["event"] == "decision_request"
    assert decision_request["session_id"] == "019e35a2-e442-75e2-84ab-3761a685a736"
    assert decision_request["target_name"] == "resume-019e35a2"
    assert decision_request["question"] == "目录迁移是保留兼容层，还是直接迁移并删除旧入口？"
    assert decision_request["reason"] == "Codex 明确要拍板，既有指示不足，文档和现状冲突。"
    assert decision_request["context_status"] == "conflict"
    assert decision_request["gate"] == {
        "codex_requested_decision": True,
        "instructions_exhausted": True,
        "context_status": "conflict",
    }
    assert decision_request["request_id"].startswith("decision-")
    assert decision_request["created_at"]
    decision_log = codex_home / "supervisor" / "decision_requests.jsonl"
    records = [
        json.loads(line)
        for line in decision_log.read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["event"] == "decision_request"
    assert records[0]["question"] == "目录迁移是保留兼容层，还是直接迁移并删除旧入口？"
    assert provider.calls == 2


def test_codex_supervisor_context_request_prefers_rg_backend(tmp_path):
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
    calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        cwd: str,
        text: bool,
        capture_output: bool,
        check: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert cwd == str(workspace)
        assert text is True
        assert capture_output is True
        assert check is False
        assert timeout == 3
        assert "--json" in command
        assert "--glob" in command
        assert "!.worktrees/**" in command
        event = {
            "type": "match",
            "data": {
                "path": {"text": "docs/current/status.md"},
                "line_number": 1,
                "lines": {"text": "Supervisor 下一步节奏：由 LLM 主导。\n"},
                "submatches": [{"match": {"text": "Supervisor"}}],
            },
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(event), "")

    result = request_project_context(
        codex_home=codex_home,
        cwd=workspace,
        query="Supervisor 下一步节奏",
        run=fake_run,
        rg_bin="rg",
    )

    assert result.backend == "rg"
    assert result.items[0].path == "docs/current/status.md"
    assert "LLM 主导" in result.items[0].text
    assert calls


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

    def fake_run(
        command: list[str],
        *,
        cwd: str,
        text: bool,
        capture_output: bool,
        check: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, text, capture_output, check, timeout
        events = [
            {
                "type": "match",
                "data": {
                    "path": {"text": "src/isotope/features/supervisor/context.py"},
                    "line_number": 1,
                    "lines": {"text": "def request_project_context():\n"},
                    "submatches": [{"match": {"text": "request_context"}}],
                },
            },
            {
                "type": "match",
                "data": {
                    "path": {"text": "docs/current/status.md"},
                    "line_number": 3,
                    "lines": {
                        "text": (
                            "request_context ranked evidence 会给 LLM title path "
                            "snippet score match_reason。\n"
                        ),
                    },
                    "submatches": [
                        {"match": {"text": "request_context"}},
                        {"match": {"text": "ranked"}},
                        {"match": {"text": "evidence"}},
                    ],
                },
            },
        ]
        return subprocess.CompletedProcess(
            command,
            0,
            "\n".join(json.dumps(event) for event in events),
            "",
        )

    result = request_project_context(
        codex_home=codex_home,
        cwd=workspace,
        query="request_context ranked evidence",
        run=fake_run,
        rg_bin="rg",
        max_results=2,
    )

    first = result.items[0]
    assert result.backend == "rg"
    assert [item.score for item in result.items] == sorted(
        (item.score for item in result.items),
        reverse=True,
    )
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
    }

    recent = read_recent_context_results(codex_home=codex_home, cwd=workspace)
    assert recent[0].items[0].title == "Codex Supervisor Status"
    assert recent[0].items[0].snippet == first.snippet
    assert recent[0].items[0].match_reason == first.match_reason


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

    def fake_run(
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
        run=fake_run,
        rg_bin="rg",
        max_results=5,
    )

    paths = [item.path for item in result.items]
    assert result.backend == "rg"
    assert "docs/current/supervisor-capability-map.md" in paths
    assert "docs/current/status.md" in paths
    assert "docs/current/docs-map.md" in paths
    assert "src/isotope/features/supervisor/context.py" in paths
    assert all(len(item.snippet) <= 240 for item in result.items)
    assert any("project context anchor" in item.match_reason for item in result.items)


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

    assert result.backend == "python"
    assert result.items[0].path == "docs/note.md"


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

    class FakeProvider:
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

    provider = FakeProvider()
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
    assert json.loads(lines[0])["executed"]["kind"] == "request_context"
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

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            raise AssertionError("loop without active goals should not ask LLM to invent work")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FakeProvider(),
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


def test_codex_supervisor_runner_supervise_reports_no_managed_lane(
    tmp_path,
    capsys,
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

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["automation"] == {
        "ready": False,
        "managed_tmux_count": 0,
        "managed_process_count": 0,
        "managed_names": [],
        "reason": "当前没有托管的 Codex 进程或可旁观 tmux lane。",
        "launch_hint": "isotope-supervisor launch --name <name> --cwd <repo> --prompt '<task>'",
        "adopt_hint": "isotope-supervisor adopt --name <name> --cwd <repo> --tmux-session <session>",
    }
    assert payload["executed"]["reason"] == "no managed tmux lane"

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--auto-execute",
        ]
    )

    assert exit_code == 0
    text = capsys.readouterr().out
    assert "当前没有托管的 Codex 进程或可旁观 tmux lane。" in text
    assert "isotope-supervisor launch --name <name>" in text
    assert "isotope-supervisor adopt --name" in text


def test_codex_supervisor_runner_supervise_ignores_exited_managed_lane(
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
        lambda session: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_window_has_bell",
        lambda session: False,
    )
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["automation"]["ready"] is False
    assert payload["auto_action"] == {
        "kind": "monitor",
        "reason": "no managed tmux lane",
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "no managed tmux lane",
    }
    assert calls == []


def test_codex_supervisor_runner_supervise_plain_omits_exited_managed_lanes(
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
        lambda session: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_window_has_bell",
        lambda session: False,
    )

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--auto-execute",
        ]
    )

    text = capsys.readouterr().out
    assert exit_code == 0
    assert "managed:managed-001" not in text
    assert "托管：lane-a" not in text
    assert "已退出" not in text
    assert "工作中：0" in text


def test_codex_supervisor_runner_supervise_llm_execute_rejects_other_execute_modes(
    tmp_path,
    capsys,
):
    codex_home = tmp_path / ".codex"

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--llm-execute",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "codex_supervisor_runner_error"
    assert "cannot be used together" in payload["error"]["message"]


def test_codex_supervisor_runner_supervise_auto_waits_without_protocol_while_running(
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
        lambda session: "",
    )
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "monitor",
        "reason": "managed lane is running without ready signal",
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "managed lane is running without ready signal",
    }
    assert calls == []


def test_codex_supervisor_runner_supervise_auto_prefers_busy_terminal_over_old_done_link(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    prompt = "Supervisor 真实使用验收：检查 loop 行为，不要修改文件。"
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "lane-a",
                "cwd": str(workspace),
                "prompt": prompt,
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
    _write_session(
        codex_home,
        "2026/05/16/rollout-old-done.jsonl",
        session_id="old-done-session",
        cwd=str(workspace),
        events=[
            _user_message("2026-05-16T11:40:00Z", prompt),
            _assistant_message(
                "2026-05-16T11:45:00Z",
                "SUPERVISOR_STATUS: done\n"
                "SUPERVISOR_SUMMARY: 旧窗口已完成。\n"
                "SUPERVISOR_NEXT: 等待 Supervisor 归档。",
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
        lambda session: (
            "› Supervisor 真实使用验收：检查 loop 行为，不要修改文件。\n\n"
            "◦ Working (12s • esc to interrupt)\n\n"
            "› Implement {feature}\n"
            "  gpt-5.5 xhigh · main"
        ),
    )
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "monitor",
        "reason": "managed lane is running without ready signal",
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "managed lane is running without ready signal",
    }
    assert calls == []


def test_codex_supervisor_runner_supervise_auto_requests_status_when_terminal_ready(
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
        "2026/05/16/rollout-working.jsonl",
        session_id="working-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:30Z",
                "SUPERVISOR_STATUS: working\n"
                "SUPERVISOR_SUMMARY: 正在执行上一条任务。\n"
                "SUPERVISOR_NEXT: 等待完成。",
            )
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
        lambda session: (
            "To continue this session, run codex resume working-session\n"
            "• SUPERVISOR_STATUS: working\n"
            "  SUPERVISOR_SUMMARY: 正在执行上一条任务。\n"
            "  SUPERVISOR_NEXT: 等待完成。\n"
            "› Improve documentation in @filename\n"
            "  gpt-5.5 xhigh · Context 96% left · ~/Github/isotope · main"
        ),
    )
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "send_status",
        "reason": "managed terminal is ready for input",
    }
    assert payload["executed"]["kind"] == "send_status"
    assert payload["executed"]["text"] == STATUS_REQUEST_TEXT
    assert calls == _tmux_send_calls(STATUS_REQUEST_TEXT)


def test_codex_supervisor_runner_supervise_auto_name_targets_ready_lane(
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
        "\n".join(
            json.dumps(record, ensure_ascii=False)
            for record in [
                {
                    "record_id": "managed-a",
                    "name": "lane-a",
                    "cwd": str(workspace),
                    "prompt": "等待输入",
                    "command": ["tmux", "attach", "-t", "session-a"],
                    "pid": 0,
                    "started_at": NOW.isoformat(),
                    "log_path": str(codex_home / "supervisor" / "logs" / "a.log"),
                    "status": "adopted",
                    "backend": "tmux",
                    "tmux_session": "session-a",
                },
                {
                    "record_id": "managed-b",
                    "name": "lane-b",
                    "cwd": str(workspace),
                    "prompt": "等待输入",
                    "command": ["tmux", "attach", "-t", "session-b"],
                    "pid": 0,
                    "started_at": NOW.isoformat(),
                    "log_path": str(codex_home / "supervisor" / "logs" / "b.log"),
                    "status": "adopted",
                    "backend": "tmux",
                    "tmux_session": "session-b",
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_session_exists",
        lambda session: session in {"session-a", "session-b"},
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_window_has_bell",
        lambda session: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._tmux_capture_pane",
        lambda session: (
            "◦ Working (7m 52s • esc to interrupt)"
            if session == "session-a"
            else "› Improve documentation in @filename\n  gpt-5.5 xhigh · main"
        ),
    )
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--name",
            "lane-b",
            "--iterations",
            "1",
            "--interval",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "send_status",
        "reason": "managed terminal is ready for input",
    }
    assert payload["executed"]["managed"]["name"] == "lane-b"
    assert calls == _tmux_send_calls(
        STATUS_REQUEST_TEXT,
        buffer_name="isotope-supervisor-managed-b",
        target="session-b",
    )


def test_codex_supervisor_runner_supervise_auto_finds_ready_lane_after_running_lane(
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
        "\n".join(
            json.dumps(record, ensure_ascii=False)
            for record in [
                {
                    "record_id": "managed-a",
                    "name": "lane-a",
                    "cwd": str(workspace),
                    "prompt": "仍在运行",
                    "command": ["tmux", "attach", "-t", "session-a"],
                    "pid": 0,
                    "started_at": NOW.isoformat(),
                    "log_path": str(codex_home / "supervisor" / "logs" / "a.log"),
                    "status": "adopted",
                    "backend": "tmux",
                    "tmux_session": "session-a",
                },
                {
                    "record_id": "managed-b",
                    "name": "lane-b",
                    "cwd": str(workspace),
                    "prompt": "等待输入",
                    "command": ["tmux", "attach", "-t", "session-b"],
                    "pid": 0,
                    "started_at": NOW.isoformat(),
                    "log_path": str(codex_home / "supervisor" / "logs" / "b.log"),
                    "status": "adopted",
                    "backend": "tmux",
                    "tmux_session": "session-b",
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_session_exists",
        lambda session: session in {"session-a", "session-b"},
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_window_has_bell",
        lambda session: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._tmux_capture_pane",
        lambda session: (
            "◦ Working (7m 52s • esc to interrupt)"
            if session == "session-a"
            else "› Improve documentation in @filename\n  gpt-5.5 xhigh · main"
        ),
    )
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "send_status",
        "reason": "managed terminal is ready for input",
        "target_name": "lane-b",
    }
    assert payload["executed"]["managed"]["name"] == "lane-b"
    assert calls == _tmux_send_calls(
        STATUS_REQUEST_TEXT,
        buffer_name="isotope-supervisor-managed-b",
        target="session-b",
    )


def test_codex_supervisor_runner_supervise_auto_continues_done_lane(
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
        "2026/05/16/rollout-done.jsonl",
        session_id="done-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:30Z",
                "SUPERVISOR_STATUS: done\n"
                "SUPERVISOR_SUMMARY: 当前任务已完成。\n"
                "SUPERVISOR_NEXT: 可以继续下一步。",
            )
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
        lambda session: (
            "SUPERVISOR_STATUS: done\n"
            "SUPERVISOR_SUMMARY: 当前任务已完成。\n"
            "SUPERVISOR_NEXT: 可以继续下一步。"
        ),
    )
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "send_continue",
        "reason": "managed lane reported done",
    }
    assert payload["executed"]["kind"] == "send_continue"
    assert payload["executed"]["text"] == CONTINUE_REQUEST_TEXT
    assert calls == _tmux_send_calls(CONTINUE_REQUEST_TEXT)


def test_codex_supervisor_runner_supervise_auto_respects_max_continue_count(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    lane_state_path = codex_home / "supervisor" / "lane_state.json"
    lane_state_path.write_text(
        json.dumps(
            {
                "lane-a": {
                    "name": "lane-a",
                    "tmux_session": "isotope-lane-a",
                    "last_status": "done",
                    "last_prompted_at": "2026-05-16T11:59:00+00:00",
                    "prompt_count": 3,
                    "last_prompt_kind": "send_continue",
                    "continue_count": 3,
                }
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-done.jsonl",
        session_id="done-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:30Z",
                "SUPERVISOR_STATUS: done\n"
                "SUPERVISOR_SUMMARY: 当前任务已完成。\n"
                "SUPERVISOR_NEXT: 可以继续下一步。",
            )
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
        lambda session: (
            "SUPERVISOR_STATUS: done\n"
            "SUPERVISOR_SUMMARY: 当前任务已完成。\n"
            "SUPERVISOR_NEXT: 可以继续下一步。"
        ),
    )
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--prompt-cooldown",
            "0",
            "--max-continue-count",
            "3",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "monitor",
        "reason": "lane continue budget exhausted",
        "target_name": "lane-a",
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "lane continue budget exhausted",
    }
    assert calls == []


def test_codex_supervisor_runner_supervise_auto_respects_max_run_minutes(
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
        "2026/05/16/rollout-done.jsonl",
        session_id="done-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:30Z",
                "SUPERVISOR_STATUS: done\n"
                "SUPERVISOR_SUMMARY: 当前任务已完成。\n"
                "SUPERVISOR_NEXT: 可以继续下一步。",
            )
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
        lambda session: (
            "SUPERVISOR_STATUS: done\n"
            "SUPERVISOR_SUMMARY: 当前任务已完成。\n"
            "SUPERVISOR_NEXT: 可以继续下一步。"
        ),
    )
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--prompt-cooldown",
            "0",
            "--max-run-minutes",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "monitor",
        "reason": "lane run budget exhausted",
        "target_name": "lane-a",
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "lane run budget exhausted",
    }
    assert calls == []


def test_codex_supervisor_runner_supervise_default_allows_long_continue_lane(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    lane_state_path = codex_home / "supervisor" / "lane_state.json"
    lane_state_path.write_text(
        json.dumps(
            {
                "lane-a": {
                    "name": "lane-a",
                    "tmux_session": "isotope-lane-a",
                    "last_status": "done",
                    "last_prompted_at": "2026-05-16T11:59:00+00:00",
                    "prompt_count": 8,
                    "last_prompt_kind": "send_continue",
                    "continue_count": 8,
                }
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-done.jsonl",
        session_id="done-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:30Z",
                "SUPERVISOR_STATUS: done\n"
                "SUPERVISOR_SUMMARY: 长任务阶段完成。\n"
                "SUPERVISOR_NEXT: 可以继续下一段。",
            )
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
        lambda session: (
            "SUPERVISOR_STATUS: done\n"
            "SUPERVISOR_SUMMARY: 长任务阶段完成。\n"
            "SUPERVISOR_NEXT: 可以继续下一段。"
        ),
    )
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--prompt-cooldown",
            "0",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "send_continue",
        "reason": "managed lane reported done",
    }
    assert payload["executed"]["kind"] == "send_continue"
    assert payload["executed"]["text"] == CONTINUE_REQUEST_TEXT
    assert calls == _tmux_send_calls(CONTINUE_REQUEST_TEXT)


def test_codex_supervisor_runner_supervise_auto_stops_terminal_done_lane(
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
        "2026/05/16/rollout-terminal-done.jsonl",
        session_id="terminal-done-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:30Z",
                "SUPERVISOR_STATUS: done\n"
                "SUPERVISOR_SUMMARY: 本次任务已经完成。\n"
                "SUPERVISOR_NEXT: 等待 Supervisor 归档或下发新任务。",
            )
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
        lambda session: (
            "SUPERVISOR_STATUS: done\n"
            "SUPERVISOR_SUMMARY: 本次任务已经完成。\n"
            "SUPERVISOR_NEXT: 等待 Supervisor 归档或下发新任务。"
        ),
    )
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "monitor",
        "reason": "managed lane reported terminal done",
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "managed lane reported terminal done",
    }
    assert calls == []


def test_codex_supervisor_runner_supervise_auto_waits_on_blocked_lane(
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
        "2026/05/16/rollout-blocked.jsonl",
        session_id="blocked-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:30Z",
                "SUPERVISOR_STATUS: blocked\n"
                "SUPERVISOR_SUMMARY: 需要用户提供 API key。\n"
                "SUPERVISOR_NEXT: 等待用户处理。",
            )
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
        lambda session: (
            "SUPERVISOR_STATUS: blocked\n"
            "SUPERVISOR_SUMMARY: 需要用户提供 API key。\n"
            "SUPERVISOR_NEXT: 等待用户处理。"
        ),
    )
    calls: list[list[str]] = []

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.subprocess.run",
        lambda command, *, check, text, capture_output: subprocess.CompletedProcess(
            command, 0, "", ""
        )
        if command[:2] == ["git", "-C"]
        else calls.append(command) or subprocess.CompletedProcess(command, 0, "", ""),
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
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "monitor",
        "reason": "lane needs human attention",
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "lane needs human attention",
    }
    assert calls == []


def test_codex_supervisor_runner_supervise_bell_rings_for_human_attention(
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
        "2026/05/16/rollout-blocked.jsonl",
        session_id="blocked-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:30Z",
                "SUPERVISOR_STATUS: blocked\n"
                "SUPERVISOR_SUMMARY: 需要用户提供 API key。\n"
                "SUPERVISOR_NEXT: 等待用户处理。",
            )
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
        lambda session: (
            "SUPERVISOR_STATUS: blocked\n"
            "SUPERVISOR_SUMMARY: 需要用户提供 API key。\n"
            "SUPERVISOR_NEXT: 等待用户处理。"
        ),
    )
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda _: None)

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "2",
            "--interval",
            "1",
            "--auto-execute",
            "--bell",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == "\a"


def test_codex_supervisor_runner_supervise_bell_ignores_unmanaged_attention_when_lane_runs(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    other_workspace = tmp_path / "other"
    workspace.mkdir()
    other_workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    _write_session(
        codex_home,
        "2026/05/16/rollout-unmanaged-attention.jsonl",
        session_id="unmanaged-attention-session",
        cwd=str(other_workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:30Z",
                "需要你确认是否继续。",
            )
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
        lambda session: "",
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
            "--auto-execute",
            "--bell",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["auto_action"] == {
        "kind": "monitor",
        "reason": "managed lane is running without ready signal",
    }


def test_codex_supervisor_runner_supervise_bell_skips_auto_handled_continue(
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
        "2026/05/16/rollout-done.jsonl",
        session_id="done-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:30Z",
                "SUPERVISOR_STATUS: done\n"
                "SUPERVISOR_SUMMARY: 当前任务已完成。\n"
                "SUPERVISOR_NEXT: 可以继续下一步。",
            )
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
        lambda session: (
            "SUPERVISOR_STATUS: done\n"
            "SUPERVISOR_SUMMARY: 当前任务已完成。\n"
            "SUPERVISOR_NEXT: 可以继续下一步。"
        ),
    )
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--auto-execute",
            "--bell",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert calls == _tmux_send_calls(CONTINUE_REQUEST_TEXT)


def test_codex_supervisor_runner_execute_skips_repeated_prompt_in_cooldown(
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

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    first_exit = supervisor_main(
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
    first_payload = json.loads(capsys.readouterr().out)
    second_exit = supervisor_main(
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
    second_payload = json.loads(capsys.readouterr().out)

    assert first_exit == 0
    assert first_payload["executed"]["kind"] == "send_status"
    assert second_exit == 0
    assert second_payload["executed"]["skipped"] is True
    assert second_payload["executed"]["reason"] == "lane prompt cooldown active"
    assert second_payload["executed"]["lane_state"]["name"] == "lane-a"
    assert second_payload["executed"]["lane_state"]["prompt_count"] == 1
    assert calls == _tmux_send_calls(STATUS_REQUEST_TEXT)


def test_codex_supervisor_runner_supervise_auto_skips_cooldown_lane_for_next_action(
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
        "\n".join(
            json.dumps(record, ensure_ascii=False)
            for record in [
                {
                    "record_id": "managed-a",
                    "name": "lane-a",
                    "cwd": str(workspace),
                    "prompt": "刚被催过",
                    "command": ["tmux", "attach", "-t", "session-a"],
                    "pid": 0,
                    "started_at": NOW.isoformat(),
                    "log_path": str(codex_home / "supervisor" / "logs" / "a.log"),
                    "status": "adopted",
                    "backend": "tmux",
                    "tmux_session": "session-a",
                },
                {
                    "record_id": "managed-b",
                    "name": "lane-b",
                    "cwd": str(workspace),
                    "prompt": "等待继续",
                    "command": ["tmux", "attach", "-t", "session-b"],
                    "pid": 0,
                    "started_at": NOW.isoformat(),
                    "log_path": str(codex_home / "supervisor" / "logs" / "b.log"),
                    "status": "adopted",
                    "backend": "tmux",
                    "tmux_session": "session-b",
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    lane_state_path = codex_home / "supervisor" / "lane_state.json"
    lane_state_path.write_text(
        json.dumps(
            {
                "lane-a": {
                    "name": "lane-a",
                    "tmux_session": "session-a",
                    "last_status": "working",
                    "last_prompted_at": "2099-01-01T00:00:00+00:00",
                    "prompt_count": 1,
                }
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-lane-b.jsonl",
        session_id="lane-b-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:30Z",
                "SUPERVISOR_STATUS: done\n"
                "SUPERVISOR_SUMMARY: lane-b 已完成。\n"
                "SUPERVISOR_NEXT: 等待继续。",
            )
        ],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_session_exists",
        lambda session: session in {"session-a", "session-b"},
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_window_has_bell",
        lambda session: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._tmux_capture_pane",
        lambda session: (
            "› Improve documentation in @filename\n  gpt-5.5 xhigh · main"
            if session == "session-a"
            else "SUPERVISOR_STATUS: done\n"
            "SUPERVISOR_SUMMARY: lane-b 已完成。\n"
            "SUPERVISOR_NEXT: 等待继续。"
        ),
    )
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_action"] == {
        "kind": "send_continue",
        "reason": "managed lane reported done",
        "target_name": "lane-b",
    }
    assert payload["executed"]["managed"]["name"] == "lane-b"
    assert calls == _tmux_send_calls(
        CONTINUE_REQUEST_TEXT,
        buffer_name="isotope-supervisor-managed-b",
        target="session-b",
    )


def test_codex_supervisor_runner_execute_can_disable_prompt_cooldown(
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

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    for _ in range(2):
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
                "--prompt-cooldown",
                "0",
                "--json",
            ]
        )
        payload = json.loads(capsys.readouterr().out)
        assert exit_code == 0
        assert payload["executed"]["kind"] == "send_status"
        assert "skipped" not in payload["executed"]

    assert calls == _tmux_send_calls(STATUS_REQUEST_TEXT) + _tmux_send_calls(
        STATUS_REQUEST_TEXT
    )


def test_codex_supervisor_runner_supervise_plain_reports_skipped_prompt(
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
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.subprocess.run",
        lambda command, *, check, text, capture_output: subprocess.CompletedProcess(
            command, 0, "", ""
        ),
    )

    for _ in range(2):
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
            ]
        )
        assert exit_code == 0
        output = capsys.readouterr().out

    assert "已跳过：lane prompt cooldown active" in output
    assert "已执行：" not in output


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

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            assert "active-session" in messages[1]["content"]
            return "窗口 A 正在读文件，暂时不用介入。"

    captured: dict[str, object] = {}

    def fake_resolver(**kwargs: object) -> FakeProvider:
        captured.update(kwargs)
        return FakeProvider()

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        fake_resolver,
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


def test_codex_supervisor_runner_llm_summary_reports_missing_key(
    tmp_path,
    capsys,
    monkeypatch,
):
    # Point the TOML path to a non-existent file so the resolver has zero entries
    monkeypatch.setenv(
        "SUPERVISOR_LLM_POOL_TOML_FILES",
        str(tmp_path / "nonexistent.toml"),
    )
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
        [
            "scan",
            "--codex-home",
            str(codex_home),
            "--llm-summary",
            "--json",
        ]
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "codex_supervisor_runner_error"
    assert "LLM pool" in payload["error"]["message"]


def test_codex_supervisor_runner_watch_changes_only_suppresses_unchanged_reports(
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
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda _: None)

    exit_code = supervisor_main(
        [
            "watch",
            "--codex-home",
            str(codex_home),
            "--interval",
            "1",
            "--iterations",
            "2",
            "--changes-only",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert output.count("[Codex Supervisor]") == 1


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


def test_codex_supervisor_runner_watch_changes_only_prints_changed_reports(
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

    def change_session(_: int) -> None:
        _write_session(
            codex_home,
            "2026/05/16/rollout-active.jsonl",
            session_id="active-session",
            cwd="/home/lumber/Github/isotope",
            events=[_assistant_message("2026-05-16T11:59:40Z", "正在运行测试。")],
        )

    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", change_session)

    exit_code = supervisor_main(
        [
            "watch",
            "--codex-home",
            str(codex_home),
            "--interval",
            "1",
            "--iterations",
            "2",
            "--changes-only",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert output.count("[Codex Supervisor]") == 2
    assert "正在运行测试" in output


def test_codex_supervisor_runner_watch_bell_rings_for_attention(
    tmp_path,
    capsys,
    monkeypatch,
):
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
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda _: None)

    exit_code = supervisor_main(
        [
            "watch",
            "--codex-home",
            str(codex_home),
            "--interval",
            "1",
            "--iterations",
            "2",
            "--bell",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == "\a"
    assert captured.out.count("[Codex Supervisor]") == 2
    assert "先查看主动汇报阻塞的窗口" in captured.out


def test_codex_supervisor_runner_guide_prints_usable_workflow(tmp_path, capsys):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    exit_code = supervisor_main(
        [
            "guide",
            "--cwd",
            str(workspace),
            "--name",
            "doc-lane",
            "--tmux-session",
            "doc-tmux",
            "--prompt",
            "继续推进文档任务",
            "--interval",
            "30",
        ]
    )

    assert exit_code == 0
    text = capsys.readouterr().out
    assert "[Codex Supervisor 使用入口]" in text
    assert "isotope-supervisor resume --name doc-lane" in text
    assert "--session-id '<session-id>'" in text
    assert "--last --prompt '继续推进文档任务'" in text
    assert f"isotope-supervisor launch --name doc-lane --cwd {workspace}" in text
    assert (
        "isotope-supervisor launch --backend tmux --name doc-lane "
        "--tmux-session doc-tmux"
    ) in text
    assert f"--cwd {workspace}" in text
    assert "--prompt '继续推进文档任务'" in text
    assert (
        "isotope-supervisor adopt --name doc-lane "
        f"--cwd {workspace} --tmux-session doc-tmux"
    ) in text
    assert (
        "isotope-supervisor daemon start --interval 30 "
        "--worker-codex-model gpt-5.5 "
        "--worker-codex-config 'model_reasoning_effort=\"high\"'"
    ) in text
    assert (
        "isotope-supervisor loop --interval 30 "
        "--worker-codex-model gpt-5.5 "
        "--worker-codex-config 'model_reasoning_effort=\"high\"'"
    ) in text
    assert "isotope-supervisor web" in text
    assert "isotope-supervisor archive --name doc-lane" in text


def test_codex_supervisor_runner_guide_can_print_json(tmp_path, capsys):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    exit_code = supervisor_main(
        [
            "guide",
            "--cwd",
            str(workspace),
            "--name",
            "doc-lane",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["workflow"]["lane_name"] == "doc-lane"
    assert payload["workflow"]["tmux_session"] == "doc-lane"
    assert payload["workflow"]["cwd"] == str(workspace)
    assert payload["workflow"]["worker_codex_model"] == "gpt-5.5"
    assert payload["workflow"]["worker_codex_config"] == [
        'model_reasoning_effort="high"'
    ]
    assert payload["commands"]["resume"] == (
        "isotope-supervisor resume --name doc-lane "
        f"--cwd {workspace} --session-id '<session-id>' "
        "--prompt '继续推进当前任务，并在完成或阻塞时按 "
        "SUPERVISOR_STATUS/SUMMARY/NEXT 汇报。'"
    )
    assert payload["commands"]["resume_last"] == (
        "isotope-supervisor resume --name doc-lane "
        f"--cwd {workspace} --last --prompt '继续推进当前任务，并在完成或阻塞时按 "
        "SUPERVISOR_STATUS/SUMMARY/NEXT 汇报。'"
    )
    assert payload["commands"]["launch_process"] == (
        "isotope-supervisor launch --name doc-lane "
        f"--cwd {workspace} --prompt '继续推进当前任务，并在完成或阻塞时按 "
        "SUPERVISOR_STATUS/SUMMARY/NEXT 汇报。'"
    )
    assert payload["commands"]["supervise"] == (
        "isotope-supervisor loop --interval 30 "
        "--worker-codex-model gpt-5.5 "
        "--worker-codex-config 'model_reasoning_effort=\"high\"'"
    )
    assert payload["commands"]["daemon"] == (
        "isotope-supervisor daemon start --interval 30 "
        "--worker-codex-model gpt-5.5 "
        "--worker-codex-config 'model_reasoning_effort=\"high\"'"
    )
    assert payload["commands"]["archive"] == "isotope-supervisor archive --name doc-lane"


def test_codex_supervisor_runner_guide_can_override_worker_options(tmp_path, capsys):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    exit_code = supervisor_main(
        [
            "guide",
            "--cwd",
            str(workspace),
            "--name",
            "doc-lane",
            "--worker-codex-model",
            "gpt-5.4-mini",
            "--worker-codex-config",
            'model_reasoning_effort="low"',
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["workflow"]["worker_codex_model"] == "gpt-5.4-mini"
    assert payload["workflow"]["worker_codex_config"] == [
        'model_reasoning_effort="low"'
    ]
    assert payload["commands"]["daemon"] == (
        "isotope-supervisor daemon start --interval 30 "
        "--worker-codex-model gpt-5.4-mini "
        "--worker-codex-config 'model_reasoning_effort=\"low\"'"
    )


def test_codex_supervisor_runner_guide_can_use_light_worker_profile(tmp_path, capsys):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    exit_code = supervisor_main(
        [
            "guide",
            "--cwd",
            str(workspace),
            "--name",
            "doc-lane",
            "--worker-profile",
            "light",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["workflow"]["worker_profile"] == "light"
    assert payload["workflow"]["worker_codex_model"] == "gpt-5.5"
    assert payload["workflow"]["worker_codex_config"] == [
        'model_reasoning_effort="low"'
    ]
    assert payload["commands"]["supervise"] == (
        "isotope-supervisor loop --interval 30 "
        "--worker-codex-model gpt-5.5 "
        "--worker-codex-config 'model_reasoning_effort=\"low\"'"
    )


def test_codex_supervisor_runner_discover_lists_adoptable_tmux_codex_sessions(
    tmp_path,
    capsys,
    monkeypatch,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert text is True
        assert capture_output is True
        if command[:3] == ["tmux", "list-sessions", "-F"]:
            return subprocess.CompletedProcess(
                command,
                0,
                "iso_dev\t0\t1\nplain-shell\t1\t1\n",
                "",
            )
        if command[:3] == ["tmux", "capture-pane", "-p"]:
            session = command[4]
            panes = {
                "iso_dev": "› 好，下一步\n  gpt-5.5 xhigh · Context 80% left\n",
                "plain-shell": "vim README.md\n",
            }
            return subprocess.CompletedProcess(command, 0, panes[session], "")
        if command[:3] == ["tmux", "display-message", "-p"]:
            return subprocess.CompletedProcess(command, 0, str(workspace) + "\n", "")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "discover",
            "--cwd",
            str(workspace),
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["cwd"] == str(workspace)
    assert payload["candidates"] == [
        {
            "tmux_session": "iso_dev",
            "suggested_name": "iso-dev",
            "cwd": str(workspace),
            "attached": False,
            "windows": 1,
            "looks_like_codex": True,
            "reason": "pane text looks like Codex",
            "adopt_command": (
                "isotope-supervisor adopt --name iso-dev "
                f"--cwd {workspace} --tmux-session iso_dev"
            ),
            "attach_command": "tmux attach -t iso_dev",
            "excerpt": "› 好，下一步\n  gpt-5.5 xhigh · Context 80% left",
        }
    ]
    assert calls[0] == [
        "tmux",
        "list-sessions",
        "-F",
        "#{session_name}\t#{session_attached}\t#{session_windows}",
    ]


def test_codex_supervisor_runner_discover_treats_missing_tmux_socket_as_empty(
    tmp_path,
    capsys,
    monkeypatch,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def fake_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert command[:3] == ["tmux", "list-sessions", "-F"]
        assert check is False
        assert text is True
        assert capture_output is True
        return subprocess.CompletedProcess(
            command,
            1,
            "",
            "error connecting to /tmp/tmux-1001/default (No such file or directory)",
        )

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "discover",
            "--cwd",
            str(workspace),
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["candidates"] == []


def test_codex_supervisor_runner_discover_can_adopt_candidate_by_index(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        check: bool = False,
        text: bool,
        capture_output: bool,
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
                "› 继续开发 supervisor\n  gpt-5.5 xhigh · Context 80% left\n",
                "",
            )
        if command[:3] == ["tmux", "display-message", "-p"]:
            return subprocess.CompletedProcess(command, 0, str(workspace) + "\n", "")
        if command[:3] == ["tmux", "has-session", "-t"]:
            assert command[3] == "iso_dev"
            assert check is False
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:4] == ["tmux", "set-hook", "-t", "iso_dev"]:
            assert check is True
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:2] == ["git", "-C"]:
            return subprocess.CompletedProcess(command, 0, "main\n", "")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "discover",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--adopt-index",
            "1",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["adopted_candidate"]["tmux_session"] == "iso_dev"
    assert payload["managed"]["name"] == "iso-dev"
    assert payload["managed"]["status"] == "adopted"
    assert payload["managed"]["backend"] == "tmux"
    assert payload["managed"]["tmux_session"] == "iso_dev"
    assert payload["next_commands"] == {
        "attach": "tmux attach -t iso_dev",
        "loop": "isotope-supervisor loop --interval 30",
        "archive": "isotope-supervisor archive --name iso-dev",
    }
    records = [
        json.loads(line)
        for line in (codex_home / "supervisor" / "managed_sessions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert records == [payload["managed"]]


def test_codex_supervisor_runner_discover_can_adopt_first_candidate(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def fake_run(
        command: list[str],
        *,
        check: bool = False,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert text is True
        assert capture_output is True
        if command[:3] == ["tmux", "list-sessions", "-F"]:
            return subprocess.CompletedProcess(command, 0, "iso_dev\t0\t1\n", "")
        if command[:3] == ["tmux", "capture-pane", "-p"]:
            return subprocess.CompletedProcess(
                command,
                0,
                "› 继续开发 supervisor\n  gpt-5.5 xhigh · Context 80% left\n",
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "discover",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--adopt-first",
        ]
    )

    assert exit_code == 0
    text = capsys.readouterr().out
    assert "已接管：iso-dev / tmux=iso_dev" in text
    assert "监督：isotope-supervisor loop --interval 30" in text


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

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)
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


def test_codex_supervisor_runner_loop_auto_executes_even_when_report_unchanged(
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
        lambda session: "› Improve documentation in @filename\n  gpt-5.5 xhigh · main",
    )
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

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
            "--rule-execute",
            "--prompt-cooldown",
            "0",
            "--json",
        ]
    )

    assert exit_code == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 2
    assert [json.loads(line)["executed"]["kind"] for line in lines] == [
        "send_status",
        "send_status",
    ]
    assert calls == _tmux_send_calls(STATUS_REQUEST_TEXT) + _tmux_send_calls(
        STATUS_REQUEST_TEXT
    )


def test_codex_supervisor_runner_daemon_start_spawns_background_loop(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 45678

    def fake_popen(
        command: list[str],
        *,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        captured["stdin"] = stdin
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return FakeProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        fake_popen,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda _: False,
    )

    exit_code = supervisor_main(
        [
            "daemon",
            "start",
            "--codex-home",
            str(codex_home),
            "--interval",
            "7",
            "--limit",
            "3",
            "--worker-codex-model",
            "gpt-5.4-mini",
            "--worker-codex-config",
            'model_reasoning_effort="low"',
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["daemon"]["status"] == "running"
    assert payload["daemon"]["pid"] == 45678
    assert payload["daemon"]["codex_home"] == str(codex_home)
    assert payload["daemon"]["log_path"].endswith("daemon.log")
    assert payload["daemon"]["command"] == [
        sys.executable,
        "-u",
        "-m",
        "isotope.features.supervisor.runner",
        "loop",
        "--codex-home",
        str(codex_home),
        "--interval",
        "7",
        "--limit",
        "3",
        "--worker-codex-model",
        "gpt-5.4-mini",
        "--worker-codex-config",
        'model_reasoning_effort="low"',
    ]
    assert captured["command"] == payload["daemon"]["command"]
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["stderr"] is subprocess.STDOUT
    assert captured["start_new_session"] is True

    state_path = codex_home / "supervisor" / "daemon.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    persisted = dict(payload["daemon"])
    persisted.pop("action")
    assert state == persisted


def test_codex_supervisor_runner_daemon_start_defaults_to_strong_worker(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 45678

    def fake_popen(
        command: list[str],
        *,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        return FakeProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        fake_popen,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda _: False,
    )

    exit_code = supervisor_main(
        [
            "daemon",
            "start",
            "--codex-home",
            str(codex_home),
            "--interval",
            "7",
            "--limit",
            "3",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["daemon"]["command"] == [
        sys.executable,
        "-u",
        "-m",
        "isotope.features.supervisor.runner",
        "loop",
        "--codex-home",
        str(codex_home),
        "--interval",
        "7",
        "--limit",
        "3",
        "--worker-codex-model",
        "gpt-5.5",
        "--worker-codex-config",
        'model_reasoning_effort="high"',
    ]
    assert captured["command"] == payload["daemon"]["command"]


def test_codex_supervisor_runner_daemon_start_queues_goal_instead_of_repeating_explicit_goal(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    goal = "持续跟进 isotope 的 Supervisor worker。"
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 45680

    def fake_popen(
        command: list[str],
        *,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        return FakeProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        fake_popen,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda _: False,
    )

    exit_code = supervisor_main(
        [
            "daemon",
            "start",
            "--codex-home",
            str(codex_home),
            "--interval",
            "7",
            "--limit",
            "3",
            "--goal",
            goal,
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "--goal" not in payload["daemon"]["command"]
    assert payload["daemon"]["queued_goal"]["goal"] == goal
    assert payload["daemon"]["queued_goal"]["cwd"] == str(Path.cwd())
    assert payload["daemon"]["command"] == [
        sys.executable,
        "-u",
        "-m",
        "isotope.features.supervisor.runner",
        "loop",
        "--codex-home",
        str(codex_home),
        "--interval",
        "7",
        "--limit",
        "3",
        "--worker-codex-model",
        "gpt-5.5",
        "--worker-codex-config",
        'model_reasoning_effort="high"',
    ]
    assert captured["command"] == payload["daemon"]["command"]


def test_codex_supervisor_runner_daemon_start_uses_goal_queue_dynamically(
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
            "后台 loop 动态读取目标队列。",
            "--json",
        ]
    )
    assert exit_code == 0
    capsys.readouterr()
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 45682

    def fake_popen(
        command: list[str],
        *,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        return FakeProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        fake_popen,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda _: False,
    )

    exit_code = supervisor_main(
        [
            "daemon",
            "start",
            "--codex-home",
            str(codex_home),
            "--interval",
            "7",
            "--limit",
            "3",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "--goal" not in payload["daemon"]["command"]
    assert captured["command"] == payload["daemon"]["command"]


def test_codex_supervisor_runner_up_starts_daemon_with_strong_worker_defaults(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 45678

    def fake_popen(
        command: list[str],
        *,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        captured["stdin"] = stdin
        captured["stderr"] = stderr
        return FakeProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        fake_popen,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda _: False,
    )

    exit_code = supervisor_main(
        [
            "up",
            "--codex-home",
            str(codex_home),
            "--interval",
            "7",
            "--limit",
            "3",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["daemon"]["action"] == "started"
    assert payload["daemon"]["command"] == [
        sys.executable,
        "-u",
        "-m",
        "isotope.features.supervisor.runner",
        "loop",
        "--codex-home",
        str(codex_home),
        "--interval",
        "7",
        "--limit",
        "3",
        "--worker-codex-model",
        "gpt-5.5",
        "--worker-codex-config",
        'model_reasoning_effort="high"',
    ]
    assert payload["daemon"]["activity"] == {
        "recent_llm_action": None,
        "recent_execution": None,
        "recent_worker": None,
    }
    assert captured["command"] == payload["daemon"]["command"]


def test_codex_supervisor_runner_up_goal_enters_persistent_queue(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    goal = "用日常入口启动后自动消费目标。"
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 45683

    def fake_popen(
        command: list[str],
        *,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        return FakeProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        fake_popen,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda _: False,
    )

    exit_code = supervisor_main(
        [
            "up",
            "--codex-home",
            str(codex_home),
            "--interval",
            "7",
            "--limit",
            "3",
            "--goal",
            goal,
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "--goal" not in payload["daemon"]["command"]
    assert payload["daemon"]["queued_goal"]["goal"] == goal
    assert payload["daemon"]["queued_goal"]["cwd"] == str(Path.cwd())
    assert payload["daemon"]["activity"]["active_goals"][0]["goal"] == goal
    assert payload["daemon"]["activity"]["active_goals"][0]["cwd"] == str(Path.cwd())
    assert captured["command"] == payload["daemon"]["command"]


def test_codex_supervisor_runner_loop_defaults_to_llm_driver(
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
        lambda session: "› 等待输入\n  gpt-5.5 xhigh · main",
    )
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"allowed_kinds"' in content
            assert '"managed_terminal_ready": true' in content
            return '{"kind":"send_status","target_name":"lane-a","reason":"让 LLM 决定本轮节奏。"}'

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FakeProvider(),
    )
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

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
    assert [payload["llm_action"]["kind"] for payload in payloads] == [
        "send_status",
        "send_status",
    ]
    assert [payload["executed"]["kind"] for payload in payloads] == [
        "send_status",
        "send_status",
    ]
    assert "auto_action" not in payloads[0]
    assert calls == _tmux_send_calls(STATUS_REQUEST_TEXT) + _tmux_send_calls(
        STATUS_REQUEST_TEXT
    )


def test_codex_supervisor_runner_loop_reports_process_backend_as_managed(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-process-001",
                "name": "process-lane",
                "cwd": str(workspace),
                "prompt": "后台继续推进 Supervisor。",
                "command": [
                    "codex",
                    "exec",
                    "-C",
                    str(workspace),
                    "--skip-git-repo-check",
                    "后台继续推进 Supervisor。",
                ],
                "pid": 4242,
                "started_at": NOW.isoformat(),
                "log_path": str(
                    codex_home / "supervisor" / "logs" / "managed-process-001.log"
                ),
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
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert f'"available_workspaces": ["{workspace}"]' in content
            assert "process-lane" in content
            return '{"kind":"monitor","reason":"后台 process lane 正在运行，继续观察。"}'

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FakeProvider(),
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
    assert payload["automation"]["ready"] is True
    assert payload["automation"]["managed_process_count"] == 1
    assert payload["automation"]["managed_tmux_count"] == 0
    assert payload["automation"]["managed_names"] == ["process-lane"]
    assert "tmux lane" not in payload["automation"]["reason"]
    assert "后台托管 Codex 进程" in payload["automation"]["reason"]
    assert payload["llm_action"] == {
        "kind": "monitor",
        "target_name": None,
        "reason": "后台 process lane 正在运行，继续观察。",
        "command_suggestion": None,
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "reason": "后台 process lane 正在运行，继续观察。",
        "skipped": True,
    }


def test_codex_supervisor_runner_loop_does_not_reprompt_completed_process_worker(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = codex_home / "supervisor" / "logs" / "managed-process-001.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: worker 已完成实现和验证。\n"
        "SUPERVISOR_NEXT: 建议主控复查 diff 后进入合并流程。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-process-001",
                "name": "process-lane",
                "cwd": str(workspace),
                "prompt": "后台继续推进 Supervisor。",
                "command": ["codex", "exec", "-C", str(workspace), "后台继续推进。"],
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
        lambda pid: False,
    )
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    class FailingProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            raise AssertionError("completed process worker should not be reprompted")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FailingProvider(),
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


def test_codex_supervisor_runner_loop_goal_can_launch_first_worker(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    goal = "实现 Supervisor goal 入口，并补最小测试。"
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert f'"available_workspaces": ["{workspace}"]' in content
            assert goal in content
            assert '"kind": "launch_session"' in content
            return json.dumps(
                {
                    "kind": "launch_session",
                    "target_name": "goal-worker",
                    "cwd": str(workspace),
                    "prompt": goal,
                    "reason": "用户给了明确目标，启动新 worker 推进。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FakeProvider(),
    )
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 45679

    def fake_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        captured["cwd"] = cwd
        captured["stdin"] = stdin
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return FakeProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)

    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--workspace-root",
            str(workspace),
            "--goal",
            goal,
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
    assert payload["llm_action"]["kind"] == "launch_session"
    assert payload["llm_action"]["prompt"] == goal
    assert payload["executed"]["kind"] == "launch_session"
    assert payload["executed"]["managed"]["name"] == "goal-worker"
    assert payload["executed"]["managed"]["pid"] == 45679
    assert payload["executed"]["worktree"] == {
        "enabled": False,
        "source_cwd": str(workspace),
        "cwd": str(workspace),
        "reason": "not_git_repo",
    }
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
    assert captured["command"][9].startswith("WORK ORDER")
    assert f"goal: {goal}" in captured["command"][9]
    assert captured["cwd"] == str(workspace)
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["stderr"] is subprocess.STDOUT
    assert captured["start_new_session"] is True


def test_codex_supervisor_runner_loop_uses_persisted_goal_queue(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    goal = "让 Supervisor 自动消费持久目标队列。"
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
            "goal-supervisor",
            "--json",
        ]
    )
    assert exit_code == 0
    add_payload = json.loads(capsys.readouterr().out)
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert f'"available_workspaces": ["{workspace}"]' in content
            assert goal in content
            assert '"target_name": "goal-supervisor"' in content
            return json.dumps(
                {
                    "kind": "launch_session",
                    "target_name": "goal-supervisor",
                    "cwd": str(workspace),
                    "prompt": goal,
                    "reason": "队列里有活跃目标，启动 worker 推进。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FakeProvider(),
    )
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 45681

    def fake_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        captured["cwd"] = cwd
        return FakeProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)

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
    assert payload["active_goals"] == add_payload["active_goals"]
    assert payload["llm_action"]["kind"] == "launch_session"
    assert payload["llm_action"]["target_name"] == "goal-supervisor"
    assert payload["executed"]["managed"]["name"] == "goal-supervisor"
    assert payload["executed"]["worktree"]["cwd"] == str(workspace)
    assert captured["command"][9].startswith("WORK ORDER")
    assert f"goal: {goal}" in captured["command"][9]


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


def test_codex_supervisor_runner_daemon_status_includes_active_goal_status(
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
            "daemon status 展示目标状态。",
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
        "SUPERVISOR_STATUS: needs_user\n"
        "SUPERVISOR_SUMMARY: 需要确认验收范围。\n"
        "SUPERVISOR_NEXT: 等待用户确认。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "goal-supervisor",
                "cwd": str(workspace),
                "prompt": "daemon status 展示目标状态。",
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
    state_path = codex_home / "supervisor" / "daemon.json"
    state_path.write_text(
        json.dumps(
            {
                "pid": 45678,
                "status": "running",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": None,
                "command": [sys.executable, "-m", "isotope.features.supervisor.runner"],
                "codex_home": str(codex_home),
                "log_path": str(codex_home / "supervisor" / "logs" / "daemon.log"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda pid: pid == 45678,
    )

    exit_code = supervisor_main(
        ["daemon", "status", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    item = payload["daemon"]["activity"]["active_goals"][0]
    assert item["target_name"] == "goal-supervisor"
    assert item["last_status"] == "needs_user"
    assert item["last_summary"] == "需要确认验收范围。"
    assert item["last_next"] == "等待用户确认。"


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

    class FakeProvider:
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

    provider = FakeProvider()
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
    assert payload["llm_action"]["kind"] == "request_context"
    assert payload["executed"]["kind"] == "request_context"
    assert payload["executed"]["context"]["query"] == "Supervisor 目标阻塞后如何继续推进"
    assert payload["llm_followup_action"]["kind"] == "monitor"


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

    class FakeProvider:
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

    provider = FakeProvider()
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
    assert payload["llm_action"]["kind"] == "request_context"
    assert payload["executed"]["kind"] == "request_context"
    assert payload["llm_followup_action"]["kind"] == "ask_user"
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
    assert payload["llm_action"] == {
        "kind": "monitor",
        "target_name": None,
        "reason": "LLM 动作无效，已跳过执行：No LLM pool entries found",
        "command_suggestion": None,
        "error": "No LLM pool entries found",
    }
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

    class FakeProvider:
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

    provider = FakeProvider()
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: provider,
    )
    calls: list[list[str]] = []

    def fake_run(
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

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
    assert [payload["llm_action"]["target_name"] for payload in payloads] == [
        "lane-a",
        "lane-b",
    ]
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


def test_codex_supervisor_runner_supervise_resume_respects_prompt_cooldown(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_session(
        codex_home,
        "2026/05/16/rollout-resume-cooldown.jsonl",
        session_id="019e35a2-e442-75e2-84ab-3761a685a736",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:50:00Z",
                "正在整理 Supervisor 验收结果。",
            )
        ],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )
    monkeypatch.setattr("isotope.features.supervisor.runner._sleep", lambda seconds: None)

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return json.dumps(
                {
                    "kind": "resume_session",
                    "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
                    "prompt_kind": "send_status",
                    "reason": "先恢复会话汇报状态。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FakeProvider(),
    )
    popen_calls: list[list[str]] = []

    class FakeProcess:
        pid = 34567

    def fake_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        popen_calls.append(command)
        return FakeProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)

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
        "resume_session",
        "resume_session",
    ]
    assert payloads[0]["executed"]["managed"]["name"] == "resume-019e35a2"
    assert payloads[1]["executed"]["skipped"] is True
    assert payloads[1]["executed"]["reason"] == "resume prompt cooldown active"
    assert len(popen_calls) == 1


def test_codex_supervisor_runner_supervise_invalid_llm_action_falls_back_to_monitor(
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
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "SUPERVISOR_STATUS: done\nSUPERVISOR_SUMMARY: 已完成。\nSUPERVISOR_NEXT: 可以继续下一步。",
            )
        ],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return json.dumps(
                {
                    "kind": "resume_session",
                    "session_id": "done-session",
                    "prompt_kind": "send_status",
                    "reason": "模型误选了已完成会话。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FakeProvider(),
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
    assert payload["llm_action"] == {
        "kind": "monitor",
        "target_name": None,
        "reason": "LLM 动作无效，已跳过执行：unknown resumable session for LLM action: done-session",
        "command_suggestion": None,
        "error": "unknown resumable session for LLM action: done-session",
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "LLM 动作无效，已跳过执行：unknown resumable session for LLM action: done-session",
    }


def test_codex_supervisor_runner_supervise_llm_provider_failure_falls_back_to_monitor(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_session(
        codex_home,
        "2026/05/16/rollout-working.jsonl",
        session_id="working-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "正在整理 Supervisor 验收结果。",
            )
        ],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    class FailingProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            raise ValueError(
                "All LLM pool entries failed: pool:ValueError(empty model response)"
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FailingProvider(),
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
    assert payload["llm_action"] == {
        "kind": "monitor",
        "target_name": None,
        "reason": (
            "LLM 动作无效，已跳过执行：All LLM pool entries failed: "
            "pool:ValueError(empty model response)"
        ),
        "command_suggestion": None,
        "error": "All LLM pool entries failed: pool:ValueError(empty model response)",
    }
    assert payload["executed"]["kind"] == "monitor"
    assert payload["executed"]["skipped"] is True


def test_codex_supervisor_runner_daemon_status_marks_existing_loop_running(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    state_path = codex_home / "supervisor" / "daemon.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "pid": 45678,
                "status": "running",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": None,
                "command": ["python", "-m", "isotope.features.supervisor.runner", "loop"],
                "codex_home": str(codex_home),
                "log_path": str(codex_home / "supervisor" / "logs" / "daemon.log"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda pid: pid == 45678,
    )

    exit_code = supervisor_main(
        ["daemon", "status", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["daemon"]["status"] == "running"
    assert payload["daemon"]["pid"] == 45678
    assert payload["daemon"]["state_path"] == str(state_path)


def test_codex_supervisor_runner_daemon_status_includes_recent_activity(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = codex_home / "supervisor" / "daemon.json"
    log_path = codex_home / "supervisor" / "logs" / "daemon.log"
    worker_log_path = codex_home / "supervisor" / "logs" / "managed-001.log"
    state_path.parent.mkdir(parents=True)
    log_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "pid": 45678,
                "status": "running",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": None,
                "command": [
                    sys.executable,
                    "-u",
                    "-m",
                    "isotope.features.supervisor.runner",
                    "loop",
                    "--worker-codex-model",
                    "gpt-5.5",
                    "--worker-codex-config",
                    'model_reasoning_effort="high"',
                ],
                "codex_home": str(codex_home),
                "log_path": str(log_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    log_path.write_text(
        "\n".join(
            [
                "[LLM 白名单动作]",
                "launch_session / 需要启动新会话继续推进。",
                "已执行：isotope-supervisor launch --name planner-session",
                "[LLM 白名单动作]",
                "launch_session / 同名任务仍在冷却。",
                "已跳过：launch prompt cooldown active",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    worker_log_path.write_text(
        "FAKE CODEX worker invoked\n"
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: worker 已完成状态汇报。\n"
        "SUPERVISOR_NEXT: 等待 Supervisor 归档。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "planner-session",
                "cwd": str(workspace),
                "prompt": "继续推进",
                "command": [
                    "codex",
                    "exec",
                    "-m",
                    "gpt-5.5",
                    "-c",
                    'model_reasoning_effort="high"',
                    "-C",
                    str(workspace),
                    "--skip-git-repo-check",
                    "继续推进",
                ],
                "pid": 45679,
                "started_at": "2026-05-18T10:01:00+00:00",
                "log_path": str(worker_log_path),
                "status": "launched",
                "backend": "process",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda pid: pid == 45678,
    )

    exit_code = supervisor_main(
        ["daemon", "status", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    activity = payload["daemon"]["activity"]
    assert activity["recent_llm_action"] == {
        "kind": "launch_session",
        "reason": "同名任务仍在冷却。",
    }
    assert activity["recent_execution"] == {
        "status": "skipped",
        "detail": "launch prompt cooldown active",
    }
    assert activity["recent_worker"]["name"] == "planner-session"
    assert activity["recent_worker"]["model"] == "gpt-5.5"
    assert activity["recent_worker"]["config"] == ['model_reasoning_effort="high"']
    assert activity["recent_worker"]["status"] == "done"
    assert activity["recent_worker"]["summary"] == "worker 已完成状态汇报。"
    assert activity["recent_worker"]["next"] == "等待 Supervisor 归档。"


def test_codex_supervisor_runner_daemon_status_marks_exited_worker_not_working(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = codex_home / "supervisor" / "daemon.json"
    worker_log_path = codex_home / "supervisor" / "logs" / "managed-001.log"
    state_path.parent.mkdir(parents=True)
    worker_log_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "pid": 45678,
                "status": "stopped",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": "2026-05-18T10:05:00+00:00",
                "command": [sys.executable, "-m", "isotope.features.supervisor.runner"],
                "codex_home": str(codex_home),
                "log_path": str(codex_home / "supervisor" / "logs" / "daemon.log"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    worker_log_path.write_text(
        "SUPERVISOR_STATUS: working\n"
        "SUPERVISOR_SUMMARY: 正在读取项目状态。\n"
        "SUPERVISOR_NEXT: 继续读取项目状态并判断下一步。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "planner-session",
                "cwd": str(workspace),
                "prompt": "继续推进",
                "command": ["codex", "exec", "-C", str(workspace), "继续推进"],
                "pid": 45679,
                "started_at": "2026-05-18T10:01:00+00:00",
                "log_path": str(worker_log_path),
                "status": "launched",
                "backend": "process",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda pid: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._pid_is_running",
        lambda pid: False,
        raising=False,
    )

    exit_code = supervisor_main(
        ["daemon", "status", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    worker = payload["daemon"]["activity"]["recent_worker"]
    assert worker["status"] == "exited"
    assert worker["summary"] == "正在读取项目状态。"


def test_codex_supervisor_runner_up_reports_existing_daemon_activity(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = codex_home / "supervisor" / "daemon.json"
    log_path = codex_home / "supervisor" / "logs" / "daemon.log"
    worker_log_path = codex_home / "supervisor" / "logs" / "managed-001.log"
    state_path.parent.mkdir(parents=True)
    log_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "pid": 45678,
                "status": "running",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": None,
                "command": ["python", "-u", "-m", "isotope.features.supervisor.runner", "loop"],
                "codex_home": str(codex_home),
                "log_path": str(log_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    log_path.write_text(
        "[LLM 白名单动作]\n"
        "launch_session / 最近启动了托管 worker。\n"
        "已执行：isotope-supervisor launch --name planner-session\n",
        encoding="utf-8",
    )
    worker_log_path.write_text(
        "SUPERVISOR_STATUS: done\n"
        "SUPERVISOR_SUMMARY: up 入口活动展示完成。\n"
        "SUPERVISOR_NEXT: 等待归档。\n",
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "planner-session",
                "cwd": str(workspace),
                "prompt": "继续推进",
                "command": [
                    "codex",
                    "exec",
                    "-m",
                    "gpt-5.5",
                    "-c",
                    'model_reasoning_effort="high"',
                    "-C",
                    str(workspace),
                    "--skip-git-repo-check",
                    "继续推进",
                ],
                "pid": 45679,
                "started_at": "2026-05-18T10:01:00+00:00",
                "log_path": str(worker_log_path),
                "status": "launched",
                "backend": "process",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda pid: pid == 45678,
    )

    exit_code = supervisor_main(["up", "--codex-home", str(codex_home), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["daemon"]["action"] == "already_running"
    assert payload["daemon"]["activity"]["recent_llm_action"] == {
        "kind": "launch_session",
        "reason": "最近启动了托管 worker。",
    }
    assert payload["daemon"]["activity"]["recent_worker"]["model"] == "gpt-5.5"
    assert payload["daemon"]["activity"]["recent_worker"]["status"] == "done"


def test_codex_supervisor_runner_daemon_stop_terminates_and_marks_stopped(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    state_path = codex_home / "supervisor" / "daemon.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "pid": 45678,
                "status": "running",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": None,
                "command": ["python", "-m", "isotope.features.supervisor.runner", "loop"],
                "codex_home": str(codex_home),
                "log_path": str(codex_home / "supervisor" / "logs" / "daemon.log"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda pid: pid == 45678,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.os.kill",
        lambda pid, signal_number: killed.append((pid, signal_number)),
    )

    exit_code = supervisor_main(
        ["daemon", "stop", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["daemon"]["status"] == "stopped"
    assert payload["daemon"]["pid"] == 45678
    assert payload["daemon"]["state_path"] == str(state_path)
    assert killed == [(45678, signal.SIGTERM)]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "stopped"
    assert state["stopped_at"] is not None


def test_codex_supervisor_runner_daemon_watchdog_restarts_stale_loop(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    state_path = codex_home / "supervisor" / "daemon.json"
    log_path = codex_home / "supervisor" / "logs" / "daemon.log"
    command = [
        sys.executable,
        "-m",
        "isotope.features.supervisor.runner",
        "loop",
        "--codex-home",
        str(codex_home),
        "--interval",
        "7",
    ]
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "pid": 11111,
                "status": "running",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": None,
                "command": command,
                "codex_home": str(codex_home),
                "log_path": str(log_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 22222

    def fake_popen(
        command_: list[str],
        *,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command_
        captured["stdin"] = stdin
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return FakeProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda pid: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        fake_popen,
    )

    exit_code = supervisor_main(
        ["daemon", "watchdog", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["daemon"]["action"] == "restarted"
    assert payload["daemon"]["previous_pid"] == 11111
    assert payload["daemon"]["pid"] == 22222
    assert payload["daemon"]["status"] == "running"
    assert payload["daemon"]["command"] == command
    assert captured["command"] == command
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["stderr"] is subprocess.STDOUT
    assert captured["start_new_session"] is True
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["pid"] == 22222
    assert persisted["command"] == command
    assert "action" not in persisted
    assert "previous_pid" not in persisted


def test_codex_supervisor_runner_daemon_watchdog_leaves_live_loop_alone(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    state_path = codex_home / "supervisor" / "daemon.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "pid": 45678,
                "status": "running",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": None,
                "command": ["python", "-m", "isotope.features.supervisor.runner", "loop"],
                "codex_home": str(codex_home),
                "log_path": str(codex_home / "supervisor" / "logs" / "daemon.log"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    def fail_popen(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("watchdog must not restart a live daemon")

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda pid: pid == 45678,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        fail_popen,
    )

    exit_code = supervisor_main(
        ["daemon", "watchdog", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["daemon"]["action"] == "alive"
    assert payload["daemon"]["pid"] == 45678
    assert payload["daemon"]["status"] == "running"


def test_codex_supervisor_runner_daemon_watcher_start_spawns_periodic_watchdog(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 33333

    def fake_popen(
        command: list[str],
        *,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        captured["stdin"] = stdin
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return FakeProcess()

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda _pid: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.subprocess.Popen",
        fake_popen,
    )

    exit_code = supervisor_main(
        [
            "daemon",
            "watcher",
            "start",
            "--codex-home",
            str(codex_home),
            "--interval",
            "5",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    expected_command = [
        sys.executable,
        "-m",
        "isotope.features.supervisor.runner",
        "daemon",
        "watcher",
        "run",
        "--codex-home",
        str(codex_home),
        "--interval",
        "5",
    ]
    assert payload["status"] == "ok"
    assert payload["watcher"]["action"] == "started"
    assert payload["watcher"]["status"] == "running"
    assert payload["watcher"]["pid"] == 33333
    assert payload["watcher"]["command"] == expected_command
    assert payload["watcher"]["log_path"].endswith("watcher.log")
    assert payload["watcher"]["state_path"].endswith("watcher.json")
    assert captured["command"] == expected_command
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["stderr"] is subprocess.STDOUT
    assert captured["start_new_session"] is True

    state = json.loads(
        (codex_home / "supervisor" / "watcher.json").read_text(encoding="utf-8")
    )
    persisted = dict(payload["watcher"])
    persisted.pop("action")
    assert state == persisted


def test_codex_supervisor_runner_daemon_watcher_run_calls_watchdog_periodically(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    calls: list[str] = []

    def fake_watchdog(*, codex_home: Path) -> dict[str, object]:
        calls.append(str(codex_home))
        return {
            "action": "alive" if len(calls) == 1 else "restarted",
            "pid": 10000 + len(calls),
            "status": "running",
        }

    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.watchdog_supervisor_daemon",
        fake_watchdog,
    )
    monkeypatch.setattr("isotope.features.supervisor.daemon._sleep", lambda _seconds: None)

    exit_code = supervisor_main(
        [
            "daemon",
            "watcher",
            "run",
            "--codex-home",
            str(codex_home),
            "--interval",
            "5",
            "--iterations",
            "2",
            "--json",
        ]
    )

    assert exit_code == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert calls == [str(codex_home), str(codex_home)]
    assert [line["watchdog"]["action"] for line in lines] == ["alive", "restarted"]
    assert [line["iteration"] for line in lines] == [1, 2]


def test_codex_supervisor_runner_daemon_watcher_stop_marks_stopped(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    state_path = codex_home / "supervisor" / "watcher.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "pid": 33333,
                "status": "running",
                "started_at": "2026-05-18T10:00:00+00:00",
                "stopped_at": None,
                "command": [
                    sys.executable,
                    "-m",
                    "isotope.features.supervisor.runner",
                    "daemon",
                    "watcher",
                    "run",
                ],
                "codex_home": str(codex_home),
                "log_path": str(codex_home / "supervisor" / "logs" / "watcher.log"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda pid: pid == 33333,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon.os.kill",
        lambda pid, signal_number: killed.append((pid, signal_number)),
    )

    exit_code = supervisor_main(
        ["daemon", "watcher", "stop", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["watcher"]["status"] == "stopped"
    assert payload["watcher"]["pid"] == 33333
    assert killed == [(33333, signal.SIGTERM)]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "stopped"
    assert state["stopped_at"] is not None


def test_codex_supervisor_runner_launch_records_managed_codex(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 12345

    def fake_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        captured["cwd"] = cwd
        captured["stdin"] = stdin
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return FakeProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)

    exit_code = supervisor_main(
        [
            "launch",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--name",
            "lane-a",
            "--prompt",
            "继续实现 supervisor",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["managed"]["name"] == "lane-a"
    assert payload["managed"]["pid"] == 12345
    assert payload["managed"]["cwd"] == str(workspace)
    assert payload["managed"]["prompt"] == "继续实现 supervisor"
    assert payload["managed"]["log_path"].endswith(".log")
    assert captured["command"][:5] == [
        "codex",
        "exec",
        "-C",
        str(workspace),
        "--skip-git-repo-check",
    ]
    assert captured["command"][5].startswith("继续实现 supervisor")
    assert "SUPERVISOR_STATUS" in captured["command"][5]
    assert "SUPERVISOR_SUMMARY" in captured["command"][5]
    assert "SUPERVISOR_NEXT" in captured["command"][5]
    assert payload["managed"]["prompt"] == "继续实现 supervisor"
    assert captured["cwd"] == str(workspace)
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["stderr"] is subprocess.STDOUT
    assert captured["start_new_session"] is True

    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    records = [
        json.loads(line)
        for line in registry_path.read_text(encoding="utf-8").splitlines()
    ]
    assert records == [payload["managed"]]


def test_codex_supervisor_runner_launch_can_override_codex_worker_options(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 12346

    def fake_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        return FakeProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)

    exit_code = supervisor_main(
        [
            "launch",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--name",
            "lane-a",
            "--prompt",
            "低成本检查",
            "--codex-model",
            "gpt-5.4-mini",
            "--codex-config",
            'model_reasoning_effort="low"',
            "--json",
        ]
    )

    assert exit_code == 0
    json.loads(capsys.readouterr().out)
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


def test_codex_supervisor_runner_launch_can_use_tmux_backend(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert check is True
        assert text is True
        assert capture_output is True
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "launch",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--name",
            "lane-a",
            "--prompt",
            "继续实现 supervisor",
            "--backend",
            "tmux",
            "--tmux-session",
            "isotope-lane-a",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["managed"]["backend"] == "tmux"
    assert payload["managed"]["tmux_session"] == "isotope-lane-a"
    assert payload["managed"]["pid"] == 0
    assert calls[0][:7] == [
        "tmux",
        "new-session",
        "-d",
        "-s",
        "isotope-lane-a",
        "-c",
        str(workspace),
    ]
    assert "codex --cd " + str(workspace) + " --no-alt-screen" in calls[0][7]
    assert "继续实现 supervisor" in calls[0][7]
    assert "SUPERVISOR_STATUS" in calls[0][7]
    assert calls[1][:4] == ["tmux", "set-hook", "-t", "isotope-lane-a"]
    assert calls[1][4] == "alert-bell"
    assert "bell_events.jsonl" in calls[1][5]
    assert "lane-a" in calls[1][5]


def test_codex_supervisor_runner_resume_exec_records_managed_codex(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 23456

    def fake_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        captured["cwd"] = cwd
        captured["stdin"] = stdin
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return FakeProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)

    exit_code = supervisor_main(
        [
            "resume",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--name",
            "lane-a",
            "--session-id",
            "019e35a2-e442-75e2-84ab-3761a685a736",
            "--prompt",
            "继续推进 supervisor 前端测试",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["managed"]["name"] == "lane-a"
    assert payload["managed"]["backend"] == "codex_exec_resume"
    assert payload["managed"]["pid"] == 23456
    assert payload["managed"]["resume_session_id"] == (
        "019e35a2-e442-75e2-84ab-3761a685a736"
    )
    assert payload["managed"]["resume_last"] is False
    assert captured["command"][:6] == [
        "codex",
        "exec",
        "-C",
        str(workspace),
        "--skip-git-repo-check",
        "resume",
    ]
    assert captured["command"][6] == "019e35a2-e442-75e2-84ab-3761a685a736"
    assert captured["command"][7].startswith("继续推进 supervisor 前端测试")
    assert "SUPERVISOR_STATUS" in captured["command"][7]
    assert captured["cwd"] == str(workspace)
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["stderr"] is subprocess.STDOUT
    assert captured["start_new_session"] is True

    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    records = [
        json.loads(line)
        for line in registry_path.read_text(encoding="utf-8").splitlines()
    ]
    assert records == [payload["managed"]]


def test_codex_supervisor_runner_resume_can_override_codex_worker_options(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 23458

    def fake_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        return FakeProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)

    exit_code = supervisor_main(
        [
            "resume",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--name",
            "lane-a",
            "--session-id",
            "019e35a2-e442-75e2-84ab-3761a685a736",
            "--prompt",
            "低成本恢复",
            "--codex-model",
            "gpt-5.4-mini",
            "--codex-config",
            'model_reasoning_effort="low"',
            "--json",
        ]
    )

    assert exit_code == 0
    json.loads(capsys.readouterr().out)
    assert captured["command"][:10] == [
        "codex",
        "exec",
        "-m",
        "gpt-5.4-mini",
        "-c",
        'model_reasoning_effort="low"',
        "-C",
        str(workspace),
        "--skip-git-repo-check",
        "resume",
    ]


def test_codex_supervisor_runner_resume_exec_last_uses_last_flag(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 23457

    def fake_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> FakeProcess:
        captured["command"] = command
        captured["cwd"] = cwd
        captured["stdin"] = stdin
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return FakeProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fake_popen)

    exit_code = supervisor_main(
        [
            "resume",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--name",
            "latest",
            "--last",
            "--prompt",
            "请汇报当前状态",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["managed"]["backend"] == "codex_exec_resume"
    assert payload["managed"]["resume_session_id"] is None
    assert payload["managed"]["resume_last"] is True
    assert captured["command"][:7] == [
        "codex",
        "exec",
        "-C",
        str(workspace),
        "--skip-git-repo-check",
        "resume",
        "--last",
    ]
    assert captured["command"][7].startswith("请汇报当前状态")


def test_codex_supervisor_runner_adopt_registers_existing_tmux_session(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        text: bool,
        capture_output: bool,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert text is True
        assert capture_output is True
        assert check is (command[:2] == ["tmux", "set-hook"])
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "adopt",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--name",
            "lane-a",
            "--tmux-session",
            "isotope-lane-a",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["managed"]["name"] == "lane-a"
    assert payload["managed"]["status"] == "adopted"
    assert payload["managed"]["backend"] == "tmux"
    assert payload["managed"]["tmux_session"] == "isotope-lane-a"
    assert payload["managed"]["prompt"] == "接管已有 tmux 会话"
    assert calls[0] == ["tmux", "has-session", "-t", "isotope-lane-a"]
    assert calls[1][:4] == ["tmux", "set-hook", "-t", "isotope-lane-a"]
    assert calls[1][4] == "alert-bell"
    assert "bell_events.jsonl" in calls[1][5]
    assert "lane-a" in calls[1][5]

    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    records = [
        json.loads(line)
        for line in registry_path.read_text(encoding="utf-8").splitlines()
    ]
    assert records == [payload["managed"]]


def test_codex_supervisor_runner_repair_hooks_installs_for_existing_tmux_records(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        text: bool,
        capture_output: bool,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert text is True
        assert capture_output is True
        assert check is (command[:2] == ["tmux", "set-hook"])
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        ["repair-hooks", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "status": "ok",
        "repairs": [
            {
                "name": "lane-a",
                "tmux_session": "isotope-lane-a",
                "status": "installed",
                "message": None,
            }
        ],
    }
    assert calls[0] == ["tmux", "has-session", "-t", "isotope-lane-a"]
    assert calls[1][:4] == ["tmux", "set-hook", "-t", "isotope-lane-a"]
    assert calls[1][4] == "alert-bell"
    assert "bell_events.jsonl" in calls[1][5]
    assert "lane-a" in calls[1][5]


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


def test_codex_supervisor_runner_send_text_to_tmux_managed_session(
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
    calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert check is True
        assert text is True
        assert capture_output is True
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "send",
            "--codex-home",
            str(codex_home),
            "--name",
            "lane-a",
            "--text",
            "继续",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "managed": {
            "name": "lane-a",
            "record_id": "managed-001",
            "tmux_session": "isotope-lane-a",
        },
        "status": "ok",
        "text": "继续",
    }
    assert calls == _tmux_send_calls("继续")


def test_codex_supervisor_runner_send_rejects_non_tmux_managed_session(
    tmp_path,
    capsys,
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
                "prompt": "继续实现 supervisor",
                "command": ["codex", "--cd", str(workspace), "--no-alt-screen", "继续"],
                "pid": 12345,
                "started_at": "2026-05-16T11:59:30+00:00",
                "log_path": str(codex_home / "supervisor" / "logs" / "managed-001.log"),
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
            "send",
            "--codex-home",
            str(codex_home),
            "--name",
            "lane-a",
            "--text",
            "继续",
            "--json",
        ]
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "codex_supervisor_runner_error"
    assert "tmux" in payload["error"]["message"]


def test_codex_supervisor_llm_messages_use_compact_session_context(tmp_path):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-active.jsonl",
        session_id="active-session",
        cwd="/home/lumber/Github/isotope",
        events=[
            _user_message("2026-05-16T11:58:00Z", "帮我继续做 supervisor"),
            _assistant_message("2026-05-16T11:59:00Z", "正在运行测试。"),
        ],
    )
    report = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW).scan()

    messages = build_llm_summary_messages(report)

    assert messages[0]["role"] == "system"
    assert "中文" in messages[0]["content"]
    assert "active-session" in messages[1]["content"]
    assert '"recommendation"' in messages[1]["content"]
    assert '"action": "monitor"' in messages[1]["content"]
    assert "source_path" not in messages[1]["content"]
    assert len(messages[1]["content"]) < 1500


def test_codex_supervisor_pooled_provider_strips_thinking():
    captured: dict[str, object] = {}

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout: int,
    ) -> dict[str, object]:
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        return {
            "choices": [
                {
                    "message": {
                        "content": "<think>hidden</think>\n窗口 A 正在测试，建议继续观察。"
                    }
                }
            ],
            "usage": {"total_tokens": 42},
        }

    provider = PooledSummaryProvider(
        entries=(
            PoolEntry(
                provider="fake",
                api_key="fake-key",
                base_url="https://fake-chat.example.com/v1",
                model="fake-model",
            ),
        ),
        transport=transport,
    )

    summary = provider.summarize([{"role": "user", "content": "hello"}])

    assert summary == "窗口 A 正在测试，建议继续观察。"
    assert captured["url"] == "https://fake-chat.example.com/v1/chat/completions"
    assert captured["headers"] == {
        "Authorization": "Bearer fake-key",
        "Content-Type": "application/json",
    }
    assert captured["payload"] == {
        "model": "fake-model",
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0,
        "max_tokens": 2048,
        "stream": False,
    }


def test_codex_supervisor_pooled_provider_calls_openai_compatible_shape():
    """PooledSummaryProvider works for any OpenAI-compatible endpoint."""
    captured: dict[str, object] = {}

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout: int,
    ) -> dict[str, object]:
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        return {
            "id": "chatcmpl_test",
            "model": "deepseek-chat",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "窗口 A 正在测试。"},
                }
            ],
            "usage": {"total_tokens": 12},
        }

    provider = PooledSummaryProvider(
        entries=(
            PoolEntry(
                provider="fake",
                api_key="fake-key",
                base_url="https://fake-openai.example.com",
                model="fake-chat-v1",
            ),
        ),
        transport=transport,
    )

    assert provider.summarize([{"role": "user", "content": "hello"}]) == "窗口 A 正在测试。"
    assert captured["url"] == "https://fake-openai.example.com/chat/completions"
    assert captured["payload"]["temperature"] == 0
    assert captured["headers"]["Authorization"] == "Bearer fake-key"


def test_codex_supervisor_pooled_provider_falls_back_during_summary():
    captured: dict[str, object] = {}
    call_count = [0]

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout: int,
    ) -> dict[str, object]:
        call_count[0] += 1
        if "dead.invalid" in url:
            raise ValueError("connection refused")
        captured["url"] = url
        captured["payload"] = payload
        return {
            "choices": [{"message": {"content": "备用 provider 摘要"}}],
            "usage": {"total_tokens": 12},
        }

    provider = PooledSummaryProvider(
        entries=(
            PoolEntry(
                provider="dead",
                api_key="sk-dead",
                base_url="https://api.dead.invalid",
                model="dead-model",
            ),
            PoolEntry(
                provider="fallback",
                api_key="sk-fallback",
                base_url="https://api.fallback.example.com/v1",
                model="fallback-model",
            ),
        ),
        transport=transport,
    )

    assert provider.summarize([{"role": "user", "content": "hello"}]) == "备用 provider 摘要"
    assert captured["url"] == "https://api.fallback.example.com/v1/chat/completions"
    assert captured["payload"]["model"] == "fallback-model"
    assert call_count[0] == 2


def test_codex_supervisor_pooled_provider_reports_safe_failure_details():
    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout: int,
    ) -> dict[str, object]:
        raise ValueError(f"connection refused for {headers['Authorization']}")

    provider = PooledSummaryProvider(
        entries=(
            PoolEntry(
                provider="dead",
                api_key="sk-secret-dead",
                base_url="https://api.dead.invalid",
                model="dead-model",
            ),
        ),
        transport=transport,
    )

    with pytest.raises(ValueError) as exc_info:
        provider.summarize([{"role": "user", "content": "hello"}])

    message = str(exc_info.value)
    assert "dead:ValueError(connection refused for Bearer sk-..." in message
    assert "sk-secret-dead" not in message


def test_codex_supervisor_env_resolver_loads_pool_entries_from_agents_format(tmp_path):
    """Resolver reads [[agents]]/[[agents.providers]] format."""
    toml_path = tmp_path / "pool.toml"
    toml_path.write_text(
        """\
[[agents]]
name = "supervisor"

[[agents.providers]]
provider = "provider-a"
base_url = "https://api.provider-a.example.com"
model = "model-a"
api_keys = ["env:PROVIDER_A_KEY"]

[[agents.providers]]
provider = "provider-b"
base_url = "https://api.provider-b.example.com/v1"
model = "model-b"
api_keys = ["env:PROVIDER_B_KEY"]
""",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout: int,
    ) -> dict[str, object]:
        captured["url"] = url
        captured["payload"] = payload
        return {
            "choices": [{"message": {"content": "第一条 provider 摘要"}}],
            "usage": {"total_tokens": 12},
        }

    provider = resolve_summary_provider_from_env(
        {
            "SUPERVISOR_LLM_POOL_TOML_FILES": str(toml_path),
            "PROVIDER_A_KEY": "sk-provider-a",
            "PROVIDER_B_KEY": "sk-provider-b",
        },
        transport=transport,
    )

    assert provider.summarize([{"role": "user", "content": "hello"}]) == "第一条 provider 摘要"
    assert captured["url"] == "https://api.provider-a.example.com/chat/completions"
    assert captured["payload"]["model"] == "model-a"


def test_codex_supervisor_pool_accepts_plaintext_keys(tmp_path):
    """Plaintext api_keys entries are used directly without env lookup."""
    toml_path = tmp_path / "pool.toml"
    toml_path.write_text(
        """\
[[keys]]
base_url = "https://api.provider-a.example.com"
model = "model-a"
api_keys = ["sk-plaintext-direct"]
""",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout: int,
    ) -> dict[str, object]:
        captured["url"] = url
        captured["headers"] = headers
        return {
            "choices": [{"message": {"content": "plaintext ok"}}],
            "usage": {"total_tokens": 12},
        }

    provider = resolve_summary_provider_from_env(
        {"SUPERVISOR_LLM_POOL_TOML_FILES": str(toml_path)},
        transport=transport,
    )

    assert provider.summarize([{"role": "user", "content": "hello"}]) == "plaintext ok"
    assert captured["headers"]["Authorization"] == "Bearer sk-plaintext-direct"


def test_codex_supervisor_env_resolver_falls_back_between_pool_entries(tmp_path):
    toml_path = tmp_path / "pool.toml"
    toml_path.write_text(
        """\
[[keys]]
base_url = "https://api.dead.invalid"
model = "dead-model"
api_keys = ["env:DEAD_KEY"]

[[keys]]
base_url = "https://api.fallback.example.com/v1"
model = "fallback-model"
api_keys = ["env:FALLBACK_KEY"]
""",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}
    call_count = [0]

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout: int,
    ) -> dict[str, object]:
        call_count[0] += 1
        if "dead.invalid" in url:
            raise ValueError("connection refused")
        captured["url"] = url
        captured["payload"] = payload
        return {
            "choices": [{"message": {"content": "备用 provider 摘要"}}],
            "usage": {"total_tokens": 12},
        }

    provider = resolve_summary_provider_from_env(
        {
            "SUPERVISOR_LLM_POOL_TOML_FILES": str(toml_path),
            "DEAD_KEY": "sk-dead",
            "FALLBACK_KEY": "sk-fallback",
        },
        transport=transport,
    )

    assert provider.summarize([{"role": "user", "content": "hello"}]) == "备用 provider 摘要"
    assert captured["url"] == "https://api.fallback.example.com/v1/chat/completions"
    assert captured["payload"]["model"] == "fallback-model"
    assert call_count[0] == 2


def test_codex_supervisor_env_resolver_combines_multiple_pool_files(tmp_path):
    first_path = tmp_path / "first.toml"
    second_path = tmp_path / "second.toml"
    first_path.write_text(
        """\
[[agents]]
name = "supervisor"

[[agents.providers]]
base_url = "https://api.dead.invalid"
model = "dead-model"
api_keys = ["env:DEAD_KEY"]
""",
        encoding="utf-8",
    )
    second_path.write_text(
        """\
[[agents]]
name = "supervisor"

[[agents.providers]]
base_url = "https://api.fallback.example.com/v1"
model = "fallback-model"
api_keys = ["env:FALLBACK_KEY"]
""",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}
    call_count = [0]

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout: int,
    ) -> dict[str, object]:
        call_count[0] += 1
        if "dead.invalid" in url:
            raise ValueError("connection refused")
        captured["url"] = url
        captured["payload"] = payload
        return {
            "choices": [{"message": {"content": "跨文件兜底摘要"}}],
            "usage": {"total_tokens": 12},
        }

    provider = resolve_summary_provider_from_env(
        {
            "SUPERVISOR_LLM_POOL_TOML_FILES": f"{first_path},{second_path}",
            "DEAD_KEY": "sk-dead",
            "FALLBACK_KEY": "sk-fallback",
        },
        agent_name="supervisor",
        transport=transport,
    )

    assert provider.summarize([{"role": "user", "content": "hello"}]) == "跨文件兜底摘要"
    assert captured["url"] == "https://api.fallback.example.com/v1/chat/completions"
    assert captured["payload"]["model"] == "fallback-model"
    assert call_count[0] == 2


def test_codex_supervisor_env_resolver_filters_by_agent_name(tmp_path):
    """When agent_name is given, only matching [[agents]] providers are loaded."""
    toml_path = tmp_path / "pool.toml"
    toml_path.write_text(
        """\
[[agents]]
name = "supervisor"

[[agents.providers]]
base_url = "https://api.supervisor.example.com"
model = "supervisor-model"
api_keys = ["env:SUPERVISOR_KEY"]

[[agents]]
name = "codex_runner"

[[agents.providers]]
base_url = "https://api.runner.example.com"
model = "runner-model"
api_keys = ["env:RUNNER_KEY"]
""",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout: int,
    ) -> dict[str, object]:
        captured["url"] = url
        captured["payload"] = payload
        return {
            "choices": [{"message": {"content": "supervisor 摘要"}}],
            "usage": {"total_tokens": 12},
        }

    provider = resolve_summary_provider_from_env(
        {
            "SUPERVISOR_LLM_POOL_TOML_FILES": str(toml_path),
            "SUPERVISOR_KEY": "sk-supervisor",
            "RUNNER_KEY": "sk-runner",
        },
        agent_name="supervisor",
        transport=transport,
    )

    assert provider.summarize([{"role": "user", "content": "hello"}]) == "supervisor 摘要"
    assert captured["url"] == "https://api.supervisor.example.com/chat/completions"
    assert captured["payload"]["model"] == "supervisor-model"


def test_codex_supervisor_env_resolver_agent_not_found_raises(tmp_path):
    """When agent_name doesn't match any [[agents]], resolver raises."""
    toml_path = tmp_path / "pool.toml"
    toml_path.write_text(
        """\
[[agents]]
name = "supervisor"

[[agents.providers]]
base_url = "https://api.supervisor.example.com"
model = "supervisor-model"
api_keys = ["env:SUPERVISOR_KEY"]
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="for agent 'unknown'"):
        resolve_summary_provider_from_env(
            {
                "SUPERVISOR_LLM_POOL_TOML_FILES": str(toml_path),
                "SUPERVISOR_KEY": "sk-supervisor",
            },
            agent_name="unknown",
        )


def test_codex_supervisor_pooled_provider_uses_per_entry_max_tokens():
    """When PoolEntry has max_tokens, it overrides the global default."""
    captured: dict[str, object] = {}

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout: int,
    ) -> dict[str, object]:
        captured["payload"] = payload
        return {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"total_tokens": 12},
        }

    provider = PooledSummaryProvider(
        entries=(
            PoolEntry(
                provider="fake",
                api_key="fake-key",
                base_url="https://fake-reasoning.example.com",
                model="reasoning-model",
                max_tokens=2048,
            ),
        ),
        max_tokens=512,  # global default
        transport=transport,
    )

    provider.summarize([{"role": "user", "content": "hello"}])
    assert captured["payload"]["max_tokens"] == 2048


def test_codex_supervisor_pooled_provider_falls_back_max_tokens_to_global():
    """When PoolEntry has no max_tokens, global default is used."""
    captured: dict[str, object] = {}

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout: int,
    ) -> dict[str, object]:
        captured["payload"] = payload
        return {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"total_tokens": 12},
        }

    provider = PooledSummaryProvider(
        entries=(
            PoolEntry(
                provider="fake",
                api_key="fake-key",
                base_url="https://fake.example.com",
                model="fake-model",
            ),
        ),
        max_tokens=256,
        transport=transport,
    )

    provider.summarize([{"role": "user", "content": "hello"}])
    assert captured["payload"]["max_tokens"] == 256


def test_codex_supervisor_env_resolver_reads_per_provider_max_tokens_from_toml(tmp_path):
    """Resolver reads optional max_tokens from TOML and passes it through."""
    toml_path = tmp_path / "pool.toml"
    toml_path.write_text(
        """\
[[keys]]
base_url = "https://api.reasoning.example.com"
model = "reasoning-model"
max_tokens = 4096
api_keys = ["env:REASONING_KEY"]
""",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout: int,
    ) -> dict[str, object]:
        captured["payload"] = payload
        return {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"total_tokens": 12},
        }

    provider = resolve_summary_provider_from_env(
        {
            "SUPERVISOR_LLM_POOL_TOML_FILES": str(toml_path),
            "REASONING_KEY": "sk-reasoning",
        },
        transport=transport,
    )

    provider.summarize([{"role": "user", "content": "hello"}])
    assert captured["payload"]["max_tokens"] == 4096


def test_codex_supervisor_env_resolver_rejects_invalid_max_tokens_in_toml(tmp_path):
    """Non-positive or non-integer max_tokens in TOML raises ValueError."""
    toml_path = tmp_path / "pool.toml"
    toml_path.write_text(
        """\
[[keys]]
base_url = "https://api.example.com"
model = "bad-model"
max_tokens = 0
api_keys = ["env:KEY"]
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="max_tokens must be a positive integer"):
        resolve_summary_provider_from_env(
            {
                "SUPERVISOR_LLM_POOL_TOML_FILES": str(toml_path),
                "KEY": "sk-test",
            },
        )


def test_codex_supervisor_generate_llm_summary_returns_provider_text(tmp_path):
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
    report = CodexSupervisorFlow(codex_home=codex_home, now=lambda: NOW).scan()

    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            assert "active-session" in messages[1]["content"]
            return "窗口 A 正在读文件，暂时不用介入。"

    assert generate_llm_summary(report, FakeProvider()) == "窗口 A 正在读文件，暂时不用介入。"


def _add_supervisor_goal(
    capsys,
    *,
    codex_home: Path,
    workspace: Path,
    goal: str,
    target_name: str,
) -> dict[str, object]:
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
    return json.loads(capsys.readouterr().out)["goal"]


def _write_session(
    codex_home: Path,
    relative_path: str,
    *,
    session_id: str,
    cwd: str,
    events: list[dict[str, object]],
    meta: dict[str, object] | None = None,
) -> Path:
    path = codex_home / "sessions" / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        {
            "timestamp": "2026-05-16T11:45:00Z",
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "cwd": cwd,
                "cli_version": "0.130.0",
                "model_provider": "openai",
                **(meta or {}),
            },
        },
        *events,
    ]
    path.write_text(
        "\n".join(json.dumps(line, ensure_ascii=False) for line in lines) + "\n",
        encoding="utf-8",
    )
    return path


def _write_session_index(
    codex_home: Path,
    *,
    session_id: str,
    thread_name: str,
    updated_at: str = "2026-05-16T11:59:20Z",
) -> None:
    path = codex_home / "session_index.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "id": session_id,
        "thread_name": thread_name,
        "updated_at": updated_at,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")


def _write_state_threads(codex_home: Path, *, session_id: str, title: str) -> None:
    path = codex_home / "state_5.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "create table threads (id text primary key, title text, updated_at integer)"
        )
        connection.execute(
            "insert into threads (id, title, updated_at) values (?, ?, ?)",
            (session_id, title, 1778324108),
        )
        connection.commit()
    finally:
        connection.close()


def _write_managed_tmux_record(
    codex_home: Path,
    *,
    workspace: Path,
    append: bool = False,
    name: str = "lane-a",
    record_id: str = "managed-001",
    tmux_session: str = "isotope-lane-a",
) -> None:
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with registry_path.open(mode, encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "record_id": record_id,
                    "name": name,
                    "cwd": str(workspace),
                    "prompt": "等待输入",
                    "command": ["tmux", "new-session", "-d", "-s", tmux_session],
                    "pid": 0,
                    "started_at": NOW.isoformat(),
                    "log_path": str(
                        codex_home / "supervisor" / "logs" / f"{record_id}.log"
                    ),
                    "status": "launched",
                    "backend": "tmux",
                    "tmux_session": tmux_session,
                },
                ensure_ascii=False,
            )
            + "\n"
        )


def _event(timestamp: str, type_: str, payload: dict[str, object]) -> dict[str, object]:
    return {"timestamp": timestamp, "type": type_, "payload": payload}


def _user_message(timestamp: str, text: str) -> dict[str, object]:
    return _event(
        timestamp,
        "response_item",
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": text}],
        },
    )


def _assistant_message(timestamp: str, text: str) -> dict[str, object]:
    return _event(
        timestamp,
        "response_item",
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text}],
        },
    )
