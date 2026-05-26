from __future__ import annotations

import pytest

import isotope.runtime.in_process as server


def _deferred_tool_by_name(catalog: dict, name: str) -> dict:
    matches = [tool for tool in catalog["deferred_tools"] if tool["name"] == name]
    assert len(matches) == 1
    return matches[0]


def test_codex_task_catalog_describes_deferred_agent_cli_boundary(tmp_path):
    api = server.InProcessServer(tmp_path)

    codex_task = _deferred_tool_by_name(api.get_model_tool_catalog(), "codex_task")

    assert codex_task == {
        "name": "codex_task",
        "action": "delegate_agent_task",
        "tool_kind": "agent_cli_task",
        "status": "deferred",
        "reason": "future agent CLI tool; requires explicit Codex adapter boundary",
        "input_schema": {
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {"type": "string", "minLength": 1},
            },
        },
        "constraints": {
            "terminal_tool": False,
            "uses_terminal_exec": False,
            "requires_selected_adapter": True,
            "requires_approval": True,
            "full_content_in_events": False,
        },
        "output_contract": {
            "result_kind": "agent_task_output",
            "content_location": "artifact_ref",
            "full_content_in_events": False,
            "full_content_in_read_model": False,
        },
    }


def test_codex_task_submission_fails_closed_without_action_events(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], "prepare delegated Codex task")

    before = api.event_store.list_events(run["run_id"])

    with pytest.raises(ValueError, match="deferred tool codex_task is not callable"):
        api.submit_action(
            run["run_id"],
            {
                "action": "call_tool",
                "tool": "codex_task",
                "prompt": "Inspect this repository and report the next step.",
            },
            requires_approval=True,
        )

    after = api.event_store.list_events(run["run_id"])
    assert [(event.event_id, event.event_type) for event in after] == [
        (event.event_id, event.event_type) for event in before
    ]
