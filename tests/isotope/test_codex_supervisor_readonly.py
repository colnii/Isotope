from __future__ import annotations

import http.client
import json
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from isotope.features.supervisor.flow import (
    CodexSessionSummary,
    CodexSupervisorFlow,
    CodexSupervisorReport,
    render_plain_report,
)
from isotope.features.supervisor.llm_summary import (
    PooledSummaryProvider,
    PoolEntry,
    build_llm_summary_messages,
    generate_llm_summary,
    resolve_summary_provider_from_env,
)
from isotope.features.supervisor.runner import _advice_payload, main as supervisor_main


NOW = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)


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
    assert report.sessions[1].status == "needs_user"
    assert report.sessions[1].reason == "最近回复像是在等待用户确认"
    assert report.sessions[2].status == "stale"
    assert report.sessions[2].reason == "超过 10 分钟没有新事件"


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
    assert "等待用户确认后继续状态协议下一片" in messages[1]["content"]


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
    assert "blocked-session blocked / 测试环境缺少 tmux。" in text
    assert "done-session done / 文档已完成。" in text


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
    assert "Codex Supervisor" in html
    assert "dashboard.json" in html
    assert json_response.status == 200
    assert payload["status"] == "ok"
    assert payload["counts"]["needs_attention"] == 1
    assert payload["groups"]["needs_attention"][0]["session_id"] == "blocked-session"


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
            "command": "isotope-supervisor send --name lane-a --text '请汇报当前状态'",
            "kind": "send_status",
            "label": "让托管 Codex 汇报状态",
        },
        {
            "command": (
                "isotope-supervisor send --name lane-a --text "
                "'继续推进，并在完成后汇报当前状态'"
            ),
            "kind": "send_continue",
            "label": "让托管 Codex 继续推进",
        },
        {
            "command": "isotope-supervisor watch --interval 180 --changes-only",
            "kind": "watch_changes",
            "label": "继续监控变化",
        },
    ]


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
        "command": "isotope-supervisor send --name lane-a --text '请汇报当前状态'",
        "kind": "send_status",
        "managed": {
            "name": "lane-a",
            "record_id": "managed-001",
            "tmux_session": "isotope-lane-a",
        },
        "text": "请汇报当前状态",
    }
    assert calls == [
        ["tmux", "send-keys", "-t", "isotope-lane-a", "-l", "请汇报当前状态"],
        ["tmux", "send-keys", "-t", "isotope-lane-a", "Enter"],
    ]


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
    assert payload["executed"]["text"] == "请汇报当前状态"
    assert calls == [
        ["tmux", "send-keys", "-t", "isotope-lane-a", "-l", "请汇报当前状态"],
        ["tmux", "send-keys", "-t", "isotope-lane-a", "Enter"],
    ]


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
    assert calls == [
        ["tmux", "send-keys", "-t", "isotope-lane-a", "-l", "请汇报当前状态"],
        ["tmux", "send-keys", "-t", "isotope-lane-a", "Enter"],
    ]


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

    assert calls == [
        ["tmux", "send-keys", "-t", "isotope-lane-a", "-l", "请汇报当前状态"],
        ["tmux", "send-keys", "-t", "isotope-lane-a", "Enter"],
        ["tmux", "send-keys", "-t", "isotope-lane-a", "-l", "请汇报当前状态"],
        ["tmux", "send-keys", "-t", "isotope-lane-a", "Enter"],
    ]


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
    monkeypatch.setattr("isotope.features.supervisor.runner.time.sleep", lambda _: None)

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

    monkeypatch.setattr("isotope.features.supervisor.runner.time.sleep", change_session)

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
    assert calls == [
        ["tmux", "send-keys", "-t", "isotope-lane-a", "-l", "继续"],
        ["tmux", "send-keys", "-t", "isotope-lane-a", "Enter"],
    ]


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
) -> None:
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
