import importlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest


MINIMAL_ROUTES = {
    ("POST", "/tasks"),
    ("GET", "/tasks"),
    ("GET", "/tasks/{task_id}"),
    ("POST", "/files"),
    ("GET", "/files"),
    ("GET", "/files/{file_id}"),
    ("POST", "/projects"),
    ("GET", "/projects"),
    ("GET", "/projects/{project_id}"),
    ("GET", "/projects/{project_id}/detail"),
    ("POST", "/projects/{project_id}/tasks"),
    ("POST", "/projects/{project_id}/files"),
    ("POST", "/search"),
    ("GET", "/workbench"),
    ("POST", "/workbench"),
    ("POST", "/sessions"),
    ("POST", "/sessions/{session_id}/runs"),
    ("POST", "/runs/{run_id}/input"),
    ("POST", "/runs/{run_id}/agent-loop-step"),
    ("POST", "/runs/{run_id}/agent-loop-planner-step"),
    ("GET", "/runs/{run_id}"),
    ("GET", "/runs/{run_id}/agent-loop-control"),
    ("GET", "/runs/{run_id}/agent-loop-tick-policy"),
    ("GET", "/runs/{run_id}/events"),
    ("GET", "/artifacts/{artifact_id}/summary"),
    ("GET", "/health"),
}

DEFERRED_ENDPOINTS = [
    ("GET", "/memory/query"),
    ("POST", "/memory/query"),
    ("POST", "/ingest"),
    ("POST", "/external-ingestion"),
    ("POST", "/runs/run_001/approvals"),
    ("GET", "/runs/run_001/events/stream"),
    ("GET", "/stream"),
    ("GET", "/artifacts/artifact_001/content"),
]

FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
}

TASK_FORBIDDEN_CONTENT_KEYS = {
    *FORBIDDEN_CONTENT_KEYS,
    "text",
}


def _http_api_module():
    return importlib.import_module("isotope.interfaces.http")


def _create_app(tmp_path: Path):
    module = _http_api_module()
    assert hasattr(module, "create_http_app"), "http_api must expose create_http_app(...)"
    return module.create_http_app(root_path=tmp_path)


def _routes(app) -> set[tuple[str, str]]:
    assert hasattr(app, "routes"), "HTTP app must expose routes() for boundary inspection"
    routes = app.routes()
    return {
        (str(method).upper(), str(path))
        for method, path in routes
    }


def _request(app, method: str, path: str, json_body: dict[str, Any] | None = None):
    assert hasattr(app, "request"), "HTTP app must expose request(method, path, json=...)"
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
    assert isinstance(body, dict), "HTTP response body must be a JSON-like dict"
    return body


def _json_list(response) -> list[dict[str, Any]]:
    if isinstance(response, Mapping):
        body = response.get("json", response.get("body"))
    elif callable(getattr(response, "json", None)):
        body = response.json()
    else:
        body = getattr(response, "body", None)
    assert isinstance(body, list), "HTTP response body must be a JSON-like list"
    assert all(isinstance(item, dict) for item in body)
    return body


def _successful_json(response) -> dict[str, Any]:
    assert 200 <= _status_code(response) < 300
    return _json_body(response)


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_CONTENT_KEYS.intersection(value)
        assert forbidden == set()
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def _assert_no_task_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = TASK_FORBIDDEN_CONTENT_KEYS.intersection(value)
        assert forbidden == set()
        for nested in value.values():
            _assert_no_task_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_task_content_keys(nested)


def _create_run_via_http(app) -> tuple[str, str]:
    session = _successful_json(_request(app, "POST", "/sessions"))
    session_id = session["session_id"]
    run = _successful_json(
        _request(
            app,
            "POST",
            f"/sessions/{session_id}/runs",
            {"goal": "produce a hello artifact"},
        )
    )
    return session_id, run["run_id"]


def _submit_input_via_http(app, run_id: str) -> dict[str, Any]:
    return _successful_json(
        _request(app, "POST", f"/runs/{run_id}/input", {"text": "hello"})
    )


def _event_types(app, run_id: str) -> list[str]:
    events = _json_list(_request(app, "GET", f"/runs/{run_id}/events"))
    return [event["event_type"] for event in events]


