from __future__ import annotations

from isotope.llm.pool import resolve_pool_entries_from_env


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
