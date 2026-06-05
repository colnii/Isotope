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
                provider="deterministic_test",
                api_key="test-key",
                base_url="https://test-chat.example.com/v1",
                model="test-model",
            ),
        ),
        transport=transport,
    )

    summary = provider.summarize([{"role": "user", "content": "hello"}])

    assert summary == "窗口 A 正在测试，建议继续观察。"
    assert captured["url"] == "https://test-chat.example.com/v1/chat/completions"
    assert captured["headers"] == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json",
    }
    assert captured["payload"] == {
        "model": "test-model",
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
                provider="deterministic_test",
                api_key="test-key",
                base_url="https://test-openai.example.com",
                model="test-chat-v1",
            ),
        ),
        transport=transport,
    )

    assert provider.summarize([{"role": "user", "content": "hello"}]) == "窗口 A 正在测试。"
    assert captured["url"] == "https://test-openai.example.com/chat/completions"
    assert captured["payload"]["temperature"] == 0
    assert captured["headers"]["Authorization"] == "Bearer test-key"



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
                provider="deterministic_test",
                api_key="test-key",
                base_url="https://test-reasoning.example.com",
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
                provider="deterministic_test",
                api_key="test-key",
                base_url="https://test.example.com",
                model="test-model",
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

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            assert "active-session" in messages[1]["content"]
            return "窗口 A 正在读文件，暂时不用介入。"

    assert generate_llm_summary(report, DeterministicProvider()) == "窗口 A 正在读文件，暂时不用介入。"


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


def _append_supervisor_goal_status(
    codex_home: Path,
    *,
    goal_id: str,
    status: str,
    target_name: str,
    summary: str,
    next_step: str,
) -> None:
    goals_path = codex_home / "supervisor" / "goals.jsonl"
    with goals_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "event": "supervisor_goal_status",
                    "goal_id": goal_id,
                    "status": status,
                    "target_name": target_name,
                    "summary": summary,
                    "next": next_step,
                    "created_at": NOW.isoformat(),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )


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

