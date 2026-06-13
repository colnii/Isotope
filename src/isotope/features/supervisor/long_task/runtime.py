"""Runtime operations for Supervisor long tasks."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from isotope.platform.ids import new_id, reserve_ids
from isotope.runtime.in_process import InProcessServer

from .contracts import LongTaskRecord
from .store import LongTaskStore, append_long_task_control


TERMINAL_RUN_STATUSES = {"completed", "failed", "denied"}


def create_long_task(root: Path | str, *, goal: str) -> dict[str, Any]:
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("goal must be a non-empty string")
    root_path = Path(root).expanduser()
    store = LongTaskStore(root_path)
    reserve_ids(record.task_id for record in store.read_task_records())

    api = InProcessServer(root_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal.strip())
    run_state = api.get_run_state(run["run_id"])
    checkpoint = api.save_checkpoint_for_run(run["run_id"])
    now = _now()
    record = store.append_task_record(
        LongTaskRecord(
            task_id=new_id("ltask"),
            run_id=run["run_id"],
            session_id=session["session_id"],
            goal=goal.strip(),
            status="queued",
            created_at=now,
            updated_at=now,
            last_event_id=run_state.last_event_id,
            last_checkpoint_event_id=checkpoint["basis_event_id"],
            summary={"phase": "queued"},
        )
    )
    return {"status": "ok", "task": _attach_run_status(root_path, record.to_dict())}


def status_long_task(root: Path | str, task_id: str) -> dict[str, Any]:
    root_path = Path(root).expanduser()
    return {
        "status": "ok",
        "task": _attach_run_status(root_path, LongTaskStore(root_path).projection(task_id)),
    }


def list_long_tasks(root: Path | str) -> dict[str, Any]:
    root_path = Path(root).expanduser()
    tasks = [
        _attach_run_status(root_path, task)
        for task in LongTaskStore(root_path).list_task_projections()
    ]
    return {
        "status": "ok",
        "summary": {
            "task_count": len(tasks),
            "requires_human_count": sum(1 for task in tasks if task.get("requires_human")),
        },
        "tasks": tasks,
    }


def pause_long_task(root: Path | str, task_id: str, *, reason: str) -> dict[str, Any]:
    return _control_long_task(root, task_id, control="pause", reason=reason)


def resume_long_task(root: Path | str, task_id: str, *, reason: str) -> dict[str, Any]:
    root_path = Path(root).expanduser()
    projection = _attach_run_status(root_path, LongTaskStore(root_path).projection(task_id))
    if projection.get("run_status") in TERMINAL_RUN_STATUSES:
        raise ValueError("terminal long task cannot be resumed")
    return _control_long_task(root_path, task_id, control="resume", reason=reason)


def stop_long_task(root: Path | str, task_id: str, *, reason: str) -> dict[str, Any]:
    return _control_long_task(root, task_id, control="stop", reason=reason)


def _control_long_task(
    root: Path | str,
    task_id: str,
    *,
    control: str,
    reason: str,
) -> dict[str, Any]:
    root_path = Path(root).expanduser()
    store = LongTaskStore(root_path)
    store.projection(task_id)
    append_long_task_control(
        store,
        task_id=task_id,
        control=control,
        reason=reason,
        created_at=_now(),
    )
    return {
        "status": "ok",
        "task": _attach_run_status(root_path, store.projection(task_id)),
    }


def _attach_run_status(root: Path, task: dict[str, Any]) -> dict[str, Any]:
    run_state = InProcessServer(root).get_run_state(str(task["run_id"]))
    return {
        **task,
        "run_status": run_state.status,
        "run_last_event_id": run_state.last_event_id,
    }


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
