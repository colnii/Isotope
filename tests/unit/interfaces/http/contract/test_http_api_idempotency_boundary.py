import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from isotope.interfaces.http import create_http_app


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


def _body(response) -> dict[str, Any] | list[dict[str, Any]]:
    if isinstance(response, Mapping):
        body = response.get("json", response.get("body"))
    elif callable(getattr(response, "json", None)):
        body = response.json()
    else:
        body = getattr(response, "body", None)
    assert isinstance(body, (dict, list))
    return body


def _json_body(response) -> dict[str, Any]:
    body = _body(response)
    assert isinstance(body, dict)
    return body


def _successful_json(response) -> dict[str, Any]:
    assert 200 <= _status_code(response) < 300
    return _json_body(response)


def _error_code(response) -> str:
    body = _json_body(response)
    assert isinstance(body["error"], dict)
    return str(body["error"]["code"])


def _create_run(app, session_id: str | None = None, key: str | None = None) -> dict[str, Any]:
    if session_id is None:
        session_id = _successful_json(_request(app, "POST", "/sessions"))["session_id"]
    body = {"goal": "produce a hello artifact"}
    if key is not None:
        body["idempotency_key"] = key
    return _successful_json(_request(app, "POST", f"/sessions/{session_id}/runs", body))


def _event_dicts(root: Path, run_id: str | None = None) -> list[dict[str, Any]]:
    paths = (
        [root / "runs" / run_id / "events.jsonl"]
        if run_id is not None
        else sorted(root.glob("runs/*/events.jsonl"))
    )
    events: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
    return events


def _event_types(root: Path, run_id: str | None = None) -> list[str]:
    return [str(event["event_type"]) for event in _event_dicts(root, run_id)]


def _artifact_files(root: Path) -> list[Path]:
    return sorted(root.glob("runs/*/artifacts/*.json"))


def test_post_sessions_without_idempotency_key_creates_new_session_each_time(tmp_path):
    app = create_http_app(tmp_path)

    first = _successful_json(_request(app, "POST", "/sessions"))
    second = _successful_json(_request(app, "POST", "/sessions"))

    assert first["session_id"] != second["session_id"]
    assert len(app.server._sessions) == 2


def test_post_sessions_with_same_idempotency_key_replays_same_session_without_duplicate(
    tmp_path,
):
    app = create_http_app(tmp_path)

    first = _successful_json(
        _request(app, "POST", "/sessions", {"idempotency_key": "session-key"})
    )
    second = _successful_json(
        _request(app, "POST", "/sessions", {"idempotency_key": "session-key"})
    )

    assert second == first
    assert len(app.server._sessions) == 1
    assert _event_types(tmp_path) == ["session.created"]


def test_create_run_with_same_idempotency_key_replays_same_run_without_duplicate_events(
    tmp_path,
):
    app = create_http_app(tmp_path)
    session = _successful_json(_request(app, "POST", "/sessions"))

    first = _create_run(app, session["session_id"], key="run-key")
    second = _create_run(app, session["session_id"], key="run-key")

    assert second == first
    assert len(app.server._runs) == 1
    assert _event_types(tmp_path, first["run_id"]) == [
        "run.created",
        "agent.created",
        "thread.created",
    ]


def test_submit_input_with_same_idempotency_key_replays_same_result_without_duplicate_action_or_artifact(
    tmp_path,
):
    app = create_http_app(tmp_path)
    run = _create_run(app)

    first = _successful_json(
        _request(
            app,
            "POST",
            f"/runs/{run['run_id']}/input",
            {"text": "hello", "idempotency_key": "input-key"},
        )
    )
    second = _successful_json(
        _request(
            app,
            "POST",
            f"/runs/{run['run_id']}/input",
            {"text": "hello", "idempotency_key": "input-key"},
        )
    )

    assert second == first
    assert _event_types(tmp_path, run["run_id"]) == [
        "run.created",
        "agent.created",
        "thread.created",
        "action.proposed",
        "action.decided",
        "action.started",
        "artifact.created",
        "action.completed",
        "run.completed",
    ]
    assert len(_artifact_files(tmp_path)) == 1


