from __future__ import annotations

from typing import Any

import isotope.runtime.in_process as server
from isotope.agents.loop.runner import run_agent_loop_until_stop


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
    run = api.create_run(session["session_id"], goal="agent loop goal runner")
    return api, run["run_id"]


def _planner_output(control: dict[str, Any], tick_index: int) -> dict[str, Any]:
    return {
        "planner_run_id": f"planner_run_goal_{tick_index:03d}",
        "basis": {
            "run_id": control["run_id"],
            "last_event_id": control["last_event_id"],
        },
        "decision": {
            "step": "call_capability",
            "request": {"capability_id": "artifact.review"},
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


def test_agent_loop_goal_runner_repeats_ticks_until_budget_exhausted(tmp_path):
    api, run_id = _new_run(tmp_path)
    planner_requests = []

    def planner(request: dict[str, Any]) -> dict[str, Any]:
        planner_requests.append(
            {
                "tick_index": request["tick_index"],
                "phase": request["tick_policy"]["phase"],
                "ticks_used": request["tick_policy"]["tick_budget"]["ticks_used"],
            }
        )
        return _planner_output(request["control"], request["tick_index"])

    result = run_agent_loop_until_stop(
        api,
        run_id,
        planner=planner,
        max_ticks=2,
        budget_basis="test:goal-runner",
    )

    assert result["kind"] == "agent_loop_goal_run"
    assert result["status"] == "stopped"
    assert result["stop_reason"] == "tick_budget_exhausted"
    assert result["tick_count"] == 2
    assert [tick["tick_status"] for tick in result["ticks"]] == ["executed", "executed"]
    assert [tick["planner_result"]["planner_run_id"] for tick in result["ticks"]] == [
        "planner_run_goal_000",
        "planner_run_goal_001",
    ]
    assert planner_requests == [
        {"tick_index": 0, "phase": "ready", "ticks_used": 0},
        {"tick_index": 1, "phase": "ready", "ticks_used": 1},
    ]
    assert result["final_policy"]["must_stop_reason"] == "tick_budget_exhausted"
    assert result["final_policy"]["tick_budget"] == {
        "max_ticks": 2,
        "ticks_used": 2,
        "remaining_ticks": 0,
        "budget_exhausted": True,
        "budget_basis": "test:goal-runner",
    }
    _assert_no_forbidden_content_keys(result)


def test_agent_loop_goal_runner_stops_before_planner_when_user_paused(tmp_path):
    api, run_id = _new_run(tmp_path)
    planner_requests = []

    result = run_agent_loop_until_stop(
        api,
        run_id,
        planner=lambda request: planner_requests.append(request) or {},
        max_ticks=3,
        user_pause={"user_paused": True, "pause_basis": "operator:test"},
    )

    assert result["status"] == "stopped"
    assert result["stop_reason"] == "user_paused"
    assert result["tick_count"] == 0
    assert result["ticks"] == []
    assert planner_requests == []
    assert result["final_policy"]["requires_human"] is True
    _assert_no_forbidden_content_keys(result)


def test_in_process_runtime_exposes_limited_goal_runner(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = api.run_agent_loop_until_stop(
        run_id,
        planner=lambda request: _planner_output(
            request["control"],
            request["tick_index"],
        ),
        max_ticks=1,
        budget_basis="test:runtime-facade",
    )

    assert result["kind"] == "agent_loop_goal_run"
    assert result["tick_count"] == 1
    assert result["stop_reason"] == "tick_budget_exhausted"
    assert result["ticks"][0]["planner_result"]["planner_run_id"] == (
        "planner_run_goal_000"
    )
    _assert_no_forbidden_content_keys(result)
