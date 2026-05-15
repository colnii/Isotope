import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from isotope.interfaces.http import create_http_app


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


def _create_completed_run(app) -> tuple[str, str]:
    session = _successful_json(_request(app, "POST", "/sessions"))
    run = _successful_json(
        _request(
            app,
            "POST",
            f"/sessions/{session['session_id']}/runs",
            {"goal": "produce a hello artifact"},
        )
    )
    _successful_json(_request(app, "POST", f"/runs/{run['run_id']}/input", {"text": "hello"}))
    state = _successful_json(_request(app, "GET", f"/runs/{run['run_id']}"))
    artifact_id = state["artifacts"][0]["ref"]["artifact_id"]
    return run["run_id"], artifact_id


def _event_types(root: Path, run_id: str | None = None) -> list[str]:
    event_types: list[str] = []
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
                event_types.append(str(json.loads(line)["event_type"]))
    return event_types


def _artifact_files(root: Path) -> list[Path]:
    return sorted(root.glob("runs/*/artifacts/*.json"))


def test_http_artifact_summary_route_stays_summary_only(tmp_path):
    app = create_http_app(tmp_path)
    _, artifact_id = _create_completed_run(app)

    response = _request(app, "GET", f"/artifacts/{artifact_id}/summary")

    assert _status_code(response) == 200
    body = _json_body(response)
    assert set(body) == {"ref", "artifact_type", "summary", "provenance"}
    assert body["summary"] == "hello artifact"
    _assert_no_forbidden_content_keys(body)


def test_http_artifact_content_route_is_still_not_enabled(tmp_path):
    app = create_http_app(tmp_path)
    _, artifact_id = _create_completed_run(app)

    response = _request(app, "GET", f"/artifacts/{artifact_id}/content")

    assert _status_code(response) == 501
    body = _json_body(response)
    assert body["status"] == "not_enabled"
    assert body["error"]["code"] == "not_enabled"
    assert body["error"]["capability"] == "artifact_content"
    _assert_no_forbidden_content_keys(body)


def test_http_artifact_content_route_does_not_read_content(tmp_path, monkeypatch):
    app = create_http_app(tmp_path)
    _, artifact_id = _create_completed_run(app)

    def fail_on_content_read(*args, **kwargs):
        raise AssertionError("HTTP content route must not read full artifact content while deferred")

    monkeypatch.setattr(app.server.artifact_store, "get_content", fail_on_content_read)

    response = _request(app, "GET", f"/artifacts/{artifact_id}/content")

    assert _status_code(response) == 501
    assert _json_body(response)["error"]["capability"] == "artifact_content"


def test_http_artifact_content_route_has_no_side_effects(tmp_path):
    app = create_http_app(tmp_path)
    run_id, artifact_id = _create_completed_run(app)
    before_events = _event_types(tmp_path, run_id)
    before_artifacts = _artifact_files(tmp_path)

    response = _request(app, "GET", f"/artifacts/{artifact_id}/content")

    assert _status_code(response) == 501
    assert _event_types(tmp_path, run_id) == before_events
    assert _artifact_files(tmp_path) == before_artifacts


@pytest.mark.parametrize(
    "path",
    [
        "/artifacts/artifact://run_001/artifact_001/content",
        "/artifacts/artifact%3A%2F%2Frun_001%2Fartifact_001/content",
    ],
)
def test_uri_string_cannot_bypass_resource_ref_boundary(tmp_path, path):
    app = create_http_app(tmp_path)

    response = _request(app, "GET", path)

    assert _status_code(response) in {404, 501}
    body = _json_body(response)
    assert body["status"] in {"not_found", "not_enabled"}
    _assert_no_forbidden_content_keys(body)
    assert _event_types(tmp_path) == []


def test_route_inventory_does_not_mark_full_content_as_supported(tmp_path):
    app = create_http_app(tmp_path)

    inventory = app.list_routes()

    for route in inventory["routes"]:
        if route["path"] == "/artifacts/{artifact_id}/content":
            assert route["status"] == "deferred"
        else:
            assert route["status"] == "supported"
    supported_paths = {
        route["path"] for route in inventory["routes"] if route["status"] == "supported"
    }
    assert "/artifacts/{artifact_id}/content" not in supported_paths


def test_deferred_artifact_content_error_shape_is_stable(tmp_path):
    app = create_http_app(tmp_path)

    response = _request(app, "GET", "/artifacts/artifact_001/content")

    assert _status_code(response) == 501
    assert _json_body(response) == {
        "status": "not_enabled",
        "error": {
            "code": "not_enabled",
            "message": "artifact_content is not enabled",
            "capability": "artifact_content",
            "category": "not_enabled",
            "retryable": False,
            "details": {"capability": "artifact_content"},
        },
    }
