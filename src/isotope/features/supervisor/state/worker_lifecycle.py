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
    worker_lifecycle_execution: dict[str, Any] | None = None,
    worker_lifecycle_execution_result: dict[str, Any] | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any] | None:
    projection = worker_lifecycle_projection_payload(
        worker_lifecycle_decision=worker_lifecycle_decision
    )
    if projection.get("status") != "ok":
        return None
    projected_event = {
        "worker_lifecycle": projection,
        "worker_lifecycle_execution": worker_lifecycle_execution_projection_payload(
            worker_lifecycle_execution
        ),
        "worker_lifecycle_execution_result": worker_lifecycle_execution_result_payload(
            worker_lifecycle_execution_result
        ),
    }
    projected_event = {
        key: value
        for key, value in projected_event.items()
        if isinstance(value, dict) and value.get("status") != "absent"
    }
    latest_event = read_latest_worker_lifecycle_event(codex_home=codex_home)
    if (
        isinstance(latest_event, dict)
        and _event_projection_payload(latest_event) == projected_event
    ):
        return None
    event = {
        "event": "worker_lifecycle_projection",
        "created_at": _ensure_aware_utc((now or _utc_now)()).isoformat(),
        **projected_event,
    }
    _append_worker_lifecycle_event(default_worker_lifecycle_path(codex_home), event)
    return event


def read_latest_worker_lifecycle(*, codex_home: Path | str) -> dict[str, Any] | None:
    latest = read_latest_worker_lifecycle_event(codex_home=codex_home)
    if not isinstance(latest, dict):
        return None
    lifecycle = latest.get("worker_lifecycle")
    return dict(lifecycle) if isinstance(lifecycle, dict) else None


def read_latest_worker_lifecycle_event(
    *,
    codex_home: Path | str,
) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    for event in _read_worker_lifecycle_events(default_worker_lifecycle_path(codex_home)):
        if event.get("event") != "worker_lifecycle_projection":
            continue
        lifecycle = event.get("worker_lifecycle")
        if isinstance(lifecycle, dict):
            latest = dict(event)
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


