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
        [sys.executable, "-m", "isotope.features.workbench.runner", *args],
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


def test_workbench_cli_returns_home_view_as_json(tmp_path):
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
        "show",
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
    assert payload["workbench"]["counts"] == {
        "projects": 1,
        "tasks": 1,
        "files": 1,
        "search_results": 1,
    }
    assert payload["workbench"]["empty_state"] is None
    assert isinstance(payload["workbench"]["updated_at"], str)
    assert [item["result_type"] for item in payload["workbench"]["search_results"]] == ["task"]
    assert [item["result_id"] for item in payload["workbench"]["search_results"]] == [
        task.task_id
    ]
    _assert_low_sensitive(payload)


def test_workbench_cli_uses_refreshed_task_and_file_summaries(tmp_path):
    task = TaskFlow.in_process(tmp_path).create_task(
        goal="build portfolio story",
        first_message="private task note",
    )
    FileFlow.in_process(tmp_path).create_text_file(
        name="portfolio-notes.md",
        summary="canonical file summary",
        content="private file content",
    )
    task_index_path = tmp_path / "tasks" / "index.json"
    task_index = json.loads(task_index_path.read_text(encoding="utf-8"))
    task_index["tasks"][0]["result_summary"] = "stale task index summary"
    task_index_path.write_text(json.dumps(task_index), encoding="utf-8")
    file_index_path = tmp_path / "files" / "index.json"
    file_index = json.loads(file_index_path.read_text(encoding="utf-8"))
    file_index["files"][0]["summary"] = "stale file index summary"
    file_index_path.write_text(json.dumps(file_index), encoding="utf-8")

    result = _run_cli(
        "show",
        "--root",
        str(tmp_path),
        "--query",
        "portfolio",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "stale task index summary" not in payload_text
    assert "stale file index summary" not in payload_text
    assert task.result_summary in payload_text
    assert "canonical file summary" in payload_text
    _assert_low_sensitive(payload)


def test_workbench_cli_plain_output_shows_empty_state(tmp_path):
    result = _run_cli("show", "--root", str(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "projects=0 tasks=0 files=0 search_results=0" in result.stdout
    assert "empty=true" in result.stdout
    assert "updated_at=none" in result.stdout