def test_http_api_module_exists_for_v0_2_minimal_surface():
    _http_api_module()


def test_http_api_exposes_create_http_app_factory(tmp_path):
    _create_app(tmp_path)


def test_http_api_defines_only_minimal_v0_2_surface(tmp_path):
    app = _create_app(tmp_path)

    assert _routes(app) == MINIMAL_ROUTES


@pytest.mark.parametrize(("method", "path"), DEFERRED_ENDPOINTS)
def test_deferred_http_endpoints_are_absent_or_not_enabled(tmp_path, method, path):
    app = _create_app(tmp_path)

    response = _request(app, method, path)

    assert _status_code(response) in {404, 405, 501}
    body = _json_body(response)
    if body:
        assert body.get("status") in {None, "not_found", "not_enabled", "method_not_allowed"}


def test_http_api_cannot_directly_modify_projected_run_state(tmp_path):
    app = _create_app(tmp_path)
    _, run_id = _create_run_via_http(app)
    before = _successful_json(_request(app, "GET", f"/runs/{run_id}"))

    response = _request(
        app,
        "PUT",
        f"/runs/{run_id}",
        {"status": "completed", "artifacts": [{"summary": "forged"}]},
    )

    assert _status_code(response) in {404, 405, 501}
    after = _successful_json(_request(app, "GET", f"/runs/{run_id}"))
    assert after == before
    assert after.get("status") != "completed"


