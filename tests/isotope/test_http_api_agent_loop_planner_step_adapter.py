from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from isotope.http_api import create_http_app


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
    return app.server.create_run(session["session_id"], goal="http planner to step driver adapter")


def _planner_output(control: dict[str, Any], step: str, request: dict[str, Any]) -> dict[str, Any]:
    return {
        "planner_run_id": "planner_run_http_001",
        "basis": {
            "run_id": control["run_id"],
            "last_event_id": control["last_event_id"],
        },
        "decision": {
            "step": step,
            "request": request,
        },
    }


def _approval_request() -> dict[str, Any]:
    return {
        "intent": {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "http planner selected step",
        },
    }


def test_http_planner_step_adapter_runs_selected_step(tmp_path):
    app = create_http_app(tmp_path)
    run = _create_run(app)
    control = app.server.get_agent_loop_control(run["run_id"])

    response = _request(
        app,
        "POST",
        f"/runs/{run['run_id']}/agent-loop-planner-step",
        _planner_output(control, "submit_approval_gated_action", _approval_request()),
    )

    assert _status_code(response) == 200
    body = _body(response)
    assert body["planner_status"] == "accepted"
    assert body["selected_step"] == "submit_approval_gated_action"
    assert body["step_result"]["status"] == "pending_user_approval"
    assert body["control"]["phase"] == "awaiting_approval"


def test_http_planner_step_adapter_rejects_stale_basis_without_events(tmp_path):
    app = create_http_app(tmp_path)
    run = _create_run(app)
    control = app.server.get_agent_loop_control(run["run_id"])
    output = _planner_output(control, "submit_approval_gated_action", _approval_request())
    output["basis"]["last_event_id"] = "evt_stale"
    before = app.server.get_events(run["run_id"])

    response = _request(app, "POST", f"/runs/{run['run_id']}/agent-loop-planner-step", output)

    assert _status_code(response) == 400
    assert _body(response)["error"]["code"] == "bad_request"
    assert app.server.get_events(run["run_id"]) == before


def test_http_planner_step_adapter_is_supported_in_route_inventory(tmp_path):
    app = create_http_app(tmp_path)

    inventory = app.list_routes()

    assert {
        "method": "POST",
        "path": "/runs/{run_id}/agent-loop-planner-step",
        "status": "supported",
    } in inventory["routes"]
