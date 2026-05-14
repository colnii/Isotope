import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from isotope.http_api import create_http_app


FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
}

ACTION_LIFECYCLE_EVENTS = {
    "action.proposed",
    "action.decided",
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


def _response_body(response) -> dict[str, Any] | list[dict[str, Any]]:
    if isinstance(response, Mapping):
        body = response.get("json", response.get("body"))
    elif callable(getattr(response, "json", None)):
        body = response.json()
    else:
        body = getattr(response, "body", None)
    assert isinstance(body, (dict, list))
    return body


def _json_body(response) -> dict[str, Any]:
    body = _response_body(response)
    assert isinstance(body, dict)
    return body


def _json_list(response) -> list[dict[str, Any]]:
    body = _response_body(response)
    assert isinstance(body, list)
    assert all(isinstance(item, dict) for item in body)
    return body


def _successful_json(response) -> dict[str, Any]:
    assert 200 <= _status_code(response) < 300
    return _json_body(response)


def _assert_json_compatible(value: Any) -> None:
    json.dumps(value)
    if isinstance(value, dict):
        for nested in value.values():
            _assert_json_compatible(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_json_compatible(nested)
    else:
        assert value is None or isinstance(value, (str, int, float, bool))


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        assert FORBIDDEN_CONTENT_KEYS.isdisjoint(value)
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def _assert_no_internal_repr(value: Any) -> None:
    if isinstance(value, str):
        forbidden_fragments = (
            "RunState(",
            "Artifact(",
            "ActionProposal(",
            "PolicyDecision(",
            "ActionExecution(",
            "CanonicalEvent(",
            "object at 0x",
        )
        assert not any(fragment in value for fragment in forbidden_fragments)
    elif isinstance(value, dict):
        for nested in value.values():
            _assert_no_internal_repr(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_internal_repr(nested)


def _assert_response_contract(response, expected_status: int) -> dict[str, Any] | list[dict[str, Any]]:
    assert hasattr(response, "status_code")
    assert _status_code(response) == expected_status
    body = _response_body(response)
    _assert_json_compatible(body)
    _assert_no_internal_repr(body)
    return body


def _assert_error_response(response, expected_status: int, expected_code: str) -> dict[str, Any]:
    body = _assert_response_contract(response, expected_status)
    assert isinstance(body, dict)
    assert body["status"] == expected_code
    assert set(body) >= {"status", "error"}
    assert isinstance(body["error"], dict)
    if expected_code == "bad_request":
        assert body["error"]["code"] in {"bad_request", "invalid_request"}
    else:
        assert body["error"]["code"] == expected_code
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"]
    _assert_no_internal_repr(body["error"]["message"])
    return body


def _create_run(app) -> tuple[str, str]:
    session = _successful_json(_request(app, "POST", "/sessions"))
    run = _successful_json(
        _request(
            app,
            "POST",
            f"/sessions/{session['session_id']}/runs",
            {"goal": "produce a hello artifact"},
        )
    )
    return session["session_id"], run["run_id"]


def _event_types(root: Path, run_id: str | None = None) -> list[str]:
    paths = (
        [root / "runs" / run_id / "events.jsonl"]
        if run_id is not None
        else sorted(root.glob("runs/*/events.jsonl"))
    )
    event_types: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                event_types.append(str(json.loads(line)["event_type"]))
    return event_types


def _artifact_files(root: Path) -> list[Path]:
    return sorted(root.glob("runs/*/artifacts/*.json"))


def test_every_response_exposes_status_code_and_json_compatible_body(tmp_path):
    app = create_http_app(tmp_path)

    success = _request(app, "POST", "/sessions")
    not_found = _request(app, "GET", "/not-found")
    method_mismatch = _request(app, "GET", "/sessions")

    _assert_response_contract(success, 201)
    _assert_response_contract(not_found, 404)
    _assert_response_contract(method_mismatch, 405)


@pytest.mark.parametrize(
    ("response_factory", "expected_status", "expected_code"),
    [
        (
            lambda app: _request(app, "GET", "/not-found"),
            404,
            "not_found",
        ),
        (
            lambda app: _request(app, "GET", "/sessions"),
            405,
            "method_not_allowed",
        ),
        (
            lambda app: _request(app, "POST", "/sessions/session_missing/runs", None),
            400,
            "bad_request",
        ),
    ],
)
def test_error_responses_use_stable_error_shape(
    tmp_path,
    response_factory,
    expected_status,
    expected_code,
):
    app = create_http_app(tmp_path)

    response = response_factory(app)

    _assert_error_response(response, expected_status, expected_code)


def test_method_mismatch_can_report_allowed_methods_without_routing_details(tmp_path):
    app = create_http_app(tmp_path)

    response = _request(app, "GET", "/sessions")

    body = _assert_error_response(response, 405, "method_not_allowed")
    assert body["error"].get("allowed_methods") == ["POST"]
    assert "handler" not in body["error"]
    assert "routes" not in body["error"]
    assert "{session_id}" not in body["error"]["message"]


def test_success_responses_do_not_return_python_dataclasses_or_raw_objects(tmp_path):
    app = create_http_app(tmp_path)
    _, run_id = _create_run(app)
    submit = _request(app, "POST", f"/runs/{run_id}/input", {"text": "hello"})
    run_state = _request(app, "GET", f"/runs/{run_id}")
    events = _request(app, "GET", f"/runs/{run_id}/events")

    for response in (submit, run_state):
        body = _assert_response_contract(response, 200)
        assert isinstance(body, dict)
        _assert_no_forbidden_content_keys(body)

    event_body = _assert_response_contract(events, 200)
    assert isinstance(event_body, list)
    _assert_no_forbidden_content_keys(event_body)


def test_artifact_summary_response_excludes_full_content_and_raw_content(tmp_path):
    app = create_http_app(tmp_path)
    _, run_id = _create_run(app)
    _successful_json(_request(app, "POST", f"/runs/{run_id}/input", {"text": "hello"}))
    run_state = _successful_json(_request(app, "GET", f"/runs/{run_id}"))
    artifact_id = run_state["artifacts"][0]["ref"]["artifact_id"]

    summary = _successful_json(_request(app, "GET", f"/artifacts/{artifact_id}/summary"))

    assert set(summary) == {"ref", "artifact_type", "summary", "provenance"}
    assert summary["summary"] == "hello artifact"
    _assert_no_forbidden_content_keys(summary)
    _assert_no_internal_repr(summary)


def test_invalid_request_contract_has_no_event_action_or_artifact_side_effects(tmp_path):
    app = create_http_app(tmp_path)
    _, run_id = _create_run(app)

    response = _request(app, "POST", f"/runs/{run_id}/input", {"text": ""})

    _assert_error_response(response, 400, "bad_request")
    assert not ACTION_LIFECYCLE_EVENTS.intersection(_event_types(tmp_path, run_id))
    assert _artifact_files(tmp_path) == []
