from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest

from isotope import codex_server
from isotope.platform.errors import IsotopeError
from isotope.interfaces.http import create_codex_cli_http_app, create_http_app
from isotope.llm.tool_bridge import submit_model_tool_call


ACTION_EXECUTION_EVENTS = {
    "action.started",
    "artifact.created",
    "action.completed",
    "action.failed",
    "run.completed",
}


class FakeCompletedProcess:
    def __init__(self, *, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class RecordingProcessRunner:
    def __init__(self, result: FakeCompletedProcess) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": list(argv), "kwargs": dict(kwargs)})
        return self.result


def _body(response) -> dict[str, Any]:
    if isinstance(response, Mapping):
        body = response.get("json", response.get("body"))
    elif callable(getattr(response, "json", None)):
        body = response.json()
    else:
        body = getattr(response, "body", None)
    assert isinstance(body, dict)
    return body


def _codex_http_app(tmp_path, runner: RecordingProcessRunner):
    return create_codex_cli_http_app(
        tmp_path,
        config=codex_server.CodexCliServerConfig(
            workspace_root=str(tmp_path / "workspace"),
            executable="/opt/codex/bin/codex",
            timeout_seconds=17,
            max_output_bytes=4096,
        ),
        process_runner=runner,
    )


def _create_run(app) -> str:
    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="model chooses a Codex task")
    return run["run_id"]


def _event_types(app, run_id: str) -> list[str]:
    return [event.event_type for event in app.server.get_events(run_id)]


def _approve_route(run_id: str, approval_id: str) -> str:
    return f"/runs/{run_id}/approvals/{approval_id}/resolve"


def _approved_body() -> dict[str, str]:
    return {
        "resolution": "approved",
        "reason": "approve model-selected Codex task",
        "resolver": "reviewer",
    }


def test_model_tool_bridge_submits_enabled_codex_task_and_waits_for_approval(tmp_path):
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)

    result = submit_model_tool_call(
        app,
        run_id,
        {
            "tool_name": "codex_task",
            "arguments": {
                "prompt": "PROMPT_SHOULD_NOT_LEAK",
                "summary": "model-selected Codex inspection",
            },
        },
    )

    assert result["status"] == "pending_user_approval"
    assert result["tool_name"] == "codex_task"
    assert result["http_status_code"] == 202
    assert result["route"] == f"/runs/{run_id}/codex-tasks"
    assert result["requires_approval"] is True
    assert result["approval_id"].startswith("approval_")
    assert result["proposal_id"].startswith("prop_")
    assert result["decision_id"].startswith("dec_")
    assert "PROMPT_SHOULD_NOT_LEAK" not in repr(result)
    assert runner.calls == []
    event_types = _event_types(app, run_id)
    assert "approval.requested" in event_types
    assert not ACTION_EXECUTION_EVENTS.intersection(event_types)


def test_model_tool_bridge_rejects_default_deferred_codex_task_without_side_effects(tmp_path):
    app = create_http_app(tmp_path)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    with pytest.raises(IsotopeError) as exc_info:
        submit_model_tool_call(
            app,
            run_id,
            {
                "tool_name": "codex_task",
                "arguments": {"prompt": "Inspect the repository."},
            },
        )

    assert exc_info.value.code == "model_tool_not_enabled"
    assert exc_info.value.details == {"tool_name": "codex_task"}
    assert _event_types(app, run_id) == before_events
    assert app.server.artifact_store.list_artifacts(run_id) == []


def test_model_tool_bridge_approval_resolution_runs_existing_codex_http_path(tmp_path):
    runner = RecordingProcessRunner(
        FakeCompletedProcess(stdout='{"event":"task_complete","message":"ok"}\n')
    )
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)

    pending = submit_model_tool_call(
        app,
        run_id,
        {
            "tool_name": "codex_task",
            "arguments": {
                "prompt": "Inspect this repository.",
                "summary": "model-selected Codex inspection",
            },
        },
    )
    approved = _body(
        app.request("POST", _approve_route(run_id, pending["approval_id"]), json=_approved_body())
    )

    assert approved["status"] == "completed"
    assert len(runner.calls) == 1
    assert runner.calls[0]["kwargs"]["timeout"] == 17
    artifact_ref = approved["artifact_ref"]
    transcript = json.loads(
        app.server.artifact_store.get_content(app.server.artifact_store.list_artifacts(run_id)[-1].ref)
    )
    assert artifact_ref["artifact_id"] == app.server.artifact_store.list_artifacts(run_id)[-1].ref.artifact_id
    assert transcript["stdout"] == '{"event":"task_complete","message":"ok"}\n'


