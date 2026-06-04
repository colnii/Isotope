from __future__ import annotations

import isotope.runtime.in_process as server


def _tool_by_name(catalog: dict, name: str) -> dict:
    matches = [tool for tool in catalog["tools"] if tool["name"] == name]
    assert len(matches) == 1
    return matches[0]


def test_codex_task_catalog_describes_callable_agent_cli_tool(tmp_path):
    api = server.InProcessServer(tmp_path)

    codex_task = _tool_by_name(api.get_model_tool_catalog(), "codex_task")

    assert codex_task["name"] == "codex_task"
    assert codex_task["action"] == "delegate_agent_task"
    assert codex_task["status"] == "enabled"
    assert codex_task["input_schema"] == {
        "type": "object",
        "required": ["prompt"],
        "properties": {"prompt": {"type": "string"}},
    }
    assert codex_task["constraints"]["requires_selected_adapter"] is True
    assert codex_task["constraints"]["requires_approval"] is True
    assert codex_task["output_contract"]["result_kind"] == "agent_task_output"


def test_codex_task_submission_creates_pending_approval(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], "prepare delegated Codex task")

    result = api.submit_action(
        run["run_id"],
        {
            "action": "delegate_agent_task",
            "tool": "codex_task",
            "prompt": "Inspect this repository and report the next step.",
        },
        requires_approval=True,
    )

    assert result["status"] == "pending_user_approval"
    assert result["approval_id"].startswith("approval_")
    assert "approval.requested" in [
        event.event_type for event in api.event_store.list_events(run["run_id"])
    ]