def test_idempotency_key_cannot_be_reused_across_different_method_or_path(tmp_path):
    app = create_http_app(tmp_path)
    session = _successful_json(
        _request(app, "POST", "/sessions", {"idempotency_key": "shared-key"})
    )

    response = _request(
        app,
        "POST",
        f"/sessions/{session['session_id']}/runs",
        {"goal": "produce a hello artifact", "idempotency_key": "shared-key"},
    )

    assert _status_code(response) == 409
    assert _error_code(response) == "idempotency_conflict"
    assert len(app.server._runs) == 0
    assert _event_types(tmp_path) == ["session.created"]


def test_idempotency_key_with_different_body_returns_conflict_without_second_side_effect(
    tmp_path,
):
    app = create_http_app(tmp_path)
    session = _successful_json(_request(app, "POST", "/sessions"))

    first = _create_run(app, session["session_id"], key="body-key")
    response = _request(
        app,
        "POST",
        f"/sessions/{session['session_id']}/runs",
        {"goal": "different goal", "idempotency_key": "body-key"},
    )

    assert _status_code(response) == 409
    assert _error_code(response) == "idempotency_conflict"
    assert len(app.server._runs) == 1
    assert _event_types(tmp_path, first["run_id"]) == [
        "run.created",
        "agent.created",
        "thread.created",
    ]


def test_idempotency_key_stays_out_of_canonical_events(tmp_path):
    app = create_http_app(tmp_path)
    session = _successful_json(
        _request(app, "POST", "/sessions", {"idempotency_key": "session-event-key"})
    )
    run = _create_run(app, session["session_id"], key="run-event-key")
    _successful_json(
        _request(
            app,
            "POST",
            f"/runs/{run['run_id']}/input",
            {"text": "hello", "idempotency_key": "input-event-key"},
        )
    )

    event_text = json.dumps(_event_dicts(tmp_path, run["run_id"]), sort_keys=True)

    assert "idempotency_key" not in event_text
    assert "session-event-key" not in event_text
    assert "run-event-key" not in event_text
    assert "input-event-key" not in event_text


def test_idempotency_cache_is_in_memory_per_http_app_instance(tmp_path):
    first_app = create_http_app(tmp_path)
    first = _successful_json(
        _request(first_app, "POST", "/sessions", {"idempotency_key": "restart-key"})
    )
    replayed = _successful_json(
        _request(first_app, "POST", "/sessions", {"idempotency_key": "restart-key"})
    )

    second_app = create_http_app(tmp_path)
    after_restart = _successful_json(
        _request(second_app, "POST", "/sessions", {"idempotency_key": "restart-key"})
    )

    assert replayed == first
    assert after_restart != first
    assert len(first_app.server._sessions) == 1
    assert len(second_app.server._sessions) == 1


def test_error_response_is_not_cached_as_success_for_later_valid_retry(tmp_path):
    app = create_http_app(tmp_path)
    run = _create_run(app)

    bad = _request(
        app,
        "POST",
        f"/runs/{run['run_id']}/input",
        {"text": "", "idempotency_key": "retry-key"},
    )
    good = _request(
        app,
        "POST",
        f"/runs/{run['run_id']}/input",
        {"text": "hello", "idempotency_key": "retry-key"},
    )

    assert _status_code(bad) == 400
    assert _error_code(bad) == "invalid_request"
    assert _status_code(good) == 200
    assert _json_body(good)["status"] == "completed"
    assert _event_types(tmp_path, run["run_id"]) == [
        "run.created",
        "agent.created",
        "thread.created",
        "action.proposed",
        "action.decided",
        "action.started",
        "artifact.created",
        "action.completed",
        "run.completed",
    ]


def test_malformed_idempotent_request_remains_error_without_side_effect_on_each_retry(
    tmp_path,
):
    app = create_http_app(tmp_path)
    run = _create_run(app)

    first = _request(
        app,
        "POST",
        f"/runs/{run['run_id']}/input",
        {"text": "", "idempotency_key": "bad-key"},
    )
    second = _request(
        app,
        "POST",
        f"/runs/{run['run_id']}/input",
        {"text": "", "idempotency_key": "bad-key"},
    )

    assert _status_code(first) == 400
    assert _status_code(second) == 400
    assert _error_code(first) == "invalid_request"
    assert _error_code(second) == "invalid_request"
    assert not ACTION_LIFECYCLE_EVENTS.intersection(_event_types(tmp_path, run["run_id"]))
    assert _artifact_files(tmp_path) == []

