from __future__ import annotations

import re

import pytest

import isotope.runtime.in_process.action_compiler as action_compiler
import isotope.platform.registry.actions as action_registry
import isotope.workspace.artifacts as artifact_store
import isotope.platform.state.event_store as event_store
import isotope.platform.events.events as events
import isotope.execution.executor as executor
from isotope.platform.schemas.actions import ActionProposal
import isotope.policy as policy
import isotope.platform.state.projector as projector
import isotope.runtime.in_process as server
import isotope.workspace as workspace


RUN_ID = "run_001"


def _proposal(
    *,
    tool: str = "write_artifact_tool",
    requested_tools: list[str] | None = None,
    workspace_mode: str = "shared_ro",
    budget_seconds: int = 30,
) -> ActionProposal:
    if requested_tools is None:
        requested_tools = [tool]
    return ActionProposal(
        proposal_id="prop_001",
        run_id=RUN_ID,
        agent_id="agent_supervisor",
        thread_id="thread_main",
        action_type="call_tool",
        payload={"tool": tool, "text": "hello"},
        requested_capabilities={
            "tools": requested_tools,
            "workspace": {"mode": workspace_mode},
            "budget": {"seconds": budget_seconds},
        },
    )


def _event(event_id: str, event_type: str, payload: dict):
    return events.CanonicalEvent(
        event_id=event_id,
        run_id=RUN_ID,
        event_type=event_type,
        payload=payload,
        created_at=f"2026-05-03T00:00:{event_id[-2:]}Z",
    )


def _stable_reason_code(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z][a-z0-9_]*", value))


def test_policy_engine_accepts_explicit_profile_version_metadata():
    engine = policy.PolicyEngine(
        policy_profile_id="demo_strict",
        policy_version="demo_strict@v1",
    )

    assert engine.policy_profile_id == "demo_strict"
    assert engine.policy_version == "demo_strict@v1"


def test_policy_decision_embeds_policy_profile_version_basis():
    decision = policy.PolicyEngine().decide(_proposal())

    assert decision.policy_profile_id == "default"
    assert isinstance(decision.policy_version, str)
    assert decision.policy_version
    assert decision.policy_basis == {
        "policy_profile_id": "default",
        "policy_version": decision.policy_version,
    }


def test_server_action_decided_event_includes_policy_basis(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="policy basis demo")

    api.submit_action(
        run["run_id"],
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "hello",
        },
    )

    decided = next(
        event.payload
        for event in api.get_events(run["run_id"])
        if event.event_type == "action.decided"
    )
    assert decided["policy_profile_id"] == api.policy.policy_profile_id
    assert decided["policy_version"] == api.policy.policy_version


def test_action_decided_payload_missing_policy_basis_fails_fast():
    canonical_events = [
        _event("evt_001", "run.created", {"run_id": RUN_ID}),
        _event(
            "evt_002",
            "action.decided",
                {
                    "proposal_id": "prop_001",
                    "decision_id": "dec_001",
                    "outcome": "denied",
                    "reason_codes": ["unsupported_tool"],
                },
            ),
    ]

    with pytest.raises(ValueError, match="policy"):
        projector.RunProjector().project(canonical_events)


def test_projector_exposes_policy_basis_from_event_payload_without_current_policy(monkeypatch):
    monkeypatch.setattr(
        policy.PolicyEngine,
        "decide",
        lambda self, proposal: pytest.fail("projector replay must not re-query current policy profile"),
    )
    canonical_events = [
        _event("evt_001", "run.created", {"run_id": RUN_ID}),
        _event(
            "evt_002",
            "action.proposed",
            {
                "proposal_id": "prop_001",
                "agent_id": "agent_supervisor",
                "action_type": "call_tool",
                "registry_id": "demo_registry",
                "registry_version": "demo_registry@v1",
            },
        ),
        _event(
            "evt_003",
            "action.decided",
            {
                "proposal_id": "prop_001",
                "decision_id": "dec_001",
                "outcome": "denied",
                "reason_codes": ["unsupported_tool"],
                "policy_profile_id": "demo_strict",
                "policy_version": "demo_strict@v1",
                "policy_basis": {
                    "policy_profile_id": "demo_strict",
                    "policy_version": "demo_strict@v1",
                },
            },
        ),
    ]

    state = projector.RunProjector().project(canonical_events)

    assert state.actions["prop_001"]["policy_profile_id"] == "demo_strict"
    assert state.actions["prop_001"]["policy_version"] == "demo_strict@v1"
    assert state.actions["prop_001"]["policy_basis"] == {
        "policy_profile_id": "demo_strict",
        "policy_version": "demo_strict@v1",
    }
    assert state.actions["prop_001"]["reason_codes"] == ["unsupported_tool"]


def test_modified_and_denied_reason_codes_are_stable_identifiers():
    engine = policy.PolicyEngine()
    modified = engine.decide(
        _proposal(
            requested_tools=["write_artifact_tool", "extra_tool"],
            workspace_mode="isolated",
            budget_seconds=999,
        )
    )
    denied = engine.decide(_proposal(requested_tools=[]))

    assert modified.outcome == "modified"
    assert denied.outcome == "denied"
    assert modified.reason_codes == ["capabilities_reduced"]
    assert denied.reason_codes == ["tool_not_requested"]
    assert all(_stable_reason_code(code) for code in modified.reason_codes + denied.reason_codes)


def test_executor_uses_decision_grants_snapshot_not_current_requested_capabilities(tmp_path):
    proposal = action_compiler.ActionCompiler().compile(
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "hello",
            "requested_tools": ["write_artifact_tool", "extra_tool"],
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
    proposal.requested_capabilities["tools"] = ["ungranted_tool"]
    proposal.requested_capabilities["workspace"] = {"mode": "isolated"}
    proposal.requested_capabilities["budget"] = {"seconds": 9999}
    runner = executor.Executor(
        event_store=event_store.FileEventStore(tmp_path),
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        workspace_manager=workspace.WorkspaceManager(),
        registry=action_registry.ActionTypeRegistry.default(),
    )

    result = runner.execute(decision, proposal)

    assert result.status == "completed"
    assert result.effective_grants_snapshot == decision.grants


def test_policy_boundary_does_not_expose_policy_dsl_or_product_ui_surface():
    assert not hasattr(policy, "PolicyDSL")
    assert not hasattr(policy, "ProductPolicyUI")
    assert not hasattr(policy.PolicyEngine, "load_remote_profile")
