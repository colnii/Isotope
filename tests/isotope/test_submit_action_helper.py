from __future__ import annotations

from typing import Any

import isotope.demo as demo
import isotope.runtime.in_process as server


def _new_run(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="submit compact action")
    return api, run["run_id"]


def _tool_intent(**overrides: Any) -> dict[str, Any]:
    intent: dict[str, Any] = {
        "action": "call_tool",
        "tool": "write_artifact_tool",
        "text": "compact action output",
    }
    intent.update(overrides)
    return intent


def _event_types(api: server.InProcessServer, run_id: str) -> list[str]:
    return [event.event_type for event in api.get_events(run_id)]


def test_submit_action_accepts_compact_tool_intent_and_uses_canonical_action_chain(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = api.submit_action(run_id, _tool_intent())

    assert result["status"] == "completed"
    assert result["proposal_id"].startswith("prop_")
    assert result["decision_id"].startswith("dec_")
    assert result["execution_id"].startswith("exec_")
    assert result["artifact_ref"].artifact_id.startswith("artifact_")
    assert result["decision"].outcome == "approved"
    assert result["run_state"].status == "completed"
    assert _event_types(api, run_id) == [
        "run.created",
        "agent.created",
        "thread.created",
        "action.proposed",
        "action.decided",
        "action.started",
        "artifact.created",
        "action.completed",
        "run.completed",
    ]


def test_submit_action_pending_approval_returns_ids_without_execution_or_artifact(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = api.submit_action(run_id, _tool_intent(), requires_approval=True)

    assert result["status"] == "pending_user_approval"
    assert result["proposal_id"].startswith("prop_")
    assert result["decision_id"].startswith("dec_")
    assert result["approval_id"].startswith("approval_")
    assert result["execution"] is None
    assert "execution_id" not in result
    assert "artifact_ref" not in result
    assert result["decision"].outcome == "pending_user_approval"
    assert api.get_pending_approvals(run_id)[0]["approval_id"] == result["approval_id"]
    assert "action.started" not in _event_types(api, run_id)
    assert "artifact.created" not in _event_types(api, run_id)
    assert api.artifact_store.list_artifacts(run_id) == []


def test_submit_action_uses_policy_grants_not_requested_capabilities(tmp_path):
    api, run_id = _new_run(tmp_path)
    intent = _tool_intent(
        requested_tools=["write_artifact_tool", "forged_tool"],
        workspace_mode="isolated",
        budget={"seconds": 999},
    )

    result = api.submit_action(run_id, intent)

    assert result["status"] == "completed"
    assert result["decision"].outcome == "modified"
    assert result["decision"].grants == {
        "tools": ["write_artifact_tool"],
        "workspace": {"mode": "shared_ro"},
        "budget": {"seconds": 30},
    }


def test_submit_action_denied_path_creates_no_execution_or_artifact(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = api.submit_action(run_id, _tool_intent(requested_tools=[]))

    assert result["status"] == "denied"
    assert result["proposal_id"].startswith("prop_")
    assert result["decision_id"].startswith("dec_")
    assert result["execution"] is None
    assert result["decision"].outcome == "denied"
    assert "action.started" not in _event_types(api, run_id)
    assert "artifact.created" not in _event_types(api, run_id)
    assert api.artifact_store.list_artifacts(run_id) == []


def test_submit_tool_request_remains_compatible_with_existing_callers(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = api.submit_tool_request(
        run_id,
        tool="write_artifact_tool",
        text="legacy helper output",
        requires_approval=True,
    )

    assert result["status"] == "pending_user_approval"
    assert result["decision"].outcome == "pending_user_approval"
    assert result["execution"] is None
    assert result["run_state"].status == "pending_user_approval"


def test_approval_tool_runner_demo_uses_submit_action_not_raw_submit_tool_request(
    tmp_path,
    monkeypatch,
):
    def fail_raw_submit_tool_request(*args: Any, **kwargs: Any):
        raise AssertionError("approval-tool-runner demo should use submit_action helper")

    monkeypatch.setattr(server.InProcessServer, "submit_tool_request", fail_raw_submit_tool_request)

    result = demo._run_approval_tool_runner_spike(tmp_path)

    assert result["approval_tool_runner_ok"] is True
    assert not any("submit_tool_request" in item for item in result["api_friction"])
