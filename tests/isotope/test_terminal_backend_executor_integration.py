from __future__ import annotations

import pytest

import isotope.workspace.artifacts as artifact_store
import isotope.platform.state.event_store as event_store
import isotope.execution.executor as executor
from isotope.platform.schemas.actions import ActionProposal, PolicyDecision
import isotope.runtime.in_process as server
import isotope.execution.terminal_runner as terminal_backend
import isotope.workspace as workspace
from isotope.platform.schemas.refs import ResourceRef


class FakeTerminalBackend:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, request):
        self.calls.append(request)
        return self.result


def _proposal() -> ActionProposal:
    return ActionProposal(
        proposal_id="prop_terminal_backend_executor",
        run_id="run_terminal_backend_executor",
        agent_id="agent_supervisor",
        thread_id="thread_main",
        action_type="call_tool",
        payload={
            "tool": "terminal_exec",
            "argv": ["printf", "adapter-secret-output"],
            "summary": "run terminal backend through executor",
        },
        requested_capabilities={
            "tools": ["terminal_exec"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 5},
        },
        registry_id="default",
        registry_version="v0.2",
    )


def _decision(proposal: ActionProposal) -> PolicyDecision:
    return PolicyDecision(
        decision_id="dec_terminal_backend_executor",
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
        policy_profile_id="default",
        policy_version="v0.2",
    )


def _completed_backend_result(*, content: str = "backend-secret-output"):
    return terminal_backend.TerminalBackendResult(
        backend_session_id="backend_session_executor_001",
        status="completed",
        started_at="2026-05-11T00:00:00Z",
        finished_at="2026-05-11T00:00:01Z",
        summary="terminal backend completed",
        output_artifacts=[
            terminal_backend.TerminalBackendOutputArtifact(
                artifact_type="terminal_backend_stdout",
                summary="stdout captured by backend",
                content=content,
            )
        ],
        exit_code=0,
        reason_code="terminal_backend_completed",
        retryable=False,
        resource_usage={"duration_ms": 1000},
    )


def _completed_backend_result_with_session(
    *,
    backend_session_id: str,
    content: str = "backend-secret-output",
):
    return terminal_backend.TerminalBackendResult(
        backend_session_id=backend_session_id,
        status="completed",
        started_at="2026-05-11T00:00:00Z",
        finished_at="2026-05-11T00:00:01Z",
        summary="terminal backend completed",
        output_artifacts=[
            terminal_backend.TerminalBackendOutputArtifact(
                artifact_type="terminal_backend_stdout",
                summary="stdout captured by backend",
                content=content,
            )
        ],
        exit_code=0,
        reason_code="terminal_backend_completed",
        retryable=False,
        resource_usage={"duration_ms": 1000},
    )


def _runner(tmp_path, backend):
    return executor.Executor(
        event_store=event_store.FileEventStore(tmp_path),
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        workspace_manager=workspace.WorkspaceManager(),
        terminal_backend=backend,
    )


def _runner_with_config(tmp_path, backend, backend_config):
    return executor.Executor(
        event_store=event_store.FileEventStore(tmp_path),
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        workspace_manager=workspace.WorkspaceManager(),
        terminal_backend=backend,
        terminal_backend_config=backend_config,
    )


