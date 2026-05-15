from __future__ import annotations

import importlib

import pytest

import isotope.runtime.action_compiler as action_compiler
import isotope.platform.registry.actions as action_registry
import isotope.workspace.artifacts as artifact_store
import isotope.platform.state.event_store as event_store
import isotope.execution.executor as executor
import isotope.platform.schemas.models as models
import isotope.policy as policy
import isotope.runtime.in_process as server
import isotope.workspace as workspace


RUN_ID = "run_001"


def _load_tool_protocol_module():
    try:
        return importlib.import_module("isotope.platform.schemas.tool_protocol")
    except ModuleNotFoundError as exc:
        pytest.fail(f"tool protocol module is missing: {exc}")


def _proposal(
    *,
    tool: str = "write_artifact_tool",
    requested_tools: list[str] | None = None,
    workspace_mode: str = "shared_ro",
    budget_seconds: int = 30,
) -> models.ActionProposal:
    if requested_tools is None:
        requested_tools = [tool]
    return models.ActionProposal(
        proposal_id="prop_001",
        run_id=RUN_ID,
        agent_id="agent_supervisor",
        thread_id="thread_main",
        action_type="call_tool",
        payload={
            "tool": tool,
            "text": "hello",
            "summary": "tool protocol artifact",
        },
        requested_capabilities={
            "tools": requested_tools,
            "workspace": {"mode": workspace_mode},
            "budget": {"seconds": budget_seconds},
        },
    )


def _runner(tmp_path):
    return executor.Executor(
        event_store=event_store.FileEventStore(tmp_path),
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        workspace_manager=workspace.WorkspaceManager(),
        registry=action_registry.ActionTypeRegistry.default(),
    )


def _event_types(runner: executor.Executor, run_id: str = RUN_ID) -> list[str]:
    return [event.event_type for event in runner.event_store.list_events(run_id)]


def test_tool_protocol_models_exist_for_invocation_result_and_error():
    module = _load_tool_protocol_module()

    assert hasattr(module, "ToolInvocation")
    assert hasattr(module, "ToolResult")
    assert hasattr(module, "ToolError")


