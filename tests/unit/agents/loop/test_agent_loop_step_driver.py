from __future__ import annotations

import json
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


def test_agent_loop_step_driver_can_call_allowlisted_capability_as_one_step(tmp_path):
    api, run_id = _new_run(tmp_path)
    before_events = list(api.get_events(run_id))

    result = api.run_agent_loop_step(
        run_id,
        {
            "step": "call_capability",
            "capability_id": "artifact.review",
        },
    )

    assert result["step"] == "call_capability"
    assert result["status"] == "completed"
    capability_run = result["action_result"]["capability_run"]
    assert capability_run["kind"] == "capability_run_result"
    assert capability_run["capability_id"] == "artifact.review"
    assert capability_run["status"] == "completed"
    assert capability_run["scenario"] == "artifact-review"
    assert capability_run["replay_ok"] is True
    assert capability_run["checkpoint_ok"] is True
    assert result["action_result"]["artifact_ref"]["ref_type"] == "artifact"
    assert result["action_result"]["artifact_summary"] == "Capability artifact.review completed"
    assert result["control"]["phase"] == "ready"
    assert result["control"]["progress"]["artifacts_total"] == 1
    event_types = [event.event_type for event in api.get_events(run_id)]
    assert event_types[len(before_events) :] == [
        "action.proposed",
        "action.decided",
        "action.started",
        "artifact.created",
        "action.completed",
    ]
    json.dumps(result)
    _assert_no_forbidden_content_keys(result)


def test_agent_loop_step_driver_passes_inputs_to_capability_runner(tmp_path):
    api, run_id = _new_run(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text(
        "Supervisor request_context can retrieve project context.\n",
        encoding="utf-8",
    )
    codex_home = tmp_path / "codex-home"

    result = api.run_agent_loop_step(
        run_id,
        {
            "step": "call_capability",
            "capability_id": "supervisor.request_context",
            "inputs": {
                "codex_home": str(codex_home),
                "cwd": str(workspace),
                "query": "request_context project context",
                "max_results": 2,
            },
        },
    )

    assert result["step"] == "call_capability"
    assert result["status"] == "completed"
    capability_run = result["action_result"]["capability_run"]
    assert capability_run["capability_id"] == "supervisor.request_context"
    assert capability_run["status"] == "completed"
    assert capability_run["runner_kind"] == "deterministic_projection"
    assert capability_run["context_result"]["query"] == "request_context project context"
    assert capability_run["context_result"]["item_count"] >= 1
    assert result["action_result"]["artifact_ref"]["ref_type"] == "artifact"
    assert (codex_home / "supervisor" / "context_results.jsonl").is_file()
    _assert_no_forbidden_content_keys(result)


def test_agent_loop_step_uses_internal_system_inputs_and_ignores_model_routing(
    tmp_path,
    monkeypatch,
):
    api, run_id = _new_run(tmp_path)
    captured: dict[str, Any] = {}

    class RecordingRunner:
        def describe_capability(self, capability_id: str) -> dict[str, Any]:
            return {
                "input_contract": {
                    "type": "object",
                    "required": ["root", "cwd", "query"],
                    "properties": {
                        "query": {"type": "string"},
                        "root": {"type": "string", "x-system-input": True},
                        "cwd": {"type": "string", "x-system-input": True},
                        "run_id": {"type": "string", "x-system-input": True},
                        "execution_id": {"type": "string", "x-system-input": True},
                    },
                }
            }

        def run_capability(self, capability_id: str, *, root_path, inputs):
            captured["inputs"] = dict(inputs)
            return {
                "kind": "capability_run_result",
                "capability_id": capability_id,
                "status": "completed",
            }

    monkeypatch.setattr(
        "isotope.capabilities.runner.CapabilityRunner",
        lambda: RecordingRunner(),
    )

    api.run_agent_loop_step(
        run_id,
        {
            "step": "call_capability",
            "capability_id": "code.search",
            "inputs": {
                "query": "value",
                "root": "/model/must/not/win",
                "cwd": "/model/must/not/win",
            },
            "_system_inputs": {
                "root": str(tmp_path / "state"),
                "cwd": str(tmp_path / "repo"),
            },
        },
    )

    assert captured["inputs"]["query"] == "value"
    assert captured["inputs"]["root"] == str(tmp_path / "state")
    assert captured["inputs"]["cwd"] == str(tmp_path / "repo")
    assert captured["inputs"]["run_id"] == run_id
    assert captured["inputs"]["execution_id"].startswith("exec_")


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


def test_agent_loop_step_driver_rejects_malformed_capability_inputs_without_side_effects(tmp_path):
    api, run_id = _new_run(tmp_path)
    before_events = list(api.get_events(run_id))

    with pytest.raises(ValueError, match="inputs must be a dict"):
        api.run_agent_loop_step(
            run_id,
            {
                "step": "call_capability",
                "capability_id": "artifact.review",
                "inputs": ["not", "an", "object"],
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
