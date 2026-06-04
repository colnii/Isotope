"""Persistent public worker-lifecycle projection for Supervisor state."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def default_worker_lifecycle_path(codex_home: Path | str) -> Path:
    return Path(codex_home).expanduser() / "supervisor" / "worker_lifecycle.jsonl"


def record_worker_lifecycle_decision(
    *,
    codex_home: Path | str,
    worker_lifecycle_decision: dict[str, Any],
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any] | None:
    projection = worker_lifecycle_projection_payload(
        worker_lifecycle_decision=worker_lifecycle_decision
    )
    if projection.get("status") != "ok":
        return None
    if read_latest_worker_lifecycle(codex_home=codex_home) == projection:
        return None
    event = {
        "event": "worker_lifecycle_projection",
        "created_at": _ensure_aware_utc((now or _utc_now)()).isoformat(),
        "worker_lifecycle": projection,
    }
    _append_worker_lifecycle_event(default_worker_lifecycle_path(codex_home), event)
    return event


def read_latest_worker_lifecycle(*, codex_home: Path | str) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    for event in _read_worker_lifecycle_events(default_worker_lifecycle_path(codex_home)):
        if event.get("event") != "worker_lifecycle_projection":
            continue
        lifecycle = event.get("worker_lifecycle")
        if isinstance(lifecycle, dict):
            latest = dict(lifecycle)
    return latest


def worker_lifecycle_projection_payload(
    *,
    worker_lifecycle_decision: dict[str, Any] | None = None,
    state_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decision = _worker_lifecycle_decision(
        worker_lifecycle_decision,
        state_snapshot=state_snapshot,
    )
    if not isinstance(decision, dict):
        return {"status": "absent"}
    if decision.get("status") == "ok" and "policy_status" in decision:
        return _copy_worker_lifecycle_projection(decision)
    policy = decision.get("policy") if isinstance(decision.get("policy"), dict) else {}
    return {
        "status": "ok",
        "stage": _lifecycle_scalar(decision.get("stage")),
        "next_step": _lifecycle_scalar(decision.get("next_step")),
        "policy_status": _lifecycle_scalar(policy.get("policy_status")),
        "program_action": _lifecycle_scalar(policy.get("program_action")),
        "remaining_step": _lifecycle_scalar(policy.get("remaining_step")),
        "blocked_reason": _lifecycle_scalar(policy.get("blocked_reason")),
        "timeline": _worker_lifecycle_timeline_payload(decision.get("timeline")),
    }


def _append_worker_lifecycle_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def _read_worker_lifecycle_events(path: Path) -> tuple[dict[str, Any], ...]:
    if not path.is_file():
        return ()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(raw, dict):
            events.append(raw)
    return tuple(events)


def _worker_lifecycle_decision(
    worker_lifecycle_decision: dict[str, Any] | None,
    *,
    state_snapshot: dict[str, Any] | None,
) -> Any:
    if isinstance(worker_lifecycle_decision, dict):
        return worker_lifecycle_decision
    if not isinstance(state_snapshot, dict):
        return None
    decision = state_snapshot.get("worker_lifecycle_decision")
    if isinstance(decision, dict):
        return decision
    return state_snapshot.get("worker_lifecycle")


def _copy_worker_lifecycle_projection(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "ok",
        "stage": _lifecycle_scalar(decision.get("stage")),
        "next_step": _lifecycle_scalar(decision.get("next_step")),
        "policy_status": _lifecycle_scalar(decision.get("policy_status")),
        "program_action": _lifecycle_scalar(decision.get("program_action")),
        "remaining_step": _lifecycle_scalar(decision.get("remaining_step")),
        "blocked_reason": _lifecycle_scalar(decision.get("blocked_reason")),
        "timeline": _worker_lifecycle_timeline_payload(decision.get("timeline")),
    }


def _worker_lifecycle_timeline_payload(timeline: Any) -> list[dict[str, Any]]:
    if not isinstance(timeline, list):
        return []
    items: list[dict[str, Any]] = []
    for item in timeline:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "stage": _lifecycle_scalar(item.get("stage")),
                "action": _lifecycle_scalar(item.get("action")),
                "source": _lifecycle_scalar(item.get("source")),
                "status": _lifecycle_scalar(item.get("status")),
                "executed": item.get("executed") is True,
            }
        )
    return items


def _lifecycle_scalar(value: Any) -> str | bool | int | float | None:
    if isinstance(value, (str, bool, int, float)):
        return value
    return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
