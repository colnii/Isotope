from __future__ import annotations

from isotope.llm.pool import PoolEntry, resolve_pool_entries_from_env
from isotope.llm.provider import create_chat_provider_from_pool_entry


def test_pool_entries_accept_codex_provider_without_api_key(tmp_path):
    workspace = tmp_path / "workspace"
    codex_home = tmp_path / "codex-home"
    toml_path = tmp_path / "pool.toml"
    toml_path.write_text(
        f"""\
[[agents]]
name = "supervisor"

[[agents.providers]]
provider = "codex"
model = "gpt-5-codex"
workspace_root = "{workspace}"
codex_home = "{codex_home}"
profile = "chatgpt"
max_tokens = 1024
""",
        encoding="utf-8",
    )

    entries = resolve_pool_entries_from_env(
        {"SUPERVISOR_LLM_POOL_TOML_FILES": str(toml_path)},
        env_var="SUPERVISOR_LLM_POOL_TOML_FILES",
        agent_name="supervisor",
    )

    assert len(entries) == 1
    assert entries[0].provider == "codex"
    assert entries[0].api_key == ""
    assert entries[0].base_url == "codex://cli"
    assert entries[0].model == "gpt-5-codex"
    assert entries[0].max_tokens == 1024
    assert entries[0].options == {
        "workspace_root": str(workspace),
        "codex_home": str(codex_home),
        "profile": "chatgpt",
    }


def test_deepseek_pool_entry_uses_deepseek_chat_payload_for_streaming():
    captured: dict[str, object] = {}

    def stream_transport(url, payload, headers, timeout):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        yield {
            "model": "deepseek-v4-flash",
            "choices": [{"delta": {"content": "你好"}}],
        }

    provider = create_chat_provider_from_pool_entry(
        PoolEntry(
            provider="llm_pool",
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
        ),
        timeout=6,
        stream_transport=stream_transport,
    )

    chunks = list(
        provider.stream_generate(
            [{"role": "user", "content": "你好"}],
            max_tokens=128,
        )
    )

    assert chunks[0].provider == "deepseek"
    assert chunks[0].content == "你好"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert captured["payload"]["stream"] is True
    assert captured["timeout"] == 6
