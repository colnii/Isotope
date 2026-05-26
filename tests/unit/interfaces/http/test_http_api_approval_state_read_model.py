import json
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


def test_get_run_pending_approval_exposes_approval_read_model(tmp_path):
    app = create_http_app(tmp_path)
    run_id, result, approval = _submit_pending_approval(app)

    response = _request(app, "GET", f"/runs/{run_id}")

    assert _status_code(response) == 200
    state = _body(response)
    assert state["status"] == "pending_user_approval"
    assert state["approvals"][approval["approval_id"]] == {
        "approval_id": approval["approval_id"],
        "run_id": run_id,
        "proposal_id": approval["proposal_id"],
        "decision_id": approval["decision_id"],
        "status": "pending",
        "reason_codes": ["approval_required"],
        "requested_action_summary": {"action_type": "call_tool"},
    }
    assert state["actions"][result["decision"].proposal_id]["status"] == "pending_user_approval"


def test_get_run_approval_state_does_not_expose_internal_repr(tmp_path):
    app = create_http_app(tmp_path)
    run_id, _result, _approval = _submit_pending_approval(app)

    encoded = json.dumps(_body(_request(app, "GET", f"/runs/{run_id}")), sort_keys=True)

    assert "RunState(" not in encoded
    assert "PolicyDecision(" not in encoded
    assert "ActionProposal(" not in encoded


def test_get_run_after_approved_resolution_shows_completed_artifact_summary(tmp_path):
    app = create_http_app(tmp_path)
    run_id, _result, approval = _submit_pending_approval(app)

    resolve = _request(
        app,
        "POST",
        _approval_resolve_path(run_id, approval["approval_id"]),
        _approved_body(),
    )
    state = _body(_request(app, "GET", f"/runs/{run_id}"))

    assert _status_code(resolve) == 200
    assert state["status"] == "completed"
    assert state["approvals"][approval["approval_id"]]["status"] == "approved"
    assert state["approvals"][approval["approval_id"]]["resolution"] == "approved"
    assert state["artifacts"]
    assert "content" not in state["artifacts"][0]
    assert "raw_content" not in state["artifacts"][0]


def test_get_run_after_denied_resolution_shows_denied_without_artifact(tmp_path):
    app = create_http_app(tmp_path)
    run_id, _result, approval = _submit_pending_approval(app)

    resolve = _request(
        app,
        "POST",
        _approval_resolve_path(run_id, approval["approval_id"]),
        _denied_body(),
    )
    state = _body(_request(app, "GET", f"/runs/{run_id}"))

    assert _status_code(resolve) == 200
    assert state["status"] == "denied"
    assert state["approvals"][approval["approval_id"]]["status"] == "denied"
    assert state["approvals"][approval["approval_id"]]["resolution"] == "denied"
    assert state["artifacts"] == []


def test_duplicate_resolve_does_not_change_http_read_model(tmp_path):
    app = create_http_app(tmp_path)
    run_id, _result, approval = _submit_pending_approval(app)
    path = _approval_resolve_path(run_id, approval["approval_id"])

    first = _request(app, "POST", path, _denied_body())
    before = _body(_request(app, "GET", f"/runs/{run_id}"))
    second = _request(app, "POST", path, _denied_body())
    after = _body(_request(app, "GET", f"/runs/{run_id}"))

    assert _status_code(first) == 200
    assert _status_code(second) == 409
    assert after == before


def test_get_events_returns_canonical_events_not_materialized_approval_state(tmp_path):
    app = create_http_app(tmp_path)
    run_id, _result, approval = _submit_pending_approval(app)
    _request(app, "POST", _approval_resolve_path(run_id, approval["approval_id"]), _denied_body())

    response = _request(app, "GET", f"/runs/{run_id}/events")

    assert _status_code(response) == 200
    events = response.json()
    assert isinstance(events, list)
    event_types = [event["event_type"] for event in events]
    assert "approval.requested" in event_types
    assert "approval.resolved" in event_types
    assert all("approvals" not in event for event in events)


def test_approval_read_model_does_not_require_network_listener(tmp_path):
    app = create_http_app(tmp_path)

    assert not hasattr(app, "serve_forever")
    assert not hasattr(app, "listen")
