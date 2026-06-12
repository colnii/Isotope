from __future__ import annotations

import io
import json
from typing import Any

import pytest

from isotope.llm.provider.codex_api import CodexApiLLMProvider


class _FakeStdin:
    def __init__(self) -> None:
        self.lines: list[dict[str, Any]] = []

    def write(self, text: str) -> int:
        self.lines.append(json.loads(text))
        return len(text)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


class _FakeProcess:
    def __init__(self, lines: list[dict[str, Any]]) -> None:
        self.stdin = _FakeStdin()
        self.stdout = io.StringIO("".join(json.dumps(line) + "\n" for line in lines))
        self.stderr = io.StringIO("")
        self.returncode = None
        self.terminated = False
        self.killed = False

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        self.returncode = 0 if self.returncode is None else self.returncode
        return self.returncode


class _FakeProcessFactory:
    def __init__(self, lines: list[dict[str, Any]]) -> None:
        self.lines = lines
        self.calls: list[dict[str, Any]] = []
        self.processes: list[_FakeProcess] = []

    def __call__(self, argv, **kwargs):
        process = _FakeProcess(self.lines)
        self.calls.append({"argv": list(argv), "kwargs": dict(kwargs), "process": process})
        self.processes.append(process)
        return process


def _resolve_codex(executable: str) -> str:
    assert executable == "codex"
    return "/opt/codex/bin/codex"


def test_codex_api_provider_generates_from_app_server_agent_message(tmp_path):
    factory = _FakeProcessFactory(
        [
            {"id": 1, "result": {"userAgent": "codex-test"}},
            {"id": 2, "result": {"thread": {"id": "thread_123"}}},
            {"id": 3, "result": {"turn": {"id": "turn_123"}}},
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "agent_message",
                        "text": "Codex API answer",
                    }
                },
            },
            {"method": "turn/completed", "params": {"turn": {"id": "turn_123"}}},
        ]
    )
    provider = CodexApiLLMProvider(
        workspace_root=tmp_path,
        executable="codex",
        model="gpt-5-codex",
        timeout=7,
        process_factory=factory,
        executable_resolver=_resolve_codex,
    )

    response = provider.generate(
        [
            {"role": "system", "content": "Answer briefly."},
            {"role": "user", "content": "hello"},
        ],
        max_tokens=123,
    )

    assert response.provider == "codex-api"
    assert response.model == "gpt-5-codex"
    assert response.content == "Codex API answer"
    assert response.finish_reason == "stop"
    assert response.usage["max_tokens"] == 123
    assert response.usage["codex_timeout_seconds"] == 7
    assert response.raw == {
        "thread_id": "thread_123",
        "events_seen": 2,
        "app_server": "codex",
    }
    call = factory.calls[0]
    assert call["argv"] == ["/opt/codex/bin/codex", "app-server", "--stdio"]
    assert call["kwargs"]["cwd"] == str(tmp_path.resolve())
    sent = call["process"].stdin.lines
    assert sent[0]["method"] == "initialize"
    assert sent[1] == {"method": "initialized", "params": {}}
    assert sent[2]["method"] == "thread/start"
    assert sent[2]["params"] == {"model": "gpt-5-codex"}
    assert sent[3]["method"] == "turn/start"
    assert sent[3]["params"]["threadId"] == "thread_123"
    assert "Do not execute shell commands" in sent[3]["params"]["input"][0]["text"]


def test_codex_api_provider_raises_safe_rpc_error(tmp_path):
    factory = _FakeProcessFactory(
        [
            {"id": 1, "error": {"code": -32000, "message": "bad token secret-value"}},
        ]
    )
    provider = CodexApiLLMProvider(
        workspace_root=tmp_path,
        executable="codex",
        process_factory=factory,
        executable_resolver=_resolve_codex,
    )

    with pytest.raises(RuntimeError) as excinfo:
        provider.generate([{"role": "user", "content": "hello"}])

    message = str(excinfo.value)
    assert "bad token" in message
    assert "secret-value" not in message
    assert "[redacted]" in message
    assert len(message) <= 180


def test_codex_api_provider_requires_agent_message(tmp_path):
    factory = _FakeProcessFactory(
        [
            {"id": 1, "result": {}},
            {"id": 2, "result": {"thread": {"id": "thread_123"}}},
            {"id": 3, "result": {"turn": {"id": "turn_123"}}},
            {"method": "turn/completed", "params": {"turn": {"id": "turn_123"}}},
        ]
    )
    provider = CodexApiLLMProvider(
        workspace_root=tmp_path,
        executable="codex",
        process_factory=factory,
        executable_resolver=_resolve_codex,
    )

    with pytest.raises(RuntimeError, match="did not return an agent message"):
        provider.generate([{"role": "user", "content": "hello"}])
