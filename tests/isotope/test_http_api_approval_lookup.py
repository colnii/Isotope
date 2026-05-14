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


def _submit_pending_approval(app):
    session = app.server.create_session()
    run = app.server.create_run(session["session_id"], goal="request approval before writing")
    result = app.server.submit_tool_request(
        run["run_id"],
        tool="write_artifact_tool",
        text="hello",
        requires_approval=True,
    )
    approval_id = next(iter(result["run_state"].approvals))
    return run["run_id"], approval_id, result


def _denied_body(**overrides):
    body = {
        "resolution": "denied",
        "reason": "operator denied deterministic artifact write",
        "resolver": "test_operator",
    }
    body.update(overrides)
    return body


def _assert_no_internal_repr(value: Any) -> None:
    if isinstance(value, str):
        assert "object at 0x" not in value
        assert "RunState(" not in value
        assert "PolicyDecision(" not in value
        assert "ActionProposal(" not in value
    elif isinstance(value, dict):
        for nested in value.values():
            _assert_no_internal_repr(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_internal_repr(nested)


def test_http_get_pending_approvals_returns_in_process_read_helper_response(tmp_path):
    app = create_http_app(tmp_path)
    run_id, approval_id, result = _submit_pending_approval(app)
    before_events = list(app.server.get_events(run_id))

    response = _request(app, "GET", f"/runs/{run_id}/approvals")

    assert _status_code(response) == 200
    body = _body(response)
    assert body["status"] == "ok"
    assert body["pending_approvals"] == [
        {
            "approval_id": approval_id,
            "run_id": run_id,
            "proposal_id": result["decision"].proposal_id,
            "decision_id": result["decision"].decision_id,
            "status": "pending",
            "reason_codes": ["approval_required"],
            "requested_action_summary": {"action_type": "call_tool"},
        }
    ]
    assert app.server.get_events(run_id) == before_events
    _assert_no_internal_repr(body)


def test_http_get_approval_returns_resolved_approval_summary(tmp_path):
    app = create_http_app(tmp_path)
    run_id, approval_id, _result = _submit_pending_approval(app)
    app.server.resolve_approval(approval_id, _denied_body())

    response = _request(app, "GET", f"/runs/{run_id}/approvals/{approval_id}")

    assert _status_code(response) == 200
    body = _body(response)
    assert body["status"] == "ok"
    assert body["approval"]["approval_id"] == approval_id
    assert body["approval"]["status"] == "denied"
    assert body["approval"]["resolution"] == "denied"
    _assert_no_internal_repr(body)


def test_http_approval_lookup_unknown_run_or_approval_is_controlled_404(tmp_path):
    app = create_http_app(tmp_path)
    run_id, _approval_id, _result = _submit_pending_approval(app)
    before_events = list(app.server.get_events(run_id))

    unknown_run = _request(app, "GET", "/runs/run_missing/approvals")
    unknown_approval = _request(app, "GET", f"/runs/{run_id}/approvals/approval_missing")

    assert _status_code(unknown_run) == 404
    assert _body(unknown_run)["error"]["code"] == "not_found"
    assert _status_code(unknown_approval) == 404
    assert _body(unknown_approval)["error"]["code"] == "not_found"
    assert app.server.get_events(run_id) == before_events


def test_http_approval_lookup_is_in_process_and_not_supported_product_inventory(
    tmp_path,
    monkeypatch,
):
    import socket

    def fail_socket(*args, **kwargs):
        raise AssertionError("approval lookup route must not open sockets")

    monkeypatch.setattr(socket, "socket", fail_socket)
    app = create_http_app(tmp_path)
    run_id, _approval_id, _result = _submit_pending_approval(app)

    response = _request(app, "GET", f"/runs/{run_id}/approvals")
    supported_paths = {
        route["path"]
        for route in app.list_routes()["routes"]
        if route["status"] == "supported"
    }

    assert _status_code(response) == 200
    assert "/runs/{run_id}/approvals" not in supported_paths
    assert "/runs/{run_id}/approvals/{approval_id}" not in supported_paths
    assert not hasattr(app, "serve_forever")
    assert not hasattr(app, "listen")

