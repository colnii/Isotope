import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from isotope.http_api import create_http_app


ACTION_LIFECYCLE_EVENTS = {
    "action.proposed",
    "action.decided",
    "action.started",
    "artifact.created",
    "action.completed",
    "action.failed",
    "run.completed",
}

DEFERRED_ENDPOINTS = [
    ("GET", "/memory/query"),
    ("POST", "/memory/query"),
    ("POST", "/external-ingestion"),
    ("POST", "/ingest"),
    ("POST", "/runs/run_001/approvals"),
    ("GET", "/runs/run_001/events/stream"),
    ("GET", "/stream"),
    ("GET", "/artifacts/artifact_001/content"),
]


def _request(app, method: str, path: str, json_body: Any = None):
    return app.request(method, path, json=json_body)


def _status_code(response) -> int:
    if isinstance(response, Mapping):
        return int(response["status_code"])
    return int(response.status_code)


def _json_body(response) -> dict[str, Any]:
    if isinstance(response, Mapping):
        body = response.get("json", response.get("body"))
    elif callable(getattr(response, "json", None)):
        body = response.json()
    else:
        body = getattr(response, "body", None)
    assert isinstance(body, dict)
    return body


def _successful_json(response) -> dict[str, Any]:
    assert 200 <= _status_code(response) < 300
    return _json_body(response)


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
    events: list[str] = []
    paths: list[Path]
    if run_id is None:
        paths = sorted(root.glob("runs/*/events.jsonl"))
    else:
        paths = [root / "runs" / run_id / "events.jsonl"]
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(str(json.loads(line)["event_type"]))
    return events


def _artifact_files(root: Path) -> list[Path]:
    return sorted(root.glob("runs/*/artifacts/*.json"))


def test_unsupported_route_returns_controlled_404_without_events(tmp_path):
    app = create_http_app(tmp_path)

    response = _request(app, "POST", "/not-a-real-route", {"anything": "ignored"})

    assert _status_code(response) == 404
    assert _json_body(response)["status"] == "not_found"
    assert _event_types(tmp_path) == []


def test_method_mismatch_returns_controlled_405_without_events(tmp_path):
    app = create_http_app(tmp_path)

    response = _request(app, "GET", "/sessions")

    assert _status_code(response) == 405
    assert _json_body(response)["status"] == "method_not_allowed"
    assert _event_types(tmp_path) == []


@pytest.mark.parametrize("body", [None, {}, "not a dict"])
def test_create_run_rejects_malformed_or_missing_body_without_events(tmp_path, body):
    app = create_http_app(tmp_path)
    session = _successful_json(_request(app, "POST", "/sessions"))

    response = _request(app, "POST", f"/sessions/{session['session_id']}/runs", body)

    assert _status_code(response) == 400
    assert _json_body(response)["status"] == "bad_request"
    assert _event_types(tmp_path) == ["session.created"]


def test_create_run_unknown_session_returns_404_without_creating_run(tmp_path):
    app = create_http_app(tmp_path)

    response = _request(
        app,
        "POST",
        "/sessions/session_missing/runs",
        {"goal": "produce a hello artifact"},
    )

    assert _status_code(response) == 404
    assert _json_body(response)["status"] == "not_found"
    assert _event_types(tmp_path) == []


def test_submit_input_unknown_run_returns_404_without_events_or_artifacts(tmp_path):
    app = create_http_app(tmp_path)

    response = _request(app, "POST", "/runs/run_missing/input", {"text": "hello"})

    assert _status_code(response) == 404
    assert _json_body(response)["status"] == "not_found"
    assert _event_types(tmp_path) == []
    assert _artifact_files(tmp_path) == []


@pytest.mark.parametrize("body", [None, {}, {"text": ""}, {"text": 123}])
def test_submit_input_rejects_missing_non_string_or_empty_text_without_action_events(
    tmp_path,
    body,
):
    app = create_http_app(tmp_path)
    _, run_id = _create_run(app)

    response = _request(app, "POST", f"/runs/{run_id}/input", body)

    assert _status_code(response) == 400
    assert _json_body(response)["status"] == "bad_request"
    assert not ACTION_LIFECYCLE_EVENTS.intersection(_event_types(tmp_path, run_id))
    assert _artifact_files(tmp_path) == []


def test_get_unknown_run_returns_404_without_creating_projected_state(tmp_path):
    app = create_http_app(tmp_path)

    response = _request(app, "GET", "/runs/run_missing")

    assert _status_code(response) == 404
    assert _json_body(response)["status"] == "not_found"
    assert _event_types(tmp_path) == []


def test_get_unknown_run_events_returns_404_without_projector_side_effects(tmp_path):
    app = create_http_app(tmp_path)

    response = _request(app, "GET", "/runs/run_missing/events")

    assert _status_code(response) == 404
    assert _json_body(response)["status"] == "not_found"
    assert _event_types(tmp_path) == []


def test_unknown_artifact_summary_returns_404_without_reading_full_content(
    tmp_path,
    monkeypatch,
):
    app = create_http_app(tmp_path)

    def fail_on_content_read(*args, **kwargs):
        raise AssertionError("artifact summary lookup must not read full content")

    monkeypatch.setattr(app.server.artifact_store, "get_content", fail_on_content_read)

    response = _request(app, "GET", "/artifacts/artifact_missing/summary")

    assert _status_code(response) == 404
    assert _json_body(response)["status"] == "not_found"


@pytest.mark.parametrize(("method", "path"), DEFERRED_ENDPOINTS)
def test_deferred_routes_remain_absent_or_not_enabled_without_events(
    tmp_path,
    method,
    path,
):
    app = create_http_app(tmp_path)

    response = _request(app, method, path, {"text": "ignored"})

    assert _status_code(response) in {404, 405, 501}
    body = _json_body(response)
    assert body.get("status") in {"not_found", "method_not_allowed", "not_enabled"}
    assert _event_types(tmp_path) == []
