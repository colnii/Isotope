from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path

import pytest

from isotope.features.supervisor.long_task.provider import (
    resolve_long_task_planner_provider_from_env,
)
from isotope.features.supervisor.long_task.runtime import (
    create_long_task,
    run_long_task_ticks,
    status_long_task,
)
from isotope.runtime.in_process import InProcessServer


_LIVE_ENV = "ISOTOPE_RUN_MIMO_LONG_TASK_LIVE"
_LOG_DIR_ENV = "ISOTOPE_LONG_TASK_LIVE_LOG_DIR"
_PROVIDER_ENV = "ISOTOPE_LONG_TASK_LLM_PROVIDER"
_MARKER = "MIMO_LONG_TASK_SMOKE"
_EVIDENCE_STEP = "record_turn_memory"
_COMPLETION_STEP = "complete_long_task"


@pytest.mark.skipif(
    os.environ.get(_LIVE_ENV) != "1",
    reason="live Mimo long-task smoke is opt-in",
)
def test_live_mimo_long_task_records_evidence_then_completes_with_log():
    log_root = _new_log_root()
    state_root = log_root / "state"
    log_path = log_root / "mimo-long-task-live.json"
    log_root.mkdir(parents=True, exist_ok=True)

    task_id = ""
    run_id = ""
    try:
        provider = resolve_long_task_planner_provider_from_env(
            {**os.environ, _PROVIDER_ENV: "mimo"},
            timeout=90,
        )
    except ValueError as exc:
        pytest.skip(f"mimo long-task provider unavailable: {exc}")

    try:
        created = create_long_task(state_root, goal=_live_goal())
        task_id = created["task"]["task_id"]
        run_id = created["task"]["run_id"]

        result = run_long_task_ticks(
            state_root,
            task_id,
            provider=provider,
            max_ticks=3,
            max_tokens=2048,
        )
        final_status = status_long_task(state_root, task_id)
        log_payload = _safe_log_payload(
            status="completed",
            state_root=state_root,
            task_id=task_id,
            run_id=run_id,
            result=result,
            final_status=final_status,
        )
        _write_log(log_path, log_payload)
    except Exception as exc:
        _write_log(
            log_path,
            _safe_log_payload(
                status="failed",
                state_root=state_root,
                task_id=task_id,
                run_id=run_id,
                error={
                    "type": type(exc).__name__,
                    "message": str(exc)[:600],
                },
            ),
        )
        raise

    ticks = result["ticks"]
    selected_steps = [tick["planner_summary"]["selected_step"] for tick in ticks]
    assert result["status"] == "ok"
    assert 2 <= len(ticks) <= 3
    assert result["stop_reason"] == "completed"
    assert result["task"]["status"] == "completed"
    assert result["task"]["summary"]["phase"] == "completed"
    assert result["task"]["summary"]["final_summary"]
    assert result["task"]["summary"]["tick_count"] == len(ticks)
    assert [tick["tick_status"] for tick in ticks] == ["executed"] * len(ticks)
    assert [tick["planner_summary"]["provider"] for tick in ticks] == ["mimo"] * len(ticks)
    assert selected_steps[0] == _EVIDENCE_STEP
    assert selected_steps[-1] == _COMPLETION_STEP
    assert set(selected_steps).issubset({_EVIDENCE_STEP, _COMPLETION_STEP})
    assert log_path.is_file()
    assert "raw_response" not in json.dumps(result, ensure_ascii=False)


def _live_goal() -> str:
    return (
        "Live Mimo long-task smoke. If default_context.memory has no result "
        f"whose summary contains {_MARKER}, choose decision.step=record_turn_memory. "
        f"The record_turn_memory request.summary must contain {_MARKER}; "
        "request.content must be a non-empty object with "
        f"marker={_MARKER}. After default_context.memory contains that marker, "
        "choose decision.step=complete_long_task with a non-empty final_summary, "
        "evidence list, and remaining_risks list. Do not choose query_memory, "
        "call_capability, terminal, worker, approval, or artifact steps."
    )


def _new_log_root() -> Path:
    base = Path(os.environ.get(_LOG_DIR_ENV, ".dev-eval-runs/long-task-mimo-live"))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return base / f"run-{stamp}-{os.getpid()}"


def _safe_log_payload(
    *,
    status: str,
    state_root: Path,
    task_id: str,
    run_id: str,
    result: dict | None = None,
    final_status: dict | None = None,
    error: dict | None = None,
) -> dict:
    event_path = state_root / "runs" / run_id / "events.jsonl" if run_id else None
    payload = {
        "kind": "mimo_long_task_live_smoke_log",
        "status": status,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "rules": {
            "provider": "mimo",
            "max_ticks": 3,
            "required_steps": [_EVIDENCE_STEP, _COMPLETION_STEP],
            "marker": _MARKER,
        },
        "paths": {
            "state_root": str(state_root),
            "events_jsonl": str(event_path) if event_path is not None else None,
        },
        "task_id": task_id or None,
        "run_id": run_id or None,
        "result": result,
        "final_status": final_status,
        "events": _event_summaries(state_root, run_id) if run_id else [],
        "error": error,
    }
    assert "raw_response" not in json.dumps(payload, ensure_ascii=False)
    return payload


def _event_summaries(state_root: Path, run_id: str) -> list[dict]:
    api = InProcessServer(state_root)
    return [
        {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "payload_keys": sorted(event.payload.keys()),
        }
        for event in api.get_events(run_id)
    ]


def _write_log(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
