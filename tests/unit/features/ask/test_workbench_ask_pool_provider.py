from __future__ import annotations

from typing import Any

import pytest

from isotope.features.ask.pool import resolve_workbench_ask_provider_from_env


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
