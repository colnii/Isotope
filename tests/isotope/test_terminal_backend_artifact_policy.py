from __future__ import annotations

import pytest

import isotope.workspace.artifacts as artifact_store
import isotope.platform.state.event_store as event_store
import isotope.execution.executor as executor
import isotope.platform.schemas.models as models
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


def _proposal() -> models.ActionProposal:
    return models.ActionProposal(
        proposal_id="prop_terminal_backend_artifact_policy",
        run_id="run_terminal_backend_artifact_policy",
        agent_id="agent_supervisor",
        thread_id="thread_main",
        action_type="call_tool",
        payload={
            "tool": "terminal_exec",
            "argv": ["printf", "artifact-policy"],
            "summary": "run terminal backend artifact policy",
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
        decision_id="dec_terminal_backend_artifact_policy",
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


def _workspace_binding() -> dict:
    return {"workspace_id": "workspace_shared_ro", "mode": "shared_ro"}


def _completed_result(outputs) -> terminal_backend.TerminalBackendResult:
    return terminal_backend.TerminalBackendResult(
        backend_session_id="backend_session_artifact_policy_001",
        status="completed",
        started_at="2026-05-11T00:00:00Z",
        finished_at="2026-05-11T00:00:01Z",
        summary="terminal backend completed with artifact refs",
        output_artifacts=outputs,
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


def test_transcript_diff_and_changed_files_are_artifacts_not_event_content(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    transcript = "TRANSCRIPT_SECRET_full terminal transcript"
    diff = "DIFF_SECRET_diff --git a/file.py b/file.py"
    changed_files = "CHANGED_FILES_SECRET_src/isotope/file.py"
    backend = FakeTerminalBackend(
        _completed_result(
            [
                {
                    "artifact_type": "terminal_backend_transcript",
                    "summary": "terminal transcript captured",
                    "content": transcript,
                },
                {
                    "artifact_type": "terminal_backend_diff",
                    "summary": "workspace diff captured",
                    "content": diff,
                },
                {
                    "artifact_type": "terminal_backend_changed_files",
                    "summary": "changed files captured",
                    "content": changed_files,
                },
            ]
        )
    )
    runner = _runner(tmp_path, backend)

    runner.execute(decision, proposal)

    events = runner.event_store.list_events(proposal.run_id)
    assert [event.event_type for event in events] == [
        "action.started",
        "artifact.created",
        "artifact.created",
        "artifact.created",
        "action.completed",
    ]
    event_payload_repr = repr([event.payload for event in events])
    assert transcript not in event_payload_repr
    assert diff not in event_payload_repr
    assert changed_files not in event_payload_repr

    artifact_refs = [
        ResourceRef(**event.payload["artifact"]["ref"])
        for event in events
        if event.event_type == "artifact.created"
    ]
    assert [runner.artifact_store.get_content(ref) for ref in artifact_refs] == [
        transcript,
        diff,
        changed_files,
    ]


def test_artifact_policy_rejects_output_kind_that_is_not_captured(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    backend = FakeTerminalBackend(
        _completed_result(
            [
                {
                    "artifact_type": "terminal_backend_diff",
                    "summary": "workspace diff captured",
                    "content": "DIFF_SECRET_not_allowed_by_policy",
                }
            ]
        )
    )
    store = artifact_store.ArtifactStore(tmp_path)
    adapter = terminal_backend.TerminalBackendAdapter(artifact_store=store, backend=backend)

    with pytest.raises(terminal_backend.TerminalBackendProtocolError) as exc_info:
        adapter.prepare_and_run(
            proposal=proposal,
            decision=decision,
            execution_id="exec_terminal_backend_artifact_policy",
            workspace_binding=_workspace_binding(),
            basis_event_ids=["evt_started"],
            artifact_policy={
                "capture": ["transcript"],
                "full_content_in_events": False,
                "full_content_in_read_model": False,
            },
        )

    assert exc_info.value.error_reason_code == "terminal_backend_artifact_policy_denied"
    assert backend.calls
    assert store.list_artifacts(proposal.run_id) == []


def test_artifact_policy_capture_only_uses_safe_full_content_defaults(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    diff = "DIFF_SECRET_capture_only_policy"
    backend = FakeTerminalBackend(
        _completed_result(
            [
                {
                    "artifact_type": "terminal_backend_diff",
                    "summary": "workspace diff captured",
                    "content": diff,
                }
            ]
        )
    )
    store = artifact_store.ArtifactStore(tmp_path)
    adapter = terminal_backend.TerminalBackendAdapter(artifact_store=store, backend=backend)

    result = adapter.prepare_and_run(
        proposal=proposal,
        decision=decision,
        execution_id="exec_terminal_backend_artifact_policy",
        workspace_binding=_workspace_binding(),
        basis_event_ids=["evt_started"],
        artifact_policy={"capture": ["diff"]},
    )

    assert len(result.artifact_refs) == 1
    assert store.get_content(result.artifact_refs[0]) == diff
    assert backend.calls[0].artifact_policy == {
        "capture": ["diff"],
        "full_content_in_events": False,
        "full_content_in_read_model": False,
    }


def test_artifact_policy_rejects_full_content_in_events_before_backend_call(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    backend = FakeTerminalBackend(
        _completed_result(
            [
                {
                    "artifact_type": "terminal_backend_transcript",
                    "summary": "terminal transcript captured",
                    "content": "TRANSCRIPT_SECRET_must_not_be_requested_for_events",
                }
            ]
        )
    )
    adapter = terminal_backend.TerminalBackendAdapter(
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        backend=backend,
    )

    with pytest.raises(terminal_backend.TerminalBackendProtocolError) as exc_info:
        adapter.prepare_and_run(
            proposal=proposal,
            decision=decision,
            execution_id="exec_terminal_backend_artifact_policy",
            workspace_binding=_workspace_binding(),
            basis_event_ids=["evt_started"],
            artifact_policy={
                "capture": ["transcript"],
                "full_content_in_events": True,
                "full_content_in_read_model": False,
            },
        )

    assert exc_info.value.error_reason_code == "terminal_backend_artifact_policy_denied"
    assert backend.calls == []
