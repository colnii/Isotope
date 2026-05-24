from __future__ import annotations

from typing import Any

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
    run = api.create_run(session["session_id"], goal="agent loop tick driver")
    return api, run["run_id"]


def _planner_output(
    control: dict[str, Any],
    step: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    return {
        "planner_run_id": "planner_run_tick_001",
        "basis": {
            "run_id": control["run_id"],
            "last_event_id": control["last_event_id"],
        },
        "decision": {
            "step": step,
            "request": request,
        },
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


def test_agent_loop_tick_driver_executes_one_planner_selected_step(tmp_path):
    api, run_id = _new_run(tmp_path)
    control = api.get_agent_loop_control(run_id)
    before_events = list(api.get_events(run_id))

    result = api.run_agent_loop_tick(
        run_id,
        _planner_output(
            control,
            "call_capability",
            {"capability_id": "artifact.review"},
        ),
        tick_budget={
            "max_ticks": 2,
            "ticks_used": 0,
            "budget_basis": "test:tick-driver",
        },
    )

    assert result["tick_status"] == "executed"
    assert result["before_policy"]["should_continue"] is True
    assert result["before_policy"]["max_next_tick_kind"] == "planner_step"
    assert result["planner_result"]["planner_status"] == "accepted"
    assert result["planner_result"]["selected_step"] == "call_capability"
    assert result["after_policy"]["phase"] == "ready"
    assert result["after_policy"]["should_continue"] is True
    assert result["after_policy"]["tick_budget"] == {
        "max_ticks": 2,
        "ticks_used": 1,
        "remaining_ticks": 1,
        "budget_exhausted": False,
        "budget_basis": "test:tick-driver",
    }
    event_types = [event.event_type for event in api.get_events(run_id)]
    assert event_types[len(before_events) :] == [
        "action.proposed",
        "action.decided",
        "action.started",
        "artifact.created",
        "action.completed",
    ]
    _assert_no_forbidden_content_keys(result)


def test_agent_loop_tick_driver_stops_without_side_effects_when_budget_exhausted(
    tmp_path,
):
    api, run_id = _new_run(tmp_path)
    before_events = list(api.get_events(run_id))

    result = api.run_agent_loop_tick(
        run_id,
        None,
        tick_budget={
            "max_ticks": 2,
            "ticks_used": 2,
            "budget_basis": "test:exhausted",
        },
    )

    assert result["tick_status"] == "stopped"
    assert result["stop_reason"] == "tick_budget_exhausted"
    assert result["planner_result"] is None
    assert result["before_policy"]["should_continue"] is False
    assert result["after_policy"] == result["before_policy"]
    assert api.get_events(run_id) == before_events
    _assert_no_forbidden_content_keys(result)


def test_agent_loop_tick_driver_stops_without_side_effects_when_user_paused(
    tmp_path,
):
    api, run_id = _new_run(tmp_path)
    before_events = list(api.get_events(run_id))

    result = api.run_agent_loop_tick(
        run_id,
        None,
        user_pause={
            "user_paused": True,
            "pause_basis": "operator:test",
        },
    )

    assert result["tick_status"] == "stopped"
    assert result["stop_reason"] == "user_paused"
    assert result["planner_result"] is None
    assert result["before_policy"]["requires_human"] is True
    assert result["after_policy"] == result["before_policy"]
    assert api.get_events(run_id) == before_events
    _assert_no_forbidden_content_keys(result)
