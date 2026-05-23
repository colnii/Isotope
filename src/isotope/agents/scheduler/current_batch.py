"""Current-batch projection helpers for scheduler-owned goal views."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from isotope.agents.scheduler.dependency_batches import build_dependency_batch_plan


TERMINAL_STATUSES = frozenset({"archived", "completed", "done", "exited", "stale"})
DEPENDENCY_SOURCE_EXCLUDED_STATUSES = TERMINAL_STATUSES - {"done"}


@dataclass(frozen=True)
class CurrentBatchView:
    active_goals: tuple[dict[str, Any], ...]
    managed_workers: tuple[dict[str, Any], ...]
    worker_reviews: dict[str, Any]
    automation_candidates: dict[str, list[dict[str, Any]]]
    target_names: tuple[str, ...]
    dependency_batch: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        automation_count = sum(len(items) for items in self.automation_candidates.values())
        payload = {
            "active_goals": list(self.active_goals),
            "managed_workers": list(self.managed_workers),
            "worker_reviews": dict(self.worker_reviews),
            "automation_candidates": {
                bucket: list(items)
                for bucket, items in self.automation_candidates.items()
                if items
            },
            "counts": {
                "active_goals": len(self.active_goals),
                "managed_workers": len(self.managed_workers),
                "worker_reviews": len(self.worker_reviews.get("workers") or []),
                "automation_candidates": automation_count,
                "total": len(self.active_goals) + len(self.managed_workers),
            },
            "target_names": list(self.target_names),
        }
        if self.dependency_batch is not None:
            payload["dependency_batch"] = dict(self.dependency_batch)
        return payload


@dataclass(frozen=True)
class _CurrentIdentity:
    target_names: frozenset[str]
    record_ids: frozenset[str]
    cwds: frozenset[str]
    branches: frozenset[str]


def build_current_batch_view(
    *,
    active_goals: Iterable[Mapping[str, Any]] | None,
    managed_workers: Iterable[Mapping[str, Any]] | None,
    worker_reviews: Mapping[str, Any] | None = None,
    automation_candidates: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
    dependency_limit: int | None = None,
) -> CurrentBatchView:
    """Return a JSON-ready current batch view from already-collected inputs."""
    dependency_goals = tuple(
        dict(goal)
        for goal in active_goals or ()
        if isinstance(goal, Mapping) and _is_dependency_source_goal(goal)
    )
    current_goals = tuple(
        dict(goal)
        for goal in active_goals or ()
        if isinstance(goal, Mapping) and _is_current_goal(goal)
    )
    current_workers = tuple(
        dict(worker)
        for worker in managed_workers or ()
        if isinstance(worker, Mapping) and _is_current_worker(worker)
    )
    identity = _current_identity(current_goals, current_workers)
    raw_candidates = automation_candidates
    if raw_candidates is None and isinstance(worker_reviews, Mapping):
        raw_candidates = _mapping_or_none(worker_reviews.get("automation_candidates"))
    filtered_candidates = _filter_automation_candidates(raw_candidates, identity)
    filtered_reviews = _filter_worker_reviews(
        worker_reviews,
        identity=identity,
        automation_candidates=filtered_candidates,
    )
    return CurrentBatchView(
        active_goals=current_goals,
        managed_workers=current_workers,
        worker_reviews=filtered_reviews,
        automation_candidates=filtered_candidates,
        target_names=tuple(_ordered_target_names(current_goals, current_workers)),
        dependency_batch=_dependency_batch(
            dependency_goals,
            current_workers=current_workers,
            dependency_limit=dependency_limit,
        ),
    )


def _is_current_goal(goal: Mapping[str, Any]) -> bool:
    if goal.get("current") is False or goal.get("cwd_exists") is False:
        return False
    return not _has_terminal_status(goal, ("last_status", "status", "supervisor_status"))


def _is_current_worker(worker: Mapping[str, Any]) -> bool:
    if worker.get("current") is False or worker.get("cwd_exists") is False:
        return False
    return not _has_terminal_status(worker, ("status", "supervisor_status", "registry_status"))


def _is_dependency_source_goal(goal: Mapping[str, Any]) -> bool:
    if goal.get("cwd_exists") is False:
        return False
    return not _has_status_in(
        goal,
        ("last_status", "status", "supervisor_status"),
        DEPENDENCY_SOURCE_EXCLUDED_STATUSES,
    )


def _dependency_batch(
    dependency_goals: tuple[dict[str, Any], ...],
    *,
    current_workers: tuple[dict[str, Any], ...],
    dependency_limit: int | None,
) -> dict[str, Any] | None:
    if not dependency_goals:
        return None
    limit = dependency_limit if dependency_limit is not None else len(dependency_goals)
    if limit <= 0:
        limit = 1
    return build_dependency_batch_plan(
        dependency_goals,
        limit=limit,
        running_target_names=_ordered_target_names((), current_workers),
    )


def _filter_worker_reviews(
    worker_reviews: Mapping[str, Any] | None,
    *,
    identity: _CurrentIdentity,
    automation_candidates: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    workers: list[dict[str, Any]] = []
    if isinstance(worker_reviews, Mapping):
        for worker in worker_reviews.get("workers") or []:
            if not isinstance(worker, Mapping):
                continue
            if _has_terminal_review_status(worker):
                continue
            if _matches_identity(worker, identity):
                workers.append(dict(worker))
    payload: dict[str, Any] = {"summary": {"total": len(workers)}}
    if isinstance(worker_reviews, Mapping) and "status" in worker_reviews:
        payload["status"] = worker_reviews.get("status")
    payload["workers"] = workers
    payload["automation_candidates"] = {
        bucket: list(items)
        for bucket, items in automation_candidates.items()
        if items
    }
    if "status" in payload:
        return {
            "status": payload["status"],
            "summary": payload["summary"],
            "workers": payload["workers"],
            "automation_candidates": payload["automation_candidates"],
        }
    return payload


def _filter_automation_candidates(
    automation_candidates: Mapping[str, Iterable[Mapping[str, Any]]] | None,
    identity: _CurrentIdentity,
) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(automation_candidates, Mapping):
        return {}
    filtered: dict[str, list[dict[str, Any]]] = {}
    for bucket, items in automation_candidates.items():
        if not isinstance(bucket, str):
            continue
        bucket_items: list[dict[str, Any]] = []
        for item in items or ():
            if isinstance(item, Mapping) and _matches_identity(item, identity):
                bucket_items.append(dict(item))
        if bucket_items:
            filtered[bucket] = bucket_items
    return filtered


def _current_identity(
    active_goals: tuple[dict[str, Any], ...],
    managed_workers: tuple[dict[str, Any], ...],
) -> _CurrentIdentity:
    items: tuple[dict[str, Any], ...] = active_goals + managed_workers
    return _CurrentIdentity(
        target_names=frozenset(_identity_values(items, ("target_name", "name", "managed_name"))),
        record_ids=frozenset(_identity_values(items, ("record_id", "session_id"))),
        cwds=frozenset(_identity_values(items, ("cwd",))),
        branches=frozenset(_identity_values(items, ("branch", "git_branch"))),
    )


def _matches_identity(item: Mapping[str, Any], identity: _CurrentIdentity) -> bool:
    return (
        _has_any_identity(item, ("target_name", "name", "managed_name"), identity.target_names)
        or _has_any_identity(item, ("record_id", "session_id"), identity.record_ids)
        or _has_any_identity(item, ("cwd",), identity.cwds)
        or _has_any_identity(item, ("branch", "git_branch"), identity.branches)
        or _worktree_branch(item) in identity.branches
    )


def _has_any_identity(
    item: Mapping[str, Any],
    keys: tuple[str, ...],
    values: frozenset[str],
) -> bool:
    if not values:
        return False
    return any(_string_value(item.get(key)) in values for key in keys)


def _identity_values(
    items: tuple[dict[str, Any], ...],
    keys: tuple[str, ...],
) -> list[str]:
    values: list[str] = []
    for item in items:
        for key in keys:
            value = _string_value(item.get(key))
            if value and value not in values:
                values.append(value)
        branch = _worktree_branch(item)
        if "branch" in keys and branch and branch not in values:
            values.append(branch)
    return values


def _ordered_target_names(
    active_goals: tuple[dict[str, Any], ...],
    managed_workers: tuple[dict[str, Any], ...],
) -> list[str]:
    return _identity_values(active_goals + managed_workers, ("target_name", "name"))


def _has_terminal_review_status(worker: Mapping[str, Any]) -> bool:
    protocol = worker.get("supervisor_protocol")
    if isinstance(protocol, Mapping):
        status = _normalized_status(protocol.get("status"))
        if status in TERMINAL_STATUSES:
            return True
    return _has_terminal_status(worker, ("status", "supervisor_status", "registry_status"))


def _has_terminal_status(item: Mapping[str, Any], keys: tuple[str, ...]) -> bool:
    return any(_normalized_status(item.get(key)) in TERMINAL_STATUSES for key in keys)


def _has_status_in(
    item: Mapping[str, Any],
    keys: tuple[str, ...],
    statuses: frozenset[str],
) -> bool:
    return any(_normalized_status(item.get(key)) in statuses for key in keys)


def _normalized_status(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    return text or None


def _string_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _mapping_or_none(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _worktree_branch(item: Mapping[str, Any]) -> str | None:
    worktree = item.get("worktree")
    if not isinstance(worktree, Mapping):
        return None
    return _string_value(worktree.get("branch"))


__all__ = ["CurrentBatchView", "build_current_batch_view"]
