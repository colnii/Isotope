from __future__ import annotations

import json
import asyncio
import os
import subprocess
import sys
from typing import Any
from pathlib import Path

from isotope.apps.api import ApiApp, create_api_app


REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "isotope.apps.api", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


async def _asgi_request(
    app: ApiApp,
    *,
    method: str,
    path: str,
    query_string: str = "",
    headers: tuple[tuple[bytes, bytes], ...] = (),
    json_body: dict[str, Any] | None = None,
    raw_body: bytes | None = None,
) -> dict[str, Any]:
    body = (
        raw_body
        if raw_body is not None
        else b"" if json_body is None else json.dumps(json_body).encode("utf-8")
    )
    messages = [
        {
            "type": "http.request",
            "body": body,
            "more_body": False,
        }
    ]
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return messages.pop(0)

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(
        {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": query_string.encode("utf-8"),
            "headers": headers,
        },
        receive,
        send,
    )

    start = sent[0]
    response = sent[1]
    assert start["type"] == "http.response.start"
    assert response["type"] == "http.response.body"
    return {
        "status_code": start["status"],
        "headers": dict(start["headers"]),
        "json": json.loads(response["body"]),
    }


def test_apps_api_exposes_routes_from_http_facade(tmp_path):
    app = create_api_app(tmp_path)

    assert ("GET", "/health") in app.routes()
    assert ("POST", "/projects/workspace") in app.routes()


def test_apps_api_routes_cli_prints_supported_routes_as_json(tmp_path):
    result = _run_cli("routes", "--root", str(tmp_path), "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert {"method": "GET", "path": "/health"} in payload["routes"]
    assert {"method": "POST", "path": "/projects/workspace"} in payload["routes"]


def test_apps_api_request_cli_invokes_local_http_facade_as_json(tmp_path):
    result = _run_cli("request", "--root", str(tmp_path), "GET", "/health", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "status_code": 200,
        "body": {"status": "ok"},
    }


def test_apps_api_request_cli_accepts_json_body(tmp_path):
    result = _run_cli(
        "request",
        "--root",
        str(tmp_path),
        "POST",
        "/tasks",
        "--body-json",
        json.dumps({"goal": "ship api entry", "message": "first note"}),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status_code"] == 201
    assert payload["body"]["status"] == "ok"
    assert payload["body"]["task"]["goal"] == "ship api entry"


def test_apps_api_asgi_health_route(tmp_path):
    app = create_api_app(tmp_path)

    response = asyncio.run(_asgi_request(app, method="GET", path="/health"))

    assert response["status_code"] == 200
    assert response["headers"][b"content-type"] == b"application/json; charset=utf-8"
    assert response["headers"][b"x-isotope-api"] == b"asgi"
    assert response["json"] == {"status": "ok"}


def test_apps_api_asgi_project_workspace_route(tmp_path):
    app = create_api_app(tmp_path)

    response = asyncio.run(
        _asgi_request(
            app,
            method="POST",
            path="/projects/workspace",
            json_body={
                "project_name": "portfolio demo",
                "project_summary": "autumn recruiting workspace",
                "task_goal": "build portfolio story",
                "task_message": "private task note",
                "file_name": "portfolio-notes.md",
                "file_summary": "portfolio notes",
                "file_content": "private file content",
                "search_query": "portfolio",
            },
        )
    )

    workspace = response["json"]["workspace"]
    assert response["status_code"] == 201
    assert workspace["workbench"]["counts"] == {
        "projects": 1,
        "tasks": 1,
        "files": 1,
        "search_results": 3,
    }


def test_apps_api_asgi_query_string_feeds_existing_workbench_route(tmp_path):
    app = create_api_app(tmp_path)
    app.request(
        "POST",
        "/projects/workspace",
        {
            "project_name": "portfolio demo",
            "project_summary": "autumn recruiting workspace",
            "task_goal": "build portfolio story",
            "task_message": "private task note",
            "file_name": "portfolio-notes.md",
            "file_summary": "portfolio notes",
            "file_content": "private file content",
            "search_query": "portfolio",
        },
    )

    response = asyncio.run(
        _asgi_request(
            app,
            method="POST",
            path="/workbench",
            query_string="query=portfolio&types=task&limit=1",
        )
    )

    assert response["status_code"] == 200
    assert response["json"]["workbench"]["counts"] == {
        "projects": 1,
        "tasks": 1,
        "files": 1,
        "search_results": 1,
    }
    assert [
        item["result_type"]
        for item in response["json"]["workbench"]["search_results"]
    ] == ["task"]


def test_apps_api_asgi_invalid_json_returns_stable_error(tmp_path):
    app = create_api_app(tmp_path)

    response = asyncio.run(
        _asgi_request(
            app,
            method="POST",
            path="/projects/workspace",
            headers=((b"content-type", b"application/json"),),
            raw_body=b"{not json",
        )
    )

    assert response["status_code"] == 400
    assert response["headers"][b"x-isotope-api"] == b"asgi"
    assert response["json"] == {
        "status": "error",
        "error": {
            "code": "invalid_json",
            "message": "request body must be valid JSON",
        },
    }
