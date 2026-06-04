from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from isotope.features.files.flow import FileFlow
from isotope.features.tasks.flow import TaskFlow


REPO_ROOT = Path(__file__).resolve().parents[3]
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


def _assert_public_metadata(value: Any) -> None:
    if isinstance(value, dict):
        assert FORBIDDEN_KEYS.isdisjoint(value)
        for nested in value.values():
            _assert_public_metadata(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_public_metadata(nested)


def test_project_cli_creates_gets_lists_and_links_project_summaries_as_json(tmp_path):
    task = TaskFlow.in_process(tmp_path).create_task(
        goal="collect notes",
        first_message="private note",
    )
    file_summary = FileFlow.in_process(tmp_path).create_text_file(
        name="notes.md",
        summary="useful notes",
        content="private file content",
    )
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
        task.task_id,
        "--json",
    )
    with_file = _run_cli(
        "add-file",
        "--root",
        str(tmp_path),
        "--project-id",
        project_id,
        "--file-id",
        file_summary.file_id,
        "--json",
    )
    get_result = _run_cli("get", "--root", str(tmp_path), "--project-id", project_id, "--json")
    list_result = _run_cli("list", "--root", str(tmp_path), "--json")

    assert created_payload["status"] == "ok"
    assert project_id.startswith("project_")
    assert project["name"] == "portfolio demo"
    assert project["summary"] == "autumn recruiting project"
    assert with_task.returncode == 0, with_task.stderr
    assert json.loads(with_task.stdout)["project"]["task_ids"] == [task.task_id]
    assert with_file.returncode == 0, with_file.stderr
    linked = json.loads(with_file.stdout)["project"]
    assert linked["task_ids"] == [task.task_id]
    assert linked["file_ids"] == [file_summary.file_id]
    assert get_result.returncode == 0, get_result.stderr
    assert json.loads(get_result.stdout) == {"status": "ok", "project": linked}
    assert list_result.returncode == 0, list_result.stderr
    assert json.loads(list_result.stdout) == {"status": "ok", "projects": [linked]}
    _assert_public_metadata(created_payload)
    _assert_public_metadata(json.loads(get_result.stdout))
    _assert_public_metadata(json.loads(list_result.stdout))


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


def test_project_cli_reads_project_detail_with_linked_summaries(tmp_path):
    task = TaskFlow.in_process(tmp_path).create_task(
        goal="collect notes",
        first_message="private note",
    )
    file_summary = FileFlow.in_process(tmp_path).create_text_file(
        name="notes.md",
        summary="useful notes",
        content="private file content",
    )
    created_result = _run_cli(
        "create",
        "--root",
        str(tmp_path),
        "--name",
        "portfolio demo",
        "--summary",
        "usable demo workspace",
        "--json",
    )
    project = json.loads(created_result.stdout)["project"]
    project_id = project["project_id"]
    with_task = _run_cli(
        "add-task",
        "--root",
        str(tmp_path),
        "--project-id",
        project_id,
        "--task-id",
        task.task_id,
        "--json",
    )
    with_file = _run_cli(
        "add-file",
        "--root",
        str(tmp_path),
        "--project-id",
        project_id,
        "--file-id",
        file_summary.file_id,
        "--json",
    )

    detail_result = _run_cli(
        "detail",
        "--root",
        str(tmp_path),
        "--project-id",
        project_id,
        "--json",
    )

    assert with_task.returncode == 0, with_task.stderr
    assert with_file.returncode == 0, with_file.stderr
    assert detail_result.returncode == 0, detail_result.stderr
    linked = json.loads(with_file.stdout)["project"]
    assert json.loads(detail_result.stdout) == {
        "status": "ok",
        "project_detail": {
            "project": linked,
            "tasks": [task.to_dict()],
            "files": [file_summary.to_dict()],
        },
    }
    _assert_public_metadata(json.loads(detail_result.stdout))


def test_project_cli_detail_uses_refreshed_linked_summaries(tmp_path):
    task = TaskFlow.in_process(tmp_path).create_task(
        goal="collect portfolio evidence",
        first_message="private note",
    )
    file_summary = FileFlow.in_process(tmp_path).create_text_file(
        name="evidence.md",
        summary="canonical file summary",
        content="private file content",
    )
    created_result = _run_cli(
        "create",
        "--root",
        str(tmp_path),
        "--name",
        "portfolio demo",
        "--summary",
        "usable demo workspace",
        "--json",
    )
    project_id = json.loads(created_result.stdout)["project"]["project_id"]
    _run_cli(
        "add-task",
        "--root",
        str(tmp_path),
        "--project-id",
        project_id,
        "--task-id",
        task.task_id,
        "--json",
    )
    _run_cli(
        "add-file",
        "--root",
        str(tmp_path),
        "--project-id",
        project_id,
        "--file-id",
        file_summary.file_id,
        "--json",
    )
    task_index_path = tmp_path / "tasks" / "index.json"
    task_index = json.loads(task_index_path.read_text(encoding="utf-8"))
    task_index["tasks"][0]["result_text"] = "stale task index summary"
    task_index_path.write_text(json.dumps(task_index), encoding="utf-8")
    file_index_path = tmp_path / "files" / "index.json"
    file_index = json.loads(file_index_path.read_text(encoding="utf-8"))
    file_index["files"][0]["summary"] = "stale file index summary"
    file_index_path.write_text(json.dumps(file_index), encoding="utf-8")

    detail_result = _run_cli(
        "detail",
        "--root",
        str(tmp_path),
        "--project-id",
        project_id,
        "--json",
    )

    assert detail_result.returncode == 0, detail_result.stderr
    payload = json.loads(detail_result.stdout)
    payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "stale task index summary" not in payload_text
    assert "stale file index summary" not in payload_text
    assert task.result_text in payload_text
    assert file_summary.summary in payload_text
    _assert_public_metadata(payload)


