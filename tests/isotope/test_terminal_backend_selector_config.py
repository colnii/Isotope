from __future__ import annotations

import pytest

import isotope.workspace.artifacts as artifact_store
import isotope.platform.state.event_store as event_store
import isotope.execution.executor as executor
import isotope.platform.schemas.models as models
import isotope.execution.terminal_runner as terminal_backend
import isotope.workspace as workspace


class RecordingBackend:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, request):
        self.calls.append(request)
        return self.result


def _proposal() -> models.ActionProposal:
    return models.ActionProposal(
        proposal_id="prop_terminal_backend_selector",
        run_id="run_terminal_backend_selector",
        agent_id="agent_supervisor",
        thread_id="thread_main",
        action_type="call_tool",
        payload={
            "tool": "terminal_exec",
            "argv": ["printf", "selector-output"],
            "summary": "run through selected terminal backend",
        },
        requested_capabilities={
            "tools": ["terminal_exec"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 5},
        },
        registry_id="default",
        registry_version="v0.2",
    )


def _decision(proposal: models.ActionProposal) -> models.PolicyDecision:
    return models.PolicyDecision(
        decision_id="dec_terminal_backend_selector",
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
                "max_output_bytes": 4096,
            },
        },
        reason_codes=[],
    )


def _workspace_binding() -> dict:
    return {"workspace_id": "workspace_shared_ro", "mode": "shared_ro"}


def _completed_backend_result(*, content: str = "selector-output"):
    return terminal_backend.TerminalBackendResult(
        backend_session_id="backend_session_selector_001",
        status="completed",
        started_at="2026-05-11T00:00:00Z",
        finished_at="2026-05-11T00:00:01Z",
        summary="selected terminal backend completed",
        output_artifacts=[
            terminal_backend.TerminalBackendOutputArtifact(
                artifact_type="terminal_backend_stdout",
                summary="stdout captured by selected backend",
                content=content,
            )
        ],
        exit_code=0,
        reason_code="terminal_backend_completed",
        retryable=False,
        resource_usage={"duration_ms": 1000},
    )


def _runner(tmp_path, *, backend=None, backend_config=None):
    return executor.Executor(
        event_store=event_store.FileEventStore(tmp_path),
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        workspace_manager=workspace.WorkspaceManager(),
        terminal_backend=backend,
        terminal_backend_config=backend_config,
    )


def test_backend_config_metadata_is_included_in_request(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    config = terminal_backend.TerminalBackendConfig(
        backend_id="fake-local-agent",
        backend_version="0.1.fake",
        protocol_version="terminal-backend.v0.2",
        mode="external_local",
    )
    backend = RecordingBackend(_completed_backend_result())
    adapter = terminal_backend.TerminalBackendAdapter(
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        backend=backend,
        backend_config=config,
    )

    adapter.prepare_and_run(
        proposal=proposal,
        decision=decision,
        execution_id="exec_terminal_backend_selector",
        workspace_binding=_workspace_binding(),
        basis_event_ids=["evt_started"],
    )

    assert backend.calls[0].backend_config == {
        "backend_id": "fake-local-agent",
        "backend_version": "0.1.fake",
        "protocol_version": "terminal-backend.v0.2",
        "mode": "external_local",
        "configured": True,
        "allow_backend_native_task": False,
    }


def test_executor_required_backend_without_backend_fails_closed(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    config = terminal_backend.TerminalBackendConfig(
        backend_id="codex-local",
        backend_version="not-configured",
        protocol_version="terminal-backend.v0.2",
        mode="external_local",
    )
    runner = _runner(tmp_path, backend_config=config)

    with pytest.raises(terminal_backend.TerminalBackendNotConfiguredError):
        runner.execute(decision, proposal)

    events = runner.event_store.list_events(proposal.run_id)
    assert [event.event_type for event in events] == ["action.started", "action.failed"]
    failed = events[-1]
    assert failed.payload["error_reason_code"] == "terminal_backend_not_configured"
    assert failed.payload["structured_error"]["details"]["backend_id"] == "codex-local"
    assert runner.artifact_store.list_artifacts(proposal.run_id) == []


def test_incompatible_backend_protocol_fails_before_backend_call(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    config = terminal_backend.TerminalBackendConfig(
        backend_id="fake-local-agent",
        backend_version="0.1.fake",
        protocol_version="terminal-backend.v9",
        mode="external_local",
    )
    backend = RecordingBackend(_completed_backend_result())
    runner = _runner(tmp_path, backend=backend, backend_config=config)

    with pytest.raises(terminal_backend.TerminalBackendProtocolError):
        runner.execute(decision, proposal)

    assert backend.calls == []
    events = runner.event_store.list_events(proposal.run_id)
    assert [event.event_type for event in events] == ["action.started", "action.failed"]
    failed = events[-1]
    assert failed.payload["error_reason_code"] == "terminal_backend_protocol_error"
    assert failed.payload["structured_error"]["details"]["protocol_version"] == "terminal-backend.v9"
    assert runner.artifact_store.list_artifacts(proposal.run_id) == []


def test_backend_native_task_requires_explicit_policy_gate(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    config = terminal_backend.TerminalBackendConfig(
        backend_id="fake-local-agent",
        backend_version="0.1.fake",
        protocol_version="terminal-backend.v0.2",
        mode="external_local",
    )
    backend = RecordingBackend(_completed_backend_result())
    adapter = terminal_backend.TerminalBackendAdapter(
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        backend=backend,
        backend_config=config,
    )

    with pytest.raises(terminal_backend.TerminalBackendProtocolError) as exc_info:
        adapter.prepare_and_run(
            proposal=proposal,
            decision=decision,
            execution_id="exec_terminal_backend_selector",
            workspace_binding=_workspace_binding(),
            basis_event_ids=["evt_started"],
            command_request={"kind": "backend_native_task", "task": {"prompt": "inspect the repo"}},
        )

    assert exc_info.value.error_reason_code == "terminal_backend_request_denied"
    assert backend.calls == []
