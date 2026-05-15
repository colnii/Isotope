from __future__ import annotations

from typing import Any

import pytest

from isotope.features.files.flow import FileFlow
from isotope.features.projects.flow import ProjectFlow
from isotope.features.search.flow import SearchFlow
from isotope.features.tasks.flow import TaskFlow


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


def test_search_flow_finds_project_task_and_file_summaries(tmp_path):
    project_flow = ProjectFlow.in_process(tmp_path)
    task_flow = TaskFlow.in_process(tmp_path)
    file_flow = FileFlow.in_process(tmp_path)
    project = project_flow.create_project(
        name="portfolio demo",
        summary="autumn recruiting workspace",
    )
    task = task_flow.create_task(
        goal="build portfolio story",
        first_message="private task note",
    )
    file_summary = file_flow.create_text_file(
        name="portfolio-notes.md",
        summary="portfolio notes",
        content="private file content",
    )

    results = SearchFlow.in_process(tmp_path).search("portfolio")

    assert [result.result_type for result in results] == ["project", "task", "file"]
    assert [result.result_id for result in results] == [
        project.project_id,
        task.task_id,
        file_summary.file_id,
    ]
    assert [result.title for result in results] == [
        "portfolio demo",
        "build portfolio story",
        "portfolio-notes.md",
    ]
    assert results[0].item == project.to_dict()
    assert results[1].item == task.to_dict()
    assert results[2].item == file_summary.to_dict()
    _assert_low_sensitive({"results": [result.to_dict() for result in results]})


def test_search_flow_requires_non_empty_query(tmp_path):
    flow = SearchFlow.in_process(tmp_path)

    with pytest.raises(ValueError, match="query must not be empty"):
        flow.search("   ")


def test_search_flow_filters_types_and_limits_results(tmp_path):
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

    results = SearchFlow.in_process(tmp_path).search(
        "portfolio",
        result_types=("task", "file"),
        limit=1,
    )

    assert [result.result_type for result in results] == ["task"]
    assert [result.result_id for result in results] == [task.task_id]


@pytest.mark.parametrize("bad_type", ["", "unknown"])
def test_search_flow_rejects_unknown_result_types(tmp_path, bad_type):
    flow = SearchFlow.in_process(tmp_path)

    with pytest.raises(ValueError, match="unsupported search result_type"):
        flow.search("portfolio", result_types=(bad_type,))


@pytest.mark.parametrize("bad_limit", [0, -1])
def test_search_flow_rejects_non_positive_limit(tmp_path, bad_limit):
    flow = SearchFlow.in_process(tmp_path)

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        flow.search("portfolio", limit=bad_limit)
