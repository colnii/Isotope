from __future__ import annotations

import isotope.platform.registry.actions as action_registry
import isotope.integrations.codex.task as codex_task
import isotope.runtime.in_process as server


class FakeCodexBackend:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, request):
        self.calls.append(request)
        return self.result


def _completed_result(*, content: str = "codex-secret-output") -> codex_task.CodexTaskResult:
    return codex_task.CodexTaskResult(
        adapter_session_id="codex_session_/Users/alice/.codex/TOKEN",
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


def _api(tmp_path, backend):
    return server.InProcessServer(
        tmp_path,
        registry=action_registry.ActionTypeRegistry.default(enable_codex_task=True),
        codex_task_adapter=backend,
        codex_task_adapter_config={
            "adapter_id": "codex-local",
            "adapter_version": "0.1.0",
            "protocol_version": "codex-task-adapter.v0.1",
            "mode": "agent_cli_task",
            "local_path": "/Users/alice/.codex",
            "env": {"OPENAI_API_KEY": "SECRET_ENV_TOKEN"},
        },
    )


def test_codex_task_requires_approval_before_adapter_call(tmp_path):
    backend = FakeCodexBackend(_completed_result())
    api = _api(tmp_path, backend)
    session = api.create_session()
    run = api.create_run(session["session_id"], "codex approval required")

    result = api.submit_action(
        run["run_id"],
        {
            "action": "delegate_agent_task",
            "tool": "codex_task",
            "prompt": "Inspect the repository and report next steps.",
        },
    )

    assert result["status"] == "denied"
    assert result["decision"].reason_codes == ["codex_task_approval_required"]
    assert backend.calls == []
    assert "action.started" not in [event.event_type for event in api.get_events(run["run_id"])]


def test_approved_codex_task_runs_through_adapter_and_projects_safe_summary(tmp_path):
    secret = "SECRET_CODEX_TRANSCRIPT_must_stay_in_artifact"
    backend = FakeCodexBackend(_completed_result(content=secret))
    api = _api(tmp_path, backend)
    session = api.create_session()
    run = api.create_run(session["session_id"], "codex adapter spike")

    pending = api.submit_action(
        run["run_id"],
        {
            "action": "delegate_agent_task",
            "tool": "codex_task",
            "prompt": "Inspect the repository and report next steps.",
            "summary": "codex repository inspection",
        },
        requires_approval=True,
    )
    assert pending["status"] == "pending_user_approval"
    assert backend.calls == []

    result = api.resolve_approval(
        pending["approval_id"],
        {
            "resolution": "approved",
            "reason": "allow fake Codex adapter spike",
            "resolver": "reviewer",
        },
    )

    assert result["status"] == "completed"
    assert len(backend.calls) == 1
    request = backend.calls[0]
    assert request.task_request == {
        "kind": "codex_prompt",
        "prompt": "Inspect the repository and report next steps.",
    }
    action = result["run_state"].actions[result["execution_id"]]
    assert action["codex_task"] == {
        "adapter_id": "codex-local",
        "adapter_version": "0.1.0",
        "protocol_version": "codex-task-adapter.v0.1",
        "mode": "agent_cli_task",
        "status": "completed",
        "reason_code": "codex_task_completed",
    }
    action_repr = repr(action)
    assert secret not in action_repr
    assert "/Users/alice" not in action_repr
    assert "SECRET_ENV_TOKEN" not in action_repr
    assert api.artifact_store.get_content(result["artifact_ref"]) == secret
