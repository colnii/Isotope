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


def run_long_task_ticks(
    root: Path | str,
    task_id: str,
    *,
    provider: Any,
    max_ticks: int,
    max_tokens: int = 512,
) -> dict[str, Any]:
    if isinstance(max_ticks, bool) or not isinstance(max_ticks, int) or max_ticks <= 0:
        raise ValueError("max_ticks must be a positive integer")
    root_path = Path(root).expanduser()
    store = LongTaskStore(root_path)
    task = store.projection(task_id)
    if task.get("control_state") == "pause":
        return {
            "status": "ok",
            "task": _attach_run_status(root_path, task),
            "ticks": [],
            "stop_reason": "user_paused",
        }
    if task.get("control_state") == "stop":
        return {
            "status": "ok",
            "task": _attach_run_status(root_path, task),
            "ticks": [],
            "stop_reason": "stopped",
        }

    api = InProcessServer(root_path)
    ticks: list[dict[str, Any]] = []
    stop_reason = None
    for tick_index in range(max_ticks):
        current_task = store.projection(task_id)
        if current_task.get("control_state") == "pause":
            stop_reason = "user_paused"
            break
        if current_task.get("control_state") == "stop":
            stop_reason = "stopped"
            break
        tick = api.run_agent_loop_provider_planner_tick(
            str(current_task["run_id"]),
            provider=provider,
            agent_id="agent_long_task",
            tick_id=f"{task_id}_tick_{tick_index + 1}",
            decision_id=f"{task_id}_decision_{tick_index + 1}",
            tick_budget={
                "max_ticks": max_ticks,
                "ticks_used": tick_index,
                "budget_basis": f"long_task:{task_id}",
            },
            max_tokens=max_tokens,
        )
        public_tick = _public_tick_summary(task_id, tick_index, tick)
        ticks.append(public_tick)
        stop_reason = tick.get("stop_reason")
        api.save_checkpoint_for_run(str(current_task["run_id"]))
        if tick.get("tick_status") != "executed":
            break

    latest_task = store.projection(task_id)
    updated_state = api.get_run_state(str(latest_task["run_id"]))
    now = _now()
    store.append_task_record(
        LongTaskRecord(
            task_id=str(latest_task["task_id"]),
            run_id=str(latest_task["run_id"]),
            session_id=str(latest_task["session_id"]),
            goal=str(latest_task["goal"]),
            status=_status_after_ticks(updated_state.status, stop_reason),
            created_at=str(latest_task["created_at"]),
            updated_at=now,
            last_event_id=updated_state.last_event_id,
            last_checkpoint_event_id=updated_state.last_event_id,
            control_state="run",
            summary={
                "phase": "ticked",
                "tick_count": _existing_tick_count(latest_task) + len(ticks),
                "last_selected_step": (
                    ticks[-1]["planner_summary"]["selected_step"] if ticks else None
                ),
                "stop_reason": stop_reason,
            },
        )
    )
    return {
        "status": "ok",
        "task": _attach_run_status(root_path, store.projection(task_id)),
        "ticks": ticks,
        "stop_reason": stop_reason,
    }


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


def _public_tick_summary(
    task_id: str,
    tick_index: int,
    tick: dict[str, Any],
) -> dict[str, Any]:
    provider_result = (
        tick.get("provider_result") if isinstance(tick.get("provider_result"), dict) else {}
    )
    planner_output = (
        provider_result.get("planner_output")
        if isinstance(provider_result.get("planner_output"), dict)
        else {}
    )
    contract = (
        tick.get("planner_contract_result")
        if isinstance(tick.get("planner_contract_result"), dict)
        else {}
    )
    planner_result = (
        contract.get("planner_result")
        if isinstance(contract.get("planner_result"), dict)
        else {}
    )
    return {
        "task_id": task_id,
        "tick_index": tick_index,
        "tick_status": tick.get("tick_status"),
        "stop_reason": tick.get("stop_reason"),
        "before_policy": tick.get("before_policy"),
        "after_policy": tick.get("after_policy"),
        "planner_summary": {
            "selected_step": planner_output.get("selected_step")
            or planner_result.get("selected_step"),
            "provider": provider_result.get("provider"),
            "model": provider_result.get("model"),
        },
        "step_summary": {
            "planner_status": planner_result.get("planner_status"),
            "selected_step": planner_result.get("selected_step"),
        },
    }


def _existing_tick_count(task: dict[str, Any]) -> int:
    summary = task.get("summary")
    if not isinstance(summary, dict):
        return 0
    value = summary.get("tick_count", 0)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _status_after_ticks(run_status: str, stop_reason: object) -> str:
    if run_status == "completed" or stop_reason == "completed":
        return "completed"
    if run_status in {"failed", "denied"} or stop_reason in {"failed", "denied"}:
        return "failed"
    if stop_reason == "awaiting_approval":
        return "blocked"
    if stop_reason in {"user_paused", "stopped"}:
        return "paused" if stop_reason == "user_paused" else "stopped"
    if stop_reason in {"no_next_actions", "blocked"}:
        return "blocked"
    return "queued"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
