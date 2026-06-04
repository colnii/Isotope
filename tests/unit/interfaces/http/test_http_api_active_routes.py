import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from isotope.interfaces.http import create_http_app


def _request(app, method: str, path: str, json_body: Any = None):
    return app.request(method, path, json=json_body)


def _status_code(response) -> int:
    if isinstance(response, Mapping):
        return int(response["status_code"])
    return int(response.status_code)


def _body(response) -> dict[str, Any] | list[dict[str, Any]]:
    if isinstance(response, Mapping):
        body = response.get("json", response.get("body"))
    elif callable(getattr(response, "json", None)):
        body = response.json()
    else:
        body = getattr(response, "body", None)
    assert isinstance(body, (dict, list))
    return body


def _create_run(app) -> tuple[str, str, dict[str, Any]]:
    session = _body(_request(app, "POST", "/sessions"))
    assert isinstance(session, dict)
    run = _body(
        _request(
            app,
            "POST",
            f"/sessions/{session['session_id']}/runs",
            {"goal": "exercise active routes"},
        )
    )
    assert isinstance(run, dict)
    result = _body(_request(app, "POST", f"/runs/{run['run_id']}/input", {"text": "hello"}))
    assert isinstance(result, dict)
    state = _body(_request(app, "GET", f"/runs/{run['run_id']}"))
    assert isinstance(state, dict)
    artifact_ref = state["artifacts"][0]["ref"]
    return run["run_id"], artifact_ref["artifact_id"], artifact_ref


def _event_types(root: Path) -> list[str]:
    event_types: list[str] = []
    for path in sorted(root.glob("runs/*/events.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                event_types.append(str(json.loads(line)["event_type"]))
    return event_types


def test_routes_are_listed_as_supported_inventory(tmp_path):
    app = create_http_app(tmp_path)
    inventory = app.list_routes()
    supported = {(route["method"], route["path"], route["status"]) for route in inventory["routes"]}

    assert ("POST", "/runs/{run_id}/memory/query", "supported") in supported
    assert ("POST", "/external-ingestion", "supported") in supported
    assert ("GET", "/runs/{run_id}/events/stream", "supported") in supported
    assert ("POST", "/runs/{run_id}/approvals", "supported") in supported
    assert ("GET", "/artifacts/{artifact_id}/content", "supported") in supported


def test_memory_query_route_executes_against_local_memory_service(tmp_path):
    app = create_http_app(tmp_path)
    run_id, _, _ = _create_run(app)

    response = _request(app, "POST", f"/runs/{run_id}/memory/query", {"query": "hello"})

    assert _status_code(response) == 200
    body = _body(response)
    assert isinstance(body, dict)
    assert body["status"] == "ok"
    assert body["capability"] == "memory_query"


def test_external_ingestion_route_captures_input_as_artifact(tmp_path):
    app = create_http_app(tmp_path)
    run_id, _, _ = _create_run(app)

    response = _request(
        app,
        "POST",
        "/external-ingestion",
        {
            "source_system": "example_provider",
            "captured_at": "2026-01-01T00:00:01Z",
            "body": {"run_id": run_id, "message": "provider says the run is done"},
        },
    )

    assert _status_code(response) == 200
    body = _body(response)
    assert isinstance(body, dict)
    assert body["status"] == "artifact_only"
    assert body["artifact_ref"]["run_id"] == run_id


def test_events_stream_route_returns_event_snapshot(tmp_path):
    app = create_http_app(tmp_path)
    run_id, _, _ = _create_run(app)

    response = _request(app, "GET", f"/runs/{run_id}/events/stream")

    assert _status_code(response) == 200
    body = _body(response)
    assert isinstance(body, dict)
    assert body["status"] == "ok"
    assert [event["event_type"] for event in body["stream"]] == [
        event_type
        for event_type in _event_types(tmp_path)
        if event_type != "session.created"
    ]


def test_approval_route_creates_pending_approval(tmp_path):
    app = create_http_app(tmp_path)
    session = _body(_request(app, "POST", "/sessions"))
    assert isinstance(session, dict)
    run = _body(
        _request(
            app,
            "POST",
            f"/sessions/{session['session_id']}/runs",
            {"goal": "approval route"},
        )
    )
    assert isinstance(run, dict)
    run_id = run["run_id"]

    response = _request(app, "POST", f"/runs/{run_id}/approvals", {"text": "needs review"})

    assert _status_code(response) == 202
    body = _body(response)
    assert isinstance(body, dict)
    assert body["status"] == "pending_user_approval"
    assert body["approval_id"]


def test_artifact_content_route_returns_full_content(tmp_path):
    app = create_http_app(tmp_path)
    _, artifact_id, artifact_ref = _create_run(app)

    response = _request(
        app,
        "GET",
        f"/artifacts/{artifact_id}/content",
        {
            "ref": artifact_ref,
            "grants": {"artifact": {"read": "full"}},
            "caller_context": {"caller": "http_api_test", "run_id": artifact_ref["run_id"]},
            "purpose": "test artifact content retrieval",
        },
    )

    assert _status_code(response) == 200
    body = _body(response)
    assert isinstance(body, dict)
    assert body["status"] == "ok"
    assert body["view"] == "full"
    assert body["content"] == "hello"
