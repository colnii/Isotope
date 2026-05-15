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


def _assert_low_sensitive(value: Any) -> None:
    if isinstance(value, dict):
        assert FORBIDDEN_CONTENT_KEYS.isdisjoint(value)
        for nested in value.values():
            _assert_low_sensitive(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_low_sensitive(nested)


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
    _assert_low_sensitive(workspace.to_dict())
