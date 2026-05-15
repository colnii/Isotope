from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


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
        [sys.executable, "-m", "isotope.features.projects.runner", *args],
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


def test_project_cli_creates_gets_lists_and_links_project_summaries_as_json(tmp_path):
    created_result = _run_cli(
        "create",
        "--root",
        str(tmp_path),
        "--name",
        "portfolio demo",
        "--summary",
        "autumn recruiting project",
        "--json",
    )

    assert created_result.returncode == 0, created_result.stderr
    created_payload = json.loads(created_result.stdout)
    project = created_payload["project"]
    project_id = project["project_id"]

    with_task = _run_cli(
        "add-task",
        "--root",
        str(tmp_path),
        "--project-id",
        project_id,
        "--task-id",
        "task_example",
        "--json",
    )
    with_file = _run_cli(
        "add-file",
        "--root",
        str(tmp_path),
        "--project-id",
        project_id,
        "--file-id",
        "artifact_example",
        "--json",
    )
    get_result = _run_cli("get", "--root", str(tmp_path), "--project-id", project_id, "--json")
    list_result = _run_cli("list", "--root", str(tmp_path), "--json")

    assert created_payload["status"] == "ok"
    assert project_id.startswith("project_")
    assert project["name"] == "portfolio demo"
    assert project["summary"] == "autumn recruiting project"
    assert with_task.returncode == 0, with_task.stderr
    assert json.loads(with_task.stdout)["project"]["task_ids"] == ["task_example"]
    assert with_file.returncode == 0, with_file.stderr
    linked = json.loads(with_file.stdout)["project"]
    assert linked["task_ids"] == ["task_example"]
    assert linked["file_ids"] == ["artifact_example"]
    assert get_result.returncode == 0, get_result.stderr
    assert json.loads(get_result.stdout) == {"status": "ok", "project": linked}
    assert list_result.returncode == 0, list_result.stderr
    assert json.loads(list_result.stdout) == {"status": "ok", "projects": [linked]}
    _assert_low_sensitive(created_payload)
    _assert_low_sensitive(json.loads(get_result.stdout))
    _assert_low_sensitive(json.loads(list_result.stdout))


def test_project_cli_requires_project_id_for_get(tmp_path):
    result = _run_cli("get", "--root", str(tmp_path), "--json")

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload == {
        "status": "error",
        "error": {
            "code": "project_runner_error",
            "message": "get requires --project-id",
        },
    }
