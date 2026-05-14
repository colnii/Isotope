from __future__ import annotations

import json

import pytest

from agents.executor.terminal_backend import (
    LinuxSystemTerminalRunner,
    TerminalBackendAdapter,
    TerminalBackendOutputArtifact,
    TerminalBackendProtocolError,
    TerminalBackendResult,
    build_terminal_backend_request,
)
from isotope_kernel import artifact_store, models
from isotope_kernel.refs import ResourceRef


def _proposal() -> models.ActionProposal:
    return models.ActionProposal(
        proposal_id="prop_terminal_backend",
        run_id="run_terminal_backend",
        agent_id="agent_supervisor",
        thread_id="thread_main",
        action_type="call_tool",
        payload={"tool": "terminal_exec", "argv": ["printf", "safe-output"]},
        requested_capabilities={
            "tools": ["terminal_exec"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 5},
        },
    )


def _decision(proposal: models.ActionProposal) -> models.PolicyDecision:
    return models.PolicyDecision(
        decision_id="dec_terminal_backend",
        proposal_id=proposal.proposal_id,
        outcome="approved",
        grants={
            "tools": ["terminal_exec"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 5},
            "terminal": {
                "shell": False,
                "argv_policy": "allowlist",
                "allowed_commands": ["printf"],
            },
        },
        reason_codes=[],
    )


def _workspace_binding() -> dict:
    return {
        "workspace_id": "workspace_shared_ro",
        "mode": "shared_ro",
        "lease_status": "active",
        "root_ref": "workspace://run_terminal_backend/shared_ro",
    }


class FakeBackend:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, request):
        self.calls.append(request)
        return self.result


def test_build_terminal_backend_request_snapshots_decision_grants():
    proposal = _proposal()
    decision = _decision(proposal)

    request = build_terminal_backend_request(
        proposal=proposal,
        decision=decision,
        execution_id="exec_terminal_backend",
        workspace_binding=_workspace_binding(),
        basis_event_ids=["evt_decided"],
    )

    assert request.command_request == {"kind": "exec_argv", "argv": ["printf", "safe-output"]}
    assert request.grants == decision.grants
    assert request.grants is not decision.grants
    decision.grants["terminal"]["allowed_commands"].append("bash")
    assert request.grants["terminal"]["allowed_commands"] == ["printf"]


def test_terminal_backend_adapter_stores_backend_output_as_artifact(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    backend = FakeBackend(
        TerminalBackendResult(
            backend_session_id="backend_session_001",
            status="completed",
            started_at="2026-05-15T00:00:00Z",
            finished_at="2026-05-15T00:00:01Z",
            summary="terminal backend completed",
            output_artifacts=[
                TerminalBackendOutputArtifact(
                    artifact_type="terminal_backend_stdout",
                    summary="stdout captured",
                    content="backend-output",
                )
            ],
            exit_code=0,
            reason_code="terminal_backend_completed",
        )
    )

    result = TerminalBackendAdapter(
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        backend=backend,
    ).prepare_and_run(
        proposal=proposal,
        decision=decision,
        execution_id="exec_terminal_backend",
        workspace_binding=_workspace_binding(),
        basis_event_ids=["evt_decided"],
    )

    assert result.status == "completed"
    assert isinstance(result.artifact_refs[0], ResourceRef)
    assert result.backend_summary["status"] == "completed"
    assert backend.calls[0].grants == decision.grants


def test_terminal_backend_adapter_rejects_summary_leaking_full_content(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    backend = FakeBackend(
        TerminalBackendResult(
            backend_session_id="backend_session_001",
            status="completed",
            started_at="2026-05-15T00:00:00Z",
            finished_at="2026-05-15T00:00:01Z",
            summary="terminal backend completed with backend-secret-output",
            output_artifacts=[
                TerminalBackendOutputArtifact(
                    artifact_type="terminal_backend_stdout",
                    summary="stdout captured",
                    content="backend-secret-output",
                )
            ],
            exit_code=0,
            reason_code="terminal_backend_completed",
        )
    )

    with pytest.raises(TerminalBackendProtocolError, match="summary exposes"):
        TerminalBackendAdapter(
            artifact_store=artifact_store.ArtifactStore(tmp_path),
            backend=backend,
        ).prepare_and_run(
            proposal=proposal,
            decision=decision,
            execution_id="exec_terminal_backend",
            workspace_binding=_workspace_binding(),
            basis_event_ids=["evt_decided"],
        )


def test_linux_system_terminal_runner_executes_approved_argv(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    request = build_terminal_backend_request(
        proposal=proposal,
        decision=decision,
        execution_id="exec_terminal_backend",
        workspace_binding=_workspace_binding(),
        basis_event_ids=["evt_decided"],
    )

    result = LinuxSystemTerminalRunner(tmp_path).run(request)

    assert result.status == "completed"
    transcript = json.loads(result.output_artifacts[0].content)
    assert transcript["stdout"] == "safe-output"
    assert transcript["shell"] is False
