from isotope.interfaces.http import create_http_app


def _request(app, method: str, path: str, body=None):
    return app.request(method, path, json=body)


def _body(response):
    return response.json()


def _create_completed_run(app):
    session = _body(_request(app, "POST", "/sessions"))
    run = _body(
        _request(
            app,
            "POST",
            f"/sessions/{session['session_id']}/runs",
            {"goal": "produce a hello artifact"},
        )
    )
    _request(app, "POST", f"/runs/{run['run_id']}/input", {"text": "hello"})
    return run["run_id"]


def test_terminal_run_http_error_maps_isotope_error_without_breaking_envelope(tmp_path):
    app = create_http_app(tmp_path)
    run_id = _create_completed_run(app)

    response = _request(app, "POST", f"/runs/{run_id}/input", {"text": "second"})
    body = _body(response)

    assert response.status_code == 409
    assert body["status"] == "conflict"
    assert body["error"]["code"] == "run_terminal"
    assert body["error"]["message"] == "run is terminal: completed"
    assert body["error"]["category"] == "conflict"
    assert body["error"]["retryable"] is False
    assert body["error"]["details"] == {"run_id": run_id, "status": "completed"}


def test_unknown_run_http_error_uses_stable_kernel_code(tmp_path):
    app = create_http_app(tmp_path)

    response = _request(app, "POST", "/runs/run_missing/input", {"text": "hello"})
    body = _body(response)

    assert response.status_code == 404
    assert body["status"] == "not_found"
    assert body["error"]["code"] == "unknown_run"
    assert body["error"]["message"] == "run not found"
    assert body["error"]["category"] == "not_found"
    assert body["error"]["retryable"] is False
    assert body["error"]["details"] == {"run_id": "run_missing"}


def test_unknown_session_http_error_uses_stable_kernel_code(tmp_path):
    app = create_http_app(tmp_path)

    response = _request(
        app,
        "POST",
        "/sessions/session_missing/runs",
        {"goal": "produce a hello artifact"},
    )
    body = _body(response)

    assert response.status_code == 404
    assert body["status"] == "not_found"
    assert body["error"]["code"] == "unknown_session"
    assert body["error"]["message"] == "session not found"
    assert body["error"]["category"] == "not_found"
    assert body["error"]["retryable"] is False
    assert body["error"]["details"] == {"session_id": "session_missing"}


def test_invalid_request_http_error_uses_stable_kernel_code(tmp_path):
    app = create_http_app(tmp_path)
    session = _body(_request(app, "POST", "/sessions"))

    response = _request(app, "POST", f"/sessions/{session['session_id']}/runs", {})
    body = _body(response)

    assert response.status_code == 400
    assert body["status"] == "bad_request"
    assert body["error"]["code"] == "invalid_request"
    assert body["error"]["message"] == "missing required request field: goal"
    assert body["error"]["category"] == "validation"
    assert body["error"]["retryable"] is False
    assert body["error"]["details"] == {"field": "goal"}


def test_external_ingestion_bad_request_includes_stable_taxonomy_metadata(tmp_path):
    app = create_http_app(tmp_path)

    response = _request(app, "POST", "/external-ingestion", {"payload": "raw"})
    body = _body(response)

    assert response.status_code == 400
    assert body["status"] == "bad_request"
    assert body["error"]["code"] == "invalid_request"
    assert body["error"]["message"] == "external input must include run_id"
    assert body["error"]["category"] == "validation"
    assert body["error"]["retryable"] is False
    assert body["error"]["details"] == {"field": "run_id"}
