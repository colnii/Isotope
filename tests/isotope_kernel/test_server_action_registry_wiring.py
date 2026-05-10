import pytest

from isotope_kernel import action_registry, checkpoint_store, projector, server


ACTION_LIFECYCLE_EVENTS = {
    "action.proposed",
    "action.decided",
    "action.started",
    "action.failed",
    "artifact.created",
    "action.completed",
    "run.completed",
}


def _registry_entry(tool_name: str = "write_artifact_tool", **overrides) -> dict:
    entry = {
        "action_type": "call_tool",
        "registry_id": "default",
        "registry_version": "v0.2",
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
    entry.update(overrides)
    return entry


def _registry_for_entries(*entries: dict) -> action_registry.ActionTypeRegistry:
    return action_registry.ActionTypeRegistry(entries=list(entries))


def _new_run(api: server.InProcessServer) -> str:
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="server registry wiring")
    return run["run_id"]


def _event_types(api: server.InProcessServer, run_id: str) -> list[str]:
    return [event.event_type for event in api.get_events(run_id)]


def test_server_accepts_explicit_action_registry(tmp_path):
    api = server.InProcessServer(
        tmp_path,
        registry=action_registry.ActionTypeRegistry.default(),
    )

    assert isinstance(api, server.InProcessServer)


def test_server_default_registry_happy_path_still_produces_hello_artifact(tmp_path):
    api = server.InProcessServer(tmp_path)
    run_id = _new_run(api)

    result = api.submit_input(run_id, "hello")

    assert result["status"] == "completed"
    assert result["run_state"].artifacts[0]["summary"] == "hello artifact"


def test_disabled_registry_fails_at_compiler_boundary_without_action_events(tmp_path):
    registry = _registry_for_entries(_registry_entry(enabled=False))
    api = server.InProcessServer(tmp_path, registry=registry)
    run_id = _new_run(api)
    before = _event_types(api, run_id)

    with pytest.raises(ValueError, match="disabled tool"):
        api.submit_input(run_id, "hello")

    after = _event_types(api, run_id)
    assert after == before
    assert not any(event_type in ACTION_LIFECYCLE_EVENTS for event_type in after[len(before):])
    assert api.artifact_store.list_artifacts(run_id) == []


def test_custom_registry_flows_through_compiler_policy_and_executor(tmp_path):
    registry = _registry_for_entries(_registry_entry("write_report_tool"))
    api = server.InProcessServer(tmp_path, registry=registry)
    run_id = _new_run(api)

    result = api.submit_tool_request(run_id, tool="write_report_tool", text="hello")

    assert result["status"] == "failed"
    assert result["execution_id"]
    event_types = _event_types(api, run_id)
    assert event_types == [
        "run.created",
        "agent.created",
        "thread.created",
        "action.proposed",
        "action.decided",
        "action.started",
        "action.failed",
    ]
    assert "artifact.created" not in event_types
    assert "action.completed" not in event_types
    assert "run.completed" not in event_types
    assert api.artifact_store.list_artifacts(run_id) == []


def test_registry_entry_does_not_create_server_dynamic_plugin(tmp_path):
    registry = _registry_for_entries(_registry_entry("write_report_tool"))
    api = server.InProcessServer(tmp_path, registry=registry)
    run_id = _new_run(api)

    result = api.submit_tool_request(run_id, tool="write_report_tool", text="hello")

    assert result["status"] == "failed"
    failed = [
        event for event in api.get_events(run_id)
        if event.event_type == "action.failed"
    ][0]
    assert "unsupported handler" in failed.payload["error"]
    assert api.artifact_store.list_artifacts(run_id) == []


def test_server_constructor_policy_metadata_flows_to_decision_read_model_replay_and_checkpoint(tmp_path):
    registry = action_registry.ActionTypeRegistry(
        entries=[_registry_entry("write_artifact_tool")],
        registry_id="tenant_registry",
        registry_version="2026-05",
    )
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path / "checkpoints")
    api = server.InProcessServer(
        tmp_path,
        checkpoint_store=checkpoints,
        registry=registry,
        policy_profile_id="tenant_policy",
        policy_version="2026-05-policy",
    )
    run_id = _new_run(api)

    result = api.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "tenant output",
            "requested_tools": ["write_artifact_tool"],
        },
    )

    decided = [
        event for event in api.get_events(run_id)
        if event.event_type == "action.decided"
    ][0]
    assert decided.payload["policy_profile_id"] == "tenant_policy"
    assert decided.payload["policy_version"] == "2026-05-policy"
    assert decided.payload["policy_basis"] == {
        "policy_profile_id": "tenant_policy",
        "policy_version": "2026-05-policy",
    }
    assert result["run_state"].actions[result["execution_id"]]["policy_basis"] == {
        "policy_profile_id": "tenant_policy",
        "policy_version": "2026-05-policy",
    }

    replayed = projector.RunProjector().rebuild(run_id, api.event_store)
    projector.RunProjector().save_checkpoint(run_id, api.event_store, checkpoints)
    restored = projector.RunProjector().rebuild_with_checkpoint(run_id, api.event_store, checkpoints)

    assert replayed.actions[result["execution_id"]]["policy_profile_id"] == "tenant_policy"
    assert replayed.actions[result["execution_id"]]["policy_version"] == "2026-05-policy"
    assert restored.actions[result["execution_id"]]["policy_basis"] == {
        "policy_profile_id": "tenant_policy",
        "policy_version": "2026-05-policy",
    }
