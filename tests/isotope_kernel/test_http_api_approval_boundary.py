from collections.abc import Mapping
from typing import Any

import pytest

from isotope_kernel.http_api import create_http_app


ACTION_EXECUTION_EVENTS = {
    "action.started",
    "artifact.created",
    "action.completed",
    "action.failed",
    "run.completed",
}


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


def _submit_pending_approval(app):
    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="request approval before writing")
    result = app.server.submit_tool_request(
        run["run_id"],
        tool="write_artifact_tool",
        text="hello",
        requires_approval=True,
    )
    approval = _single_event_payload(app, run["run_id"], "approval.requested")
    return run["run_id"], result, approval


def _single_event_payload(app, run_id: str, event_type: str) -> dict:
    matches = [
        event.payload
        for event in app.server.get_events(run_id)
        if event.event_type == event_type
    ]
    assert len(matches) == 1
    return matches[0]


def _event_types(app, run_id: str) -> list[str]:
    return [event.event_type for event in app.server.get_events(run_id)]


def _approval_resolve_path(run_id: str, approval_id: str) -> str:
    return f"/runs/{run_id}/approvals/{approval_id}/resolve"


def _approved_body(**overrides):
    body = {
        "resolution": "approved",
        "reason": "operator approved deterministic artifact write",
        "resolver": "test_operator",
    }
    body.update(overrides)
    return body


def _denied_body(**overrides):
    body = {
        "resolution": "denied",
        "reason": "operator denied deterministic artifact write",
        "resolver": "test_operator",
    }
    body.update(overrides)
    return body


def test_route_inventory_does_not_mark_approval_api_as_supported(tmp_path):
    app = create_http_app(tmp_path)
    inventory = app.list_routes()

    supported_paths = {
        route["path"]
        for route in inventory["routes"]
        if route["status"] == "supported"
    }

    assert "/runs/{run_id}/approvals" not in supported_paths
    assert "/runs/{run_id}/approvals/{approval_id}/resolve" not in supported_paths


def test_approval_route_remains_in_process_facade_not_real_network(tmp_path, monkeypatch):
    import socket

    def fail_socket(*args, **kwargs):
        raise AssertionError("approval route must not open sockets")

    monkeypatch.setattr(socket, "socket", fail_socket)
    app = create_http_app(tmp_path)

    assert not hasattr(app, "serve_forever")
    assert not hasattr(app, "listen")
    response = _request(app, "POST", "/runs/run_missing/approvals/approval_missing/resolve")
    assert _status_code(response) in {404, 501}


def test_approval_resolve_unknown_approval_returns_controlled_404(tmp_path):
    app = create_http_app(tmp_path)

    response = _request(
        app,
        "POST",
        "/runs/run_missing/approvals/approval_missing/resolve",
        _approved_body(),
    )

    assert _status_code(response) == 404
    body = _body(response)
    assert body["status"] == "not_found"
    assert body["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"resolution": "approved"},
        {"resolution": "maybe", "reason": "invalid", "resolver": "test_operator"},
        {"resolution": "approved", "reason": "", "resolver": "test_operator"},
    ],
)
def test_approval_resolve_malformed_body_returns_400(tmp_path, body):
    app = create_http_app(tmp_path)
    run_id, _result, approval = _submit_pending_approval(app)

    response = _request(app, "POST", _approval_resolve_path(run_id, approval["approval_id"]), body)

    assert _status_code(response) == 400
    assert _body(response)["error"]["code"] == "bad_request"
    assert _event_types(app, run_id).count("approval.resolved") == 0


def test_denied_http_approval_resolve_does_not_create_execution_or_artifact(tmp_path):
    app = create_http_app(tmp_path)
    run_id, _result, approval = _submit_pending_approval(app)

    response = _request(
        app,
        "POST",
        _approval_resolve_path(run_id, approval["approval_id"]),
        _denied_body(),
    )

    assert _status_code(response) == 200
    assert _body(response)["status"] == "denied"
    event_types = _event_types(app, run_id)
    assert "approval.resolved" in event_types
    assert not ACTION_EXECUTION_EVENTS.intersection(event_types)
    assert app.server.artifact_store.list_artifacts(run_id) == []


def test_submit_input_with_requires_approval_true_emits_approval_requested(tmp_path):
    app = create_http_app(tmp_path)
    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="approval-gated input")

    response = _request(
        app,
        "POST",
        f"/runs/{run['run_id']}/input",
        {"text": "hello", "requires_approval": True},
    )

    assert _status_code(response) == 200
    body = _body(response)
    assert body["status"] == "pending_user_approval"
    event_types = _event_types(app, run["run_id"])
    assert "approval.requested" in event_types
    assert not ACTION_EXECUTION_EVENTS.intersection(event_types)
    run_state = _body(_request(app, "GET", f"/runs/{run['run_id']}"))
    assert run_state["status"] == "pending_user_approval"
    assert run_state["approvals"]
    assert run_state["artifacts"] == []


def test_submit_input_with_invalid_requires_approval_is_rejected(tmp_path):
    app = create_http_app(tmp_path)
    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="reject invalid approval flag")

    response = _request(
        app,
        "POST",
        f"/runs/{run['run_id']}/input",
        {"text": "hello", "requires_approval": "true"},
    )

    assert _status_code(response) == 400
    assert _body(response)["error"]["code"] == "bad_request"
    assert "approval.requested" not in _event_types(app, run["run_id"])


def test_approved_http_approval_resolve_uses_action_chain(tmp_path):
    app = create_http_app(tmp_path)
    run_id, _result, approval = _submit_pending_approval(app)

    response = _request(
        app,
        "POST",
        _approval_resolve_path(run_id, approval["approval_id"]),
        _approved_body(grants={"tools": ["forged_tool"]}),
    )

    assert _status_code(response) == 200
    assert _body(response)["status"] == "completed"
    event_types = _event_types(app, run_id)
    assert event_types.index("approval.resolved") < event_types.index("action.started")
    assert "action.proposed" in event_types
    assert "action.decided" in event_types
    assert "artifact.created" in event_types
    assert "action.completed" in event_types


def test_duplicate_http_approval_resolve_is_controlled(tmp_path):
    app = create_http_app(tmp_path)
    run_id, _result, approval = _submit_pending_approval(app)
    path = _approval_resolve_path(run_id, approval["approval_id"])

    first = _request(app, "POST", path, _denied_body())
    second = _request(app, "POST", path, _denied_body())

    assert _status_code(first) == 200
    assert _status_code(second) in {200, 409}
    if _status_code(second) == 409:
        assert _body(second)["error"]["code"] in {"conflict", "approval_already_resolved"}
    assert _event_types(app, run_id).count("approval.resolved") == 1


def test_deferred_approval_collection_route_error_shape_remains_stable(tmp_path):
    app = create_http_app(tmp_path)

    response = _request(app, "POST", "/runs/run_001/approvals", {"resolution": "approved"})

    assert _status_code(response) == 501
    body = _body(response)
    assert body["status"] == "not_enabled"
    assert body["error"]["code"] == "not_enabled"
    assert body["error"]["capability"] == "approval_api"
