from collections.abc import Mapping
from typing import Any

from isotope_kernel.http_api import create_http_app


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


def _create_run(app) -> dict[str, Any]:
    session = app.server.create_session()
    return app.server.create_run(session["session_id"], goal="http agent loop step driver")


def _approval_step() -> dict[str, Any]:
    return {
        "step": "submit_approval_gated_action",
        "intent": {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "http agent loop step",
        },
    }


def _approval_resolution(approval_id: str) -> dict[str, Any]:
    return {
        "step": "resolve_approval",
        "approval_id": approval_id,
        "resolution": {
            "resolution": "approved",
            "reason": "operator approved http agent loop step",
            "resolver": "test_operator",
        },
    }


def test_http_agent_loop_step_driver_runs_one_step_and_returns_control(tmp_path):
    app = create_http_app(tmp_path)
    run = _create_run(app)

    response = _request(app, "POST", f"/runs/{run['run_id']}/agent-loop-step", _approval_step())

    assert _status_code(response) == 200
    body = _body(response)
    assert body["step"] == "submit_approval_gated_action"
    assert body["status"] == "pending_user_approval"
    assert body["action_result"]["approval_id"]
    assert body["control"]["phase"] == "awaiting_approval"
    assert body["control"]["next_actions"] == ["get_approval", "resolve_approval"]


def test_http_agent_loop_step_driver_can_resume_approval(tmp_path):
    app = create_http_app(tmp_path)
    run = _create_run(app)
    pending = _body(_request(app, "POST", f"/runs/{run['run_id']}/agent-loop-step", _approval_step()))

    response = _request(
        app,
        "POST",
        f"/runs/{run['run_id']}/agent-loop-step",
        _approval_resolution(pending["action_result"]["approval_id"]),
    )

    assert _status_code(response) == 200
    body = _body(response)
    assert body["step"] == "resolve_approval"
    assert body["status"] == "completed"
    assert body["action_result"]["artifact_ref"]["ref_type"] == "artifact"
    assert body["control"]["phase"] == "completed"


def test_http_agent_loop_step_driver_unknown_run_is_404(tmp_path):
    app = create_http_app(tmp_path)

    response = _request(app, "POST", "/runs/run_missing/agent-loop-step", _approval_step())

    assert _status_code(response) == 404
    assert _body(response)["error"]["code"] == "not_found"


def test_http_agent_loop_step_driver_malformed_body_is_400_without_events(tmp_path):
    app = create_http_app(tmp_path)
    run = _create_run(app)
    before = app.server.get_events(run["run_id"])

    response = _request(app, "POST", f"/runs/{run['run_id']}/agent-loop-step", {"step": "unknown"})

    assert _status_code(response) == 400
    assert _body(response)["error"]["code"] == "bad_request"
    assert app.server.get_events(run["run_id"]) == before


def test_http_agent_loop_step_driver_is_supported_in_route_inventory(tmp_path):
    app = create_http_app(tmp_path)

    inventory = app.list_routes()

    assert {
        "method": "POST",
        "path": "/runs/{run_id}/agent-loop-step",
        "status": "supported",
    } in inventory["routes"]
