from __future__ import annotations

import json
import pytest
from typing import Any

from isotope.features.files.flow import FileFlow
from isotope.features.projects.flow import ProjectFlow
from isotope.features.tasks.flow import TaskFlow


FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
    "text",
}


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        assert FORBIDDEN_CONTENT_KEYS.isdisjoint(value)
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def test_project_flow_creates_user_facing_project_summary(tmp_path):
    flow = ProjectFlow.in_process(tmp_path)

    created = flow.create_project(
        name="portfolio demo",
        summary="autumn recruiting project",
    )
    fetched = flow.get_project(created.project_id)

    assert created.project_id.startswith("project_")
    assert created.name == "portfolio demo"
    assert created.summary == "autumn recruiting project"
    assert created.task_ids == ()
    assert created.file_ids == ()
    assert fetched == created
    _assert_no_forbidden_content_keys(created.to_dict())


def test_project_flow_links_tasks_files_and_reloads_summaries(tmp_path):
    project_flow = ProjectFlow.in_process(tmp_path)
    task_flow = TaskFlow.in_process(tmp_path)
    file_flow = FileFlow.in_process(tmp_path)

    project = project_flow.create_project(
        name="application workspace",
        summary="usable project workspace",
    )
    task = task_flow.create_task(goal="collect useful notes", first_message="first note")
    file_summary = file_flow.create_text_file(
        name="notes.md",
        summary="useful notes",
        content="private durable file content",
    )

    with_task = project_flow.add_task(project.project_id, task.task_id)
    linked = project_flow.add_file(with_task.project_id, file_summary.file_id)

    assert linked.task_ids == (task.task_id,)
    assert linked.file_ids == (file_summary.file_id,)
    assert project_flow.list_projects() == [linked]

    reloaded = ProjectFlow.in_process(tmp_path)

    assert reloaded.get_project(project.project_id) == linked
    assert reloaded.list_projects() == [linked]
    _assert_no_forbidden_content_keys(
        {"projects": [summary.to_dict() for summary in reloaded.list_projects()]}
    )


def test_project_flow_reads_linked_task_and_file_summaries(tmp_path):
    project_flow = ProjectFlow.in_process(tmp_path)
    task_flow = TaskFlow.in_process(tmp_path)
    file_flow = FileFlow.in_process(tmp_path)

    project = project_flow.create_project(
        name="portfolio demo",
        summary="usable demo workspace",
    )
    task = task_flow.create_task(goal="collect notes", first_message="private note")
    file_summary = file_flow.create_text_file(
        name="notes.md",
        summary="useful notes",
        content="private file content",
    )
    project_flow.add_task(project.project_id, task.task_id)
    linked = project_flow.add_file(project.project_id, file_summary.file_id)

    detail = project_flow.get_project_detail(project.project_id)

    assert detail.project == linked
    assert detail.tasks == (task,)
    assert detail.files == (file_summary,)
    assert detail.to_dict() == {
        "project": linked.to_dict(),
        "tasks": [task.to_dict()],
        "files": [file_summary.to_dict()],
    }
    _assert_no_forbidden_content_keys(detail.to_dict())


def test_project_flow_rejects_missing_task_link(tmp_path):
    project_flow = ProjectFlow.in_process(tmp_path)
    project = project_flow.create_project(
        name="portfolio demo",
        summary="usable demo workspace",
    )

    with pytest.raises(ValueError, match="unknown task_id"):
        project_flow.add_task(project.project_id, "task_missing")

    assert project_flow.get_project(project.project_id).task_ids == ()


def test_project_flow_rejects_missing_file_link(tmp_path):
    project_flow = ProjectFlow.in_process(tmp_path)
    project = project_flow.create_project(
        name="portfolio demo",
        summary="usable demo workspace",
    )

    with pytest.raises(ValueError, match="unknown file_id"):
        project_flow.add_file(project.project_id, "artifact_missing")

    assert project_flow.get_project(project.project_id).file_ids == ()


def test_project_flow_rejects_reloaded_project_with_missing_task_link(tmp_path):
    project_flow = ProjectFlow.in_process(tmp_path)
    project = project_flow.create_project(
        name="portfolio demo",
        summary="usable demo workspace",
    )
    index_path = tmp_path / "projects" / "index.json"
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    payload["projects"][0]["task_ids"] = ["task_missing"]
    index_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    reloaded = ProjectFlow.in_process(tmp_path)

    with pytest.raises(ValueError, match="unknown task_id"):
        reloaded.get_project(project.project_id)
    with pytest.raises(ValueError, match="unknown task_id"):
        reloaded.list_projects()


def test_project_flow_rejects_reloaded_project_with_missing_file_link(tmp_path):
    project_flow = ProjectFlow.in_process(tmp_path)
    project = project_flow.create_project(
        name="portfolio demo",
        summary="usable demo workspace",
    )
    index_path = tmp_path / "projects" / "index.json"
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    payload["projects"][0]["file_ids"] = ["artifact_missing"]
    index_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    reloaded = ProjectFlow.in_process(tmp_path)

    with pytest.raises(ValueError, match="unknown file_id"):
        reloaded.get_project(project.project_id)
    with pytest.raises(ValueError, match="unknown file_id"):
        reloaded.list_projects()
