from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

import pytest

import isotope.integrations.codex.server as codex_server
from isotope.interfaces.http import create_codex_cli_http_app, create_http_app


ACTION_EXECUTION_EVENTS = {
    "action.started",
    "artifact.created",
    "action.completed",
    "action.failed",
    "run.completed",
}


class StubCompletedProcess:
    def __init__(self, *, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class RecordingProcessRunner:
    def __init__(self, result: StubCompletedProcess) -> None:
        self.result = result
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": list(argv), "kwargs": dict(kwargs)})
        return self.result


def _request(app, method: str, path: str, json_body: Any = None):
    return app.request(method, path, json=json_body)


def _status_code(response) -> int:
    if isinstance(response, Mapping):
        return int(response["status_code"])
    return int(response.status_code)


def _body(response) -> dict[str, Any]:
    if isinstance(response, Mapping):
        body = response.get("json", response.get("body"))
    elif callable(getattr(response, "json", None)):
        body = response.json()
    else:
        body = getattr(response, "body", None)
    assert isinstance(body, dict)
    return body


def _create_run(app) -> str:
    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="run HTTP Codex task")
    return run["run_id"]


def _codex_route(run_id: str) -> str:
    return f"/runs/{run_id}/codex-tasks"


def _approve_route(run_id: str, approval_id: str) -> str:
    return f"/runs/{run_id}/approvals/{approval_id}/resolve"


def _approved_body() -> dict[str, str]:
    return {
        "resolution": "approved",
        "reason": "approve explicit HTTP Codex task",
        "resolver": "reviewer",
    }


def _event_types(app, run_id: str) -> list[str]:
    return [event.event_type for event in app.server.get_events(run_id)]


def _codex_http_app(tmp_path, runner: RecordingProcessRunner):
    return create_codex_cli_http_app(
        tmp_path,
        config=codex_server.CodexCliServerConfig(
            workspace_root=str(tmp_path / "workspace"),
            executable="/opt/codex/bin/codex",
            timeout_seconds=19,
            max_output_bytes=4096,
        ),
        process_runner=runner,
    )


def test_default_http_codex_task_route_submits_pending_approval(tmp_path):
    app = create_http_app(tmp_path)
    run_id = _create_run(app)

    response = _request(
        app,
        "POST",
        _codex_route(run_id),
        {
            "prompt": "Inspect the repository and report the next step.",
            "summary": "HTTP Codex task",
        },
    )

    assert _status_code(response) == 202
    body = _body(response)
    assert body["status"] == "pending_user_approval"
    assert body["approval_id"].startswith("approval_")
    assert body["proposal_id"].startswith("prop_")
    assert "approval.requested" in _event_types(app, run_id)
    assert app.server.artifact_store.list_artifacts(run_id) == []


def test_codex_http_route_is_listed_by_default(tmp_path):
    default_app = create_http_app(tmp_path / "default")
    runner = RecordingProcessRunner(StubCompletedProcess(stdout='{"event":"task_complete"}\n'))
    codex_app = _codex_http_app(tmp_path / "codex", runner)

    assert ("POST", "/runs/{run_id}/codex-tasks") in default_app.routes()
    assert ("POST", "/runs/{run_id}/codex-tasks") in codex_app.routes()


def test_codex_http_route_submits_pending_approval_without_starting_codex(tmp_path):
    runner = RecordingProcessRunner(StubCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)

    response = _request(
        app,
        "POST",
        _codex_route(run_id),
        {
            "prompt": "Inspect this repository and reply with a short next step.",
            "summary": "HTTP Codex inspection",
        },
    )

    assert _status_code(response) == 202
    body = _body(response)
    assert body["status"] == "pending_user_approval"
    assert body["approval_id"].startswith("approval_")
    assert body["proposal_id"].startswith("prop_")
    assert body["decision_id"].startswith("dec_")
    assert runner.calls == []
    assert "Inspect this repository" not in repr(body)
    event_types = _event_types(app, run_id)
    assert "approval.requested" in event_types
    assert not ACTION_EXECUTION_EVENTS.intersection(event_types)


