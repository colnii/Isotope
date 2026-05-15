from __future__ import annotations

import pytest

import isotope.workspace.artifacts as artifact_store
from isotope.platform.schemas.actions import ActionProposal, PolicyDecision
import isotope.execution.terminal_runner as terminal_backend
from isotope.platform.schemas.refs import ResourceRef


def _proposal() -> ActionProposal:
    return ActionProposal(
        proposal_id="prop_terminal_backend",
        run_id="run_terminal_backend",
        agent_id="agent_supervisor",
        thread_id="thread_main",
        action_type="call_tool",
        payload={
            "tool": "terminal_exec",
            "argv": ["printf", "safe-output"],
            "summary": "run terminal backend",
        },
        requested_capabilities={
            "tools": ["terminal_exec"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 5},
        },
        registry_id="default",
        registry_version="v0.2",
    )


def _decision(
    proposal: ActionProposal,
    *,
    outcome: str = "approved",
    grants: dict | None = None,
) -> PolicyDecision:
    return PolicyDecision(
        decision_id="dec_terminal_backend",
        proposal_id=proposal.proposal_id,
        outcome=outcome,
        grants=grants
        if grants is not None
        else {
            "tools": ["terminal_exec"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 5},
            "terminal": {"shell": False, "argv_policy": "allowlist", "allowed_commands": ["printf"]},
        },
        reason_codes=[] if outcome != "denied" else ["terminal_command_not_allowed"],
        policy_profile_id="default",
        policy_version="v0.2",
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
        self.cancel_calls = []

    def run(self, request):
        self.calls.append(request)
        return self.result

    def cancel(self, request, *, basis_event_ids):
        self.cancel_calls.append({"request": request, "basis_event_ids": list(basis_event_ids)})
        return {
            "status": "cancelled",
            "summary": "cancel acknowledged",
            "reason_code": "terminal_backend_cancelled",
            "retryable": False,
        }


def _completed_backend_result(*, content: str = "backend-secret-output"):
    return terminal_backend.TerminalBackendResult(
        backend_session_id="backend_session_001",
        status="completed",
        started_at="2026-05-11T00:00:00Z",
        finished_at="2026-05-11T00:00:01Z",
        summary="terminal backend completed",
        output_artifacts=[
            terminal_backend.TerminalBackendOutputArtifact(
                artifact_type="terminal_backend_stdout",
                summary="stdout captured",
                content=content,
            )
        ],
        exit_code=0,
        reason_code="terminal_backend_completed",
        retryable=False,
        resource_usage={"duration_ms": 1000},
    )


def test_approved_decision_creates_request_with_exact_grants_snapshot(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)

    request = terminal_backend.build_terminal_backend_request(
        proposal=proposal,
        decision=decision,
        execution_id="exec_terminal_backend",
        workspace_binding=_workspace_binding(),
        basis_event_ids=["evt_proposed", "evt_decided"],
    )

    assert request.run_id == proposal.run_id
    assert request.proposal_id == proposal.proposal_id
    assert request.decision_id == decision.decision_id
    assert request.grants == decision.grants
    assert request.grants is not decision.grants
    assert request.workspace_binding["workspace_id"] == "workspace_shared_ro"
    assert request.command_request == {"kind": "exec_argv", "argv": ["printf", "safe-output"]}
    assert request.basis_event_ids == ["evt_proposed", "evt_decided"]

    decision.grants["terminal"]["allowed_commands"].append("bash")
    assert request.grants["terminal"]["allowed_commands"] == ["printf"]


def test_denied_decision_does_not_call_backend(tmp_path):
    proposal = _proposal()
    backend = FakeBackend(_completed_backend_result())
    adapter = terminal_backend.TerminalBackendAdapter(
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        backend=backend,
    )

    with pytest.raises(PermissionError, match="denied"):
        adapter.prepare_and_run(
            proposal=proposal,
            decision=_decision(proposal, outcome="denied", grants={"tools": [], "workspace": {"mode": "none"}}),
            execution_id="exec_terminal_backend",
            workspace_binding=_workspace_binding(),
            basis_event_ids=["evt_decided"],
        )

    assert backend.calls == []


def test_pending_approval_does_not_call_backend(tmp_path):
    proposal = _proposal()
    backend = FakeBackend(_completed_backend_result())
    adapter = terminal_backend.TerminalBackendAdapter(
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        backend=backend,
    )

    with pytest.raises(PermissionError, match="pending approval"):
        adapter.prepare_and_run(
            proposal=proposal,
            decision=_decision(proposal),
            execution_id="exec_terminal_backend",
            workspace_binding=_workspace_binding(),
            basis_event_ids=["evt_approval_requested"],
            approval_status="pending",
        )

    assert backend.calls == []


def test_backend_result_creates_artifact_refs_without_exposing_full_output(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    secret = "very-secret-terminal-output"
    backend = FakeBackend(_completed_backend_result(content=secret))
    store = artifact_store.ArtifactStore(tmp_path)
    adapter = terminal_backend.TerminalBackendAdapter(artifact_store=store, backend=backend)

    result = adapter.prepare_and_run(
        proposal=proposal,
        decision=decision,
        execution_id="exec_terminal_backend",
        workspace_binding=_workspace_binding(),
        basis_event_ids=["evt_proposed", "evt_decided"],
    )

    assert result.status == "completed"
    assert len(result.artifact_refs) == 1
    assert isinstance(result.artifact_refs[0], ResourceRef)
    assert store.get_content(result.artifact_refs[0]) == secret
    assert secret not in result.summary
    assert secret not in repr(result)
    assert backend.calls[0].grants == decision.grants


def test_backend_reported_grants_are_rejected(tmp_path):
    proposal = _proposal()
    backend_result = _completed_backend_result()
    backend_result.reported_grants = {"tools": ["terminal_exec", "write_artifact_tool"]}
    backend = FakeBackend(backend_result)
    adapter = terminal_backend.TerminalBackendAdapter(
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        backend=backend,
    )

    with pytest.raises(terminal_backend.TerminalBackendProtocolError) as exc_info:
        adapter.prepare_and_run(
            proposal=proposal,
            decision=_decision(proposal),
            execution_id="exec_terminal_backend",
            workspace_binding=_workspace_binding(),
            basis_event_ids=["evt_decided"],
        )

    assert exc_info.value.error_reason_code == "terminal_backend_protocol_error"


def test_backend_raw_file_artifact_ref_is_rejected(tmp_path):
    proposal = _proposal()
    backend = FakeBackend(
        {
            "backend_session_id": "backend_session_001",
            "status": "completed",
            "started_at": "2026-05-11T00:00:00Z",
            "finished_at": "2026-05-11T00:00:01Z",
            "summary": "completed with raw ref",
            "artifact_refs": ["/tmp/raw-output.txt"],
            "exit_code": 0,
            "reason_code": "terminal_backend_completed",
            "retryable": False,
            "resource_usage": {},
        }
    )
    adapter = terminal_backend.TerminalBackendAdapter(
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        backend=backend,
    )

    with pytest.raises(terminal_backend.TerminalBackendProtocolError, match="artifact_ref"):
        adapter.prepare_and_run(
            proposal=proposal,
            decision=_decision(proposal),
            execution_id="exec_terminal_backend",
            workspace_binding=_workspace_binding(),
            basis_event_ids=["evt_decided"],
        )


def test_unknown_backend_status_fails_closed_with_structured_error(tmp_path):
    proposal = _proposal()
    backend = FakeBackend(
        {
            "backend_session_id": "backend_session_001",
            "status": "mystery",
            "started_at": "2026-05-11T00:00:00Z",
            "finished_at": "2026-05-11T00:00:01Z",
            "summary": "unknown status",
            "artifact_refs": [],
            "exit_code": 0,
            "reason_code": "terminal_backend_completed",
            "retryable": False,
            "resource_usage": {},
        }
    )
    adapter = terminal_backend.TerminalBackendAdapter(
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        backend=backend,
    )

    with pytest.raises(terminal_backend.TerminalBackendProtocolError) as exc_info:
        adapter.prepare_and_run(
            proposal=proposal,
            decision=_decision(proposal),
            execution_id="exec_terminal_backend",
            workspace_binding=_workspace_binding(),
            basis_event_ids=["evt_decided"],
        )

    assert exc_info.value.error_reason_code == "terminal_backend_protocol_error"
    assert exc_info.value.structured_details["status"] == "mystery"


def test_terminal_backend_failure_shape_is_structured():
    failure = terminal_backend.TerminalBackendFailure(
        reason_code="terminal_backend_timeout",
        message="backend timed out",
        retryable=True,
        details={"timeout_seconds": 5},
    )

    assert failure.reason_code == "terminal_backend_timeout"
    assert failure.message == "backend timed out"
    assert failure.retryable is True
    assert failure.details == {"timeout_seconds": 5}

    with pytest.raises(ValueError, match="stable identifier"):
        terminal_backend.TerminalBackendFailure(
            reason_code="TerminalBackendTimeout",
            message="bad reason",
            retryable=False,
        )


def test_cancel_request_calls_backend_and_preserves_basis_linkage(tmp_path):
    proposal = _proposal()
    request = terminal_backend.build_terminal_backend_request(
        proposal=proposal,
        decision=_decision(proposal),
        execution_id="exec_terminal_backend",
        workspace_binding=_workspace_binding(),
        basis_event_ids=["evt_proposed", "evt_decided"],
    )
    backend = FakeBackend(_completed_backend_result())
    adapter = terminal_backend.TerminalBackendAdapter(
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        backend=backend,
    )

    result = adapter.cancel(request, basis_event_ids=["evt_cancel_requested"])

    assert result.status == "cancelled"
    assert result.basis_event_ids == ["evt_cancel_requested"]
    assert backend.cancel_calls == [
        {"request": request, "basis_event_ids": ["evt_cancel_requested"]},
    ]
