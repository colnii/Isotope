from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from isotope.features.supervisor.flow import CodexSupervisorFlow, render_plain_report
from isotope.features.supervisor.llm_summary import (
    PooledSummaryProvider,
    PoolEntry,
    build_llm_summary_messages,
    generate_llm_summary,
    resolve_summary_provider_from_env,
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
            _assistant_message("2026-05-16T11:59:20Z", "正在读文件。")
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
    assert captured["command"] == [
        "codex",
        "--cd",
        str(workspace),
        "--no-alt-screen",
        "继续实现 supervisor",
    ]
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
