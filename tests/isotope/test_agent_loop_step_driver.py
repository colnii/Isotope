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
    run = api.create_run(session["session_id"], goal="product agent loop step driver")
    return api, run["run_id"]


def _approval_intent(text: str = "agent loop step output") -> dict[str, Any]:
    return {
        "action": "call_tool",
        "tool": "write_artifact_tool",
        "text": text,
    }


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


def test_agent_loop_step_driver_submits_one_approval_gated_action(tmp_path):
    api, run_id = _new_run(tmp_path)
    before_events = list(api.get_events(run_id))

    result = api.run_agent_loop_step(
        run_id,
        {
            "step": "submit_approval_gated_action",
            "intent": _approval_intent(),
        },
    )

    assert result["step"] == "submit_approval_gated_action"
    assert result["status"] == "pending_user_approval"
    assert result["control"]["phase"] == "awaiting_approval"
    assert result["control"]["next_actions"] == ["get_approval", "resolve_approval"]
    assert result["action_result"]["approval_id"]
    event_types = [event.event_type for event in api.get_events(run_id)]
    assert event_types[len(before_events) :] == [
        "action.proposed",
        "action.decided",
        "approval.requested",
    ]
    assert result["control"]["progress"]["actions_pending_approval"] == 1
    _assert_no_forbidden_content_keys(result)


def test_agent_loop_step_driver_resolves_pending_approval_and_returns_control(tmp_path):
    api, run_id = _new_run(tmp_path)
    pending = api.run_agent_loop_step(
        run_id,
        {
            "step": "submit_approval_gated_action",
            "intent": _approval_intent(),
        },
    )
    approval_id = pending["action_result"]["approval_id"]

    result = api.run_agent_loop_step(
        run_id,
        {
            "step": "resolve_approval",
            "approval_id": approval_id,
            "resolution": _approved_body(),
        },
    )

    assert result["step"] == "resolve_approval"
    assert result["status"] == "completed"
    assert result["control"]["phase"] == "completed"
    assert result["control"]["next_actions"] == []
    assert result["action_result"]["artifact_ref"]["ref_type"] == "artifact"
    assert result["control"]["progress"]["actions_completed"] == 1
    assert result["control"]["progress"]["artifacts_total"] == 1
    _assert_no_forbidden_content_keys(result)


def test_agent_loop_step_driver_can_create_source_artifact_as_one_step(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = api.run_agent_loop_step(
        run_id,
        {
            "step": "create_source_artifact",
            "summary": "source brief",
            "content": "source material",
        },
    )

    assert result["step"] == "create_source_artifact"
    assert result["status"] == "completed"
    assert result["action_result"]["artifact_ref"]["ref_type"] == "artifact"
    assert result["action_result"]["artifact_summary"] == "source brief"
    assert result["control"]["phase"] == "ready"
    assert result["control"]["progress"]["artifacts_total"] == 1
    _assert_no_forbidden_content_keys(result)


def test_agent_loop_step_driver_rejects_unavailable_step_without_side_effects(tmp_path):
    api, run_id = _new_run(tmp_path)
    before_events = list(api.get_events(run_id))

    with pytest.raises(ValueError, match="not available"):
        api.run_agent_loop_step(
            run_id,
            {
                "step": "resolve_approval",
                "approval_id": "approval_missing",
                "resolution": _approved_body(),
            },
        )

    assert api.get_events(run_id) == before_events
    assert api.get_agent_loop_control(run_id)["phase"] == "ready"


def test_agent_loop_step_driver_rejects_malformed_step_without_side_effects(tmp_path):
    api, run_id = _new_run(tmp_path)
    before_events = list(api.get_events(run_id))

    with pytest.raises(ValueError, match="step"):
        api.run_agent_loop_step(run_id, {"step": "unknown"})

    assert api.get_events(run_id) == before_events