def test_codex_http_approval_resolution_runs_cli_backend_and_keeps_response_public_metadata(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "SECRET_ENV_SHOULD_NOT_BE_INHERITED")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7890")
    runner = RecordingProcessRunner(
        StubCompletedProcess(stdout='{"event":"task_complete","message":"ok"}\n')
    )
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)

    pending = _body(
        _request(
            app,
            "POST",
            _codex_route(run_id),
            {
                "prompt": "PROMPT_SHOULD_NOT_LEAK",
                "summary": "HTTP Codex inspection",
            },
        )
    )
    response = _request(app, "POST", _approve_route(run_id, pending["approval_id"]), _approved_body())

    assert _status_code(response) == 200
    body = _body(response)
    assert body["status"] == "completed"
    assert len(runner.calls) == 1
    assert runner.calls[0]["kwargs"]["timeout"] == 19
    assert runner.calls[0]["kwargs"]["shell"] is False
    assert runner.calls[0]["kwargs"]["env"]["HTTPS_PROXY"] == "http://127.0.0.1:7890"
    assert "OPENAI_API_KEY" not in runner.calls[0]["kwargs"]["env"]
    assert "PROMPT_SHOULD_NOT_LEAK" not in repr(body)
    assert "task_complete" not in repr(body)

    action = body["run_state"]["actions"][body["execution_id"]]
    assert action["codex_task"] == {
        "adapter_id": "codex_cli",
        "adapter_version": "server-wiring.v0.1",
        "protocol_version": "codex-task-adapter.v0.1",
        "mode": "agent_cli_task",
        "status": "completed",
        "reason_code": "codex_cli_completed",
    }
    artifact_ref = body["artifact_ref"]
    transcript = json.loads(
        app.server.artifact_store.get_content(app.server.artifact_store.list_artifacts(run_id)[-1].ref)
    )
    assert artifact_ref["artifact_id"] == app.server.artifact_store.list_artifacts(run_id)[-1].ref.artifact_id
    assert transcript["stdout"] == '{"event":"task_complete","message":"ok"}\n'


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"prompt": ""},
        {"prompt": "valid", "summary": ""},
        {"prompt": "valid", "requires_approval": False},
    ],
)
def test_codex_http_route_rejects_malformed_body_without_action_side_effects(tmp_path, body):
    runner = RecordingProcessRunner(StubCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    before_events = _event_types(app, run_id)

    response = _request(app, "POST", _codex_route(run_id), body)

    assert _status_code(response) == 400
    response_body = _body(response)
    assert response_body["status"] == "bad_request"
    assert response_body["error"]["code"] == "invalid_request"
    assert _event_types(app, run_id) == before_events
    assert runner.calls == []


def test_codex_http_route_idempotency_replays_pending_response_without_duplicate_approval(tmp_path):
    runner = RecordingProcessRunner(StubCompletedProcess(stdout='{"event":"task_complete"}\n'))
    app = _codex_http_app(tmp_path, runner)
    run_id = _create_run(app)
    body = {
        "prompt": "Inspect this repository and report the next step.",
        "summary": "HTTP Codex inspection",
        "idempotency_key": "codex-task-001",
    }

    first = _request(app, "POST", _codex_route(run_id), body)
    second = _request(app, "POST", _codex_route(run_id), body)

    assert _status_code(first) == 202
    assert _status_code(second) == 202
    assert _body(first) == _body(second)
    assert _event_types(app, run_id).count("approval.requested") == 1
    assert runner.calls == []


@pytest.mark.skipif(
    os.environ.get("ISOTOPE_RUN_LIVE_CODEX_HTTP_SMOKE") != "1",
    reason="live Codex HTTP route smoke is opt-in",
)
def test_live_codex_http_route_runs_after_approval(tmp_path):
    app = create_codex_cli_http_app(
        tmp_path,
        config=codex_server.CodexCliServerConfig(
            workspace_root=str(tmp_path / "workspace"),
            timeout_seconds=90,
        ),
    )
    run_id = _create_run(app)

    pending = _body(
        _request(
            app,
            "POST",
            _codex_route(run_id),
            {
                "prompt": "Reply exactly ISOTOPE_HTTP_CODEX_SMOKE_OK. Do not modify files.",
                "summary": "live HTTP Codex smoke",
            },
        )
    )
    result = _body(
        _request(app, "POST", _approve_route(run_id, pending["approval_id"]), _approved_body())
    )

    assert result["status"] == "completed"
    assert result["artifact_ref"]["artifact_id"]
    content = app.server.artifact_store.get_content(app.server.artifact_store.list_artifacts(run_id)[-1].ref)
    assert "exit_code" in content
