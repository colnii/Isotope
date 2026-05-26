import inspect
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

import isotope.demo as demo
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


def _body(response) -> dict[str, Any]:
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
    return _body(response)


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        assert FORBIDDEN_CONTENT_KEYS.isdisjoint(value)
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def _create_completed_run(app) -> tuple[str, str, dict[str, Any]]:
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
    artifact_ref = state["artifacts"][0]["ref"]
    return run["run_id"], artifact_ref["artifact_id"], artifact_ref


def _content_request_body(ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref": ref,
        "grants": {"artifact": {"read": "full"}},
        "caller_context": {"caller": "http_api_test", "run_id": ref["run_id"]},
        "purpose": "test controlled artifact content retrieval",
    }


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


def test_create_http_app_exposes_disabled_artifact_content_guard_by_default():
    signature = inspect.signature(create_http_app)

    assert "allow_artifact_content" in signature.parameters
    assert signature.parameters["allow_artifact_content"].default is False


def test_default_full_content_route_stays_not_enabled_even_with_auth_shape(
    tmp_path,
    monkeypatch,
):
    app = create_http_app(tmp_path)
    assert app.allow_artifact_content is False
    run_id, artifact_id, artifact_ref = _create_completed_run(app)
    before_events = _event_types(tmp_path, run_id)
    before_artifacts = _artifact_files(tmp_path)

    def fail_on_content_read(*args, **kwargs):
        raise AssertionError("default HTTP content route must not read full artifact content")

    monkeypatch.setattr(app.server.artifact_store, "get_content", fail_on_content_read)

    response = _request(
        app,
        "GET",
        f"/artifacts/{artifact_id}/content",
        _content_request_body(artifact_ref),
    )

    assert _status_code(response) == 501
    body = _body(response)
    assert body["status"] == "not_enabled"
    assert body["error"]["capability"] == "artifact_content"
    _assert_no_forbidden_content_keys(body)
    assert _event_types(tmp_path, run_id) == before_events
    assert _artifact_files(tmp_path) == before_artifacts


def test_enabled_flag_without_retrieval_wiring_fails_closed(tmp_path, monkeypatch):
    app = create_http_app(tmp_path, allow_artifact_content=True)
    assert app.allow_artifact_content is True
    run_id, artifact_id, artifact_ref = _create_completed_run(app)
    before_events = _event_types(tmp_path, run_id)
    before_artifacts = _artifact_files(tmp_path)

    def fail_on_content_read(*args, **kwargs):
        raise AssertionError("unwired content route must not read full artifact content")

    monkeypatch.setattr(app.server.artifact_store, "get_content", fail_on_content_read)

    response = _request(
        app,
        "GET",
        f"/artifacts/{artifact_id}/content",
        _content_request_body(artifact_ref),
    )

    assert _status_code(response) in {501, 403}
    body = _body(response)
    assert body["status"] in {"not_enabled", "forbidden"}
    assert body["error"]["capability"] == "artifact_content"
    _assert_no_forbidden_content_keys(body)
    assert _event_types(tmp_path, run_id) == before_events
    assert _artifact_files(tmp_path) == before_artifacts


@pytest.mark.parametrize(
    "json_body",
    [
        None,
        {},
        {"grants": {"artifact": {"read": "full"}}},
        {"caller_context": {"caller": "http_api_test"}, "purpose": "test"},
    ],
)
def test_enabled_flag_without_required_request_context_fails_closed(
    tmp_path,
    monkeypatch,
    json_body,
):
    app = create_http_app(tmp_path, allow_artifact_content=True)
    run_id, artifact_id, _ = _create_completed_run(app)
    before_events = _event_types(tmp_path, run_id)

    def fail_on_content_read(*args, **kwargs):
        raise AssertionError("bad content route request must not read full artifact content")

    monkeypatch.setattr(app.server.artifact_store, "get_content", fail_on_content_read)

    response = _request(app, "GET", f"/artifacts/{artifact_id}/content", json_body)

    assert _status_code(response) in {400, 403, 501}
    assert _body(response)["error"]["capability"] == "artifact_content"
    assert _event_types(tmp_path, run_id) == before_events


@pytest.mark.parametrize(
    "ref",
    [
        "artifact://run_001/artifact_001",
        "artifact_001",
        {"ref_type": "artifact", "artifact_id": "artifact_001"},
    ],
)
def test_enabled_flag_does_not_allow_raw_id_or_uri_string_to_bypass_ref_boundary(
    tmp_path,
    monkeypatch,
    ref,
):
    app = create_http_app(tmp_path, allow_artifact_content=True)
    run_id, artifact_id, _ = _create_completed_run(app)

    def fail_on_content_read(*args, **kwargs):
        raise AssertionError("raw id / URI ref must not read full artifact content")

    monkeypatch.setattr(app.server.artifact_store, "get_content", fail_on_content_read)

    response = _request(
        app,
        "GET",
        f"/artifacts/{artifact_id}/content",
        {
            "ref": ref,
            "grants": {"artifact": {"read": "full"}},
            "caller_context": {"caller": "http_api_test", "run_id": run_id},
            "purpose": "test controlled artifact content retrieval",
        },
    )

    assert _status_code(response) in {400, 403, 501}
    _assert_no_forbidden_content_keys(_body(response))


def test_route_inventory_keeps_artifact_content_deferred_under_default_and_enabled_flag(tmp_path):
    for app in (
        create_http_app(tmp_path / "default"),
        create_http_app(tmp_path / "enabled", allow_artifact_content=True),
    ):
        inventory = app.list_routes()
        supported = {
            route["path"] for route in inventory["routes"] if route["status"] == "supported"
        }
        assert "/artifacts/{artifact_id}/content" not in supported
        content_routes = [
            route for route in inventory["routes"] if route["path"] == "/artifacts/{artifact_id}/content"
        ]
        assert content_routes == [] or all(route["status"] == "deferred" for route in content_routes)


def test_artifact_content_error_response_shape_remains_stable_with_guard(tmp_path):
    app = create_http_app(tmp_path, allow_artifact_content=True)

    response = _request(app, "GET", "/artifacts/artifact_001/content")

    assert _status_code(response) in {501, 403}
    body = _body(response)
    assert set(body) == {"status", "error"}
    assert body["error"]["code"] in {"not_enabled", "forbidden", "bad_request"}
    assert body["error"]["capability"] == "artifact_content"
    _assert_no_forbidden_content_keys(body)


def test_demo_output_does_not_imply_artifact_content_is_available(tmp_path):
    result = demo.run_demo(tmp_path)

    assert "artifact_summary" in result
    assert "artifact_ref" in result
    _assert_no_forbidden_content_keys(result)
    assert "artifact_content_status" not in result