def test_tool_invocation_shape_carries_grants_budget_workspace_and_provenance():
    module = _load_tool_protocol_module()

    invocation = module.ToolInvocation(
        tool_name="write_artifact_tool",
        input_payload={"text": "hello"},
        execution_id="exec_001",
        proposal_id="prop_001",
        decision_id="dec_001",
        grants_snapshot={
            "tools": ["write_artifact_tool"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
        budget={"seconds": 30},
        workspace_binding={
            "workspace_id": "workspace_001",
            "mode": "shared_ro",
            "lease_status": "bound",
        },
        provenance={
            "execution_id": "exec_001",
            "proposal_id": "prop_001",
            "decision_id": "dec_001",
        },
    )

    assert invocation.tool_name == "write_artifact_tool"
    assert invocation.input_payload == {"text": "hello"}
    assert invocation.grants_snapshot["tools"] == ["write_artifact_tool"]
    assert invocation.budget == {"seconds": 30}
    assert invocation.workspace_binding["mode"] == "shared_ro"
    assert invocation.provenance == {
        "execution_id": "exec_001",
        "proposal_id": "prop_001",
        "decision_id": "dec_001",
    }


def test_malformed_tool_invocation_fails_fast():
    module = _load_tool_protocol_module()

    with pytest.raises(ValueError, match="tool_name"):
        module.ToolInvocation(
            tool_name="",
            input_payload={"text": "hello"},
            execution_id="exec_001",
            proposal_id="prop_001",
            decision_id="dec_001",
            grants_snapshot={"tools": ["write_artifact_tool"]},
            provenance={
                "execution_id": "exec_001",
                "proposal_id": "prop_001",
                "decision_id": "dec_001",
            },
        )

    with pytest.raises(ValueError, match="decision_id"):
        module.ToolInvocation(
            tool_name="write_artifact_tool",
            input_payload={"text": "hello"},
            execution_id="exec_001",
            proposal_id="prop_001",
            decision_id="",
            grants_snapshot={"tools": ["write_artifact_tool"]},
            provenance={
                "execution_id": "exec_001",
                "proposal_id": "prop_001",
                "decision_id": "",
            },
        )


def test_tool_invocation_rejects_requested_capabilities_outside_grants():
    module = _load_tool_protocol_module()

    with pytest.raises(ValueError, match="outside grants"):
        module.ToolInvocation(
            tool_name="write_artifact_tool",
            input_payload={"text": "hello"},
            execution_id="exec_001",
            proposal_id="prop_001",
            decision_id="dec_001",
            grants_snapshot={
                "tools": ["write_artifact_tool"],
                "workspace": {"mode": "shared_ro"},
                "budget": {"seconds": 30},
            },
            requested_capabilities={
                "tools": ["write_artifact_tool", "forged_tool"],
                "workspace": {"mode": "isolated"},
                "budget": {"seconds": 999},
            },
            provenance={
                "execution_id": "exec_001",
                "proposal_id": "prop_001",
                "decision_id": "dec_001",
            },
        )


def test_executor_uses_decision_grants_snapshot_not_requested_capabilities(tmp_path):
    proposal = action_compiler.ActionCompiler().compile(
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "hello",
            "requested_tools": ["write_artifact_tool", "forged_tool"],
            "workspace_mode": "isolated",
            "budget": {"seconds": 999},
        },
        {
            "run_id": RUN_ID,
            "agent_id": "agent_supervisor",
            "thread_id": "thread_main",
        },
    )
    decision = policy.PolicyEngine().decide(proposal)
    proposal.requested_capabilities["tools"] = ["forged_tool"]
    proposal.requested_capabilities["workspace"] = {"mode": "isolated"}
    proposal.requested_capabilities["budget"] = {"seconds": 9999}

    result = _runner(tmp_path).execute(decision, proposal)

    assert result.status == "completed"
    assert result.effective_grants_snapshot == decision.grants
    assert result.effective_grants_snapshot == {
        "tools": ["write_artifact_tool"],
        "workspace": {"mode": "shared_ro"},
        "budget": {"seconds": 30},
    }


def test_ungranted_tool_rejected_without_artifact_side_effects(tmp_path):
    proposal = _proposal()
    decision = models.PolicyDecision(
        decision_id="dec_001",
        proposal_id=proposal.proposal_id,
        outcome="approved",
        grants={
            "tools": [],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
        reason_codes=[],
    )
    runner = _runner(tmp_path)

    with pytest.raises(PermissionError, match="not granted"):
        runner.execute(decision, proposal)

    assert _event_types(runner) == ["action.started", "action.failed"]
    assert runner.artifact_store.list_artifacts(RUN_ID) == []


def test_ungranted_workspace_memory_and_external_access_are_rejected(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="tool protocol grants")

    result = api.submit_action(
        run["run_id"],
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "hello",
            "workspace_mode": "isolated",
            "requested_tools": ["write_artifact_tool", "write_memory", "external_ingest"],
        },
    )

    assert result["decision"].outcome == "modified"
    assert result["decision"].grants["tools"] == ["write_artifact_tool"]
    assert result["decision"].grants["workspace"] == {"mode": "shared_ro"}
    assert "write_memory" not in result["decision"].grants["tools"]
    assert "external_ingest" not in result["decision"].grants["tools"]


def test_tool_protocol_does_not_expose_overreach_surfaces():
    assert not hasattr(action_registry, "PluginMarketplace")
    assert not hasattr(action_registry.ActionTypeRegistry, "load_remote")
    assert not hasattr(executor.Executor, "spawn_sandboxed_process")
    assert not hasattr(executor.Executor, "execute_remote_tool")
    assert not hasattr(executor.Executor, "stream_tool_output")
    assert not hasattr(server.InProcessServer, "register_public_tool_sdk")
