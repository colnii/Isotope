import pytest

import isotope.runtime.action_compiler as action_compiler
import isotope.workspace.artifacts as artifact_store
import isotope.platform.state.event_store as event_store
import isotope.platform.events.events as events
import isotope.execution.executor as executor
import isotope.platform.schemas.models as models
import isotope.platform.state.projector as projector
import isotope.workspace as workspace


ARTIFACT_REF = {
    "ref_type": "artifact",
    "scope": "run",
    "run_id": "run_001",
    "artifact_id": "artifact_001",
}


def _event(event_id: str, event_type: str, payload: dict):
    return events.CanonicalEvent(
        event_id=event_id,
        run_id="run_001",
        event_type=event_type,
        payload=payload,
        created_at=f"2026-05-02T00:03:{event_id[-2:]}Z",
    )


def _run_created():
    return _event("evt_001", "run.created", {"run_id": "run_001"})


def _agent_created():
    return _event("evt_002", "agent.created", {"agent_id": "agent_supervisor"})


def _workspace_bound(**overrides):
    payload = {
        "workspace_id": "workspace_shared_ro",
        "run_id": "run_001",
        "mode": "shared_ro",
        "bound_to": {"agent_id": "agent_supervisor"},
        "lease_status": "active",
        "provenance": {
            "decision_id": "dec_workspace_001",
            "grant_basis": {"workspace": {"mode": "shared_ro"}},
        },
    }
    payload.update(overrides)
    return _event("evt_003", "workspace.bound", payload)


def _delegation_proposed(requested_workspace_mode: str = "isolated_rw"):
    return _event(
        "evt_003",
        "delegation.proposed",
        {
            "delegation_id": "deleg_001",
            "run_id": "run_001",
            "parent_agent_id": "agent_supervisor",
            "requested_worker_role": "worker",
            "requested_capabilities": {
                "tools": ["write_artifact_tool"],
                "workspace": {"mode": requested_workspace_mode},
                "budget": {"seconds": 999},
            },
        },
    )


def _delegation_decided(grants: dict | None = None):
    if grants is None:
        grants = {
            "tools": ["write_artifact_tool"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        }
    return _event(
        "evt_004",
        "delegation.decided",
        {
            "delegation_id": "deleg_001",
            "decision_id": "dec_deleg_001",
            "outcome": "modified",
            "grants": grants,
        },
    )


def _worker_created(workspace_payload: dict | None = None):
    if workspace_payload is None:
        workspace_payload = {"mode": "isolated_rw"}
    return _event(
        "evt_005",
        "worker.created",
        {
            "worker_id": "worker_001",
            "agent_id": "agent_worker_001",
            "run_id": "run_001",
            "parent_agent_id": "agent_supervisor",
            "delegation_id": "deleg_001",
            "decision_id": "dec_deleg_001",
            "role": "worker",
            "status": "created",
            "workspace": workspace_payload,
        },
    )


def _action_proposal(workspace_mode="isolated_rw"):
    return action_compiler.ActionCompiler().compile(
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "hello",
            "requested_tools": ["write_artifact_tool"],
            "workspace_mode": workspace_mode,
            "budget": {"seconds": 30},
        },
        {
            "run_id": "run_001",
            "agent_id": "agent_supervisor",
            "thread_id": "thread_main",
        },
    )


def _decision(proposal, grants):
    return models.PolicyDecision(
        decision_id="dec_001",
        proposal_id=proposal.proposal_id,
        outcome="approved",
        grants=grants,
        reason_codes=[],
    )


def test_existing_workspace_manager_requires_policy_grants():
    manager = workspace.WorkspaceManager()

    with pytest.raises(TypeError, match="workspace grants must be a dict"):
        manager.get_binding(None)
    with pytest.raises(PermissionError, match="workspace grant is required"):
        manager.get_binding({})


def test_write_or_isolated_workspace_mode_cannot_be_granted_implicitly():
    manager = workspace.WorkspaceManager()

    for mode in ("write", "shared_rw", "isolated_rw", "isolated"):
        with pytest.raises(PermissionError, match="workspace mode is not supported"):
            manager.get_binding({"workspace": {"mode": mode}})