def test_submit_input_uses_action_chain_and_writes_canonical_events(tmp_path):
    app = _create_app(tmp_path)
    _, run_id = _create_run_via_http(app)

    result = _submit_input_via_http(app, run_id)

    assert result["status"] == "completed"
    event_types = _event_types(app, run_id)
    assert event_types == [
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


def test_http_api_tasks_route_creates_and_reads_task_summary(tmp_path):
    app = _create_app(tmp_path)

    created = _successful_json(
        _request(
            app,
            "POST",
            "/tasks",
            {
                "goal": "collect useful notes",
                "message": "first note",
            },
        )
    )
    task = created["task"]
    fetched = _successful_json(_request(app, "GET", f"/tasks/{task['task_id']}"))

    assert created["status"] == "ok"
    assert task["task_id"].startswith("task_")
    assert task["goal"] == "collect useful notes"
    assert task["status"] == "completed"
    assert task["turn_count"] == 1
    assert task["result_ref"]["ref_type"] == "artifact"
    assert fetched == {"status": "ok", "task": task}
    _assert_no_task_content_keys(created)


def test_http_api_tasks_route_lists_task_summaries(tmp_path):
    app = _create_app(tmp_path)

    created = _successful_json(
        _request(
            app,
            "POST",
            "/tasks",
            {
                "goal": "collect useful notes",
                "message": "first note",
            },
        )
    )
    listed = _successful_json(_request(app, "GET", "/tasks"))

    assert listed == {"status": "ok", "tasks": [created["task"]]}
    _assert_no_task_content_keys(listed)


def test_http_api_files_routes_create_get_and_list_file_summaries(tmp_path):
    app = _create_app(tmp_path)

    created = _successful_json(
        _request(
            app,
            "POST",
            "/files",
            {
                "name": "notes.md",
                "summary": "useful notes",
                "content": "private durable file content",
            },
        )
    )
    file_summary = created["file"]
    fetched = _successful_json(_request(app, "GET", f"/files/{file_summary['file_id']}"))
    listed = _successful_json(_request(app, "GET", "/files"))

    assert created["status"] == "ok"
    assert file_summary["file_id"].startswith("artifact_")
    assert file_summary["name"] == "notes.md"
    assert file_summary["summary"] == "useful notes"
    assert file_summary["artifact_ref"]["ref_type"] == "artifact"
    assert fetched == {"status": "ok", "file": file_summary}
    assert listed == {"status": "ok", "files": [file_summary]}
    _assert_no_task_content_keys(created)
    _assert_no_task_content_keys(fetched)
    _assert_no_task_content_keys(listed)


def test_http_api_projects_routes_create_get_list_and_link_summaries(tmp_path):
    app = _create_app(tmp_path)

    created = _successful_json(
        _request(
            app,
            "POST",
            "/projects",
            {
                "name": "portfolio demo",
                "summary": "autumn recruiting project",
            },
        )
    )
    project = created["project"]
    with_task = _successful_json(
        _request(app, "POST", f"/projects/{project['project_id']}/tasks", {"task_id": "task_example"})
    )
    with_file = _successful_json(
        _request(
            app,
            "POST",
            f"/projects/{project['project_id']}/files",
            {"file_id": "artifact_example"},
        )
    )
    fetched = _successful_json(_request(app, "GET", f"/projects/{project['project_id']}"))
    listed = _successful_json(_request(app, "GET", "/projects"))

    linked = with_file["project"]
    assert created["status"] == "ok"
    assert project["project_id"].startswith("project_")
    assert project["name"] == "portfolio demo"
    assert project["summary"] == "autumn recruiting project"
    assert with_task["project"]["task_ids"] == ["task_example"]
    assert linked["task_ids"] == ["task_example"]
    assert linked["file_ids"] == ["artifact_example"]
    assert fetched == {"status": "ok", "project": linked}
    assert listed == {"status": "ok", "projects": [linked]}
    _assert_no_task_content_keys(created)
    _assert_no_task_content_keys(fetched)
    _assert_no_task_content_keys(listed)


def test_http_api_projects_route_reads_linked_detail_summaries(tmp_path):
    app = _create_app(tmp_path)
    created_task = _successful_json(
        _request(
            app,
            "POST",
            "/tasks",
            {
                "goal": "collect notes",
                "message": "private note",
            },
        )
    )["task"]
    created_file = _successful_json(
        _request(
            app,
            "POST",
            "/files",
            {
                "name": "notes.md",
                "summary": "useful notes",
                "content": "private file content",
            },
        )
    )["file"]
    project = _successful_json(
        _request(
            app,
            "POST",
            "/projects",
            {
                "name": "portfolio demo",
                "summary": "usable demo workspace",
            },
        )
    )["project"]
    _successful_json(
        _request(
            app,
            "POST",
            f"/projects/{project['project_id']}/tasks",
            {"task_id": created_task["task_id"]},
        )
    )
    linked = _successful_json(
        _request(
            app,
            "POST",
            f"/projects/{project['project_id']}/files",
            {"file_id": created_file["file_id"]},
        )
    )["project"]

    detail = _successful_json(
        _request(app, "GET", f"/projects/{project['project_id']}/detail")
    )

    assert detail == {
        "status": "ok",
        "project_detail": {
            "project": linked,
            "tasks": [created_task],
            "files": [created_file],
        },
    }
    _assert_no_task_content_keys(detail)


def test_http_api_search_route_reads_low_sensitive_summaries(tmp_path):
    app = _create_app(tmp_path)
    project = _successful_json(
        _request(
            app,
            "POST",
            "/projects",
            {
                "name": "portfolio demo",
                "summary": "autumn recruiting workspace",
            },
        )
    )["project"]
    task = _successful_json(
        _request(
            app,
            "POST",
            "/tasks",
            {
                "goal": "build portfolio story",
                "message": "private task note",
            },
        )
    )["task"]
    file_summary = _successful_json(
        _request(
            app,
            "POST",
            "/files",
            {
                "name": "portfolio-notes.md",
                "summary": "portfolio notes",
                "content": "private file content",
            },
        )
    )["file"]

    searched = _successful_json(_request(app, "POST", "/search", {"query": "portfolio"}))

    assert searched == {
        "status": "ok",
        "results": [
            {
                "result_type": "project",
                "result_id": project["project_id"],
                "title": "portfolio demo",
                "summary": "autumn recruiting workspace",
                "item": project,
            },
            {
                "result_type": "task",
                "result_id": task["task_id"],
                "title": "build portfolio story",
                "summary": task["result_summary"],
                "item": task,
            },
            {
                "result_type": "file",
                "result_id": file_summary["file_id"],
                "title": "portfolio-notes.md",
                "summary": "portfolio notes",
                "item": file_summary,
            },
        ],
    }
    _assert_no_task_content_keys(searched)


def test_http_api_search_route_filters_types_and_limit(tmp_path):
    app = _create_app(tmp_path)
    _successful_json(
        _request(
            app,
            "POST",
            "/projects",
            {
                "name": "portfolio demo",
                "summary": "autumn recruiting workspace",
            },
        )
    )
    task = _successful_json(
        _request(
            app,
            "POST",
            "/tasks",
            {
                "goal": "build portfolio story",
                "message": "private task note",
            },
        )
    )["task"]
    _successful_json(
        _request(
            app,
            "POST",
            "/files",
            {
                "name": "portfolio-notes.md",
                "summary": "portfolio notes",
                "content": "private file content",
            },
        )
    )

    searched = _successful_json(
        _request(
            app,
            "POST",
            "/search",
            {"query": "portfolio", "types": ["task", "file"], "limit": 1},
        )
    )

    assert searched["status"] == "ok"
    assert [item["result_type"] for item in searched["results"]] == ["task"]
    assert [item["result_id"] for item in searched["results"]] == [task["task_id"]]
    _assert_no_task_content_keys(searched)


def test_http_api_workbench_route_returns_home_view(tmp_path):
    app = _create_app(tmp_path)
    project = _successful_json(
        _request(
            app,
            "POST",
            "/projects",
            {
                "name": "portfolio demo",
                "summary": "autumn recruiting workspace",
            },
        )
    )["project"]
    task = _successful_json(
        _request(
            app,
            "POST",
            "/tasks",
            {
                "goal": "build portfolio story",
                "message": "private task note",
            },
        )
    )["task"]
    file_summary = _successful_json(
        _request(
            app,
            "POST",
            "/files",
            {
                "name": "portfolio-notes.md",
                "summary": "portfolio notes",
                "content": "private file content",
            },
        )
    )["file"]

    response = _successful_json(
        _request(
            app,
            "POST",
            "/workbench",
            {"query": "portfolio", "types": ["task", "file"], "limit": 1},
        )
    )
    updated_at = response["workbench"]["updated_at"]

    assert response == {
        "status": "ok",
        "workbench": {
            "projects": [project],
            "tasks": [task],
            "files": [file_summary],
            "search_results": [
                {
                    "result_type": "task",
                    "result_id": task["task_id"],
                    "title": "build portfolio story",
                    "summary": task["result_summary"],
                    "item": task,
                }
            ],
            "empty_state": None,
            "updated_at": updated_at,
            "counts": {
                "projects": 1,
                "tasks": 1,
                "files": 1,
                "search_results": 1,
            },
        },
    }
    assert isinstance(updated_at, str)
    _assert_no_task_content_keys(response)


def test_get_run_returns_projector_read_model_from_event_log_not_executor_memory(tmp_path):
    writer = _create_app(tmp_path)
    _, run_id = _create_run_via_http(writer)
    _submit_input_via_http(writer, run_id)

    fresh_reader = _create_app(tmp_path)
    state = _successful_json(_request(fresh_reader, "GET", f"/runs/{run_id}"))

    assert state["run_id"] == run_id
    assert state["status"] == "completed"
    assert state["artifacts"][0]["summary"] == "hello artifact"


def test_artifact_summary_endpoint_does_not_return_full_or_raw_content(tmp_path):
    app = _create_app(tmp_path)
    _, run_id = _create_run_via_http(app)
    _submit_input_via_http(app, run_id)
    state = _successful_json(_request(app, "GET", f"/runs/{run_id}"))
    artifact_ref = state["artifacts"][0]["ref"]
    artifact_id = artifact_ref["artifact_id"]

    summary = _successful_json(_request(app, "GET", f"/artifacts/{artifact_id}/summary"))

    assert summary["summary"] == "hello artifact"
    assert summary["ref"] == artifact_ref
    assert summary["provenance"]
    _assert_no_forbidden_content_keys(summary)


def test_http_api_source_does_not_import_x_agent_when_present():
    source = Path(__file__).resolve().parents[2] / "src" / "isotope" / "http_api.py"
    if not source.exists():
        return
    text = source.read_text(encoding="utf-8")
    assert "x_agent" not in text