def test_model_tool_bridge_rejects_model_attempt_to_disable_approval(tmp_path):
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    with pytest.raises(IsotopeError) as exc_info:
        submit_model_tool_call(
            app,
            run_id,
            {
                "tool_name": "codex_task",
                "arguments": {
                    "prompt": "Inspect this repository.",
                    "requires_approval": False,
                },
            },
        )

    assert exc_info.value.code == "invalid_model_tool_call"
    assert exc_info.value.details == {"field": "requires_approval"}
    assert _event_types(app, run_id) == before_events
    assert runner.calls == []


def test_model_tool_bridge_routes_terminal_exec_through_controlled_action_chain(tmp_path):
    app = create_http_app(tmp_path)
    run_id = _create_run(app)
    secret = "MODEL_TERMINAL_SECRET"

    result = submit_model_tool_call(
        app,
        run_id,
        {
            "tool_name": "terminal_exec",
            "arguments": {
                "argv": ["printf", secret],
                "summary": "model-selected terminal command",
            },
        },
    )

    assert result["status"] == "completed"
    assert result["tool_name"] == "terminal_exec"
    assert result["route"] == "in-process:submit_action"
    assert result["requires_approval"] is False
    assert result["tool_execution_status"] == "completed"
    assert result["artifact_ref"]["ref_type"] == "artifact"
    assert secret not in repr(result)
    assert _event_types(app, run_id) == [
        "run.created",
        "agent.created",
        "thread.created",
        "action.proposed",
        "action.decided",
        "action.started",
        "artifact.created",
        "action.completed",
        "run.completed",
    ]
    transcript = json.loads(
        app.server.artifact_store.get_content(app.server.artifact_store.list_artifacts(run_id)[-1].ref)
    )
    assert transcript["stdout"] == secret
    assert transcript["shell"] is False


def test_model_tool_bridge_terminal_exec_rejects_shell_string_without_side_effects(tmp_path):
    app = create_http_app(tmp_path)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    with pytest.raises(IsotopeError) as exc_info:
        submit_model_tool_call(
            app,
            run_id,
            {
                "tool_name": "terminal_exec",
                "arguments": {"argv": "printf should-not-run"},
            },
        )

    assert exc_info.value.code == "invalid_model_tool_call"
    assert exc_info.value.details == {"field": "argv"}
    assert _event_types(app, run_id) == before_events
    assert app.server.artifact_store.list_artifacts(run_id) == []


def test_model_tool_bridge_terminal_exec_can_pause_for_approval(tmp_path):
    app = create_http_app(tmp_path)
    run_id = _create_run(app)

    result = submit_model_tool_call(
        app,
        run_id,
        {
            "tool_name": "terminal_exec",
            "arguments": {
                "argv": ["printf", "needs-approval"],
                "requires_approval": True,
            },
        },
    )

    assert result["status"] == "pending_user_approval"
    assert result["tool_name"] == "terminal_exec"
    assert result["requires_approval"] is True
    assert result["approval_id"].startswith("approval_")
    assert "action.started" not in _event_types(app, run_id)
    assert app.server.artifact_store.list_artifacts(run_id) == []


def test_model_tool_bridge_rejects_enabled_tool_without_bridge_route(tmp_path):
    app = create_http_app(tmp_path)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    with pytest.raises(IsotopeError) as exc_info:
        submit_model_tool_call(
            app,
            run_id,
            {
                "tool_name": "write_artifact_tool",
                "arguments": {"text": "should-not-write"},
            },
        )

    assert exc_info.value.code == "model_tool_route_not_enabled"
    assert exc_info.value.details == {"tool_name": "write_artifact_tool"}
    assert _event_types(app, run_id) == before_events
    assert app.server.artifact_store.list_artifacts(run_id) == []


def test_model_tool_bridge_preserves_route_error_shape_for_unknown_run(tmp_path):
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)

    with pytest.raises(IsotopeError) as exc_info:
        submit_model_tool_call(
            app,
            "run_missing",
            {
                "tool_name": "codex_task",
                "arguments": {"prompt": "Inspect this repository."},
            },
        )

    assert exc_info.value.code == "unknown_run"
    assert exc_info.value.category == "not_found"
    assert exc_info.value.http_status == 404
    assert exc_info.value.details == {"run_id": "run_missing"}
    assert runner.calls == []
