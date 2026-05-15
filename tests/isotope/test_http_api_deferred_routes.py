import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from isotope.interfaces.http import create_http_app


DEFERRED_ROUTES = [
    ("POST", "/runs/run_001/memory/query", "memory_query"),
    ("POST", "/external-ingestion", "external_ingestion"),
    ("GET", "/runs/run_001/events/stream", "sse_stream"),
    ("POST", "/runs/run_001/approvals", "approval_api"),
    ("GET", "/artifacts/artifact_001/content", "artifact_content"),
]


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


def _event_types(root: Path) -> list[str]:
    event_types: list[str] = []
    for path in sorted(root.glob("runs/*/events.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                event_types.append(str(json.loads(line)["event_type"]))
    return event_types


def _artifact_files(root: Path) -> list[Path]:
    return sorted(root.glob("runs/*/artifacts/*.json"))


@pytest.mark.parametrize(("method", "path", "capability"), DEFERRED_ROUTES)
def test_deferred_routes_return_stable_not_enabled_response(
    tmp_path,
    method,
    path,
    capability,
):
    app = create_http_app(tmp_path)

    response = _request(app, method, path, {"text": "ignored"})

    assert _status_code(response) == 501
    body = _body(response)
    assert body["status"] == "not_enabled"
    assert body["error"]["code"] == "not_enabled"
    assert body["error"]["capability"] == capability


@pytest.mark.parametrize(("method", "path", "capability"), DEFERRED_ROUTES)
def test_deferred_routes_do_not_create_events_actions_or_artifacts(
    tmp_path,
    method,
    path,
    capability,
):
    app = create_http_app(tmp_path)

    response = _request(app, method, path, {"text": "ignored", "idempotency_key": "ignored"})

    assert _status_code(response) == 501
    assert _body(response)["error"]["capability"] == capability
    assert _event_types(tmp_path) == []
    assert _artifact_files(tmp_path) == []


def test_full_artifact_content_route_does_not_read_artifact_content(tmp_path, monkeypatch):
    app = create_http_app(tmp_path)

    def fail_on_content_read(*args, **kwargs):
        raise AssertionError("deferred content route must not read full artifact content")

    monkeypatch.setattr(app.server.artifact_store, "get_content", fail_on_content_read)

    response = _request(app, "GET", "/artifacts/artifact_001/content")

    assert _status_code(response) == 501
    assert _body(response)["error"]["capability"] == "artifact_content"


def test_deferred_routes_are_not_listed_as_supported_inventory(tmp_path):
    app = create_http_app(tmp_path)
    inventory = app.list_routes()

    for route in inventory["routes"]:
        if route["path"] in {
            "/runs/{run_id}/memory/query",
            "/external-ingestion",
            "/runs/{run_id}/events/stream",
            "/runs/{run_id}/approvals",
            "/artifacts/{artifact_id}/content",
        }:
            assert route["status"] == "deferred"
        else:
            assert route["status"] == "supported"
