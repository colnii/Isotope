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
    run = api.create_run(session["session_id"], goal="agent loop tick policy")
    return api, run["run_id"]


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_CONTENT_KEYS.intersection(value)
        assert forbidden == set()
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def test_tick_policy_for_ready_run_allows_one_planner_tick_without_side_effects(tmp_path):
    api, run_id = _new_run(tmp_path)
    before_events = list(api.get_events(run_id))

    policy = api.get_agent_loop_tick_policy(run_id)

    assert policy["run_id"] == run_id
    assert policy["phase"] == "ready"
    assert policy["should_continue"] is True
    assert policy["must_stop_reason"] is None
    assert policy["requires_human"] is False
    assert policy["max_next_tick_kind"] == "planner_step"
    assert policy["next_actions"] == [
        "query_memory",
        "create_source_artifact",
        "record_turn_memory",
        "submit_worker_handoff",
        "submit_approval_gated_action",
        "call_capability",
    ]
    assert policy["deferred_capabilities"] == [
        "real_llm_provider",
        "scheduler",
        "real_worker_runtime",
    ]
    assert api.get_events(run_id) == before_events
    _assert_no_forbidden_content_keys(policy)


def test_tick_policy_stops_when_tick_budget_is_exhausted(tmp_path):
    api, run_id = _new_run(tmp_path)

    policy = api.get_agent_loop_tick_policy(
        run_id,
        tick_budget={
            "max_ticks": 2,
            "ticks_used": 2,
            "budget_basis": "app-request:test",
        },
    )

    assert policy["should_continue"] is False
    assert policy["must_stop_reason"] == "tick_budget_exhausted"
    assert policy["requires_human"] is False
    assert policy["max_next_tick_kind"] is None
    assert policy["tick_budget"] == {
        "max_ticks": 2,
        "ticks_used": 2,
        "remaining_ticks": 0,
        "budget_exhausted": True,
        "budget_basis": "app-request:test",
    }


def test_tick_policy_stops_when_user_paused(tmp_path):
    api, run_id = _new_run(tmp_path)

    policy = api.get_agent_loop_tick_policy(
        run_id,
        user_pause={
            "user_paused": True,
            "pause_basis": "operator:test",
        },
    )

    assert policy["should_continue"] is False
    assert policy["must_stop_reason"] == "user_paused"
    assert policy["requires_human"] is True
    assert policy["max_next_tick_kind"] is None
    assert policy["user_pause"] == {
        "user_paused": True,
        "pause_basis": "operator:test",
    }
