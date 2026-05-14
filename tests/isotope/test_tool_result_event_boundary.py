from __future__ import annotations

import importlib
from dataclasses import asdict
from typing import Any

import pytest

from isotope import action_registry, events, models, projector, server
from isotope.checkpoint_store import FileCheckpointStore
from isotope.refs import ResourceRef


RUN_ID = "run_001"

FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
}


def _load_tool_protocol_module():
    try:
        return importlib.import_module("isotope.tool_protocol")
    except ModuleNotFoundError as exc:
        pytest.fail(f"tool protocol module is missing: {exc}")


def _new_run(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="tool result boundary")
    return api, run["run_id"]


def _event(event_id: str, event_type: str, payload: dict[str, Any]):
    return events.CanonicalEvent(
        event_id=event_id,
        run_id=RUN_ID,
        event_type=event_type,
        payload=payload,
        created_at=f"2026-05-09T00:00:{event_id[-2:]}Z",
    )


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        assert FORBIDDEN_CONTENT_KEYS.intersection(value) == set()
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def _event_types(api: server.InProcessServer, run_id: str) -> list[str]:
    return [event.event_type for event in api.get_events(run_id)]


def _registry_entry(tool_name: str) -> dict[str, Any]:
    return {
        "action_type": "call_tool",
        "tool_name": tool_name,
        "payload_requirements": {"required": ["text"]},
        "required_capabilities": {
            "tools": [tool_name],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
        "default_workspace_mode": "shared_ro",
        "result_kind": "artifact",
        "enabled": True,
    }


def test_tool_result_and_error_models_define_canonical_public_shape():
    module = _load_tool_protocol_module()

    result = module.ToolResult(
        result_summary="artifact written",
        artifact_refs=[
            ResourceRef(
                ref_type="artifact",
                scope="run",
                run_id=RUN_ID,
                artifact_id="artifact_001",
            ).to_dict()
        ],
        diagnostics=[],
        provenance={
            "execution_id": "exec_001",
            "proposal_id": "prop_001",
            "decision_id": "dec_001",
        },
    )
    error = module.ToolError(
        error_reason_code="tool_execution_failed",
        message="tool failed",
        partial_artifact_refs=[],
        provenance={
            "execution_id": "exec_001",
            "proposal_id": "prop_001",
            "decision_id": "dec_001",
        },
    )

    assert result.result_summary == "artifact written"
    assert result.artifact_refs[0]["artifact_id"] == "artifact_001"
    assert result.provenance["decision_id"] == "dec_001"
    assert error.error_reason_code == "tool_execution_failed"
    assert error.partial_artifact_refs == []


def test_successful_tool_result_uses_canonical_artifact_ref_events(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = api.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "hello",
            "summary": "tool result summary",
        },
    )

    assert result["status"] == "completed"
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
    artifact_event = next(
        event for event in api.get_events(run_id) if event.event_type == "artifact.created"
    )
    completed_event = next(
        event for event in api.get_events(run_id) if event.event_type == "action.completed"
    )
    assert artifact_event.payload["artifact"]["ref"]["artifact_id"].startswith("artifact_")
    assert completed_event.payload["artifact_refs"] == [
        artifact_event.payload["artifact"]["ref"]
    ]


def test_tool_result_events_include_execution_proposal_and_decision_provenance(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = api.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "hello",
            "summary": "tool result provenance",
        },
    )
    artifact_event = next(
        event for event in api.get_events(run_id) if event.event_type == "artifact.created"
    )

    assert artifact_event.payload["artifact"]["provenance"] == {
        "execution_id": result["execution_id"],
        "proposal_id": result["proposal_id"],
        "decision_id": result["decision_id"],
    }


def test_tool_output_does_not_expose_full_content_by_default(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = api.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "full content should stay out of events",
            "summary": "summary only",
        },
    )
    public_shape = {
        "result": {key: value for key, value in result.items() if key != "run_state"},
        "events": [event.payload for event in api.get_events(run_id)],
        "run_state": asdict(api.get_run_state(run_id)),
    }

    _assert_no_forbidden_content_keys(public_shape)
    assert "full content should stay out of events" not in repr(public_shape)


def test_malformed_tool_artifact_refs_fail_fast():
    canonical_events = [
        _event("evt_001", "run.created", {"run_id": RUN_ID}),
        _event(
            "evt_002",
            "artifact.created",
            {
                "artifact": {
                    "ref": {
                        "ref_type": "artifact",
                        "scope": "run",
                        "run_id": RUN_ID,
                    },
                    "artifact_type": "text",
                    "summary": "missing artifact id",
                    "provenance": {"execution_id": "exec_001", "proposal_id": "prop_001", "decision_id": "dec_001"},
                }
            },
        ),
    ]

    with pytest.raises(ValueError, match="artifact_id"):
        projector.RunProjector().project(canonical_events)


def test_tool_failure_uses_structured_action_failed_error(tmp_path):
    registry = action_registry.ActionTypeRegistry(
        entries=[_registry_entry("unsupported_structured_error_tool")]
    )
    api = server.InProcessServer(tmp_path, registry=registry)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="tool structured error")
    run_id = run["run_id"]

    result = api.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "unsupported_structured_error_tool",
            "text": "hello",
        },
    )
    failed_events = [
        event for event in api.get_events(run_id) if event.event_type == "action.failed"
    ]

    assert result["status"] == "failed"
    assert len(failed_events) == 1
    assert failed_events[0].payload["error_reason_code"] == "tool_execution_failed"
    assert failed_events[0].payload["structured_error"] == {
        "reason_code": "tool_execution_failed",
        "message": "unsupported handler for tool unsupported_structured_error_tool",
    }


def test_tool_failure_does_not_leave_partial_artifact_or_completed_event(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = api.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "hello",
            "requested_tools": [],
        },
    )

    assert result["status"] == "denied"
    assert "artifact.created" not in _event_types(api, run_id)
    assert "action.completed" not in _event_types(api, run_id)
    assert api.artifact_store.list_artifacts(run_id) == []


def test_tool_error_state_is_replayable_from_canonical_events(tmp_path):
    checkpoint_store = FileCheckpointStore(tmp_path / "checkpoints")
    api = server.InProcessServer(tmp_path, checkpoint_store=checkpoint_store)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="tool error replay")
    run_id = run["run_id"]

    result = api.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "hello",
            "requested_tools": [],
        },
    )
    replay_state = projector.RunProjector().rebuild(run_id, api.event_store)
    projector.RunProjector().save_checkpoint(run_id, api.event_store, checkpoint_store)
    checkpoint_state = projector.RunProjector().rebuild_with_checkpoint(
        run_id,
        api.event_store,
        checkpoint_store,
    )

    assert result["status"] == "denied"
    assert asdict(replay_state) == asdict(api.get_run_state(run_id))
    assert asdict(checkpoint_state) == asdict(api.get_run_state(run_id))


def test_tool_result_boundary_does_not_expose_product_tool_surfaces():
    module = _load_tool_protocol_module()

    assert not hasattr(module, "PluginMarketplace")
    assert not hasattr(module, "RemoteToolExecutor")
    assert not hasattr(module, "ToolStreamingResponse")
    assert not hasattr(module, "PublicToolSDK")