def test_executor_routes_terminal_exec_through_configured_backend_adapter(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    secret = "adapter-secret-output"
    backend = FakeTerminalBackend(_completed_backend_result(content=secret))
    runner = _runner(tmp_path, backend)

    execution = runner.execute(decision, proposal)

    events = runner.event_store.list_events(proposal.run_id)
    event_types = [event.event_type for event in events]
    assert event_types == ["action.started", "artifact.created", "action.completed"]
    assert len(backend.calls) == 1

    started = events[0]
    request = backend.calls[0]
    assert request.run_id == proposal.run_id
    assert request.proposal_id == proposal.proposal_id
    assert request.decision_id == decision.decision_id
    assert request.execution_id == execution.execution_id
    assert request.grants == decision.grants
    assert request.command_request == {"kind": "exec_argv", "argv": ["printf", "adapter-secret-output"]}
    assert request.workspace_binding == {"workspace_id": "workspace_shared_ro", "mode": "shared_ro"}
    assert request.basis_event_ids == [started.event_id]

    artifact_event = events[1]
    artifact_payload = artifact_event.payload["artifact"]
    assert artifact_payload["artifact_type"] == "terminal_backend_stdout"
    assert artifact_payload["summary"] == "stdout captured by backend"
    assert secret not in repr(artifact_event.payload)

    completed = events[2]
    assert completed.payload["execution_id"] == execution.execution_id
    assert completed.payload["artifact_refs"] == [artifact_payload["ref"]]
    ref = ResourceRef(**artifact_payload["ref"])
    assert runner.artifact_store.get_content(ref) == secret


def test_executor_completed_event_has_low_sensitive_terminal_backend_summary(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    secret = "SECRET_OUTPUT_must_stay_in_artifact"
    internal_session_id = "backend_session_/Users/alice/.codex/TOKEN"
    backend = FakeTerminalBackend(
        _completed_backend_result_with_session(
            backend_session_id=internal_session_id,
            content=secret,
        )
    )
    backend_config = {
        "backend_id": "codex-local",
        "backend_version": "0.123.0",
        "protocol_version": "terminal-backend.v0.2",
        "mode": "external_local",
        "local_path": "/Users/alice/.codex",
        "env": {"OPENAI_API_KEY": "SECRET_ENV_TOKEN"},
    }
    runner = _runner_with_config(tmp_path, backend, backend_config)

    runner.execute(decision, proposal)

    completed = runner.event_store.list_events(proposal.run_id)[-1]
    assert completed.event_type == "action.completed"
    assert completed.payload["terminal_backend"] == {
        "backend_id": "codex-local",
        "backend_version": "0.123.0",
        "protocol_version": "terminal-backend.v0.2",
        "mode": "external_local",
        "status": "completed",
        "reason_code": "terminal_backend_completed",
    }
    payload_repr = repr(completed.payload)
    assert secret not in payload_repr
    assert internal_session_id not in payload_repr
    assert "/Users/alice" not in payload_repr
    assert "SECRET_ENV_TOKEN" not in payload_repr


def test_in_process_server_projects_low_sensitive_terminal_backend_summary(tmp_path):
    secret = "SERVER_SECRET_OUTPUT_must_stay_in_artifact"
    backend = FakeTerminalBackend(
        _completed_backend_result_with_session(
            backend_session_id="backend_session_/Users/alice/.codex/TOKEN",
            content=secret,
        )
    )
    api = server.InProcessServer(
        tmp_path,
        terminal_backend=backend,
        terminal_backend_config={
            "backend_id": "codex-local",
            "backend_version": "0.123.0",
            "protocol_version": "terminal-backend.v0.2",
            "mode": "external_local",
            "local_path": "/Users/alice/.codex",
            "env": {"OPENAI_API_KEY": "SECRET_ENV_TOKEN"},
        },
    )
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="terminal backend summary")

    result = api.submit_action(
        run["run_id"],
        {
            "action": "call_tool",
            "tool": "terminal_exec",
            "argv": ["printf", "server-backend"],
            "summary": "terminal backend summary",
        },
    )

    action = result["run_state"].actions[result["execution_id"]]
    assert action["terminal_backend"] == {
        "backend_id": "codex-local",
        "backend_version": "0.123.0",
        "protocol_version": "terminal-backend.v0.2",
        "mode": "external_local",
        "status": "completed",
        "reason_code": "terminal_backend_completed",
    }
    action_repr = repr(action)
    assert secret not in action_repr
    assert "/Users/alice" not in action_repr
    assert "SECRET_ENV_TOKEN" not in action_repr


def test_executor_terminal_backend_protocol_error_fails_without_artifact(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    backend = FakeTerminalBackend(
        {
            "backend_session_id": "backend_session_executor_001",
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
    runner = _runner(tmp_path, backend)

    with pytest.raises(terminal_backend.TerminalBackendProtocolError):
        runner.execute(decision, proposal)

    events = runner.event_store.list_events(proposal.run_id)
    assert [event.event_type for event in events] == ["action.started", "action.failed"]
    failed = events[-1]
    assert failed.payload["error_reason_code"] == "terminal_backend_protocol_error"
    assert failed.payload["structured_error"]["details"]["status"] == "mystery"
    assert runner.artifact_store.list_artifacts(proposal.run_id) == []


def test_executor_rejects_completed_terminal_backend_without_output_artifact(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    backend = FakeTerminalBackend(
        terminal_backend.TerminalBackendResult(
            backend_session_id="backend_session_executor_001",
            status="completed",
            started_at="2026-05-11T00:00:00Z",
            finished_at="2026-05-11T00:00:01Z",
            summary="terminal backend completed without output",
            output_artifacts=[],
            exit_code=0,
            reason_code="terminal_backend_completed",
            retryable=False,
            resource_usage={},
        )
    )
    runner = _runner(tmp_path, backend)

    with pytest.raises(terminal_backend.TerminalBackendProtocolError):
        runner.execute(decision, proposal)

    events = runner.event_store.list_events(proposal.run_id)
    assert [event.event_type for event in events] == ["action.started", "action.failed"]
    assert events[-1].payload["error_reason_code"] == "terminal_backend_protocol_error"
    assert runner.artifact_store.list_artifacts(proposal.run_id) == []


def test_executor_terminal_backend_reported_failure_becomes_action_failed(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    backend = FakeTerminalBackend(
        terminal_backend.TerminalBackendResult(
            backend_session_id="backend_session_executor_001",
            status="failed",
            started_at="2026-05-11T00:00:00Z",
            finished_at="2026-05-11T00:00:01Z",
            summary="terminal backend failed before output",
            output_artifacts=[],
            exit_code=2,
            reason_code="terminal_backend_failed",
            retryable=False,
            resource_usage={"duration_ms": 1000},
        )
    )
    runner = _runner(tmp_path, backend)

    with pytest.raises(terminal_backend.TerminalBackendExecutionError):
        runner.execute(decision, proposal)

    events = runner.event_store.list_events(proposal.run_id)
    assert [event.event_type for event in events] == ["action.started", "action.failed"]
    failed = events[-1]
    assert failed.payload["error_reason_code"] == "terminal_backend_failed"
    assert failed.payload["structured_error"]["details"]["backend_status"] == "failed"
    assert failed.payload["structured_error"]["details"]["exit_code"] == 2
    assert runner.artifact_store.list_artifacts(proposal.run_id) == []


def test_in_process_server_can_use_configured_terminal_backend(tmp_path):
    secret = "server-backend-secret-output"
    backend = FakeTerminalBackend(_completed_backend_result(content=secret))
    api = server.InProcessServer(tmp_path, terminal_backend=backend)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="terminal backend server route")

    result = api.submit_action(
        run["run_id"],
        {
            "action": "call_tool",
            "tool": "terminal_exec",
            "argv": ["printf", "server-backend"],
            "summary": "terminal backend server route",
        },
    )

    assert result["status"] == "completed"
    assert len(backend.calls) == 1
    assert backend.calls[0].run_id == run["run_id"]
    assert backend.calls[0].command_request == {"kind": "exec_argv", "argv": ["printf", "server-backend"]}
    assert api.artifact_store.get_content(result["artifact_ref"]) == secret
