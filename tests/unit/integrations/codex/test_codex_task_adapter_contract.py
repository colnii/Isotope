from __future__ import annotations

import pytest

import isotope.workspace.artifacts as artifact_store
import isotope.integrations.codex.task as codex_task
from isotope.platform.schemas.actions import ActionProposal, PolicyDecision
from isotope.platform.schemas.refs import ResourceRef


def _proposal() -> ActionProposal:
    return ActionProposal(
        proposal_id="prop_codex_task",
        run_id="run_codex_task",
        agent_id="agent_supervisor",
        thread_id="thread_main",
        action_type="delegate_agent_task",
        payload={
            "tool": "codex_task",
            "prompt": "Inspect the repository and report the next step.",
            "summary": "delegate repository inspection to Codex",
        },
        requested_capabilities={
            "tools": ["codex_task"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 60},
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
        decision_id="dec_codex_task",
        proposal_id=proposal.proposal_id,
        outcome=outcome,
        grants=grants
        if grants is not None
        else {
            "tools": ["codex_task"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 60},
            "codex_task": {"adapter_required": True},
        },
        reason_codes=[] if outcome != "denied" else ["codex_task_approval_required"],
        policy_profile_id="default",
        policy_version="v0.2",
    )


def _workspace_binding() -> dict:
    return {
        "workspace_id": "workspace_shared_ro",
        "mode": "shared_ro",
        "lease_status": "active",
        "root_ref": "workspace://run_codex_task/shared_ro",
    }


class StubCodexBackend:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, request):
        self.calls.append(request)
        return self.result


def _completed_result(*, content: str = "codex-secret-output") -> codex_task.CodexTaskResult:
    return codex_task.CodexTaskResult(
        adapter_session_id="codex_session_001",
        status="completed",
        started_at="2026-05-11T00:00:00Z",
        finished_at="2026-05-11T00:00:01Z",
        summary="codex task completed",
        output_artifacts=[
            codex_task.CodexTaskOutputArtifact(
                artifact_type="codex_task_transcript",
                summary="codex transcript captured",
                content=content,
            )
        ],
        reason_code="codex_task_completed",
        retryable=False,
        resource_usage={"duration_ms": 1000},
    )


def test_build_codex_task_request_copies_prompt_and_grants_snapshot():
    proposal = _proposal()
    decision = _decision(proposal)

    request = codex_task.build_codex_task_request(
        proposal=proposal,
        decision=decision,
        execution_id="exec_codex_task",
        workspace_binding=_workspace_binding(),
        basis_event_ids=["evt_proposed", "evt_decided"],
    )

    assert request.run_id == proposal.run_id
    assert request.task_request == {
        "kind": "codex_prompt",
        "prompt": "Inspect the repository and report the next step.",
    }
    assert request.grants == decision.grants
    assert request.grants is not decision.grants
    assert request.workspace_binding["workspace_id"] == "workspace_shared_ro"
    assert request.basis_event_ids == ["evt_proposed", "evt_decided"]

    decision.grants["tools"].append("terminal_exec")
    assert request.grants["tools"] == ["codex_task"]


@pytest.mark.parametrize(
    ("outcome", "approval_status", "message"),
    [
        ("denied", "approved", "denied"),
        ("approved", "pending", "pending approval"),
    ],
)
def test_denied_or_pending_decision_does_not_call_codex_backend(
    tmp_path,
    outcome,
    approval_status,
    message,
):
    proposal = _proposal()
    backend = StubCodexBackend(_completed_result())
    adapter = codex_task.CodexTaskAdapter(
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        backend=backend,
    )

    with pytest.raises(PermissionError, match=message):
        adapter.prepare_and_run(
            proposal=proposal,
            decision=_decision(
                proposal,
                outcome=outcome,
                grants={"tools": [], "workspace": {"mode": "none"}} if outcome == "denied" else None,
            ),
            execution_id="exec_codex_task",
            workspace_binding=_workspace_binding(),
            basis_event_ids=["evt_decided"],
            approval_status=approval_status,
        )

    assert backend.calls == []


def test_codex_result_creates_artifact_without_exposing_full_output(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    secret = "very-secret-codex-transcript"
    backend = StubCodexBackend(_completed_result(content=secret))
    store = artifact_store.ArtifactStore(tmp_path)
    adapter = codex_task.CodexTaskAdapter(artifact_store=store, backend=backend)

    result = adapter.prepare_and_run(
        proposal=proposal,
        decision=decision,
        execution_id="exec_codex_task",
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


def test_codex_result_allows_summary_artifact_without_treating_it_as_leak(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    summary_content = '{"status":"completed","reason_code":"codex_cli_completed"}'
    backend = StubCodexBackend(
        codex_task.CodexTaskResult(
            adapter_session_id="codex_session_001",
            status="completed",
            started_at="2026-05-11T00:00:00Z",
            finished_at="2026-05-11T00:00:01Z",
            summary=summary_content,
            output_artifacts=[
                codex_task.CodexTaskOutputArtifact(
                    artifact_type="codex_task_summary",
                    summary="codex cli runtime summary captured",
                    content=summary_content,
                )
            ],
            reason_code="codex_task_completed",
            retryable=False,
            resource_usage={"duration_ms": 1000},
        )
    )
    store = artifact_store.ArtifactStore(tmp_path)
    adapter = codex_task.CodexTaskAdapter(artifact_store=store, backend=backend)

    result = adapter.prepare_and_run(
        proposal=proposal,
        decision=decision,
        execution_id="exec_codex_task",
        workspace_binding=_workspace_binding(),
        basis_event_ids=["evt_proposed", "evt_decided"],
        artifact_policy={"capture": ["summary"]},
    )

    assert result.status == "completed"
    assert len(result.artifact_refs) == 1
    assert store.get_content(result.artifact_refs[0]) == summary_content


def test_codex_backend_reported_widened_grants_are_rejected(tmp_path):
    proposal = _proposal()
    backend_result = _completed_result()
    backend_result.reported_grants = {"tools": ["codex_task", "terminal_exec"]}
    backend = StubCodexBackend(backend_result)
    adapter = codex_task.CodexTaskAdapter(
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        backend=backend,
    )

    with pytest.raises(codex_task.CodexTaskProtocolError) as exc_info:
        adapter.prepare_and_run(
            proposal=proposal,
            decision=_decision(proposal),
            execution_id="exec_codex_task",
            workspace_binding=_workspace_binding(),
            basis_event_ids=["evt_decided"],
        )

    assert exc_info.value.error_reason_code == "codex_task_protocol_error"
