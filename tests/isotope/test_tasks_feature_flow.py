from __future__ import annotations

from typing import Any

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


def test_task_flow_creates_user_facing_task_summary(tmp_path):
    flow = TaskFlow.in_process(tmp_path)

    created = flow.create_task(goal="collect useful notes", first_message="first note")
    updated = flow.submit_message(created.task_id, "second note")
    fetched = flow.get_task(created.task_id)

    assert created.task_id.startswith("task_")
    assert created.goal == "collect useful notes"
    assert created.status == "completed"
    assert created.turn_count == 1
    assert updated.turn_count == 2
    assert updated.run_ids != created.run_ids
    assert updated.latest_run_id == updated.run_ids[-1]
    assert updated.result_summary
    assert updated.result_ref["ref_type"] == "artifact"
    assert fetched == updated
    _assert_no_forbidden_content_keys(updated.to_dict())
