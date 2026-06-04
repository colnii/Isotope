"""Pure worker lifecycle decisions for Supervisor loop planning."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def build_worker_lifecycle_decision(
    *,
    worker_reviews: Mapping[str, Any] | None = None,
    integration_review: Mapping[str, Any] | None = None,
    merge_dispatch: Mapping[str, Any] | None = None,
    cleanup_candidates: Sequence[Mapping[str, Any]] | None = None,
    cleanup_archived: Sequence[Mapping[str, Any]] | None = None,
    cleanup_deleted_worktrees: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    del worker_reviews
    integration_summary = _integration_summary(integration_review)
    cleanup_count = len(cleanup_candidates or [])
    archived_items = [dict(item) for item in cleanup_archived or []]
    deleted_worktree_items = [
        dict(item) for item in cleanup_deleted_worktrees or []
    ]
    summary = {
        **integration_summary,
        "cleanup_candidates": cleanup_count,
        "cleanup_archived": len(archived_items),
        "cleanup_deleted_worktrees": len(deleted_worktree_items),
    }
    timeline = _timeline(
        integration_summary=integration_summary,
        merge_dispatch=merge_dispatch,
        cleanup_count=cleanup_count,
        archived_items=archived_items,
        deleted_worktree_items=deleted_worktree_items,
    )
    if deleted_worktree_items:
        return _decision(
            action="cleanup_worktree",
            reason="archived worker worktrees deleted",
            source="cleanup",
            summary=summary,
            execution=deleted_worktree_items,
            timeline=timeline,
        )
    if archived_items:
        return _decision(
            action="archive_integrated",
            reason="integrated workers archived",
            source="cleanup",
            summary=summary,
            execution=archived_items,
            timeline=timeline,
        )
    if merge_dispatch is not None:
        status = _text(merge_dispatch.get("status"))
        summary["merge_dispatch_status"] = status
        running_worker = merge_dispatch.get("running_worker")
        if isinstance(running_worker, Mapping):
            summary["running_worker"] = dict(running_worker)
        if status == "worker_already_running":
            return _decision(
                action="monitor",
                reason="merge worker already running",
                source="integration_review",
                summary=summary,
                timeline=timeline,
            )
    if integration_summary["conflict_risk"] or integration_summary["needs_review"]:
        return _decision(
            action="needs_human",
            reason="integration review has conflict or review-required workers",
            source="integration_review",
            summary=summary,
            timeline=timeline,
        )
    if integration_summary["ready_to_integrate"] and merge_dispatch is not None:
        return _decision(
            action="dispatch_merge",
            reason="ready_to_integrate workers require merge dispatch",
            source="integration_review",
            summary=summary,
            timeline=timeline,
        )
    if integration_summary["already_integrated"] and cleanup_count:
        return _decision(
            action="archive_integrated",
            reason="integrated workers can be archived",
            source="integration_review",
            summary=summary,
            timeline=timeline,
        )
    return _decision(
        action="monitor",
        reason="no lifecycle-ready worker evidence",
        source="worker_review",
        summary=summary,
        timeline=timeline,
    )


def _decision(
    *,
    action: str,
    reason: str,
    source: str,
    summary: Mapping[str, Any],
    execution: Any | None = None,
    timeline: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    stage, next_step = _stage_and_next_step(action, source=source)
    policy = _policy(
        action=action,
        reason=reason,
        source=source,
        next_step=next_step,
    )
    return {
        "kind": "worker_lifecycle_decision",
        "action": action,
        "stage": stage,
        "next_step": next_step,
        "policy": policy,
        "reason": reason,
        "source": source,
        "summary": dict(summary),
        "execution": execution,
        "timeline": [dict(item) for item in timeline or []],
    }


def _stage_and_next_step(action: str, *, source: str) -> tuple[str, str]:
    if action == "dispatch_merge":
        return "ready_to_merge", "launch_merge_worker"
    if action == "archive_integrated":
        if source == "cleanup":
            return "archived", "cleanup_worktree"
        return "integrated", "archive_worker"
    if action == "cleanup_worktree":
        return "worktree_cleaned", "monitor"
    if action == "needs_human":
        return "blocked", "request_human_review"
    return "monitoring", "monitor"


def _policy(
    *,
    action: str,
    reason: str,
    source: str,
    next_step: str,
) -> dict[str, Any]:
    if action == "needs_human":
        return {
            "policy_status": "human_required",
            "program_action": None,
            "remaining_step": "request_human_review",
            "blocked_reason": reason,
        }
    if action == "monitor" and source == "worker_review":
        return {
            "policy_status": "model_required",
            "program_action": None,
            "remaining_step": next_step,
            "blocked_reason": reason,
        }
    return {
        "policy_status": "program_resolved",
        "program_action": action,
        "remaining_step": next_step,
        "blocked_reason": None,
    }


def _timeline(
    *,
    integration_summary: Mapping[str, int],
    merge_dispatch: Mapping[str, Any] | None,
    cleanup_count: int,
    archived_items: Sequence[Mapping[str, Any]],
    deleted_worktree_items: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if integration_summary["ready_to_integrate"]:
        items.append(
            _timeline_item(
                stage="ready_to_merge",
                action="dispatch_merge",
                source="integration_review",
                status=(
                    "pending"
                    if isinstance(merge_dispatch, Mapping)
                    and _text(merge_dispatch.get("status")) == "ready_to_launch"
                    else "observed"
                ),
            )
        )
    if integration_summary["already_integrated"]:
        items.append(
            _timeline_item(
                stage="integrated",
                action="archive_integrated",
                source="integration_review",
                status="pending" if cleanup_count else "observed",
            )
        )
    if archived_items:
        items.append(
            _timeline_item(
                stage="archived",
                action="archive_integrated",
                source="cleanup",
                status="executed",
                execution=archived_items,
            )
        )
    if deleted_worktree_items:
        items.append(
            _timeline_item(
                stage="worktree_cleaned",
                action="cleanup_worktree",
                source="cleanup",
                status="executed",
                execution=deleted_worktree_items,
            )
        )
    return items


def _timeline_item(
    *,
    stage: str,
    action: str,
    source: str,
    status: str,
    execution: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "stage": stage,
        "action": action,
        "source": source,
        "status": status,
        "executed": status == "executed",
    }
    if execution is not None:
        item["execution"] = [dict(entry) for entry in execution]
    return item


def _integration_summary(payload: Mapping[str, Any] | None) -> dict[str, int]:
    summary = payload.get("summary") if isinstance(payload, Mapping) else None
    if not isinstance(summary, Mapping):
        return {
            "ready_to_integrate": 0,
            "conflict_risk": 0,
            "needs_review": 0,
            "already_integrated": 0,
        }
    return {
        "ready_to_integrate": _non_negative_int(summary.get("ready_to_integrate")),
        "conflict_risk": _non_negative_int(summary.get("conflict_risk")),
        "needs_review": _non_negative_int(summary.get("needs_review")),
        "already_integrated": _non_negative_int(summary.get("already_integrated")),
    }


def _non_negative_int(value: object) -> int:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
        else 0
    )


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""
