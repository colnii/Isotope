"""Lifecycle trace payload helpers for the Supervisor CLI."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _default_api() -> Any:
    from isotope.features.supervisor import runner as api

    return api


def lifecycle_trace_payload(
    args: Any,
    *,
    lightweight: bool = False,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    codex_home = Path(args.codex_home)
    active_goals = api._active_goal_dicts_for_codex_home(
        codex_home,
        include_status=True,
    )
    records = api.read_managed_records(api.default_registry_path(codex_home))
    record_limit = 40 if lightweight else None
    visible_records = records[-record_limit:] if record_limit else records
    active_records = [
        managed_record_trace_dict(record, api=api)
        for record in visible_records
    ]
    archived_events = [
        record
        for record in latest_managed_record_events(codex_home, api=api)
        if record.status == "archived"
    ]
    archive_limit = 20 if lightweight else None
    visible_archived_events = (
        archived_events[-archive_limit:] if archive_limit else archived_events
    )
    archived_records = [
        managed_record_trace_dict(record, api=api)
        for record in visible_archived_events
    ]
    active_decisions = api._decision_request_dicts(args)
    recent_decision_answers = api._decision_answer_dicts(args)
    merge_workers = [
        record
        for record in active_records
        if record.get("worker_role") == api.MERGE_DISPATCH_WORKER_ROLE
    ]
    repair_workers = [
        record
        for record in active_records
        if record.get("worker_role") == api.MERGE_REPAIR_WORKER_ROLE
    ]
    stages = {
        "goal_queue": {
            "active": active_goals,
        },
        "workers": {
            "active": active_records,
        },
        "merge": {
            "merge_workers": merge_workers,
            "repair_workers": repair_workers,
        },
        "decisions": {
            "active": active_decisions,
            "recent_answers": recent_decision_answers,
        },
        "cleanup": {
            "candidates": api._cleanup_candidate_dicts(codex_home),
            "archived_workers": archived_records,
        },
    }
    summary = {
        "active_goals": len(active_goals),
        "active_managed_workers": len(records),
        "visible_managed_workers": len(active_records),
        "hidden_managed_workers": len(records) - len(active_records),
        "active_decisions": len(active_decisions),
        "merge_workers": len(merge_workers),
        "repair_workers": len(repair_workers),
        "archived_workers": len(archived_events),
        "visible_archived_workers": len(archived_records),
        "hidden_archived_workers": len(archived_events) - len(archived_records),
    }
    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "next_attention": lifecycle_next_attention(stages),
        "stages": lightweight_lifecycle_stages(stages, api=api)
        if lightweight
        else stages,
    }


def lightweight_lifecycle_stages(
    stages: dict[str, Any],
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    workers = stages.get("workers") if isinstance(stages.get("workers"), dict) else {}
    goals = stages.get("goal_queue") if isinstance(stages.get("goal_queue"), dict) else {}
    decisions = stages.get("decisions") if isinstance(stages.get("decisions"), dict) else {}
    merge = stages.get("merge") if isinstance(stages.get("merge"), dict) else {}
    cleanup = stages.get("cleanup") if isinstance(stages.get("cleanup"), dict) else {}
    return {
        "goal_queue": {
            "active_count": len(goals.get("active", [])),
        },
        "workers": {
            "active_count": len(workers.get("active", [])),
            "active": [
                lightweight_lifecycle_worker(worker, api=api)
                for worker in workers.get("active", [])
                if isinstance(worker, dict)
            ],
        },
        "merge": {
            "merge_worker_count": len(merge.get("merge_workers", [])),
            "repair_worker_count": len(merge.get("repair_workers", [])),
        },
        "decisions": {
            "active_count": len(decisions.get("active", [])),
            "recent_answer_count": len(decisions.get("recent_answers", [])),
        },
        "cleanup": {
            "candidate_count": len(cleanup.get("candidates", [])),
            "candidates": [
                lightweight_cleanup_candidate(candidate, api=api)
                for candidate in cleanup.get("candidates", [])[:20]
                if isinstance(candidate, dict)
            ],
            "archived_worker_count": len(cleanup.get("archived_workers", [])),
        },
    }


def lightweight_lifecycle_worker(
    worker: dict[str, Any],
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    return api._drop_none_values(
        {
            "name": worker.get("name"),
            "record_id": worker.get("record_id"),
            "status": worker.get("status"),
            "worker_role": worker.get("worker_role"),
            "protocol": worker.get("protocol"),
            "still_working": worker.get("still_working"),
        }
    )


def lightweight_cleanup_candidate(
    candidate: dict[str, Any],
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    return api._drop_none_values(
        {
            "kind": candidate.get("kind"),
            "name": candidate.get("name") or candidate.get("target_name"),
            "goal_id": candidate.get("goal_id"),
            "record_id": candidate.get("record_id"),
            "notification_id": candidate.get("notification_id"),
            "archived": candidate.get("archived"),
        }
    )


def latest_managed_record_events(codex_home: Path, *, api: Any | None = None) -> list[Any]:
    if api is None:
        api = _default_api()
    latest_by_record_id: dict[str, Any] = {}
    for record in api.read_managed_record_events(api.default_registry_path(codex_home)):
        latest_by_record_id[record.record_id] = record
    return list(latest_by_record_id.values())


def managed_record_trace_dict(record: Any, *, api: Any | None = None) -> dict[str, Any]:
    if api is None:
        api = _default_api()
    protocol = api._managed_record_supervisor_protocol(record)
    return api._drop_none_values(
        {
            "name": record.name,
            "record_id": record.record_id,
            "cwd": record.cwd,
            "pid": record.pid,
            "backend": record.backend,
            "tmux_session": record.tmux_session,
            "status": record.status,
            "worker_role": getattr(record, "worker_role", "worker"),
            "started_at": record.started_at,
            "resume_session_id": record.resume_session_id,
            "resume_last": record.resume_last or None,
            "protocol": protocol or None,
            "still_working": api._managed_record_is_still_working(record),
        }
    )


def lifecycle_next_attention(stages: dict[str, Any]) -> dict[str, Any]:
    decisions = stages.get("decisions")
    active_decisions = (
        decisions.get("active")
        if isinstance(decisions, dict) and isinstance(decisions.get("active"), list)
        else []
    )
    if active_decisions:
        first = active_decisions[0]
        return {
            "kind": "answer_decision",
            "request_id": first.get("request_id"),
            "target_name": first.get("target_name"),
        }
    cleanup = stages.get("cleanup")
    cleanup_candidates = (
        cleanup.get("candidates")
        if isinstance(cleanup, dict) and isinstance(cleanup.get("candidates"), list)
        else []
    )
    if cleanup_candidates:
        first = cleanup_candidates[0]
        return {
            "kind": "archive_cleanup",
            "target": first.get("name")
            or first.get("goal_id")
            or first.get("notification_id"),
        }
    workers = stages.get("workers")
    active_workers = (
        workers.get("active")
        if isinstance(workers, dict) and isinstance(workers.get("active"), list)
        else []
    )
    waiting_workers = [
        worker
        for worker in active_workers
        if lifecycle_worker_is_waiting(worker)
    ]
    if waiting_workers:
        return {
            "kind": "wait_workers",
            "active_managed_workers": len(waiting_workers),
        }
    merge = stages.get("merge")
    repair_workers = (
        merge.get("repair_workers")
        if isinstance(merge, dict) and isinstance(merge.get("repair_workers"), list)
        else []
    )
    for worker in repair_workers:
        protocol = worker.get("protocol")
        status = protocol.get("status") if isinstance(protocol, dict) else None
        if status != "done":
            return {
                "kind": "wait_repair",
                "target_name": worker.get("name"),
            }
    goals = stages.get("goal_queue")
    active_goals = (
        goals.get("active")
        if isinstance(goals, dict) and isinstance(goals.get("active"), list)
        else []
    )
    if active_goals:
        return {
            "kind": "continue_goal",
            "target_name": active_goals[0].get("target_name"),
        }
    return {"kind": "idle"}


def lifecycle_worker_is_waiting(worker: Any) -> bool:
    if not isinstance(worker, dict):
        return False
    protocol = worker.get("protocol")
    protocol_status = (
        protocol.get("status")
        if isinstance(protocol, dict) and isinstance(protocol.get("status"), str)
        else None
    )
    if protocol_status in {"done", "blocked", "needs_user"}:
        return False
    if worker.get("still_working") is True:
        return True
    record_status = worker.get("status")
    return record_status in {"launched", "resumed", "adopted"}


def print_lifecycle_trace_plain(payload: dict[str, Any]) -> None:
    summary = payload.get("summary") or {}
    print("Supervisor 生命周期 trace")
    print(f"- active goals: {summary.get('active_goals', 0)}")
    print(f"- active workers: {summary.get('active_managed_workers', 0)}")
    print(f"- active decisions: {summary.get('active_decisions', 0)}")
    print(f"- merge workers: {summary.get('merge_workers', 0)}")
    print(f"- repair workers: {summary.get('repair_workers', 0)}")
    print(f"- archived workers: {summary.get('archived_workers', 0)}")
    attention = payload.get("next_attention") or {}
    print(f"下一关注：{attention.get('kind', 'unknown')}")
