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
    assert {"bash", "pwsh", "powershell.exe"}.issubset(
        set(terminal["constraints"]["approval_required_commands"])
    )
    assert terminal["output_contract"] == {
        "result_kind": "terminal_output",
        "content_location": "artifact_ref",
        "full_content_in_events": False,
        "full_content_in_read_model": False,
    }


def test_model_tool_catalog_exposes_codex_task_as_callable_tool(tmp_path):
    api = server.InProcessServer(tmp_path)

    catalog = api.get_model_tool_catalog()

    codex_task = _tool_by_name(catalog, "codex_task")
    assert codex_task["action"] == "delegate_agent_task"
    assert codex_task["status"] == "enabled"
    assert codex_task["constraints"]["requires_approval"] is True
    assert codex_task["constraints"]["requires_selected_adapter"] is True
    assert "queued" + "_tools" not in catalog


def test_model_tool_catalog_exposes_write_memory_as_approval_gated_tool(tmp_path):
    api = server.InProcessServer(tmp_path)

    catalog = api.get_model_tool_catalog()

    write_memory = _tool_by_name(catalog, "write_memory")
    assert write_memory["action"] == "write_memory"
    assert write_memory["status"] == "enabled"
    assert write_memory["constraints"]["requires_approval"] is True
    assert write_memory["output_contract"] == {
        "result_kind": "memory_record",
        "content_location": "memory_record_ref",
        "full_content_in_events": False,
        "full_content_in_read_model": False,
    }


def test_model_tool_catalog_is_view_only_and_returns_copies(tmp_path):
    api = server.InProcessServer(tmp_path)

    catalog = api.get_model_tool_catalog()
    _tool_by_name(catalog, "terminal_exec")["constraints"]["allowed_commands"].append("forged")
    _tool_by_name(catalog, "codex_task")["constraints"]["requires_approval"] = False

    fresh_catalog = api.get_model_tool_catalog()

    assert (
        "forged"
        not in _tool_by_name(fresh_catalog, "terminal_exec")["constraints"]["allowed_commands"]
    )
    assert _tool_by_name(fresh_catalog, "codex_task")["constraints"]["requires_approval"] is True
    assert list((tmp_path / "runs").glob("*")) == []
