from __future__ import annotations

from typing import Any

from isotope.features.projects.workspace import ProjectWorkspaceFlow


FORBIDDEN_CONTENT_KEYS = {
    "artifact_content",
    "content",
    "full_content",
    "full_text",
    "raw_artifact_content",
    "raw_content",
    "text",
}


def _assert_public_metadata(value: Any) -> None:
    if isinstance(value, dict):
        assert FORBIDDEN_CONTENT_KEYS.isdisjoint(value)
        for nested in value.values():
            _assert_public_metadata(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_public_metadata(nested)


def test_project_workspace_flow_creates_linked_detail_and_workbench_view(tmp_path):
    workspace = ProjectWorkspaceFlow.in_process(tmp_path).create_workspace(
        project_name="portfolio demo",
        project_summary="autumn recruiting workspace",
        task_goal="build portfolio story",
        task_message="private task note",
        file_name="portfolio-notes.md",
        file_summary="portfolio notes",
        file_content="private file content",
        search_query="portfolio",
    )

    project = workspace.project_detail.project
    task = workspace.project_detail.tasks[0]
    file_summary = workspace.project_detail.files[0]

    assert project.task_ids == (task.task_id,)
    assert project.file_ids == (file_summary.file_id,)
    assert workspace.workbench.projects == (project,)
    assert workspace.workbench.tasks == (task,)
    assert workspace.workbench.files == (file_summary,)
    assert workspace.workbench.counts == {
        "projects": 1,
        "tasks": 1,
        "files": 1,
        "search_results": 3,
    }
    assert [result.result_type for result in workspace.workbench.search_results] == [
        "project",
        "task",
        "file",
    ]
    assert workspace.to_dict() == {
        "project_detail": workspace.project_detail.to_dict(),
        "workbench": workspace.workbench.to_dict(),
    }
    _assert_public_metadata(workspace.to_dict())


def test_project_workspace_flow_appends_task_and_file_to_existing_project(tmp_path):
    flow = ProjectWorkspaceFlow.in_process(tmp_path)
    first = flow.create_workspace(
        project_name="portfolio demo",
        project_summary="autumn recruiting workspace",
        task_goal="build portfolio story",
        task_message="private task note",
        file_name="portfolio-notes.md",
        file_summary="portfolio notes",
        file_content="private file content",
        search_query="portfolio",
    )

    appended = flow.append_to_project(
        first.project_detail.project.project_id,
        task_goal="polish portfolio case study",
        task_message="private second task note",
        file_name="portfolio-case-study.md",
        file_summary="portfolio case study notes",
        file_content="private second file content",
        search_query="portfolio",
    )

    project = appended.project_detail.project
    assert project.project_id == first.project_detail.project.project_id
    assert len(project.task_ids) == 2
    assert len(project.file_ids) == 2
    assert project.task_ids[0] == first.project_detail.tasks[0].task_id
    assert project.file_ids[0] == first.project_detail.files[0].file_id
    assert appended.workbench.counts == {
        "projects": 1,
        "tasks": 2,
        "files": 2,
        "search_results": 5,
    }
    assert [result.result_type for result in appended.workbench.search_results] == [
        "project",
        "task",
        "task",
        "file",
        "file",
    ]
    _assert_public_metadata(appended.to_dict())
