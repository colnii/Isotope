"""Merge-dispatch orchestration helpers for Supervisor loop commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from isotope.features.supervisor.merge_dispatch import build_merge_dispatch_payload


def integration_merge_dispatch_payload(
    args: argparse.Namespace,
    *,
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    if getattr(args, "command", None) != "loop":
        return None
    if getattr(args, "name", None):
        return None
    if api.MERGE_DISPATCH_TARGET_NAME in api._running_managed_target_names_from_registry(
        Path(args.codex_home)
    ):
        return None
    review_payload = api.collect_integration_reviews(
        codex_home=Path(args.codex_home),
        base_ref="main",
        include_unfinished=False,
        run_test_gate=False,
        run_candidate_validation=False,
    )
    running_worker = api._running_managed_process_by_name(
        codex_home=Path(args.codex_home),
        name=api.MERGE_DISPATCH_TARGET_NAME,
    )
    return build_merge_dispatch_payload(
        review_payload,
        cwd=merge_dispatch_cwd(args, api=api),
        running_worker=running_worker,
        managed_worker_reference=managed_worker_reference,
    )


def managed_worker_reference(record: Any) -> dict[str, Any]:
    return {
        "name": record.name,
        "record_id": record.record_id,
        "pid": record.pid,
        "backend": record.backend,
        "worker_role": getattr(record, "worker_role", "worker"),
    }


def merge_dispatch_cwd(
    args: argparse.Namespace,
    *,
    api: Any | None = None,
) -> Path:
    if api is None:
        from isotope.features.supervisor import runner as api

    workspace_root = api._workspace_root(args)
    return workspace_root if workspace_root is not None else Path.cwd()


def recursive_worker_role_guard_payload(
    args: argparse.Namespace,
    *,
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    role = current_workspace_worker_role(args, api.RECURSIVE_WORKER_ROLES, api=api)
    if role is None:
        return None
    reason = (
        "当前工作区是 merge worker，跳过 merge dispatch。"
        if role == api.MERGE_DISPATCH_WORKER_ROLE
        else f"当前工作区是 {role} worker，跳过递归调度。"
    )
    return {
        "status": "skipped_current_worker_role",
        "worker_role": role,
        "reason": reason,
    }


def recursive_worker_role_guard_action(guard: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "monitor",
        "target_name": None,
        "reason": guard["reason"],
        "command_suggestion": None,
    }


def recursive_worker_role_guard_executed(guard: dict[str, Any]) -> dict[str, Any]:
    executed = recursive_worker_role_guard_action(guard)
    executed["skipped"] = True
    executed["worker_role"] = guard["worker_role"]
    return executed


def current_workspace_has_worker_role(
    args: argparse.Namespace,
    roles: set[str],
    *,
    api: Any | None = None,
) -> bool:
    return current_workspace_worker_role(args, roles, api=api) is not None


def current_workspace_worker_role(
    args: argparse.Namespace,
    roles: set[str],
    *,
    api: Any | None = None,
) -> str | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    workspace = api._workspace_root(args)
    if workspace is None:
        return None
    workspace_identity = api._path_identity(str(workspace))
    if workspace_identity is None:
        return None
    for record in reversed(
        api.read_managed_records(api.default_registry_path(Path(args.codex_home)))
    ):
        role = getattr(record, "worker_role", "worker")
        if role not in roles:
            continue
        if api._path_identity(record.cwd) == workspace_identity:
            return role
    return None


def is_merge_dispatch_launch_action(
    action: dict[str, Any],
    *,
    api: Any | None = None,
) -> bool:
    if api is None:
        from isotope.features.supervisor import runner as api

    return (
        action.get("kind") == "launch_session"
        and action.get("source") == "integration_review"
        and action.get("target_name") == api.MERGE_DISPATCH_TARGET_NAME
    )


def mark_merge_dispatch_execution(executed: dict[str, Any]) -> dict[str, Any]:
    if executed.get("kind") == "launch_session":
        executed["display_kind"] = "merge_dispatch"
        executed["source"] = "integration_review"
    return executed
