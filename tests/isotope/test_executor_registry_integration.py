import pytest

from isotope import action_registry, artifact_store, event_store, executor, models, workspace


_NO_REGISTRY = object()


def _registry_entry(tool_name: str = "write_artifact_tool", **overrides) -> dict:
    entry = {
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
    entry.update(overrides)
    return entry


def _registry_for_entries(*entries: dict) -> action_registry.ActionTypeRegistry:
    return action_registry.ActionTypeRegistry(entries=list(entries))


def _proposal(tool: str = "write_artifact_tool") -> models.ActionProposal:
    return models.ActionProposal(
        proposal_id="prop_001",
        run_id="run_001",
        agent_id="agent_supervisor",
        thread_id="thread_main",
        action_type="call_tool",
        payload={"tool": tool, "text": "hello"},
        requested_capabilities={
            "tools": [tool],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
    )


def _decision(
    proposal: models.ActionProposal,
    *,
    granted_tools: list[str] | None = None,
) -> models.PolicyDecision:
    if granted_tools is None:
        granted_tools = [proposal.payload["tool"]]
    return models.PolicyDecision(
        decision_id="dec_001",
        proposal_id=proposal.proposal_id,
        outcome="approved",
        grants={
            "tools": granted_tools,
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
        reason_codes=[],
    )


def _runner(tmp_path, registry=_NO_REGISTRY) -> executor.Executor:
    kwargs = {}
    if registry is not _NO_REGISTRY:
        kwargs["registry"] = registry
    return executor.Executor(
        event_store=event_store.FileEventStore(tmp_path),
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        workspace_manager=workspace.WorkspaceManager(),
        **kwargs,
    )


def _event_types(runner: executor.Executor, run_id: str = "run_001") -> list[str]:
    return [event.event_type for event in runner.event_store.list_events(run_id)]


def test_executor_accepts_explicit_registry(tmp_path):
    runner = _runner(tmp_path, registry=action_registry.ActionTypeRegistry.default())

    assert isinstance(runner, executor.Executor)


def test_default_executor_still_executes_write_artifact_tool(tmp_path):
    proposal = _proposal()
    runner = _runner(tmp_path)

    result = runner.execute(_decision(proposal), proposal)

    assert result.status == "completed"
    assert runner.artifact_store.list_artifacts(proposal.run_id)


def test_executor_unknown_granted_tool_fails_closed_without_hardcoded_error(tmp_path):
    proposal = _proposal(tool="unknown_tool")
    runner = _runner(tmp_path)

    with pytest.raises(PermissionError) as exc_info:
        runner.execute(_decision(proposal, granted_tools=["unknown_tool"]), proposal)

    assert "unknown tool" in str(exc_info.value) or "unsupported handler" in str(exc_info.value)
    assert "write_artifact_tool is not granted" not in str(exc_info.value)
    assert _event_types(runner) == ["action.started", "action.failed"]
    assert runner.artifact_store.list_artifacts(proposal.run_id) == []


def test_disabled_registry_entry_is_rejected_by_executor(tmp_path):
    proposal = _proposal()
    registry = _registry_for_entries(_registry_entry(enabled=False))
    runner = _runner(tmp_path, registry=registry)

    with pytest.raises(PermissionError, match="disabled tool|unsupported handler"):
        runner.execute(_decision(proposal), proposal)

    assert _event_types(runner) == ["action.started", "action.failed"]
    assert runner.artifact_store.list_artifacts(proposal.run_id) == []


def test_registry_does_not_replace_policy_grants(tmp_path):
    proposal = _proposal()
    runner = _runner(tmp_path, registry=action_registry.ActionTypeRegistry.default())

    with pytest.raises(PermissionError, match="not granted"):
        runner.execute(_decision(proposal, granted_tools=[]), proposal)

    assert _event_types(runner) == ["action.started", "action.failed"]
    assert runner.artifact_store.list_artifacts(proposal.run_id) == []


def test_registry_entry_does_not_create_dynamic_plugin_handler(tmp_path):
    proposal = _proposal(tool="write_report_tool")
    registry = _registry_for_entries(_registry_entry("write_report_tool"))
    runner = _runner(tmp_path, registry=registry)

    with pytest.raises(PermissionError, match="no handler|unsupported handler"):
        runner.execute(_decision(proposal, granted_tools=["write_report_tool"]), proposal)

    assert _event_types(runner) == ["action.started", "action.failed"]
    assert runner.artifact_store.list_artifacts(proposal.run_id) == []


def test_registry_backed_write_artifact_success_event_order_is_unchanged(tmp_path):
    proposal = _proposal()
    runner = _runner(tmp_path, registry=action_registry.ActionTypeRegistry.default())

    result = runner.execute(_decision(proposal), proposal)

    assert result.status == "completed"
    assert _event_types(runner) == ["action.started", "artifact.created", "action.completed"]
