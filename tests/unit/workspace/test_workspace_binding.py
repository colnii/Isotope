import pytest

import isotope.runtime.in_process.action_compiler as action_compiler
import isotope.workspace.artifacts as artifact_store
import isotope.platform.state.event_store as event_store
import isotope.execution.executor as executor
from isotope.platform.schemas.actions import PolicyDecision
import isotope.workspace as workspace


def _proposal(workspace_mode="isolated_rw"):
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
    return PolicyDecision(
        decision_id="dec_001",
        proposal_id=proposal.proposal_id,
        outcome="approved",
        grants=grants,
        reason_codes=[],
    )


def test_workspace_rejects_missing_grants():
    manager = workspace.WorkspaceManager()

    with pytest.raises(TypeError, match="workspace grants must be a dict"):
        manager.get_binding(None)


def test_workspace_rejects_non_dict_grants():
    manager = workspace.WorkspaceManager()

    with pytest.raises(TypeError, match="workspace grants must be a dict"):
        manager.get_binding(["workspace:shared_ro"])


def test_workspace_rejects_missing_workspace_grant():
    manager = workspace.WorkspaceManager()

    with pytest.raises(PermissionError, match="workspace grant is required"):
        manager.get_binding({})


def test_workspace_rejects_missing_workspace_mode():
    manager = workspace.WorkspaceManager()

    with pytest.raises(PermissionError, match="workspace.mode is required"):
        manager.get_binding({"workspace": {}})


def test_workspace_accepts_shared_ro_grant():
    manager = workspace.WorkspaceManager()

    binding = manager.get_binding({"workspace": {"mode": "shared_ro"}})

    assert binding.workspace_id == "workspace_shared_ro"
    assert binding.mode == "shared_ro"


def test_workspace_rejects_isolated_rw_in_current_slice():
    manager = workspace.WorkspaceManager()

    for mode in ("isolated_rw", "broad_workspace", "unknown"):
        with pytest.raises(PermissionError, match="workspace mode is not supported"):
            manager.get_binding({"workspace": {"mode": mode}})


def test_executor_uses_decision_workspace_grant_not_requested_workspace(tmp_path):
    proposal = _proposal(workspace_mode="isolated_rw")
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

    result = runner.execute(decision, proposal)

    assert manager.seen_grants is decision.grants
    assert proposal.requested_capabilities["workspace"]["mode"] == "isolated_rw"
    assert result.effective_grants_snapshot["workspace"]["mode"] == "shared_ro"


def test_executor_fails_when_decision_lacks_workspace_grant(tmp_path):
    proposal = _proposal(workspace_mode="isolated_rw")
    decision = _decision(
        proposal,
        {
            "tools": ["write_artifact_tool"],
            "budget": {"seconds": 30},
        },
    )
    runner = executor.Executor(
        event_store=event_store.FileEventStore(tmp_path),
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        workspace_manager=workspace.WorkspaceManager(),
    )

    with pytest.raises(PermissionError, match="workspace grant is required"):
        runner.execute(decision, proposal)