def test_requested_workspace_mode_cannot_bypass_policy_decision_grants(tmp_path):
    proposal = _action_proposal(workspace_mode="isolated_rw")
    decision = _decision(
        proposal,
        {
            "tools": ["write_artifact_tool"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
    )

    class RecordingWorkspaceManager:
        def __init__(self):
            self.seen_grants = None

        def get_binding(self, grants):
            self.seen_grants = grants
            return workspace.WorkspaceBinding(workspace_id="workspace_shared_ro", mode=grants["workspace"]["mode"])

    manager = RecordingWorkspaceManager()
    runner = executor.Executor(
        event_store=event_store.FileEventStore(tmp_path),
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        workspace_manager=manager,
    )

    execution = runner.execute(decision, proposal)

    assert manager.seen_grants is decision.grants
    assert proposal.requested_capabilities["workspace"]["mode"] == "isolated_rw"
    assert execution.effective_grants_snapshot["workspace"]["mode"] == "shared_ro"


def test_workspace_binding_event_requires_policy_grants():
    with pytest.raises((PermissionError, ValueError), match="workspace|grant"):
        projector.RunProjector().project(
            [
                _run_created(),
                _agent_created(),
                _workspace_bound(provenance={}),
            ]
        )


def test_malformed_workspace_grant_does_not_create_binding():
    with pytest.raises((TypeError, ValueError), match="workspace|grant"):
        projector.RunProjector().project(
            [
                _run_created(),
                _agent_created(),
                _workspace_bound(provenance={"decision_id": "dec_workspace_001", "grant_basis": "not-a-dict"}),
            ]
        )


def test_worker_workspace_binding_comes_from_grants_not_requested_or_payload_workspace():
    state = projector.RunProjector().project(
        [
            _run_created(),
            _agent_created(),
            _delegation_proposed(requested_workspace_mode="isolated_rw"),
            _delegation_decided(
                grants={
                    "tools": ["write_artifact_tool"],
                    "workspace": {"mode": "shared_ro"},
                    "budget": {"seconds": 30},
                }
            ),
            _worker_created(workspace_payload={"mode": "isolated_rw"}),
        ]
    )

    worker = state.workers["worker_001"]
    assert worker["requested_capabilities"]["workspace"]["mode"] == "isolated_rw"
    assert worker["grants"]["workspace"]["mode"] == "shared_ro"
    assert worker["workspace"]["mode"] == "shared_ro"


def test_denied_workspace_grant_does_not_produce_binding():
    with pytest.raises((PermissionError, ValueError), match="workspace|grant|mode"):
        projector.RunProjector().project(
            [
                _run_created(),
                _agent_created(),
                _workspace_bound(
                    mode="write",
                    provenance={
                        "decision_id": "dec_workspace_001",
                        "grant_basis": {"workspace": {"mode": "shared_ro"}},
                    },
                ),
            ]
        )


def test_artifact_capture_from_workspace_still_uses_artifact_provenance_path():
    state = projector.RunProjector().project(
        [
            _run_created(),
            _event(
                "evt_002",
                "action.proposed",
                {
                    "proposal_id": "prop_001",
                    "agent_id": "agent_supervisor",
                    "action_type": "call_tool",
                    "registry_id": "default",
                    "registry_version": "v0.2",
                },
            ),
            _event(
                "evt_003",
                "action.decided",
                {
                    "proposal_id": "prop_001",
                    "decision_id": "dec_001",
                    "outcome": "approved",
                    "policy_profile_id": "default",
                    "policy_version": "v0.2",
                },
            ),
            _event("evt_004", "action.started", {"execution_id": "exec_001", "proposal_id": "prop_001", "decision_id": "dec_001"}),
            _event(
                "evt_005",
                "artifact.created",
                {
                    "artifact": {
                        "ref": ARTIFACT_REF,
                        "artifact_type": "text",
                        "summary": "captured workspace output",
                        "provenance": {
                            "execution_id": "exec_001",
                            "proposal_id": "prop_001",
                            "decision_id": "dec_001",
                            "workspace_id": "workspace_shared_ro",
                        },
                    }
                },
            ),
        ]
    )

    artifact = state.artifacts[0]
    assert artifact["provenance"]["workspace_id"] == "workspace_shared_ro"
    assert "content" not in artifact
    assert "workspace_file_content" not in artifact["provenance"]


def test_no_container_git_worktree_remote_executor_or_real_filesystem_mutation_in_first_slice():
    assert not hasattr(workspace, "ContainerWorkspaceManager")
    assert not hasattr(workspace, "GitWorktreeWorkspaceManager")
    assert not hasattr(workspace, "RemoteWorkspaceExecutor")
    assert not hasattr(workspace.WorkspaceManager(), "mutate_filesystem")