def worker_lifecycle_execution_projection_payload(
    worker_lifecycle_execution: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(worker_lifecycle_execution, dict):
        return {"status": "absent"}
    payload = {
        "kind": _lifecycle_scalar(worker_lifecycle_execution.get("kind")),
        "source": _lifecycle_scalar(worker_lifecycle_execution.get("source")),
        "next_step": _lifecycle_scalar(worker_lifecycle_execution.get("next_step")),
        "status": _lifecycle_scalar(worker_lifecycle_execution.get("status")),
    }
    cleanup_candidates = _cleanup_candidate_payloads(
        worker_lifecycle_execution.get("cleanup_candidates")
    )
    if cleanup_candidates:
        payload["cleanup_candidates"] = cleanup_candidates
    delete_worktree_actions = _delete_worktree_action_payloads(
        worker_lifecycle_execution.get("delete_worktree_actions")
    )
    if delete_worktree_actions:
        payload["delete_worktree_actions"] = delete_worktree_actions
    merge_dispatch = _merge_dispatch_payload(
        worker_lifecycle_execution.get("merge_dispatch")
    )
    if merge_dispatch:
        payload["merge_dispatch"] = merge_dispatch
    return payload


def worker_lifecycle_execution_result_payload(
    worker_lifecycle_execution_result: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(worker_lifecycle_execution_result, dict):
        return {"status": "absent"}
    result_actions = _execution_result_action_payloads(
        worker_lifecycle_execution_result
    )
    count = _lifecycle_scalar(worker_lifecycle_execution_result.get("count"))
    if count is None and result_actions:
        count = len(result_actions)
    payload = {
        "kind": _lifecycle_scalar(worker_lifecycle_execution_result.get("kind")),
        "source": _lifecycle_scalar(worker_lifecycle_execution_result.get("source")),
        "skipped": worker_lifecycle_execution_result.get("skipped") is True,
        "reason": _lifecycle_scalar(worker_lifecycle_execution_result.get("reason")),
        "count": count,
    }
    if result_actions:
        payload["result_actions"] = result_actions
    return payload


def _execution_result_action_payloads(result: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    actions.extend(
        _deleted_result_action_payload(item)
        for item in _mapping_items(result.get("deleted"))
    )
    actions.extend(
        _archived_result_action_payload(item)
        for item in _mapping_items(result.get("archived"))
    )
    managed = result.get("managed")
    if isinstance(managed, dict):
        actions.append(
            _result_action_payload(
                kind=_lifecycle_scalar(result.get("display_kind"))
                or _lifecycle_scalar(result.get("kind"))
                or "launch_session",
                status="launched",
                target_name=_lifecycle_scalar(result.get("target_name"))
                or _lifecycle_scalar(managed.get("name")),
                record_id=_lifecycle_scalar(managed.get("record_id")),
                reason=_lifecycle_scalar(result.get("reason")),
            )
        )
    return [action for action in actions if action]


def _deleted_result_action_payload(item: dict[str, Any]) -> dict[str, Any]:
    managed = item.get("managed") if isinstance(item.get("managed"), dict) else {}
    status = "skipped" if item.get("skipped") is True else "deleted"
    return _result_action_payload(
        kind=_lifecycle_scalar(item.get("kind")) or "delete_worktree",
        status=status,
        target_name=_lifecycle_scalar(item.get("target_name"))
        or _lifecycle_scalar(managed.get("name")),
        record_id=_lifecycle_scalar(item.get("record_id"))
        or _lifecycle_scalar(managed.get("record_id")),
        reason=_lifecycle_scalar(item.get("reason")),
    )


def _archived_result_action_payload(item: dict[str, Any]) -> dict[str, Any]:
    managed = item.get("managed") if isinstance(item.get("managed"), dict) else {}
    status = "skipped" if item.get("skipped") is True else "archived"
    return _result_action_payload(
        kind=_lifecycle_scalar(item.get("kind")) or "managed_worker",
        status=status,
        target_name=_lifecycle_scalar(item.get("target_name"))
        or _lifecycle_scalar(item.get("name"))
        or _lifecycle_scalar(managed.get("name")),
        record_id=_lifecycle_scalar(item.get("record_id"))
        or _lifecycle_scalar(managed.get("record_id")),
        reason=_lifecycle_scalar(item.get("reason")),
    )


def _result_action_payload(
    *,
    kind: str | bool | int | float | None,
    status: str,
    target_name: str | bool | int | float | None,
    record_id: str | bool | int | float | None,
    reason: str | bool | int | float | None,
) -> dict[str, Any]:
    payload = {
        "kind": kind,
        "target_name": target_name,
        "record_id": record_id,
        "status": status,
        "reason": reason,
    }
    return {
        key: value
        for key, value in payload.items()
        if value is not None and value is not False
    }


def _mapping_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


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


def _cleanup_candidate_payloads(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        candidate = {
            "kind": _lifecycle_scalar(item.get("kind")),
            "name": _lifecycle_scalar(item.get("name")),
            "record_id": _lifecycle_scalar(item.get("record_id")),
        }
        items.append(
            {key: value for key, value in candidate.items() if value is not None}
        )
    return items


def _delete_worktree_action_payloads(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        action = {
            "kind": _lifecycle_scalar(item.get("kind")),
            "target_name": _lifecycle_scalar(item.get("target_name")),
            "record_id": _lifecycle_scalar(item.get("record_id")),
            "base_ref": _lifecycle_scalar(item.get("base_ref")),
            "source": _lifecycle_scalar(item.get("source")),
        }
        evidence = _delete_evidence_payload(item.get("delete_evidence"))
        if evidence:
            action["delete_evidence"] = evidence
        items.append(
            {key: value for key, value in action.items() if value is not None}
        )
    return items


def _delete_evidence_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    evidence = {
        "archived": _lifecycle_bool(value.get("archived")),
        "supervisor_protocol_status": _lifecycle_scalar(
            value.get("supervisor_protocol_status")
        ),
        "supervisor_worktree": _lifecycle_bool(value.get("supervisor_worktree")),
        "integration_group": _lifecycle_scalar(value.get("integration_group")),
        "main_contains_worker": _lifecycle_bool(value.get("main_contains_worker")),
        "main_has_worker_patch": _lifecycle_bool(value.get("main_has_worker_patch")),
        "dirty": _lifecycle_bool(value.get("dirty")),
        "base_ref": _lifecycle_scalar(value.get("base_ref")),
    }
    return {key: item for key, item in evidence.items() if item is not None}


def _merge_dispatch_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    launch_spec = value.get("launch_spec")
    launch_spec = launch_spec if isinstance(launch_spec, dict) else {}
    payload = {
        "status": _lifecycle_scalar(value.get("status")),
        "target_name": _lifecycle_scalar(launch_spec.get("target_name")),
        "source": _lifecycle_scalar(launch_spec.get("source")),
    }
    return {key: value for key, value in payload.items() if value is not None}


def _event_projection_payload(event: dict[str, Any]) -> dict[str, Any]:
    return {
        key: dict(value)
        for key, value in event.items()
        if key.startswith("worker_lifecycle") and isinstance(value, dict)
    }


def _lifecycle_scalar(value: Any) -> str | bool | int | float | None:
    if isinstance(value, (str, bool, int, float)):
        return value
    return None


def _lifecycle_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
