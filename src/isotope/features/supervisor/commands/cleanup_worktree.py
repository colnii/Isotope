"""Worktree cleanup guards for the Supervisor cleanup command."""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path
from typing import Any

from isotope.features.supervisor.flow import (
    _managed_process_log_excerpt,
    _supervisor_protocol_from_text,
)
from isotope.features.supervisor.registry import (
    default_registry_path,
    read_managed_record_events,
)


def execute_delete_worktree_action(
    args: argparse.Namespace,
    action: dict[str, Any],
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    target_name = action.get("target_name") or action.get("name")
    record_id = action.get("record_id")
    if not isinstance(target_name, str) or not target_name.strip():
        raise ValueError("target_name is required for delete_worktree")
    if record_id is not None and not isinstance(record_id, str):
        raise ValueError("record_id must be a string for delete_worktree")
    if action.get("confirm_delete_worktree") is not True:
        return {
            "kind": "delete_worktree",
            "target_name": target_name,
            "skipped": True,
            "reason": "missing delete_worktree confirmation",
        }
    record = latest_managed_record_event(
        codex_home=Path(args.codex_home),
        target_name=target_name,
        record_id=record_id,
    )
    if record is None:
        return {
            "kind": "delete_worktree",
            "target_name": target_name,
            "skipped": True,
            "reason": "managed worker not found",
        }
    if record.status != "archived":
        return {
            "kind": "delete_worktree",
            "target_name": target_name,
            "skipped": True,
            "reason": "managed worker is not archived",
            "managed": managed_record_ref(record),
        }
    protocol = _supervisor_protocol_from_text(
        _managed_process_log_excerpt(record.log_path) or ""
    )
    if (protocol.get("status") or "").strip().lower() != "done":
        return {
            "kind": "delete_worktree",
            "target_name": target_name,
            "skipped": True,
            "reason": "managed worker is not done",
            "managed": managed_record_ref(record),
            "supervisor_protocol": protocol,
        }
    worktree = supervisor_worktree_root_for_cwd(record.cwd)
    if worktree is None:
        return {
            "kind": "delete_worktree",
            "target_name": target_name,
            "skipped": True,
            "reason": "worktree is outside .worktrees/supervisor",
            "managed": managed_record_ref(record),
            "cwd": record.cwd,
        }
    if not worktree["worktree_root"].is_dir():
        return {
            "kind": "delete_worktree",
            "target_name": target_name,
            "skipped": True,
            "reason": "worktree missing",
            "managed": managed_record_ref(record),
            "worktree_root": str(worktree["worktree_root"]),
        }
    run = api.subprocess.run
    integration = api.review_managed_record_integration(
        record,
        base_ref=str(action.get("base_ref") or "main"),
        run=run,
    )
    if not integration_review_allows_worktree_delete(integration):
        return {
            "kind": "delete_worktree",
            "target_name": target_name,
            "skipped": True,
            "reason": "worker is not integrated",
            "managed": managed_record_ref(record),
            "integration": delete_worktree_integration_summary(integration),
        }
    command = [
        "git",
        "-C",
        str(worktree["repo_root"]),
        "worktree",
        "remove",
        str(worktree["worktree_root"]),
    ]
    completed = run(
        command,
        check=False,
        text=True,
        capture_output=True,
    )
    command_text = shlex.join(command)
    if completed.returncode != 0:
        return {
            "kind": "delete_worktree",
            "target_name": target_name,
            "command": command_text,
            "skipped": True,
            "reason": "git worktree remove failed",
            "managed": managed_record_ref(record),
            "worktree_root": str(worktree["worktree_root"]),
            "stderr": (completed.stderr or completed.stdout or "").strip(),
        }
    result = {
        "kind": "delete_worktree",
        "target_name": target_name,
        "command": command_text,
        "deleted_worktree": str(worktree["worktree_root"]),
        "managed": managed_record_ref(record),
        "integration": delete_worktree_integration_summary(integration),
    }
    branch = delete_worktree_branch_name(integration)
    if branch is not None:
        result["branch_cleanup"] = delete_integrated_supervisor_branch(
            repo_root=worktree["repo_root"],
            branch=branch,
            base_ref=str(action.get("base_ref") or "main"),
            run=run,
        )
    return result


def delete_worktree_candidate_payloads(
    args: argparse.Namespace,
    *,
    api: Any | None = None,
) -> list[dict[str, Any]]:
    if api is None:
        from isotope.features.supervisor import runner as api

    candidates: list[dict[str, Any]] = []
    for record in api._latest_managed_record_events(Path(args.codex_home)):
        if record.status != "archived":
            continue
        if supervisor_worktree_root_for_cwd(record.cwd) is None:
            continue
        protocol = _supervisor_protocol_from_text(
            _managed_process_log_excerpt(record.log_path) or ""
        )
        if (protocol.get("status") or "").strip().lower() != "done":
            continue
        integration = api.review_managed_record_integration(
            record,
            run=api.subprocess.run,
            run_test_gate=False,
            run_candidate_validation=False,
        )
        if not integration_review_allows_worktree_delete(integration):
            continue
        candidates.append(
            {
                "name": record.name,
                "target_name": record.name,
                "record_id": record.record_id,
                "cwd": record.cwd,
                "archived": True,
                "integration_group": integration.get("group"),
                "main_contains_worker": integration.get("main_contains_worker"),
                "main_has_worker_patch": integration.get("main_has_worker_patch"),
                "worker_commit": integration.get("worker_commit"),
                "base_ref": integration.get("base_ref"),
            }
        )
    return candidates


def latest_managed_record_event(
    *,
    codex_home: Path,
    target_name: str,
    record_id: str | None,
) -> Any | None:
    for record in reversed(read_managed_record_events(default_registry_path(codex_home))):
        if record_id is not None and record.record_id != record_id:
            continue
        if record.name == target_name:
            return record
    return None


def managed_record_ref(record: Any) -> dict[str, Any]:
    return {
        "name": record.name,
        "record_id": record.record_id,
        "status": record.status,
        "cwd": record.cwd,
    }


def supervisor_worktree_root_for_cwd(cwd: str) -> dict[str, Path] | None:
    path = Path(cwd).expanduser().resolve(strict=False)
    parts = path.parts
    for index in range(0, len(parts) - 2):
        if parts[index] != ".worktrees" or parts[index + 1] != "supervisor":
            continue
        repo_root = Path(*parts[:index])
        worktree_root = Path(*parts[: index + 3])
        if worktree_root.parent.name != "supervisor":
            return None
        return {"repo_root": repo_root, "worktree_root": worktree_root}
    return None


def integration_review_allows_worktree_delete(integration: dict[str, Any]) -> bool:
    return (
        integration.get("group") in {"already_integrated", "merge_workers"}
        and integration.get("dirty") is False
        and (
            integration.get("main_contains_worker") is True
            or integration.get("main_has_worker_patch") is True
        )
    )


def delete_worktree_integration_summary(integration: dict[str, Any]) -> dict[str, Any]:
    return {
        "group": integration.get("group"),
        "reason": integration.get("reason"),
        "worker_commit": integration.get("worker_commit"),
        "base_ref": integration.get("base_ref"),
        "main_contains_worker": integration.get("main_contains_worker"),
        "main_has_worker_patch": integration.get("main_has_worker_patch"),
        "dirty": integration.get("dirty"),
    }


def delete_worktree_branch_name(integration: dict[str, Any]) -> str | None:
    branch = integration.get("branch")
    if isinstance(branch, str) and branch.strip():
        return branch.strip()
    return None


def delete_integrated_supervisor_branch(
    *,
    repo_root: Path,
    branch: str,
    base_ref: str,
    run: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {"branch": branch}
    if not is_deletable_supervisor_branch(branch):
        result.update(
            {"skipped": True, "reason": "branch is outside supervisor namespace"}
        )
        return result
    upstream = branch_upstream(repo_root=repo_root, branch=branch, run=run)
    if upstream is not None:
        result["upstream"] = upstream
    if not branch_is_merged_into_base(
        repo_root=repo_root,
        branch=branch,
        base_ref=base_ref,
        run=run,
    ):
        result.update({"skipped": True, "reason": "branch is not merged into base"})
        return result
    local_delete = run(
        ["git", "-C", str(repo_root), "branch", "-d", branch],
        check=False,
        text=True,
        capture_output=True,
    )
    if local_delete.returncode != 0:
        result.update(
            {
                "skipped": True,
                "reason": "git branch delete failed",
                "stderr": (local_delete.stderr or local_delete.stdout or "").strip(),
            }
        )
        return result
    result["deleted_local_branch"] = branch
    if upstream is not None and is_deletable_supervisor_upstream(upstream):
        remote, remote_branch = upstream.split("/", 1)
        remote_delete = run(
            ["git", "-C", str(repo_root), "push", remote, "--delete", remote_branch],
            check=False,
            text=True,
            capture_output=True,
        )
        if remote_delete.returncode == 0:
            result["deleted_upstream_branch"] = upstream
        else:
            result["upstream_delete_skipped"] = True
            result["upstream_delete_reason"] = "git push --delete failed"
            result["upstream_delete_stderr"] = (
                remote_delete.stderr or remote_delete.stdout or ""
            ).strip()
    return result


def is_deletable_supervisor_branch(branch: str) -> bool:
    return branch.startswith("supervisor/") and branch not in {"supervisor/main"}


def is_deletable_supervisor_upstream(upstream: str) -> bool:
    return upstream.startswith("origin/supervisor/")


def branch_upstream(*, repo_root: Path, branch: str, run: Any) -> str | None:
    completed = run(
        [
            "git",
            "-C",
            str(repo_root),
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            f"{branch}@{{upstream}}",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        return None
    upstream = (completed.stdout or "").strip()
    return upstream or None


def branch_is_merged_into_base(
    *,
    repo_root: Path,
    branch: str,
    base_ref: str,
    run: Any,
) -> bool:
    completed = run(
        ["git", "-C", str(repo_root), "merge-base", "--is-ancestor", branch, base_ref],
        check=False,
        text=True,
        capture_output=True,
    )
    return completed.returncode == 0
