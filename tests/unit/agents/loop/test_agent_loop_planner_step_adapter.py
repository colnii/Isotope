from __future__ import annotations

from typing import Any

import pytest

import isotope.runtime.in_process as server


FORBIDDEN_CONTENT_KEYS = {
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
    run = api.create_run(session["session_id"], goal="planner to step driver adapter")
    return api, run["run_id"]


def _planner_output(control: dict[str, Any], step: str, request: dict[str, Any]) -> dict[str, Any]:
    return {
        "planner_run_id": "planner_run_001",
        "basis": {
            "run_id": control["run_id"],
            "last_event_id": control["last_event_id"],
        },
        "decision": {
            "step": step,
            "request": request,
        },
    }


def _approval_request(text: str = "planner selected step output") -> dict[str, Any]:
    return {
        "intent": {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": text,
        },
    }


def _approved_body() -> dict[str, str]:
    return {
        "resolution": "approved",
        "reason": "operator approved planner selected step",
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


def test_planner_step_adapter_executes_valid_symbolic_step_through_step_driver(tmp_path):
    api, run_id = _new_run(tmp_path)
    control = api.get_agent_loop_control(run_id)
    before_events = list(api.get_events(run_id))

    result = api.run_agent_loop_planner_step(
        run_id,
        _planner_output(control, "submit_approval_gated_action", _approval_request()),
    )

    assert result["planner_run_id"] == "planner_run_001"
    assert result["planner_status"] == "accepted"
    assert result["selected_step"] == "submit_approval_gated_action"
    assert result["step_result"]["status"] == "pending_user_approval"
    assert result["control"]["phase"] == "awaiting_approval"
    assert result["control"]["next_actions"] == ["get_approval", "resolve_approval"]
    assert result["step_result"]["action_result"]["approval_id"]
    event_types = [event.event_type for event in api.get_events(run_id)]
    assert event_types[len(before_events) :] == [
        "action.proposed",
        "action.decided",
        "approval.requested",
    ]
    _assert_no_forbidden_content_keys(result)


def test_planner_step_adapter_can_select_capability_call_through_step_driver(tmp_path):
    api, run_id = _new_run(tmp_path)
    control = api.get_agent_loop_control(run_id)
    before_events = list(api.get_events(run_id))

    result = api.run_agent_loop_planner_step(
        run_id,
        _planner_output(
            control,
            "call_capability",
            {"capability_id": "artifact.review"},
        ),
    )

    assert result["planner_status"] == "accepted"
    assert result["selected_step"] == "call_capability"
    assert result["step_result"]["status"] == "completed"
    capability_run = result["step_result"]["action_result"]["capability_run"]
    assert capability_run["kind"] == "capability_run_result"
    assert capability_run["capability_id"] == "artifact.review"
    assert capability_run["status"] == "completed"
    assert result["step_result"]["action_result"]["artifact_ref"]["ref_type"] == "artifact"
    assert result["control"]["phase"] == "ready"
    event_types = [event.event_type for event in api.get_events(run_id)]
    assert event_types[len(before_events) :] == [
        "action.proposed",
        "action.decided",
        "action.started",
        "artifact.created",
        "action.completed",
    ]
    _assert_no_forbidden_content_keys(result)


def test_planner_step_adapter_can_resume_approval_after_restart(tmp_path):
    api, run_id = _new_run(tmp_path)
    pending = api.run_agent_loop_step(
        run_id,
        {
            "step": "submit_approval_gated_action",
            **_approval_request(),
        },
    )
    approval_id = pending["action_result"]["approval_id"]
    restarted = server.InProcessServer(tmp_path)
    control = restarted.get_agent_loop_control(run_id)

    result = restarted.run_agent_loop_planner_step(
        run_id,
        _planner_output(
            control,
            "resolve_approval",
            {
                "approval_id": approval_id,
                "resolution": _approved_body(),
            },
        ),
    )

    assert result["selected_step"] == "resolve_approval"
    assert result["step_result"]["status"] == "completed"
    assert result["control"]["phase"] == "completed"
    assert result["step_result"]["action_result"]["artifact_ref"]["ref_type"] == "artifact"


def test_planner_step_adapter_rejects_stale_basis_without_side_effects(tmp_path):
    api, run_id = _new_run(tmp_path)
    control = api.get_agent_loop_control(run_id)
    output = _planner_output(control, "submit_approval_gated_action", _approval_request())
    output["basis"]["last_event_id"] = "evt_stale"
    before_events = list(api.get_events(run_id))

    with pytest.raises(ValueError, match="planner basis"):
        api.run_agent_loop_planner_step(run_id, output)

    assert api.get_events(run_id) == before_events
    assert api.get_agent_loop_control(run_id)["phase"] == "ready"


def test_planner_step_adapter_rejects_raw_model_payload_without_side_effects(tmp_path):
    api, run_id = _new_run(tmp_path)
    control = api.get_agent_loop_control(run_id)
    output = _planner_output(control, "submit_approval_gated_action", _approval_request())
    output["model_response"] = "raw model text should stay outside this adapter"
    before_events = list(api.get_events(run_id))

    with pytest.raises(ValueError, match="raw planner"):
        api.run_agent_loop_planner_step(run_id, output)

    assert api.get_events(run_id) == before_events
