from __future__ import annotations

from typing import Any

import pytest

import isotope.runtime.in_process as server


FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "model_prompt",
    "model_response",
    "raw_artifact_content",
    "raw_content",
}


def _new_run(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="product agent loop control")
    return api, session["session_id"], run["run_id"]


def _tool_intent(**overrides: Any) -> dict[str, Any]:
    intent: dict[str, Any] = {
        "action": "call_tool",
        "tool": "write_artifact_tool",
        "text": "agent loop control output",
    }
    intent.update(overrides)
    return intent


def _approved_body() -> dict[str, str]:
    return {
        "resolution": "approved",
        "reason": "operator approved product agent loop step",
        "resolver": "test_operator",
    }


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_CONTENT_KEYS.intersection(value)
        assert forbidden == set()
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def test_agent_loop_control_for_new_run_exposes_ready_product_summary(tmp_path):
    api, session_id, run_id = _new_run(tmp_path)
    before_events = list(api.get_events(run_id))

    control = api.get_agent_loop_control(run_id)

    assert control["run_id"] == run_id
    assert control["session_id"] == session_id
    assert control["goal"] == "product agent loop control"
    assert control["status"] == "running"
    assert control["phase"] == "ready"
    assert control["waiting_on"] == []
    assert control["next_actions"] == [
        "query_memory",
        "create_source_artifact",
        "record_turn_memory",
        "promote_run_memory",
        "submit_worker_handoff",
        "submit_approval_gated_action",
        "call_capability",
    ]
    assert control["progress"] == {
        "actions_total": 0,
        "actions_completed": 0,
        "actions_pending_approval": 0,
        "artifacts_total": 0,
        "memory_records_total": 0,
        "workers_total": 0,
        "workspaces_total": 0,
    }
    assert control["deferred_capabilities"] == [
        "real_llm_provider",
        "scheduler",
        "real_worker_runtime",
    ]
    assert api.get_events(run_id) == before_events
    _assert_no_forbidden_content_keys(control)


def test_agent_loop_control_for_pending_approval_shows_blocker_and_resume_actions(tmp_path):
    api, _session_id, run_id = _new_run(tmp_path)
    result = api.submit_action(run_id, _tool_intent(), requires_approval=True)
    approval_id = result["approval_id"]

    control = api.get_agent_loop_control(run_id)

    assert control["status"] == "pending_user_approval"
    assert control["phase"] == "awaiting_approval"
    assert control["waiting_on"] == [
        {
            "kind": "approval",
            "approval_id": approval_id,
            "status": "pending",
            "reason_codes": ["approval_required"],
            "requested_action_summary": {"action_type": "call_tool"},
        }
    ]
    assert control["next_actions"] == ["get_approval", "resolve_approval"]
    assert control["progress"]["actions_pending_approval"] == 1
    assert control["approvals"]["pending_count"] == 1
    assert control["approvals"]["pending_ids"] == [approval_id]
    assert control["blocked_reason_codes"] == ["approval_required"]


def test_agent_loop_control_for_completed_run_has_no_next_actions(tmp_path):
    api, _session_id, run_id = _new_run(tmp_path)
    result = api.submit_action(run_id, _tool_intent(), requires_approval=True)
    api.resolve_approval(result["approval_id"], _approved_body())

    control = api.get_agent_loop_control(run_id)

    assert control["status"] == "completed"
    assert control["phase"] == "completed"
    assert control["waiting_on"] == []
    assert control["next_actions"] == []
    assert control["progress"]["actions_completed"] == 1
    assert control["progress"]["artifacts_total"] == 1
    assert control["approvals"]["pending_count"] == 0


def test_agent_loop_control_returns_copy_and_does_not_scan_public_events(tmp_path, monkeypatch):
    api, _session_id, run_id = _new_run(tmp_path)

    def fail_public_event_scan(*args: Any, **kwargs: Any):
        raise AssertionError("agent loop control should use projected state, not public event scan")

    monkeypatch.setattr(api, "get_events", fail_public_event_scan)

    control = api.get_agent_loop_control(run_id)
    control["next_actions"].append("mutated")

    fresh = api.get_agent_loop_control(run_id)
    assert "mutated" not in fresh["next_actions"]


def test_agent_loop_control_unknown_run_is_controlled_error(tmp_path):
    api = server.InProcessServer(tmp_path)

    with pytest.raises(ValueError, match="unknown run_id"):
        api.get_agent_loop_control("run_missing")
