import socket
from collections.abc import Mapping
from typing import Any

import pytest

from isotope_kernel.http_api import create_http_app


FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
}


def _request(app, method: str, path: str, json_body: Any = None):
    return app.request(method, path, json=json_body)


def _status_code(response) -> int:
    if isinstance(response, Mapping):
        return int(response["status_code"])
    return int(response.status_code)


def _body(response):
    if isinstance(response, Mapping):
        return response.get("json", response.get("body"))
    if callable(getattr(response, "json", None)):
        return response.json()
    return getattr(response, "body", None)


def _json_body(response) -> dict[str, Any]:
    body = _body(response)
    assert isinstance(body, dict)
    return body


def _json_list(response) -> list[dict[str, Any]]:
    body = _body(response)
    assert isinstance(body, list)
    assert all(isinstance(item, dict) for item in body)
    return body


def _successful_json(response) -> dict[str, Any]:
    assert 200 <= _status_code(response) < 300
    return _json_body(response)


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        assert FORBIDDEN_CONTENT_KEYS.isdisjoint(value)
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def test_http_api_demo_smoke_runs_kernel_loop_without_network_or_listener(
    tmp_path,
    monkeypatch,
):
    def fail_socket(*args, **kwargs):
        raise AssertionError("HTTP API demo smoke must not open sockets")

    monkeypatch.setattr(socket, "socket", fail_socket)

    app = create_http_app(tmp_path)
    assert not hasattr(app, "serve_forever")
    assert not hasattr(app, "listen")

    session = _successful_json(_request(app, "POST", "/sessions"))
    run = _successful_json(
        _request(
            app,
            "POST",
            f"/sessions/{session['session_id']}/runs",
            {"goal": "produce a hello artifact"},
        )
    )
    submit = _successful_json(
        _request(app, "POST", f"/runs/{run['run_id']}/input", {"text": "hello"})
    )
    run_state = _successful_json(_request(app, "GET", f"/runs/{run['run_id']}"))
    events = _json_list(_request(app, "GET", f"/runs/{run['run_id']}/events"))

    assert submit["status"] == "completed"
    assert run_state["status"] == "completed"
    assert run_state["artifacts"]
    event_types = [event["event_type"] for event in events]
    assert event_types
    assert {
        "action.proposed",
        "action.decided",
        "action.started",
        "artifact.created",
        "action.completed",
    }.issubset(event_types)

    artifact_id = run_state["artifacts"][0]["ref"]["artifact_id"]
    artifact_summary = _successful_json(
        _request(app, "GET", f"/artifacts/{artifact_id}/summary")
    )
    assert set(artifact_summary) == {"ref", "artifact_type", "summary", "provenance"}
    assert artifact_summary["summary"] == "hello artifact"
    assert artifact_summary["ref"]["artifact_id"] == artifact_id
    assert artifact_summary["provenance"]["execution_id"]

    for body in (submit, run_state, events, artifact_summary):
        _assert_no_forbidden_content_keys(body)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/memory/query"),
        ("POST", "/external-ingestion"),
        ("GET", "/runs/run_001/events/stream"),
        ("GET", "/artifacts/artifact_001/content"),
    ],
)
def test_http_api_demo_smoke_keeps_deferred_routes_absent_or_not_enabled(
    tmp_path,
    method,
    path,
):
    app = create_http_app(tmp_path)

    response = _request(app, method, path, {"text": "ignored"})

    assert _status_code(response) in {404, 405, 501}
    body = _json_body(response)
    assert body["status"] in {"not_found", "method_not_allowed", "not_enabled"}
