from __future__ import annotations

import isotope.runtime.in_process as server


def _tool_by_name(catalog: dict, name: str) -> dict:
    matches = [tool for tool in catalog["tools"] if tool["name"] == name]
    assert len(matches) == 1
    return matches[0]


def test_model_tool_catalog_exposes_terminal_exec_as_llm_callable_tool(tmp_path):
    api = server.InProcessServer(tmp_path)

    catalog = api.get_model_tool_catalog()

    terminal = _tool_by_name(catalog, "terminal_exec")
    assert terminal["action"] == "call_tool"
    assert terminal["status"] == "enabled"
    assert terminal["input_schema"] == {
        "type": "object",
        "required": ["argv"],
        "properties": {
            "argv": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            }
        },
    }
    assert terminal["constraints"]["shell"] is False
    assert terminal["constraints"]["argv_policy"] == "allowlist"
    assert terminal["constraints"]["allowed_commands"]
    assert terminal["output_contract"] == {
        "result_kind": "terminal_output",
        "content_location": "artifact_ref",
        "full_content_in_events": False,
        "full_content_in_read_model": False,
    }


def test_model_tool_catalog_keeps_codex_task_deferred_not_callable(tmp_path):
    api = server.InProcessServer(tmp_path)

    catalog = api.get_model_tool_catalog()

    callable_names = [tool["name"] for tool in catalog["tools"]]
    assert "codex_task" not in callable_names
    codex_task = [tool for tool in catalog["deferred_tools"] if tool["name"] == "codex_task"]
    assert len(codex_task) == 1
    assert codex_task[0]["status"] == "deferred"
    assert codex_task[0]["tool_kind"] == "agent_cli_task"


def test_model_tool_catalog_is_read_only_and_returns_copies(tmp_path):
    api = server.InProcessServer(tmp_path)

    catalog = api.get_model_tool_catalog()
    _tool_by_name(catalog, "terminal_exec")["constraints"]["allowed_commands"].append("forged")
    catalog["deferred_tools"][0]["constraints"]["requires_approval"] = False

    fresh_catalog = api.get_model_tool_catalog()

    assert (
        "forged"
        not in _tool_by_name(fresh_catalog, "terminal_exec")["constraints"]["allowed_commands"]
    )
    assert fresh_catalog["deferred_tools"][0]["constraints"]["requires_approval"] is True
    assert list((tmp_path / "runs").glob("*")) == []
