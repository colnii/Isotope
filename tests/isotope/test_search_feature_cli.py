from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from isotope.features.files.flow import FileFlow
from isotope.features.projects.flow import ProjectFlow
from isotope.features.tasks.flow import TaskFlow


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"

FORBIDDEN_KEYS = {
    "artifact_content",
    "content",
    "full_content",
    "full_text",
    "raw_artifact_content",
    "raw_content",
    "text",
}


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "isotope.features.search.runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def _assert_low_sensitive(value: Any) -> None:
    if isinstance(value, dict):
        assert FORBIDDEN_KEYS.isdisjoint(value)
        for nested in value.values():
            _assert_low_sensitive(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_low_sensitive(nested)


def test_search_cli_returns_matching_summaries_as_json(tmp_path):
    project = ProjectFlow.in_process(tmp_path).create_project(
        name="portfolio demo",
        summary="autumn recruiting workspace",
    )
    task = TaskFlow.in_process(tmp_path).create_task(
        goal="build portfolio story",
        first_message="private task note",
    )
    file_summary = FileFlow.in_process(tmp_path).create_text_file(
        name="portfolio-notes.md",
        summary="portfolio notes",
        content="private file content",
    )

    result = _run_cli("search", "--root", str(tmp_path), "--query", "portfolio", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "status": "ok",
        "results": [
            {
                "result_type": "project",
                "result_id": project.project_id,
                "title": "portfolio demo",
                "summary": "autumn recruiting workspace",
                "item": project.to_dict(),
            },
            {
                "result_type": "task",
                "result_id": task.task_id,
                "title": "build portfolio story",
                "summary": task.result_summary,
                "item": task.to_dict(),
            },
            {
                "result_type": "file",
                "result_id": file_summary.file_id,
                "title": "portfolio-notes.md",
                "summary": "portfolio notes",
                "item": file_summary.to_dict(),
            },
        ],
    }
    _assert_low_sensitive(payload)


def test_search_cli_requires_query(tmp_path):
    result = _run_cli("search", "--root", str(tmp_path), "--json")

    assert result.returncode == 2
    assert json.loads(result.stdout) == {
        "status": "error",
        "error": {
            "code": "search_runner_error",
            "message": "search requires --query",
        },
    }


def test_search_cli_filters_type_and_limit(tmp_path):
    ProjectFlow.in_process(tmp_path).create_project(
        name="portfolio demo",
        summary="autumn recruiting workspace",
    )
    task = TaskFlow.in_process(tmp_path).create_task(
        goal="build portfolio story",
        first_message="private task note",
    )
    FileFlow.in_process(tmp_path).create_text_file(
        name="portfolio-notes.md",
        summary="portfolio notes",
        content="private file content",
    )

    result = _run_cli(
        "search",
        "--root",
        str(tmp_path),
        "--query",
        "portfolio",
        "--type",
        "task",
        "--type",
        "file",
        "--limit",
        "1",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert [item["result_type"] for item in payload["results"]] == ["task"]
    assert [item["result_id"] for item in payload["results"]] == [task.task_id]


def test_search_cli_rejects_bad_type(tmp_path):
    result = _run_cli(
        "search",
        "--root",
        str(tmp_path),
        "--query",
        "portfolio",
        "--type",
        "unknown",
        "--json",
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["message"] == (
        "unsupported search result_type: unknown"
    )
