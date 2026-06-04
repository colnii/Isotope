from __future__ import annotations

import json
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
    assert updated.result_text
    assert updated.result_ref["ref_type"] == "artifact"
    assert fetched == updated
    _assert_no_forbidden_content_keys(updated.to_dict())


def test_task_flow_lists_and_reloads_task_summaries(tmp_path):
    flow = TaskFlow.in_process(tmp_path)

    first = flow.create_task(goal="collect useful notes", first_message="first note")
    second = flow.create_task(goal="write short plan", first_message="plan note")

    assert flow.list_tasks() == [first, second]

    reloaded = TaskFlow.in_process(tmp_path)

    assert reloaded.get_task(first.task_id) == first
    assert reloaded.get_task(second.task_id) == second
    assert reloaded.list_tasks() == [first, second]
    _assert_no_forbidden_content_keys(
        {"tasks": [task_summary.to_dict() for task_summary in reloaded.list_tasks()]}
    )


def test_task_flow_refreshes_reloaded_result_from_artifact_record(tmp_path):
    flow = TaskFlow.in_process(tmp_path)
    created = flow.create_task(goal="collect useful notes", first_message="first note")
    assert created.result_text is not None
    assert created.result_ref is not None

    index_path = tmp_path / "tasks" / "index.json"
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    payload["tasks"][0]["result_text"] = "stale local result"
    payload["tasks"][0]["result_ref"]["extra"] = "stale local field"
    index_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    reloaded = TaskFlow.in_process(tmp_path)
    listed = reloaded.list_tasks()
    refreshed = reloaded.get_task(created.task_id)

    assert listed == [refreshed]
    assert refreshed.result_text == created.result_text
    assert refreshed.result_ref == created.result_ref
    assert reloaded.list_tasks() == [refreshed]
    _assert_no_forbidden_content_keys(refreshed.to_dict())
