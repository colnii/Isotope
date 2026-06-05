from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCENARIO = "project-workspace"

FORBIDDEN_CONTENT_KEYS = {
    "artifact_content",
    "content",
    "full_content",
    "full_text",
    "raw_artifact_content",
    "raw_content",
    "text",
}


def _run_demo(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "isotope.demo", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        assert FORBIDDEN_CONTENT_KEYS.isdisjoint(value)
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def test_project_workspace_demo_json_shows_linked_detail_and_workbench():
    result = _run_demo("--scenario", SCENARIO, "--json")

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["scenario"] == SCENARIO
    assert data["workspace_ok"] is True
    assert data["project_task_count"] == 1
    assert data["project_file_count"] == 1
    assert data["workbench_counts"] == {
        "projects": 1,
        "tasks": 1,
        "files": 1,
        "search_results": 3,
    }
    assert data["search_result_types"] == ["project", "task", "file"]
    _assert_no_forbidden_content_keys(data)


def test_project_workspace_demo_trace_is_human_readable():
    result = _run_demo("--scenario", SCENARIO, "--trace")

    assert result.returncode == 0, result.stderr
    assert "scenario: project-workspace" in result.stdout
    assert "POST /projects/workspace 创建并关联 project/task/file" in result.stdout
    assert "project detail: tasks=1 files=1" in result.stdout
    assert "workbench: projects=1 tasks=1 files=1 search_results=3" in result.stdout
    assert "private task note" not in result.stdout
    assert "private file content" not in result.stdout


def test_project_workspace_append_demo_reuses_existing_project():
    result = _run_demo("--scenario", "project-workspace-append", "--json")

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["scenario"] == "project-workspace-append"
    assert data["workspace_ok"] is True
    assert data["project_task_count"] == 2
    assert data["project_file_count"] == 2
    assert data["workbench_counts"] == {
        "projects": 1,
        "tasks": 2,
        "files": 2,
        "search_results": 5,
    }
    assert data["search_result_types"] == [
        "project",
        "task",
        "task",
        "file",
        "file",
    ]
    _assert_no_forbidden_content_keys(data)
