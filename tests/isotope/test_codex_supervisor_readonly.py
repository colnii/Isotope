from __future__ import annotations

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

from isotope.features.supervisor import flow as supervisor_flow
from isotope.features.supervisor.flow import (
    CodexSessionSummary,
    CodexSupervisorFlow,
    CodexSupervisorReport,
    render_plain_report,
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
    _report_fingerprint,
    main as supervisor_main,
)


NOW = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)
STATUS_REQUEST_TEXT = EXECUTABLE_ADVICE_TEXT["send_status"]
CONTINUE_REQUEST_TEXT = EXECUTABLE_ADVICE_TEXT["send_continue"]


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
    _write_session(
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
                cwd="/home/lumber/Github/isotope",
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
                cwd="/home/lumber/Github/isotope",
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
                cwd="/home/lumber/Github/isotope",
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
                cwd="/home/lumber/Github/isotope",
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
    assert payload["counts"]["needs_attention"] == 1
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
        cwd="/home/lumber/Github/isotope",
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
    assert "命令：暂无可安全生成的命令草案。" in text


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
    suggestions = _advice_payload(report)["command_suggestions"]

    messages = build_llm_action_messages(report, suggestions)

    assert messages[0]["role"] == "system"
    assert "只能从白名单里选择" in messages[0]["content"]
    assert '"allowed_kinds": ["monitor", "send_status", "send_continue"]' in messages[1][
        "content"
    ]
    assert '"kind": "send_continue"' in messages[1]["content"]
    assert '"target_name": "lane-a"' in messages[1]["content"]
    assert '"managed_terminal_ready": true' in messages[1]["content"]
    assert '"managed_bell": true' in messages[1]["content"]
    assert '"supervisor_status": "done"' in messages[1]["content"]


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
    suggestions = _advice_payload(report)["command_suggestions"]

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
        "reason": "当前没有可控的托管 tmux lane，先继续监控。",
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
            assert '"allowed_kinds": ["monitor", "send_status", "send_continue"]' in content
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
        cwd="/home/lumber/Github/isotope",
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
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: (_ for _ in ()).throw(
            AssertionError("LLM resolver should not run without managed targets")
        ),
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
        "reason": "当前没有可控的托管 tmux lane，先继续监控。",
        "command_suggestion": None,
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "当前没有可控的托管 tmux lane，先继续监控。",
    }
    assert calls == []


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
        "managed_names": [],
        "reason": "当前没有可控的托管 tmux lane，自动发送不会生效。",
        "launch_hint": "isotope-supervisor launch --backend tmux --name <name> --cwd <repo> --prompt '<task>'",
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
    assert "当前没有可控的托管 tmux lane，自动发送不会生效。" in text
    assert "isotope-supervisor launch --backend tmux" in text
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
    assert "isotope-supervisor daemon start --interval 30" in text
    assert "isotope-supervisor loop --interval 30" in text
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
    assert payload["commands"]["supervise"] == (
        "isotope-supervisor loop --interval 30"
    )
    assert (
        payload["commands"]["daemon"]
        == "isotope-supervisor daemon start --interval 30"
    )
    assert payload["commands"]["archive"] == "isotope-supervisor archive --name doc-lane"


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
    assert payload["auto_action"] == {
        "kind": "monitor",
        "reason": "no managed tmux lane",
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "reason": "no managed tmux lane",
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
        "-m",
        "isotope.features.supervisor.runner",
        "loop",
        "--codex-home",
        str(codex_home),
        "--interval",
        "7",
        "--limit",
        "3",
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
    assert captured["command"][:4] == [
        "codex",
        "--cd",
        str(workspace),
        "--no-alt-screen",
    ]
    assert captured["command"][4].startswith("继续实现 supervisor")
    assert "SUPERVISOR_STATUS" in captured["command"][4]
    assert "SUPERVISOR_SUMMARY" in captured["command"][4]
    assert "SUPERVISOR_NEXT" in captured["command"][4]
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
        "max_tokens": 512,
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
