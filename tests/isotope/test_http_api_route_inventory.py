from collections.abc import Mapping
from typing import Any

from isotope.interfaces.http import create_http_app


SUPPORTED_ROUTES = [
    ("GET", "/health"),
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
    ("POST", "/projects/workspace"),
    ("POST", "/projects/{project_id}/workspace"),
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
]

DEFERRED_PATTERNS = {
    "/runs/{run_id}/memory/query",
    "/external-ingestion",
    "/runs/{run_id}/events/stream",
    "/runs/{run_id}/llm/chat-turns",
    "/runs/{run_id}/approvals",
    "/artifacts/{artifact_id}/content",
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


def _routes_from_inventory(inventory: dict[str, Any]) -> list[tuple[str, str, str]]:
    routes = inventory["routes"]
    assert isinstance(routes, list)
    return [
        (str(route["method"]), str(route["path"]), str(route["status"]))
        for route in routes
    ]


def _assert_no_internal_repr(value: Any) -> None:
    if isinstance(value, str):
        assert "object at 0x" not in value
        assert "bound method" not in value
        assert "HttpApiApp." not in value
        assert "function " not in value
    elif isinstance(value, dict):
        for nested in value.values():
            _assert_no_internal_repr(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_internal_repr(nested)


def test_http_api_exposes_stable_list_routes_inventory(tmp_path):
    app = create_http_app(tmp_path)

    assert hasattr(app, "list_routes")
    inventory = app.list_routes()

    assert inventory["status"] == "ok"
    assert _routes_from_inventory(inventory) == [
        (method, path, "supported") for method, path in SUPPORTED_ROUTES
    ]
    _assert_no_internal_repr(inventory)


def test_get_routes_returns_same_supported_inventory(tmp_path):
    app = create_http_app(tmp_path)

    response = _request(app, "GET", "/routes")

    assert _status_code(response) == 200
    inventory = _body(response)
    assert _routes_from_inventory(inventory) == [
        (method, path, "supported") for method, path in SUPPORTED_ROUTES
    ]


def test_route_inventory_does_not_mark_deferred_routes_as_supported(tmp_path):
    app = create_http_app(tmp_path)
    inventory = app.list_routes()

    route_entries = inventory["routes"]
    supported_paths = {
        route["path"]
        for route in route_entries
        if route.get("status") == "supported"
    }

    assert not DEFERRED_PATTERNS.intersection(supported_paths)
    for route in route_entries:
        if route["path"] in DEFERRED_PATTERNS:
            assert route["status"] == "deferred"


def test_legacy_routes_remains_minimal_supported_tuple_surface(tmp_path):
    app = create_http_app(tmp_path)

    assert app.routes() == [(method, path) for method, path in SUPPORTED_ROUTES]


def test_inventory_response_keeps_method_mismatch_and_unknown_route_boundaries(tmp_path):
    app = create_http_app(tmp_path)

    method_mismatch = _request(app, "GET", "/sessions")
    unknown = _request(app, "GET", "/not-a-route")

    assert _status_code(method_mismatch) == 405
    assert _body(method_mismatch)["error"]["code"] == "method_not_allowed"
    assert _status_code(unknown) == 404
    assert _body(unknown)["error"]["code"] == "not_found"
