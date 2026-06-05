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


def _successful_json(response) -> dict[str, Any]:
    assert 200 <= _status_code(response) < 300
    return _body(response)


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
        "purpose": "test artifact content retrieval",
    }


def test_default_artifact_content_route_returns_full_content(tmp_path):
    app = create_http_app(tmp_path)
    _, artifact_id, artifact_ref = _create_completed_run(app)

    response = _request(
        app,
        "GET",
        f"/artifacts/{artifact_id}/content",
        _content_request_body(artifact_ref),
    )

    body = _successful_json(response)
    assert body["status"] == "ok"
    assert body["view"] == "full"
    assert body["content"] == "hello"
    assert body["ref"] == artifact_ref


def test_artifact_content_route_can_infer_ref_from_artifact_id(tmp_path):
    app = create_http_app(tmp_path)
    _, artifact_id, _ = _create_completed_run(app)

    response = _request(app, "GET", f"/artifacts/{artifact_id}/content")

    body = _successful_json(response)
    assert body["status"] == "ok"
    assert body["content"] == "hello"


def test_artifact_content_route_rejects_raw_id_or_uri_string_refs(tmp_path):
    app = create_http_app(tmp_path)
    run_id, artifact_id, _ = _create_completed_run(app)

    for ref in ("artifact://run_001/artifact_001", "artifact_001"):
        response = _request(
            app,
            "GET",
            f"/artifacts/{artifact_id}/content",
            {
                "ref": ref,
                "grants": {"artifact": {"read": "full"}},
                "caller_context": {"caller": "http_api_test", "run_id": run_id},
                "purpose": "test artifact content retrieval",
            },
        )

        assert _status_code(response) == 400
        assert _body(response)["error"]["capability"] == "artifact_content"


def test_artifact_content_route_requires_matching_ref(tmp_path):
    app = create_http_app(tmp_path)
    run_id, artifact_id, artifact_ref = _create_completed_run(app)
    mismatched_ref = {**artifact_ref, "artifact_id": "artifact_other"}

    response = _request(
        app,
        "GET",
        f"/artifacts/{artifact_id}/content",
        {
            "ref": mismatched_ref,
            "grants": {"artifact": {"read": "full"}},
            "caller_context": {"caller": "http_api_test", "run_id": run_id},
            "purpose": "test artifact content retrieval",
        },
    )

    assert _status_code(response) == 400
    assert _body(response)["error"]["code"] == "bad_request"


def test_artifact_content_route_enforces_full_read_grant(tmp_path):
    app = create_http_app(tmp_path)
    _, artifact_id, artifact_ref = _create_completed_run(app)

    response = _request(
        app,
        "GET",
        f"/artifacts/{artifact_id}/content",
        {
            "ref": artifact_ref,
            "grants": {"artifact": {"read": "summary"}},
            "caller_context": {"caller": "http_api_test", "run_id": artifact_ref["run_id"]},
            "purpose": "test artifact content retrieval",
        },
    )

    assert _status_code(response) == 403
    assert _body(response)["error"]["capability"] == "artifact_content"
