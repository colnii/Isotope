from __future__ import annotations

from isotope.features.supervisor.long_task.runtime import (
    create_long_task,
    list_long_tasks,
    pause_long_task,
    resume_long_task,
    status_long_task,
    stop_long_task,
)


def test_create_long_task_creates_run_and_queued_projection(tmp_path):
    result = create_long_task(tmp_path, goal="Run a long Supervisor task.")

    assert result["status"] == "ok"
    assert result["task"]["status"] == "queued"
    assert result["task"]["goal"] == "Run a long Supervisor task."
    assert result["task"]["run_id"].startswith("run_")
    assert result["task"]["session_id"].startswith("session_")

    status = status_long_task(tmp_path, result["task"]["task_id"])
    assert status["task"]["task_id"] == result["task"]["task_id"]
    assert status["task"]["run_status"] == "running"


def test_pause_resume_and_stop_long_task_update_projection(tmp_path):
    task_id = create_long_task(tmp_path, goal="Pause me.")["task"]["task_id"]

    paused = pause_long_task(tmp_path, task_id, reason="Need user review.")
    assert paused["task"]["status"] == "paused"
    assert paused["task"]["requires_human"] is True

    resumed = resume_long_task(tmp_path, task_id, reason="Continue.")
    assert resumed["task"]["status"] == "queued"
    assert resumed["task"]["control_state"] == "resume"

    stopped = stop_long_task(tmp_path, task_id, reason="User stopped.")
    assert stopped["task"]["status"] == "stopped"
    assert stopped["task"]["requires_human"] is False


def test_list_long_tasks_returns_compact_summary(tmp_path):
    first = create_long_task(tmp_path, goal="First.")["task"]["task_id"]
    second = create_long_task(tmp_path, goal="Second.")["task"]["task_id"]
    pause_long_task(tmp_path, first, reason="Hold first.")

    result = list_long_tasks(tmp_path)

    assert result["status"] == "ok"
    assert result["summary"]["task_count"] == 2
    assert result["summary"]["requires_human_count"] == 1
    assert {task["task_id"] for task in result["tasks"]} == {first, second}
