"""Automatic cleanup lifecycle helpers for Supervisor loop."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any


def auto_delete_archived_worktrees_after_cleanup(
    args: argparse.Namespace,
    *,
    cleanup_archived: list[dict[str, Any]],
    api: Any | None = None,
) -> list[dict[str, Any]]:
    if api is None:
        from isotope.features.supervisor import runner as api

    if not cleanup_archived:
        return []
    if getattr(args, "command", None) != "loop":
        return []
    if api._current_workspace_has_worker_role(args, api.RECURSIVE_WORKER_ROLES):
        return []
    archived_record_ids = {
        record_id
        for item in cleanup_archived
        for record_id in (item.get("record_id"),)
        if isinstance(record_id, str) and record_id
    }
    if not archived_record_ids:
        return []
    deleted: list[dict[str, Any]] = []
    for candidate in api._delete_worktree_candidate_payloads(args):
        target_name = candidate.get("target_name") or candidate.get("name")
        record_id = candidate.get("record_id")
        if not isinstance(target_name, str) or not target_name.strip():
            continue
        if not isinstance(record_id, str) or not record_id.strip():
            continue
        if record_id not in archived_record_ids:
            continue
        deleted.append(
            api._execute_delete_worktree_action(
                args,
                {
                    "kind": "delete_worktree",
                    "target_name": target_name,
                    "record_id": record_id,
                    "confirm_delete_worktree": True,
                    "base_ref": "main",
                    "source": "cleanup_auto",
                },
            )
        )
    return deleted


def auto_archive_integrated_merge_workers(
    *,
    codex_home: Path,
    review_payload: dict[str, Any],
    api: Any | None = None,
) -> list[dict[str, Any]]:
    if api is None:
        from isotope.features.supervisor import runner as api

    groups = review_payload.get("groups")
    if not isinstance(groups, dict):
        return []
    integrated_record_ids = review_group_record_ids(groups, "already_integrated")
    if not integrated_record_ids:
        return []
    records = {
        record.record_id: record
        for record in api.read_managed_records(api.default_registry_path(codex_home))
    }
    archived: list[dict[str, Any]] = []
    archived_record_ids: set[str] = set()
    for item in review_group_items(groups, "merge_workers"):
        record_id = item.get("record_id")
        if not isinstance(record_id, str) or not record_id:
            continue
        record = records.get(record_id)
        if record is None:
            continue
        if not merge_worker_review_item_is_done(item):
            continue
        candidate_record_ids = merge_candidate_record_ids(record)
        if not candidate_record_ids:
            continue
        if not candidate_record_ids <= integrated_record_ids:
            continue
        for candidate_record_id in sorted(candidate_record_ids):
            if candidate_record_id in archived_record_ids:
                continue
            candidate_record = records.get(candidate_record_id)
            if candidate_record is None:
                continue
            archived.append(
                archive_integrated_source_worker(
                    codex_home,
                    candidate_record,
                    api=api,
                )
            )
            archived_record_ids.add(candidate_record_id)
        if record_id in archived_record_ids:
            continue
        archived.append(
            archive_integrated_merge_worker(codex_home, record, item, api=api)
        )
        archived_record_ids.add(record_id)
    return archived


def archive_integrated_source_worker(
    codex_home: Path,
    record: Any,
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    managed = api.archive_managed_codex(
        codex_home=codex_home,
        name=record.name,
        record_id=record.record_id,
    )
    return {
        "kind": "source_worker",
        "name": record.name,
        "record_id": record.record_id,
        "managed": managed.to_dict(),
        "integration_group": "already_integrated",
    }


def archive_integrated_merge_worker(
    codex_home: Path,
    record: Any,
    review_item: dict[str, Any],
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    managed = api.archive_managed_codex(
        codex_home=codex_home,
        name=record.name,
        record_id=record.record_id,
    )
    protocol = review_item.get("supervisor_protocol")
    protocol = protocol if isinstance(protocol, dict) else {}
    goal = archive_related_merge_goal(
        codex_home=codex_home,
        target_name=record.name,
        protocol=protocol,
        api=api,
    )
    notification = api.notify_merge_worker_auto_archived(
        codex_home=codex_home,
        record_id=record.record_id,
        status="done",
        group="already_integrated",
    )
    result: dict[str, Any] = {
        "kind": "merge_worker",
        "name": record.name,
        "record_id": record.record_id,
        "managed": managed.to_dict(),
        "integration_group": "already_integrated",
    }
    if goal is not None:
        result["goal"] = goal
    if notification is not None:
        result["notification"] = notification.to_dict()
    return result


def archive_related_merge_goal(
    *,
    codex_home: Path,
    target_name: str,
    protocol: dict[str, Any],
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    for goal in api.read_active_supervisor_goals(codex_home=codex_home, limit=1000):
        if goal.target_name != target_name:
            continue
        return api.archive_supervisor_goal(
            codex_home=codex_home,
            goal_id=goal.goal_id,
            status="done",
            target_name=target_name,
            summary=(
                protocol.get("summary")
                if isinstance(protocol.get("summary"), str)
                else None
            ),
            next_step=(
                protocol.get("next")
                if isinstance(protocol.get("next"), str)
                else None
            ),
        )
    return None


def merge_worker_review_item_is_done(item: dict[str, Any]) -> bool:
    protocol = item.get("supervisor_protocol")
    if not isinstance(protocol, dict):
        return False
    status = protocol.get("status")
    return isinstance(status, str) and status.lower() == "done"


def merge_worker_review_item_is_blocked(item: dict[str, Any]) -> bool:
    protocol = item.get("supervisor_protocol")
    if not isinstance(protocol, dict):
        return False
    status = protocol.get("status")
    return isinstance(status, str) and status.lower() == "blocked"


def merge_candidate_record_ids(record: Any) -> set[str]:
    text = "\n".join(
        [
            str(getattr(record, "prompt", "") or ""),
            " ".join(str(part) for part in getattr(record, "command", ()) or ()),
        ]
    )
    return {
        match.group(0)
        for match in re.finditer(r"\bmanaged-[A-Za-z0-9_-]+\b", text)
        if match.group(0) != getattr(record, "record_id", None)
    }


def review_group_record_ids(groups: dict[str, Any], group: str) -> set[str]:
    return {
        record_id
        for item in review_group_items(groups, group)
        for record_id in (item.get("record_id"),)
        if isinstance(record_id, str) and record_id
    }


def review_group_items(groups: dict[str, Any], group: str) -> list[dict[str, Any]]:
    items = groups.get(group)
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def integration_reviews_by_record_ref(
    payload: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    reviews: dict[tuple[str, str], dict[str, Any]] = {}
    raw_workers = payload.get("workers")
    workers = raw_workers if isinstance(raw_workers, list) else []
    for raw in workers:
        if not isinstance(raw, dict):
            continue
        record_id = raw.get("record_id")
        name = raw.get("name")
        if isinstance(record_id, str) and record_id:
            reviews[("record_id", record_id)] = raw
        if isinstance(name, str) and name:
            reviews[("name", name)] = raw
    return reviews


def integration_review_for_cleanup_candidate(
    candidate: dict[str, Any],
    reviews: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    record_id = candidate.get("record_id")
    if isinstance(record_id, str) and record_id:
        review = reviews.get(("record_id", record_id))
        if review is not None:
            return review
    name = candidate.get("name")
    if isinstance(name, str) and name:
        return reviews.get(("name", name))
    return None


def auto_cleanup_integration_summary(
    review: dict[str, Any],
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    return api._drop_none_values(
        {
            "group": review.get("group"),
            "reason": review.get("reason"),
            "record_id": review.get("record_id"),
            "name": review.get("name"),
            "branch": review.get("branch"),
            "worker_commit": review.get("worker_commit"),
            "base_ref": review.get("base_ref"),
            "main_contains_worker": review.get("main_contains_worker"),
            "main_has_worker_patch": review.get("main_has_worker_patch"),
            "dirty": review.get("dirty"),
        }
    )
