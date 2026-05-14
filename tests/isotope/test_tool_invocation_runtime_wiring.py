from __future__ import annotations

import pytest

from isotope import action_registry, artifact_store, event_store, executor, models, server, workspace
from isotope.tool_protocol import ToolInvocation, ToolResult


RUN_ID = "run_tool_runtime_001"


def _registry() -> action_registry.ActionTypeRegistry:
    return action_registry.ActionTypeRegistry(
        entries=[
            {
                "action_type": "call_tool",
                "tool_name": "write_artifact_tool",
                "payload_requirements": {"required": ["text"]},
                "required_capabilities": {
                    "tools": ["write_artifact_tool"],
                    "workspace": {"mode": "shared_ro"},
                    "budget": {"seconds": 30},
                },
                "default_workspace_mode": "shared_ro",
                "result_kind": "artifact",
                "enabled": True,
            },
            {
                "action_type": "call_tool",
                "tool_name": "app_probe_tool",
                "payload_requirements": {"required": ["text"]},
                "required_capabilities": {
                    "tools": ["app_probe_tool"],
                    "workspace": {"mode": "shared_ro"},
                    "budget": {"seconds": 30},
                },
                "default_workspace_mode": "shared_ro",
                "result_kind": "diagnostic",
                "enabled": True,
            }
        ]
    )


def _proposal(*, requested_tools: list[str] | None = None) -> models.ActionProposal:
    return models.ActionProposal(
        proposal_id="prop_tool_runtime_001",
        run_id=RUN_ID,
        agent_id="agent_supervisor",
        thread_id="thread_main",
        action_type="call_tool",
        payload={"tool": "app_probe_tool", "text": "hello"},
        requested_capabilities={
            "tools": requested_tools or ["app_probe_tool"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
    )


def _decision(
    proposal: models.ActionProposal,
    *,
    granted_tools: list[str] | None = None,
) -> models.PolicyDecision:
    return models.PolicyDecision(
        decision_id="dec_tool_runtime_001",
        proposal_id=proposal.proposal_id,
        outcome="approved",
        grants={
            "tools": granted_tools if granted_tools is not None else ["app_probe_tool"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
        reason_codes=["approved_for_test"],
    )


def _runner(tmp_path, handler):
    return executor.Executor(
        event_store=event_store.FileEventStore(tmp_path),
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        workspace_manager=workspace.WorkspaceManager(),
        registry=_registry(),
        tool_handlers={"app_probe_tool": handler},
    )


def test_executor_passes_tool_invocation_to_explicit_in_process_handler(tmp_path):
    calls: list[ToolInvocation] = []

    def handler(invocation: ToolInvocation) -> ToolResult:
        calls.append(invocation)
        return ToolResult(
            result_summary="probe handled",
            diagnostics=[{"kind": "probe", "text": invocation.input_payload["text"]}],
            provenance=invocation.provenance,
        )

    proposal = _proposal(requested_tools=["app_probe_tool", "forged_tool"])
    decision = _decision(proposal, granted_tools=["app_probe_tool"])

    result = _runner(tmp_path, handler).execute(decision, proposal)

    assert result.status == "completed"
    assert len(calls) == 1
    invocation = calls[0]
    assert invocation.tool_name == "app_probe_tool"
    assert invocation.input_payload == proposal.payload
    assert invocation.proposal_id == proposal.proposal_id
    assert invocation.decision_id == decision.decision_id
    assert invocation.grants_snapshot == decision.grants
    assert invocation.requested_capabilities == {
        "tools": ["app_probe_tool"],
        "workspace": {"mode": "shared_ro"},
        "budget": {"seconds": 30},
    }


def test_ungranted_tool_handler_is_not_invoked(tmp_path):
    calls: list[ToolInvocation] = []

    def handler(invocation: ToolInvocation) -> ToolResult:
        calls.append(invocation)
        return ToolResult(result_summary="must not run", provenance=invocation.provenance)

    proposal = _proposal()
    decision = _decision(proposal, granted_tools=[])
    runner = _runner(tmp_path, handler)

    with pytest.raises(PermissionError, match="not granted"):
        runner.execute(decision, proposal)

    assert calls == []
    assert [event.event_type for event in runner.event_store.list_events(RUN_ID)] == [
        "action.started",
        "action.failed",
    ]


def test_tool_invocation_runtime_does_not_add_overreach_surfaces():
    assert not hasattr(executor.Executor, "load_plugin")
    assert not hasattr(executor.Executor, "spawn_sandboxed_process")
    assert not hasattr(executor.Executor, "call_remote_tool")


def test_in_process_server_forwards_tool_handlers_to_executor(tmp_path):
    calls: list[ToolInvocation] = []

    def handler(invocation: ToolInvocation) -> ToolResult:
        calls.append(invocation)
        return ToolResult(
            result_summary="probe handled through facade",
            diagnostics=[{"kind": "probe", "text": invocation.input_payload["text"]}],
            provenance=invocation.provenance,
        )

    api = server.InProcessServer(
        tmp_path,
        registry=_registry(),
        tool_handlers={"app_probe_tool": handler},
    )
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="facade tool handler")

    result = api.submit_action(
        run["run_id"],
        {
            "action": "call_tool",
            "tool": "app_probe_tool",
            "text": "hello",
            "requested_tools": ["app_probe_tool", "forged_tool"],
        },
    )

    assert result["status"] == "completed"
    assert "artifact_ref" not in result
    assert len(calls) == 1
    assert calls[0].tool_name == "app_probe_tool"
    assert calls[0].requested_capabilities == {
        "tools": ["app_probe_tool"],
        "workspace": {"mode": "shared_ro"},
        "budget": {"seconds": 30},
    }


def test_in_process_server_non_artifact_tool_does_not_return_stale_artifact_ref(tmp_path):
    calls: list[ToolInvocation] = []

    def handler(invocation: ToolInvocation) -> ToolResult:
        calls.append(invocation)
        return ToolResult(
            result_summary="diagnostic only",
            artifact_refs=[],
            provenance=invocation.provenance,
        )

    api = server.InProcessServer(
        tmp_path,
        registry=_registry(),
        tool_handlers={"app_probe_tool": handler},
    )
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="no stale artifact ref")
    source = api.create_source_artifact(run["run_id"], content="source", summary="source")

    result = api.submit_action(
        run["run_id"],
        {
            "action": "call_tool",
            "tool": "app_probe_tool",
            "text": "hello",
        },
    )
    completed_events = [
        event
        for event in api.get_events(run["run_id"])
        if event.event_type == "action.completed"
    ]

    assert result["status"] == "completed"
    assert source["artifact_ref"].artifact_id.startswith("artifact_")
    assert "artifact_ref" not in result
    assert calls
    assert completed_events[-1].payload["artifact_refs"] == []


def test_in_process_server_denied_tool_does_not_call_handler(tmp_path):
    calls: list[ToolInvocation] = []

    def handler(invocation: ToolInvocation) -> ToolResult:
        calls.append(invocation)
        return ToolResult(result_summary="must not run", provenance=invocation.provenance)

    api = server.InProcessServer(
        tmp_path,
        registry=_registry(),
        tool_handlers={"app_probe_tool": handler},
    )
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="facade denied tool")

    result = api.submit_action(
        run["run_id"],
        {
            "action": "call_tool",
            "tool": "app_probe_tool",
            "text": "hello",
            "requested_tools": [],
        },
    )

    assert result["status"] == "denied"
    assert calls == []
