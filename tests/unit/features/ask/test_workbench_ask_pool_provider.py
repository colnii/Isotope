from __future__ import annotations

import json
from typing import Any

import pytest

from isotope.features.ask.pool import resolve_workbench_ask_provider_from_env


class _FakeCompletedProcess:
    def __init__(self, *, stdout: str) -> None:
        self.returncode = 0
        self.stdout = stdout
        self.stderr = ""


class _RecordingCodexRunner:
    def __init__(self, agent_text: str) -> None:
        self.agent_text = agent_text
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": list(argv), "kwargs": dict(kwargs)})
        return _FakeCompletedProcess(
            stdout=json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": self.agent_text},
                }
            )
            + "\n"
        )


def _resolve_codex_executable(executable: str) -> str:
    assert executable == "codex"
    return "/opt/codex/bin/codex"


def test_workbench_ask_pool_provider_uses_isotope_toml_alias(tmp_path):
    toml_path = tmp_path / "pool.toml"
    toml_path.write_text(
        """\
[[keys]]
provider = "company-pool"
base_url = "https://api.company.example.com/v1"
model = "answer-model"
api_keys = ["env:ASK_KEY"]
""",
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}

    def transport(
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: int,
    ) -> dict[str, Any]:
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        return {
            "choices": [{"message": {"content": "先整理作品集故事线。"}}],
            "usage": {"total_tokens": 18},
        }

    provider = resolve_workbench_ask_provider_from_env(
        {
            "ISOTOPE_LLM_POOL_TOML_FILES": str(toml_path),
            "ASK_KEY": "sk-ask",
            "ISOTOPE_LLM_TIMEOUT_SECONDS": "7",
        },
        transport=transport,
    )
    response = provider.generate(
        [{"role": "user", "content": "下一步做什么？"}],
        max_tokens=128,
    )

    assert response.content == "先整理作品集故事线。"
    assert response.provider == "company-pool"
    assert response.model == "answer-model"
    assert captured["url"] == "https://api.company.example.com/v1/chat/completions"
    assert captured["payload"]["model"] == "answer-model"
    assert captured["payload"]["max_tokens"] == 128
    assert captured["headers"]["Authorization"] == "Bearer sk-ask"
    assert captured["timeout"] == 7


def test_workbench_ask_pool_provider_can_filter_agent_name(tmp_path):
    toml_path = tmp_path / "pool.toml"
    toml_path.write_text(
        """\
[[agents]]
name = "supervisor"

[[agents.providers]]
provider = "supervisor-provider"
base_url = "https://api.supervisor.example.com"
model = "supervisor-model"
api_keys = ["env:SUPERVISOR_KEY"]

[[agents]]
name = "workbench_ask"

[[agents.providers]]
provider = "ask-provider"
base_url = "https://api.ask.example.com"
model = "ask-model"
api_keys = ["env:ASK_KEY"]
""",
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}

    def transport(
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: int,
    ) -> dict[str, Any]:
        captured["url"] = url
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "ask ok"}}]}

    provider = resolve_workbench_ask_provider_from_env(
        {
            "ISOTOPE_LLM_POOL_TOML_FILES": str(toml_path),
            "SUPERVISOR_KEY": "sk-supervisor",
            "ASK_KEY": "sk-ask",
        },
        agent_name="workbench_ask",
        transport=transport,
    )

    assert provider.generate([{"role": "user", "content": "hello"}]).content == "ask ok"
    assert captured["url"] == "https://api.ask.example.com/chat/completions"
    assert captured["payload"]["model"] == "ask-model"


def test_workbench_ask_pool_provider_reports_missing_entries(tmp_path):
    missing = tmp_path / "missing.toml"

    with pytest.raises(ValueError, match="No Workbench Ask LLM pool entries"):
        resolve_workbench_ask_provider_from_env(
            {"ISOTOPE_LLM_POOL_TOML_FILES": str(missing)}
        )


def test_workbench_ask_pool_provider_uses_codex_entry_without_api_key(tmp_path):
    toml_path = tmp_path / "pool.toml"
    toml_path.write_text(
        f"""\
[[agents]]
name = "workbench_ask"

[[agents.providers]]
provider = "codex"
workspace_root = "{tmp_path}"
""",
        encoding="utf-8",
    )
    runner = _RecordingCodexRunner("Codex pooled answer")

    provider = resolve_workbench_ask_provider_from_env(
        {"ISOTOPE_LLM_POOL_TOML_FILES": str(toml_path)},
        agent_name="workbench_ask",
        codex_process_runner=runner,
        codex_executable_resolver=_resolve_codex_executable,
    )
    response = provider.generate(
        [{"role": "user", "content": "下一步做什么？"}],
        max_tokens=128,
    )

    assert response.provider == "codex"
    assert response.content == "Codex pooled answer"
    assert runner.calls
    assert runner.calls[0]["kwargs"]["cwd"] == str(tmp_path.resolve())


def test_workbench_ask_pool_provider_can_skip_codex_for_low_latency_chat(tmp_path):
    toml_path = tmp_path / "pool.toml"
    toml_path.write_text(
        f"""\
[[agents]]
name = "supervisor"

[[agents.providers]]
provider = "codex"
workspace_root = "{tmp_path}"

[[agents.providers]]
provider = "fast-chat"
base_url = "https://api.fast.example.com"
model = "fast-model"
api_keys = ["env:FAST_KEY"]
""",
        encoding="utf-8",
    )
    runner = _RecordingCodexRunner("slow codex answer")
    captured: dict[str, Any] = {}

    def transport(
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: int,
    ) -> dict[str, Any]:
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        return {"choices": [{"message": {"content": "fast answer"}}]}

    provider = resolve_workbench_ask_provider_from_env(
        {
            "ISOTOPE_LLM_POOL_TOML_FILES": str(toml_path),
            "FAST_KEY": "sk-fast",
        },
        agent_name="supervisor",
        allow_codex=False,
        transport=transport,
        codex_process_runner=runner,
        codex_executable_resolver=_resolve_codex_executable,
    )

    response = provider.generate([{"role": "user", "content": "你好"}])

    assert response.provider == "fast-chat"
    assert response.content == "fast answer"
    assert runner.calls == []
    assert captured["url"] == "https://api.fast.example.com/chat/completions"