def test_project_cli_creates_workspace_with_detail_and_workbench(tmp_path):
    result = _run_cli(
        "workspace",
        "--root",
        str(tmp_path),
        "--project-name",
        "portfolio demo",
        "--project-summary",
        "autumn recruiting workspace",
        "--task-goal",
        "build portfolio story",
        "--task-message",
        "private task note",
        "--file-name",
        "portfolio-notes.md",
        "--file-summary",
        "portfolio notes",
        "--file-content",
        "private file content",
        "--search-query",
        "portfolio",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    project = payload["workspace"]["project_detail"]["project"]
    task = payload["workspace"]["project_detail"]["tasks"][0]
    file_summary = payload["workspace"]["project_detail"]["files"][0]

    assert payload["status"] == "ok"
    assert project["task_ids"] == [task["task_id"]]
    assert project["file_ids"] == [file_summary["file_id"]]
    assert payload["workspace"]["workbench"]["counts"] == {
        "projects": 1,
        "tasks": 1,
        "files": 1,
        "search_results": 3,
    }
    assert [item["result_type"] for item in payload["workspace"]["workbench"]["search_results"]] == [
        "project",
        "task",
        "file",
    ]
    _assert_public_metadata(payload)


def test_project_cli_appends_workspace_items_to_existing_project(tmp_path):
    created = _run_cli(
        "workspace",
        "--root",
        str(tmp_path),
        "--project-name",
        "portfolio demo",
        "--project-summary",
        "autumn recruiting workspace",
        "--task-goal",
        "build portfolio story",
        "--task-message",
        "private task note",
        "--file-name",
        "portfolio-notes.md",
        "--file-summary",
        "portfolio notes",
        "--file-content",
        "private file content",
        "--search-query",
        "portfolio",
        "--json",
    )
    project_id = json.loads(created.stdout)["workspace"]["project_detail"]["project"]["project_id"]

    result = _run_cli(
        "workspace-add",
        "--root",
        str(tmp_path),
        "--project-id",
        project_id,
        "--task-goal",
        "polish portfolio case study",
        "--task-message",
        "private second task note",
        "--file-name",
        "portfolio-case-study.md",
        "--file-summary",
        "portfolio case study notes",
        "--file-content",
        "private second file content",
        "--search-query",
        "portfolio",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    project = payload["workspace"]["project_detail"]["project"]
    assert project["project_id"] == project_id
    assert len(project["task_ids"]) == 2
    assert len(project["file_ids"]) == 2
    assert payload["workspace"]["workbench"]["counts"] == {
        "projects": 1,
        "tasks": 2,
        "files": 2,
        "search_results": 5,
    }
    _assert_public_metadata(payload)


def test_project_cli_workspace_add_uses_refreshed_linked_summaries(tmp_path):
    created = _run_cli(
        "workspace",
        "--root",
        str(tmp_path),
        "--project-name",
        "portfolio demo",
        "--project-summary",
        "autumn recruiting workspace",
        "--task-goal",
        "build portfolio story",
        "--task-message",
        "private task note",
        "--file-name",
        "portfolio-notes.md",
        "--file-summary",
        "canonical file summary",
        "--file-content",
        "private file content",
        "--search-query",
        "portfolio",
        "--json",
    )
    created_workspace = json.loads(created.stdout)["workspace"]
    project_id = created_workspace["project_detail"]["project"]["project_id"]
    original_task_summary = created_workspace["project_detail"]["tasks"][0]["result_text"]
    original_file_summary = created_workspace["project_detail"]["files"][0]["summary"]
    task_index_path = tmp_path / "tasks" / "index.json"
    task_index = json.loads(task_index_path.read_text(encoding="utf-8"))
    task_index["tasks"][0]["result_text"] = "stale task index summary"
    task_index_path.write_text(json.dumps(task_index), encoding="utf-8")
    file_index_path = tmp_path / "files" / "index.json"
    file_index = json.loads(file_index_path.read_text(encoding="utf-8"))
    file_index["files"][0]["summary"] = "stale file index summary"
    file_index_path.write_text(json.dumps(file_index), encoding="utf-8")

    result = _run_cli(
        "workspace-add",
        "--root",
        str(tmp_path),
        "--project-id",
        project_id,
        "--task-goal",
        "polish portfolio case study",
        "--task-message",
        "private second task note",
        "--file-name",
        "portfolio-case-study.md",
        "--file-summary",
        "portfolio case study notes",
        "--file-content",
        "private second file content",
        "--search-query",
        "portfolio",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "stale task index summary" not in payload_text
    assert "stale file index summary" not in payload_text
    assert original_task_summary in payload_text
    assert original_file_summary in payload_text
    _assert_public_metadata(payload)
