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
    return app.server.create_run(session["session_id"], goal="agent loop tick policy")


def test_http_agent_loop_tick_policy_returns_ready_decision(tmp_path):
    app = create_http_app(tmp_path)
    run = _create_run(app)

    response = _request(app, "GET", f"/runs/{run['run_id']}/agent-loop-tick-policy")

    assert _status_code(response) == 200
    body = _body(response)
    assert body["run_id"] == run["run_id"]
    assert body["phase"] == "ready"
    assert body["should_continue"] is True
    assert body["must_stop_reason"] is None
    assert body["max_next_tick_kind"] == "planner_step"


def test_http_agent_loop_tick_policy_accepts_budget_and_pause_controls(tmp_path):
    app = create_http_app(tmp_path)
    run = _create_run(app)

    response = _request(
        app,
        "GET",
        f"/runs/{run['run_id']}/agent-loop-tick-policy",
        {
            "tick_budget": {
                "max_ticks": 1,
                "ticks_used": 1,
                "budget_basis": "http-test",
            },
            "user_pause": {"user_paused": False},
        },
    )

    assert _status_code(response) == 200
    body = _body(response)
    assert body["should_continue"] is False
    assert body["must_stop_reason"] == "tick_budget_exhausted"
    assert body["tick_budget"]["remaining_ticks"] == 0
    assert body["user_pause"] == {"user_paused": False, "pause_basis": None}


def test_http_agent_loop_tick_policy_is_supported_in_route_inventory(tmp_path):
    app = create_http_app(tmp_path)

    inventory = app.list_routes()

    assert {
        "method": "GET",
        "path": "/runs/{run_id}/agent-loop-tick-policy",
        "status": "supported",
    } in inventory["routes"]
