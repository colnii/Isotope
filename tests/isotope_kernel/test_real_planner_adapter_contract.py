from __future__ import annotations

from typing import Any

import pytest

from isotope_kernel.checkpoint_store import FileCheckpointStore
from isotope_kernel import server


FORBIDDEN_PROVIDER_KEYS = {
    "api_key",
    "artifact_content",
    "full_content",
    "full_text",
    "messages",
    "model_prompt",
    "model_request",
    "model_response",
    "prompt",
    "raw_artifact_content",
    "raw_content",
    "raw_prompt",
    "raw_response",
}


def _new_run(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="real planner adapter contract")
    return api, run["run_id"]


def _planner_output(control: dict[str, Any], step: str, request: dict[str, Any]) -> dict[str, Any]:
    return {
        "planner_run_id": "planner_run_contract_001",
        "basis": {
            "run_id": control["run_id"],
            "last_event_id": control["last_event_id"],
        },
        "decision": {
            "step": step,
            "request": request,
        },
    }


def _approval_request(text: str = "contract wrapper selected step") -> dict[str, Any]:
    return {
        "intent": {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": text,
        },
    }


def _provider_result(parsed_output: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider_result_id": "fake_provider_result_001",
        "provider_status": "completed",
        "raw_prompt_quarantined": True,
        "raw_response_quarantined": True,
        "parsed_planner_output": parsed_output,
    }


def _assert_no_forbidden_provider_keys(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_PROVIDER_KEYS.intersection(value)
        assert forbidden == set()
        for nested in value.values():
            _assert_no_forbidden_provider_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_provider_keys(nested)


def test_real_planner_contract_executes_only_parsed_symbolic_output(tmp_path):
    api, run_id = _new_run(tmp_path)
    control = api.get_agent_loop_control(run_id)
    before_events = list(api.get_events(run_id))

    result = api.run_agent_loop_real_planner_contract_step(
        run_id,
        _provider_result(
            _planner_output(control, "submit_approval_gated_action", _approval_request())
        ),
    )

    assert result["contract_status"] == "accepted"
    assert result["provider_result_id"] == "fake_provider_result_001"
    assert result["raw_prompt_quarantined"] is True
    assert result["raw_response_quarantined"] is True
    assert result["planner_result"]["planner_status"] == "accepted"
    assert result["planner_result"]["selected_step"] == "submit_approval_gated_action"
    assert result["control"]["phase"] == "awaiting_approval"
    event_types = [event.event_type for event in api.get_events(run_id)]
    assert event_types[len(before_events) :] == [
        "action.proposed",
        "action.decided",
        "approval.requested",
    ]
    _assert_no_forbidden_provider_keys(result)


def test_real_planner_contract_rejects_unquarantined_raw_payload_without_side_effects(tmp_path):
    api, run_id = _new_run(tmp_path)
    control = api.get_agent_loop_control(run_id)
    provider_result = _provider_result(
        _planner_output(control, "submit_approval_gated_action", _approval_request())
    )
    provider_result["raw_response_quarantined"] = False
    provider_result["raw_response"] = "raw model text must stay outside kernel"
    before_events = list(api.get_events(run_id))

    with pytest.raises(ValueError, match="raw planner provider payload"):
        api.run_agent_loop_real_planner_contract_step(run_id, provider_result)

    assert api.get_events(run_id) == before_events


def test_real_planner_contract_rejects_invalid_parsed_output_without_side_effects(tmp_path):
    api, run_id = _new_run(tmp_path)
    control = api.get_agent_loop_control(run_id)
    parsed_output = _planner_output(control, "submit_approval_gated_action", _approval_request())
    parsed_output["basis"]["last_event_id"] = "evt_stale"
    before_events = list(api.get_events(run_id))

    with pytest.raises(ValueError, match="planner basis"):
        api.run_agent_loop_real_planner_contract_step(run_id, _provider_result(parsed_output))

    assert api.get_events(run_id) == before_events


def test_real_planner_contract_keeps_provider_raw_fields_out_of_events_and_checkpoint(tmp_path):
    root = tmp_path / "runtime"
    checkpoints = FileCheckpointStore(tmp_path / "checkpoints")
    api = server.InProcessServer(root, checkpoint_store=checkpoints)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="real planner checkpoint quarantine")
    run_id = run["run_id"]
    control = api.get_agent_loop_control(run_id)

    api.run_agent_loop_real_planner_contract_step(
        run_id,
        _provider_result(
            _planner_output(control, "submit_approval_gated_action", _approval_request())
        ),
    )
    api.save_checkpoint_for_run(run_id)

    serialized_events = repr([event.payload for event in api.get_events(run_id)])
    serialized_checkpoint = repr(checkpoints.load_latest_checkpoint(run_id))
    assert "raw_response" not in serialized_events
    assert "model_response" not in serialized_events
    assert "raw_response" not in serialized_checkpoint
    assert "model_response" not in serialized_checkpoint
