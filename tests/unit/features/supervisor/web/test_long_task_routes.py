from __future__ import annotations

import pytest

from isotope.features.supervisor.desktop_snapshot import build_desktop_snapshot
from isotope.features.supervisor.long_task.runtime import create_long_task
from isotope.features.supervisor.web.routes.long_tasks import (
    desktop_long_task_control_id_from_path,
    desktop_long_task_id_from_path,
    parse_long_task_control_payload,
    parse_long_task_create_payload,
)


def test_long_task_route_helpers_parse_paths_and_payloads():
    assert desktop_long_task_id_from_path("/desktop/long-tasks/ltask%201") == "ltask 1"
    assert desktop_long_task_id_from_path("/desktop/long-tasks/bad%2Fid") is None
    assert (
        desktop_long_task_control_id_from_path("/desktop/long-tasks/ltask%201/control")
        == "ltask 1"
    )
    assert parse_long_task_create_payload({"goal": "  Run long task  "}) == {
        "goal": "Run long task"
    }
    assert parse_long_task_control_payload(
        {"control": "pause", "reason": "Need review."}
    ) == {
        "control": "pause",
        "reason": "Need review.",
    }
    with pytest.raises(ValueError, match="control must be pause, resume, or stop"):
        parse_long_task_control_payload({"control": "delete", "reason": "bad"})


def test_desktop_snapshot_includes_long_task_projection(tmp_path):
    task = create_long_task(tmp_path, goal="Visible in desktop.")["task"]

    snapshot = build_desktop_snapshot(state_root=tmp_path)

    assert snapshot["longTasks"]["summary"]["task_count"] == 1
    assert snapshot["longTasks"]["tasks"][0]["task_id"] == task["task_id"]
