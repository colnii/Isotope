from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from isotope.features.supervisor.flow import CodexSupervisorFlow, render_plain_report
from isotope.features.supervisor.llm_summary import (
    OpenAICompatibleSummaryProvider,
    build_llm_summary_messages,
    generate_llm_summary,
)
from isotope.features.supervisor.runner import main as supervisor_main


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


def test_codex_supervisor_report_serializes_to_json_shape(tmp_path):
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

    assert payload["status"] == "ok"
    assert payload["summary"]["total"] == 1
    assert payload["sessions"][0]["session_id"] == "active-session"
    assert payload["sessions"][0]["status_label"] == "工作中"


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

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.OpenAICompatibleSummaryProvider.from_minimax_env",
        lambda: FakeProvider(),
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


def test_codex_supervisor_runner_llm_summary_reports_missing_key(
    tmp_path,
    capsys,
    monkeypatch,
):
    for name in ("MINIMAX_API_KEY", "MINIMAX_TOKEN", "MINIMAX_API_TOKEN"):
        monkeypatch.delenv(name, raising=False)
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
    assert "MINIMAX_API_KEY" in payload["error"]["message"]


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
    assert "source_path" not in messages[1]["content"]
    assert len(messages[1]["content"]) < 1500


def test_codex_supervisor_openai_compatible_provider_calls_minimax_shape():
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

    provider = OpenAICompatibleSummaryProvider(
        api_key="sk-test",
        base_url="https://api.minimax.io/v1",
        model="MiniMax-M2.7-highspeed",
        transport=transport,
    )

    summary = provider.summarize([{"role": "user", "content": "hello"}])

    assert summary == "窗口 A 正在测试，建议继续观察。"
    assert captured["url"] == "https://api.minimax.io/v1/chat/completions"
    assert captured["headers"] == {
        "Authorization": "Bearer sk-test",
        "Content-Type": "application/json",
    }
    assert captured["payload"] == {
        "model": "MiniMax-M2.7-highspeed",
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0,
        "max_tokens": 512,
        "stream": False,
    }


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
