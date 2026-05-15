from __future__ import annotations

from typing import Any

from isotope.features.files.flow import FileFlow


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


def test_file_flow_creates_user_facing_file_summary(tmp_path):
    flow = FileFlow.in_process(tmp_path)

    created = flow.create_text_file(
        name="notes.md",
        summary="useful notes",
        content="private durable file content",
    )
    fetched = flow.get_file(created.file_id)

    assert created.file_id.startswith("artifact_")
    assert created.name == "notes.md"
    assert created.summary == "useful notes"
    assert created.artifact_type == "text"
    assert created.artifact_ref["ref_type"] == "artifact"
    assert created.artifact_ref["artifact_id"] == created.file_id
    assert created.run_id.startswith("run_")
    assert fetched == created
    assert "private durable file content" not in repr(created)
    _assert_no_forbidden_content_keys(created.to_dict())


def test_file_flow_lists_and_reloads_file_summaries(tmp_path):
    flow = FileFlow.in_process(tmp_path)

    first = flow.create_text_file(
        name="first.md",
        summary="first summary",
        content="first private content",
    )
    second = flow.create_text_file(
        name="second.md",
        summary="second summary",
        content="second private content",
    )

    assert flow.list_files() == [first, second]

    reloaded = FileFlow.in_process(tmp_path)

    assert reloaded.get_file(first.file_id) == first
    assert reloaded.get_file(second.file_id) == second
    assert reloaded.list_files() == [first, second]
    _assert_no_forbidden_content_keys(
        {"files": [file_summary.to_dict() for file_summary in reloaded.list_files()]}
    )
