from __future__ import annotations

from typing import Any

from isotope.features.files.flow import FileFlow
from isotope.features.projects.flow import ProjectFlow
from isotope.features.tasks.flow import TaskFlow
from isotope.features.workbench.flow import WorkbenchFlow


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


def test_workbench_flow_returns_low_sensitive_home_view(tmp_path):
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

    view = WorkbenchFlow.in_process(tmp_path).summary(
        query="portfolio",
        search_types=("task", "file"),
        search_limit=1,
    )

    assert view.projects == (project,)
    assert view.tasks == (task,)
    assert view.files == (file_summary,)
    assert [result.result_type for result in view.search_results] == ["task"]
    assert view.to_dict() == {
        "projects": [project.to_dict()],
        "tasks": [task.to_dict()],
        "files": [file_summary.to_dict()],
        "search_results": [view.search_results[0].to_dict()],
        "counts": {
            "projects": 1,
            "tasks": 1,
            "files": 1,
            "search_results": 1,
        },
    }
    _assert_low_sensitive(view.to_dict())
