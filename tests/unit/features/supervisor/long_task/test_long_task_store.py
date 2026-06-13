from __future__ import annotations

import json

import pytest

from isotope.features.supervisor.long_task import (
    LongTaskRecord,
    LongTaskStore,
    append_long_task_control,
    append_long_task_record,
    long_task_projection,
)


def test_long_task_store_appends_and_folds_projection(tmp_path):
    store = LongTaskStore(tmp_path)
    append_long_task_record(
        store,
        LongTaskRecord(
            task_id="ltask_001",
            run_id="run_001",
            session_id="session_001",
            goal="Ship long tasks",
            status="queued",
            created_at="2026-06-14T00:00:00Z",
            updated_at="2026-06-14T00:00:00Z",
        ),
    )
    append_long_task_control(
        store,
        task_id="ltask_001",
        control="pause",
        reason="User paused from CLI.",
        created_at="2026-06-14T00:01:00Z",
    )

    projection = long_task_projection(store, "ltask_001")

    assert projection["task_id"] == "ltask_001"
    assert projection["status"] == "paused"
    assert projection["control_state"] == "pause"
    assert projection["requires_human"] is True
    assert projection["goal"] == "Ship long tasks"


def test_long_task_public_projection_rejects_raw_content(tmp_path):
    store = LongTaskStore(tmp_path)

    with pytest.raises(ValueError, match="raw long-task payload"):
        append_long_task_record(
            store,
            LongTaskRecord(
                task_id="ltask_raw",
                run_id="run_001",
                session_id="session_001",
                goal="bad",
                status="queued",
                created_at="2026-06-14T00:00:00Z",
                updated_at="2026-06-14T00:00:00Z",
                summary={"raw_content": "hidden"},
            ),
        )


def test_long_task_store_reports_malformed_json_line(tmp_path):
    store = LongTaskStore(tmp_path)
    store.tasks_path.parent.mkdir(parents=True, exist_ok=True)
    store.tasks_path.write_text("{bad json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="tasks.jsonl line 1"):
        store.read_task_records()


def test_long_task_list_orders_latest_update_first(tmp_path):
    store = LongTaskStore(tmp_path)
    append_long_task_record(
        store,
        LongTaskRecord(
            task_id="ltask_old",
            run_id="run_old",
            session_id="session_old",
            goal="Old",
            status="queued",
            created_at="2026-06-14T00:00:00Z",
            updated_at="2026-06-14T00:00:00Z",
        ),
    )
    append_long_task_record(
        store,
        LongTaskRecord(
            task_id="ltask_new",
            run_id="run_new",
            session_id="session_new",
            goal="New",
            status="queued",
            created_at="2026-06-14T00:00:00Z",
            updated_at="2026-06-14T00:02:00Z",
        ),
    )

    assert [item["task_id"] for item in store.list_task_projections()] == [
        "ltask_new",
        "ltask_old",
    ]
    assert json.loads(store.tasks_path.read_text(encoding="utf-8").splitlines()[0])[
        "task_id"
    ] == "ltask_old"
