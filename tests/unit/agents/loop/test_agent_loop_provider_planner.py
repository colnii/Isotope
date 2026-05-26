from __future__ import annotations

from typing import Any

import pytest

import isotope.runtime.in_process as server
from isotope.llm.provider import LLMResponse


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


class FakePlannerProvider:
    provider = "fake"
    model = "fake-loop-planner"

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=self.content,
            finish_reason="stop",
            usage={"prompt_tokens": 11, "completion_tokens": 7},
            raw={"raw_response": "SHOULD_NOT_LEAK"},
        )


def _new_run(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="loop provider planner")
    return api, run["run_id"]


def _provider_json(
    control: dict[str, Any],
    *,
    step: str = "call_capability",
    tick_id: str = "tick_001",
    decision_id: str = "decision_001",
) -> str:
    return (
        "{"
        '"planner_run_id":"planner_run_provider_001",'
        '"agent_id":"agent_loop",'
        f'"tick_id":"{tick_id}",'
        f'"decision_id":"{decision_id}",'
        '"basis":{'
        f'"run_id":"{control["run_id"]}",'
        f'"last_event_id":"{control["last_event_id"]}"'
        "},"
        '"decision":{'
        f'"step":"{step}",'
        '"request":{"capability_id":"artifact.review"}'
        "},"
        '"rationale":"review the source artifact"'
        "}"
    )


def _assert_no_forbidden_provider_keys(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_PROVIDER_KEYS.intersection(value)
        assert forbidden == set()
        for nested in value.values():
            _assert_no_forbidden_provider_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_provider_keys(nested)


def test_provider_planner_tick_runs_fake_provider_through_tick_execution(tmp_path):
    api, run_id = _new_run(tmp_path)
    control = api.get_agent_loop_control(run_id)
    provider = FakePlannerProvider(_provider_json(control))

    result = api.run_agent_loop_provider_planner_tick(
        run_id,
        provider=provider,
        agent_id="agent_loop",
        tick_id="tick_001",
        decision_id="decision_001",
        tick_budget={"max_ticks": 1, "ticks_used": 0, "budget_basis": "test"},
        max_tokens=128,
    )

    assert len(provider.calls) == 1
    assert provider.calls[0]["max_tokens"] == 128
    assert result["kind"] == "agent_loop_provider_planner_tick"
    assert result["tick_status"] == "executed"
    assert result["provider_result"]["provider_status"] == "completed"
    assert result["provider_result"]["agent_id"] == "agent_loop"
    assert result["provider_result"]["tick_id"] == "tick_001"
    assert result["provider_result"]["decision_id"] == "decision_001"
    assert result["provider_result"]["raw_prompt_quarantined"] is True
    assert result["provider_result"]["raw_response_quarantined"] is True
    assert result["planner_contract_result"]["planner_result"]["selected_step"] == (
        "call_capability"
    )
    assert result["after_policy"]["must_stop_reason"] == "tick_budget_exhausted"
    assert result["safety"]["real_llm_provider"] is True
    _assert_no_forbidden_provider_keys(result)


def test_provider_planner_tick_rejects_bad_json_without_side_effects(tmp_path):
    api, run_id = _new_run(tmp_path)
    provider = FakePlannerProvider("not-json")
    before_events = list(api.get_events(run_id))

    with pytest.raises(ValueError, match="planner provider response must contain a JSON object"):
        api.run_agent_loop_provider_planner_tick(
            run_id,
            provider=provider,
            agent_id="agent_loop",
            tick_id="tick_bad_json",
            decision_id="decision_bad_json",
            max_tokens=64,
        )

    assert api.get_events(run_id) == before_events
    assert len(provider.calls) == 1


def test_provider_planner_tick_rejects_missing_decision_without_side_effects(tmp_path):
    api, run_id = _new_run(tmp_path)
    control = api.get_agent_loop_control(run_id)
    provider = FakePlannerProvider(
        "{"
        '"planner_run_id":"planner_run_missing_decision",'
        f'"basis":{{"run_id":"{control["run_id"]}","last_event_id":"{control["last_event_id"]}"}}'
        "}"
    )
    before_events = list(api.get_events(run_id))

    with pytest.raises(ValueError, match="planner decision must be a dict"):
        api.run_agent_loop_provider_planner_tick(
            run_id,
            provider=provider,
            agent_id="agent_loop",
            tick_id="tick_missing_decision",
            decision_id="decision_missing_decision",
        )

    assert api.get_events(run_id) == before_events


def test_provider_planner_tick_rejects_illegal_action_without_side_effects(tmp_path):
    api, run_id = _new_run(tmp_path)
    control = api.get_agent_loop_control(run_id)
    provider = FakePlannerProvider(
        _provider_json(
            control,
            step="delete_worktree",
            tick_id="tick_illegal",
            decision_id="decision_illegal",
        )
    )
    before_events = list(api.get_events(run_id))

    with pytest.raises(ValueError, match="planner selected step"):
        api.run_agent_loop_provider_planner_tick(
            run_id,
            provider=provider,
            agent_id="agent_loop",
            tick_id="tick_illegal",
            decision_id="decision_illegal",
        )

    assert api.get_events(run_id) == before_events
