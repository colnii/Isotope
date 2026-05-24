from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from isotope.interfaces.http import create_http_app


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
    return app.server.create_run(session["session_id"], goal="http agent loop tick")


def _planner_output(
    control: dict[str, Any],
    step: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    return {
        "planner_run_id": "planner_run_http_tick_001",
        "basis": {
            "run_id": control["run_id"],
            "last_event_id": control["last_event_id"],
        },
        "decision": {
            "step": step,
            "request": request,
        },
    }


def test_http_agent_loop_tick_driver_runs_one_planner_tick(tmp_path):
    app = create_http_app(tmp_path)
    run = _create_run(app)
    control = app.server.get_agent_loop_control(run["run_id"])

    response = _request(
        app,
        "POST",
        f"/runs/{run['run_id']}/agent-loop-tick",
        {
            "planner_output": _planner_output(
                control,
                "call_capability",
                {"capability_id": "artifact.review"},
            ),
            "tick_budget": {
                "max_ticks": 2,
                "ticks_used": 0,
                "budget_basis": "http-test",
            },
        },
    )

    assert _status_code(response) == 200
    body = _body(response)
    assert body["tick_status"] == "executed"
    assert body["planner_result"]["selected_step"] == "call_capability"
    assert body["after_policy"]["tick_budget"]["ticks_used"] == 1


def test_http_agent_loop_tick_driver_stops_when_user_paused(tmp_path):
    app = create_http_app(tmp_path)
    run = _create_run(app)
    before = app.server.get_events(run["run_id"])

    response = _request(
        app,
        "POST",
        f"/runs/{run['run_id']}/agent-loop-tick",
        {
            "user_pause": {
                "user_paused": True,
                "pause_basis": "operator:http-test",
            },
        },
    )

    assert _status_code(response) == 200
    body = _body(response)
    assert body["tick_status"] == "stopped"
    assert body["stop_reason"] == "user_paused"
    assert body["planner_result"] is None
    assert app.server.get_events(run["run_id"]) == before


def test_http_agent_loop_tick_driver_is_supported_in_route_inventory(tmp_path):
    app = create_http_app(tmp_path)

    inventory = app.list_routes()

    assert {
        "method": "POST",
        "path": "/runs/{run_id}/agent-loop-tick",
        "status": "supported",
    } in inventory["routes"]
