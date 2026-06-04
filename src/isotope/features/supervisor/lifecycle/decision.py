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
) -> dict[str, Any]:
    del worker_reviews
    integration_summary = _integration_summary(integration_review)
    cleanup_count = len(cleanup_candidates or [])
    archived_items = [dict(item) for item in cleanup_archived or []]
    summary = {
        **integration_summary,
        "cleanup_candidates": cleanup_count,
        "cleanup_archived": len(archived_items),
    }
    if archived_items:
        return _decision(
            action="archive_integrated",
            reason="integrated workers archived",
            source="cleanup",
            summary=summary,
            execution=archived_items,
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
            )
    if integration_summary["conflict_risk"] or integration_summary["needs_review"]:
        return _decision(
            action="needs_human",
            reason="integration review has conflict or review-required workers",
            source="integration_review",
            summary=summary,
        )
    if integration_summary["ready_to_integrate"] and merge_dispatch is not None:
        return _decision(
            action="dispatch_merge",
            reason="ready_to_integrate workers require merge dispatch",
            source="integration_review",
            summary=summary,
        )
    if integration_summary["already_integrated"] and cleanup_count:
        return _decision(
            action="archive_integrated",
            reason="integrated workers can be archived",
            source="integration_review",
            summary=summary,
        )
    return _decision(
        action="monitor",
        reason="no lifecycle-ready worker evidence",
        source="worker_review",
        summary=summary,
    )


def _decision(
    *,
    action: str,
    reason: str,
    source: str,
    summary: Mapping[str, Any],
    execution: Any | None = None,
) -> dict[str, Any]:
    return {
        "kind": "worker_lifecycle_decision",
        "action": action,
        "reason": reason,
        "source": source,
        "summary": dict(summary),
        "execution": execution,
    }


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
