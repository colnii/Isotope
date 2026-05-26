"""Cleanup command handling for the Supervisor CLI and loop."""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path
from typing import Any

from isotope.features.notifications.flow import NotificationFlow
from isotope.features.supervisor.planner.goal_queue import archive_supervisor_goal
from isotope.features.supervisor.registry import archive_managed_codex


def handle_cleanup_command(args: argparse.Namespace, *, api: Any) -> int:
    payload = cleanup_payload(args, api=api)
    if args.json:
        api._print_json(payload)
    else:
        print_cleanup_plain(payload)
    return 0


def cleanup_payload(
    args: argparse.Namespace,
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    codex_home = Path(args.codex_home)
    candidates = cleanup_candidate_dicts(codex_home, api=api)
    if args.cleanup_command == "list":
        return {
            "status": "ok",
            "candidates": candidates,
            "worktree_candidates": cleanup_worktree_candidate_dicts(args, api=api),
        }
    if args.cleanup_command == "archive":
        selected = select_cleanup_candidates(args, candidates)
        archived = [
            archive_cleanup_candidate(codex_home, item)
            for item in selected
        ]
        return {
            "status": "ok",
            "candidates": cleanup_candidate_dicts(codex_home, api=api),
            "archived": archived,
            "active_goals": api._active_goal_dicts_for_codex_home(
                codex_home,
                include_status=True,
            ),
        }
    if args.cleanup_command == "delete-worktree":
        deleted = api._execute_delete_worktree_action(
            args,
            {
                "kind": "delete_worktree",
                "target_name": args.name,
                "record_id": args.record_id,
                "confirm_delete_worktree": args.confirm_delete_worktree,
                "base_ref": args.base,
            },
        )
        return {
            "status": "ok",
            "deleted": deleted,
            "worktree_candidates": cleanup_worktree_candidate_dicts(args, api=api),
        }
    raise ValueError(f"unsupported cleanup command: {args.cleanup_command}")


def print_cleanup_plain(payload: dict[str, Any]) -> None:
    deleted = payload.get("deleted")
    if isinstance(deleted, dict) and deleted:
        target = deleted.get("target_name") or deleted.get("name") or "unknown"
        print(f"已删除 worktree：{target}")
        if deleted.get("deleted_worktree"):
            print(f"  cwd：{deleted['deleted_worktree']}")
    archived = payload.get("archived") or []
    if archived:
        print(f"已归档/标记：{len(archived)}")
        for item in archived:
            target = item.get("goal_id") or item.get("name") or item.get("notification_id")
            print(f"- {item['kind']} {target}")
    candidates = payload.get("candidates") or []
    print(f"可归档项：{len(candidates)}")
    for item in candidates:
        target = item.get("goal_id") or item.get("name") or item.get("notification_id")
        print(f"- {item['kind']} {target}")
        if item.get("summary"):
            print(f"  摘要：{item['summary']}")
        if item.get("command"):
            print(f"  归档：{item['command']}")
    worktree_candidates = payload.get("worktree_candidates") or []
    if worktree_candidates:
        print(f"可删除 worktree：{len(worktree_candidates)}")
        for item in worktree_candidates:
            target = item.get("name") or item.get("target_name")
            print(f"- worktree {target}")
            if item.get("cwd"):
                print(f"  cwd：{item['cwd']}")
            if item.get("command"):
                print(f"  删除：{item['command']}")


def cleanup_candidate_dicts(
    codex_home: Path,
    *,
    api: Any | None = None,
) -> list[dict[str, Any]]:
    if api is None:
        from isotope.features.supervisor import runner as api

    goals = cleanup_goal_candidates(codex_home, api=api)
    return [
        *goals,
        *cleanup_managed_worker_candidates(codex_home, api=api),
        *cleanup_stale_missing_worker_candidates(codex_home, api=api),
        *cleanup_notification_candidates(codex_home),
    ]


def cleanup_goal_candidates(
    codex_home: Path,
    *,
    api: Any | None = None,
) -> list[dict[str, Any]]:
    if api is None:
        from isotope.features.supervisor import runner as api

    candidates: list[dict[str, Any]] = []
    for goal in api._active_goal_dicts_for_codex_home(codex_home, include_status=True):
        status = goal.get("last_status")
        if status not in api.ARCHIVABLE_SUPERVISOR_STATUSES:
            continue
        goal_id = goal.get("goal_id")
        if not isinstance(goal_id, str) or not goal_id:
            continue
        candidate = {
            "kind": "goal",
            "goal_id": goal_id,
            "status": status,
            "target_name": goal.get("target_name"),
            "cwd": goal.get("cwd"),
            "goal": goal.get("goal"),
            "summary": goal.get("last_summary"),
            "next": goal.get("last_next"),
            "command": cleanup_archive_command(
                codex_home,
                "--goal-id",
                goal_id,
            ),
        }
        candidates.append(drop_none_values(candidate))
    return candidates


def cleanup_managed_worker_candidates(
    codex_home: Path,
    *,
    require_existing_cwd: bool = False,
    api: Any | None = None,
) -> list[dict[str, Any]]:
    if api is None:
        from isotope.features.supervisor import runner as api

    candidates: list[dict[str, Any]] = []
    for record in api.read_managed_records(api.default_registry_path(codex_home)):
        if require_existing_cwd and not api._cwd_is_existing_dir(record.cwd):
            continue
        protocol = managed_record_supervisor_protocol(record, api=api)
        if protocol.get("status") not in api.ARCHIVABLE_SUPERVISOR_STATUSES:
            continue
        if managed_record_is_still_working(record, api=api):
            continue
        candidate = {
            "kind": "managed_worker",
            "name": record.name,
            "record_id": record.record_id,
            "status": protocol.get("status"),
            "summary": protocol.get("summary"),
            "next": protocol.get("next"),
            "cwd": record.cwd,
            "backend": record.backend,
            "tmux_session": record.tmux_session,
            "command": cleanup_archive_command(
                codex_home,
                "--name",
                record.name,
                "--record-id",
                record.record_id,
            ),
        }
        candidates.append(drop_none_values(candidate))
    return candidates


def cleanup_stale_missing_worker_candidates(
    codex_home: Path,
    *,
    api: Any | None = None,
) -> list[dict[str, Any]]:
    if api is None:
        from isotope.features.supervisor import runner as api

    candidates: list[dict[str, Any]] = []
    for record in api.read_managed_records(api.default_registry_path(codex_home)):
        if ".worktrees" not in Path(record.cwd).expanduser().parts:
            continue
        if api._cwd_is_existing_dir(record.cwd):
            continue
        if managed_record_is_still_working(record, api=api):
            continue
        protocol = managed_record_supervisor_protocol(record, api=api)
        if protocol.get("status") in api.ARCHIVABLE_SUPERVISOR_STATUSES:
            continue
        candidate = {
            "kind": "managed_worker",
            "name": record.name,
            "record_id": record.record_id,
            "status": "stale_missing_worktree",
            "summary": protocol.get("summary"),
            "next": protocol.get("next"),
            "cwd": record.cwd,
            "backend": record.backend,
            "tmux_session": record.tmux_session,
            "command": cleanup_archive_command(
                codex_home,
                "--name",
                record.name,
                "--record-id",
                record.record_id,
            ),
        }
        candidates.append(drop_none_values(candidate))
    return candidates


def cleanup_notification_candidates(codex_home: Path) -> list[dict[str, Any]]:
    try:
        notifications = NotificationFlow.in_process(codex_home).list_notifications(
            unread=True,
            notification_type="supervisor_goal_status",
        )
    except (OSError, ValueError):
        return []
    candidates: list[dict[str, Any]] = []
    for notification in notifications:
        source_ref = notification.source_ref or {}
        if not isinstance(source_ref, dict):
            continue
        goal_id = source_ref.get("goal_id")
        status = source_ref.get("status")
        if status not in {"done"}:
            continue
        candidate = {
            "kind": "notification",
            "notification_id": notification.notification_id,
            "type": notification.notification_type,
            "title": notification.title,
            "goal_id": goal_id,
            "status": status,
            "command": cleanup_archive_command(
                codex_home,
                "--notification-id",
                notification.notification_id,
            ),
        }
        candidates.append(drop_none_values(candidate))
    return candidates


def cleanup_worktree_candidate_dicts(
    args: argparse.Namespace,
    *,
    api: Any | None = None,
) -> list[dict[str, Any]]:
    if api is None:
        from isotope.features.supervisor import runner as api

    candidates: list[dict[str, Any]] = []
    for item in api._delete_worktree_candidate_payloads(args):
        candidate = dict(item)
        target_name = candidate.get("target_name") or candidate.get("name")
        record_id = candidate.get("record_id")
        if not isinstance(target_name, str) or not target_name:
            continue
        if not isinstance(record_id, str) or not record_id:
            continue
        candidate["command"] = cleanup_delete_worktree_command(
            Path(args.codex_home),
            target_name=target_name,
            record_id=record_id,
            base_ref=str(getattr(args, "base", "main") or "main"),
        )
        candidates.append(candidate)
    return candidates


def cleanup_archive_command(codex_home: Path, *target_args: str) -> str:
    return shlex.join(
        [
            "isotope-supervisor",
            "cleanup",
            "archive",
            "--codex-home",
            str(codex_home),
            *target_args,
        ]
    )


def cleanup_delete_worktree_command(
    codex_home: Path,
    *,
    target_name: str,
    record_id: str,
    base_ref: str = "main",
) -> str:
    args = [
        "isotope-supervisor",
        "cleanup",
        "delete-worktree",
        "--codex-home",
        str(codex_home),
        "--name",
        target_name,
        "--record-id",
        record_id,
    ]
    if base_ref != "main":
        args.extend(["--base", base_ref])
    args.append("--confirm-delete-worktree")
    return shlex.join(args)


def select_cleanup_candidates(
    args: argparse.Namespace,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if getattr(args, "all", False):
        return candidates
    goal_id = getattr(args, "goal_id", None)
    name = getattr(args, "name", None)
    record_id = getattr(args, "record_id", None)
    notification_id = getattr(args, "notification_id", None)
    selected = [
        item
        for item in candidates
        if (goal_id and item.get("kind") == "goal" and item.get("goal_id") == goal_id)
        or (
            name
            and item.get("kind") == "managed_worker"
            and item.get("name") == name
            and (not record_id or item.get("record_id") == record_id)
        )
        or (
            notification_id
            and item.get("kind") == "notification"
            and item.get("notification_id") == notification_id
        )
    ]
    if not selected:
        raise ValueError("cleanup target is not currently archivable")
    return selected


def archive_cleanup_candidate(
    codex_home: Path,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    kind = candidate.get("kind")
    if kind == "goal":
        goal_id = str(candidate["goal_id"])
        archived = archive_supervisor_goal(codex_home=codex_home, goal_id=goal_id)
        return {
            "kind": kind,
            "goal_id": goal_id,
            "archived": archived,
        }
    if kind == "managed_worker":
        name = str(candidate["name"])
        record_id = candidate.get("record_id")
        record = archive_managed_codex(
            codex_home=codex_home,
            name=name,
            record_id=str(record_id) if record_id else None,
        )
        return {
            "kind": kind,
            "name": name,
            "managed": record.to_dict(),
        }
    if kind == "notification":
        notification_id = str(candidate["notification_id"])
        marked = NotificationFlow.in_process(codex_home).mark_read(notification_id)
        return {
            "kind": kind,
            "notification_id": notification_id,
            "notification": marked.to_dict(),
        }
    raise ValueError(f"unsupported cleanup candidate kind: {kind}")


def managed_record_supervisor_protocol(
    record: Any,
    *,
    api: Any | None = None,
) -> dict[str, str]:
    if api is None:
        from isotope.features.supervisor import runner as api

    excerpt = managed_record_status_excerpt(record, api=api)
    if not excerpt:
        return {}
    return api._supervisor_protocol_from_text(excerpt)


def managed_record_is_still_working(
    record: Any,
    *,
    api: Any | None = None,
) -> bool:
    if api is None:
        from isotope.features.supervisor import runner as api

    if record.backend != "tmux" and record.pid > 0 and api._pid_is_running(record.pid):
        return True
    excerpt = managed_record_status_excerpt(record, api=api)
    if not excerpt:
        return False
    lines = [line.strip() for line in excerpt.splitlines() if line.strip()]
    return api._terminal_has_active_work_marker(lines[-8:])


def managed_record_status_excerpt(
    record: Any,
    *,
    api: Any | None = None,
) -> str | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    if record.backend == "tmux" and record.tmux_session:
        pane_text = api._tmux_capture_pane(record.tmux_session)
        if pane_text:
            return pane_text
    return api._managed_process_log_excerpt(record.log_path)


def drop_none_values(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if value is not None}


def auto_archive_done_merge_workers(
    args: argparse.Namespace,
    *,
    api: Any | None = None,
) -> list[dict[str, Any]]:
    if api is None:
        from isotope.features.supervisor import runner as api

    if getattr(args, "command", None) != "loop":
        return []
    if api._current_workspace_has_worker_role(args, api.RECURSIVE_WORKER_ROLES):
        return []
    codex_home = api.Path(args.codex_home)
    review_payload = api.collect_integration_reviews(
        codex_home=codex_home,
        base_ref="main",
        include_unfinished=False,
        run_test_gate=False,
        run_candidate_validation=False,
    )
    return api._auto_archive_integrated_merge_workers(
        codex_home=codex_home,
        review_payload=review_payload,
    )
