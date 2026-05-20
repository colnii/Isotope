"""Read-only integration review for Supervisor-managed workers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable

from .flow import _managed_process_log_excerpt, _supervisor_protocol_from_text
from .registry import ManagedCodexRecord, default_registry_path, read_managed_records

RunCommand = Callable[..., subprocess.CompletedProcess[str]]

GROUPS = (
    "merge_workers",
    "ready_to_integrate",
    "already_integrated",
    "needs_review",
    "conflict_risk",
)

MERGE_DISPATCH_TARGET_NAME = "supervisor-merge-dispatch"


def collect_integration_reviews(
    *,
    codex_home: Path | str,
    base_ref: str = "main",
    include_unfinished: bool = False,
    run: RunCommand | None = None,
) -> dict[str, Any]:
    """Collect read-only integration status for Supervisor-managed workers."""
    run_command = run or subprocess.run
    records = [
        record
        for record in read_managed_records(default_registry_path(codex_home))
        if _integration_record_is_in_scope(record, include_unfinished=include_unfinished)
    ]
    workers = [
        _worker_integration_review(record, base_ref=base_ref, run=run_command)
        for record in records
    ]
    groups: dict[str, list[dict[str, Any]]] = {group: [] for group in GROUPS}
    for worker in workers:
        groups[worker["group"]].append(worker)
    return {
        "status": "ok",
        "base_ref": base_ref,
        "include_unfinished": include_unfinished,
        "summary": {
            "total": len(workers),
            **{group: len(groups[group]) for group in GROUPS},
        },
        "groups": groups,
        "workers": workers,
        "safety": {
            "auto_merge": False,
            "push": False,
            "delete_branch": False,
            "note": "只读扫描 managed worker、git 分支和提交包含关系，不执行 merge/push/delete。",
        },
    }


def _integration_record_is_in_scope(
    record: ManagedCodexRecord,
    *,
    include_unfinished: bool,
) -> bool:
    if record.status == "archived":
        return False
    if _merge_worker_source(record) is not None:
        return True
    if include_unfinished:
        return True
    protocol = _protocol_from_record(record)
    return (protocol.get("status") or "").strip().lower() == "done"


def render_integration_review_plain(payload: dict[str, Any]) -> str:
    lines = ["[Supervisor Integration Review]"]
    lines.append(f"base：{payload.get('base_ref') or 'main'}")
    summary = payload.get("summary", {})
    lines.extend(
        [
            f"merge_workers：{summary.get('merge_workers', 0)}",
            f"ready_to_integrate：{summary.get('ready_to_integrate', 0)}",
            f"already_integrated：{summary.get('already_integrated', 0)}",
            f"needs_review：{summary.get('needs_review', 0)}",
            f"conflict_risk：{summary.get('conflict_risk', 0)}",
        ]
    )
    groups = payload.get("groups", {})
    for group in GROUPS:
        items = groups.get(group, [])
        if not items:
            continue
        lines.extend(["", f"{group}:"])
        for item in items:
            branch = item.get("branch") or "未知分支"
            commit = item.get("worker_commit") or "未知提交"
            lines.append(f"- {item.get('name')} / {item.get('record_id')}")
            lines.append(f"  {branch} @ {commit}")
            lines.append(f"  cwd：{item.get('cwd')}")
            lines.append(f"  原因：{item.get('reason')}")
    return "\n".join(lines)


def _worker_integration_review(
    record: ManagedCodexRecord,
    *,
    base_ref: str,
    run: RunCommand,
) -> dict[str, Any]:
    cwd = Path(record.cwd).expanduser()
    cwd_exists = cwd.is_dir()
    protocol = _protocol_from_record(record)
    merge_worker_source = _merge_worker_source(record)
    branch = _git_text(cwd, ["rev-parse", "--abbrev-ref", "HEAD"], run=run) if cwd_exists else _infer_supervisor_branch(cwd)
    worker_commit = _git_text(cwd, ["rev-parse", "HEAD"], run=run) if cwd_exists else None
    base_commit = _git_text(cwd, ["rev-parse", base_ref], run=run) if cwd_exists else None
    status_text = _git_text(cwd, ["status", "--short"], run=run) if cwd_exists else None
    dirty_paths = _parse_status_paths(status_text)
    main_contains_worker = (
        _git_success(cwd, ["merge-base", "--is-ancestor", worker_commit, base_ref], run=run)
        if cwd_exists and worker_commit
        else None
    )
    worker_contains_main = (
        _git_success(cwd, ["merge-base", "--is-ancestor", base_ref, worker_commit], run=run)
        if cwd_exists and worker_commit
        else None
    )
    main_has_worker_patch = _main_has_worker_patch(
        cwd=cwd,
        base_ref=base_ref,
        worker_commit=worker_commit,
        protocol=protocol,
        dirty_paths=dirty_paths,
        main_contains_worker=main_contains_worker,
        cwd_exists=cwd_exists,
        run=run,
    )
    merge_check = (
        _merge_tree_check(cwd, base_ref=base_ref, worker_commit=worker_commit, run=run)
        if cwd_exists and worker_commit
        else _empty_merge_check()
    )
    group, reason, reasons = _classify(
        cwd_exists=cwd_exists,
        protocol=protocol,
        dirty_paths=dirty_paths,
        worker_commit=worker_commit,
        base_commit=base_commit,
        main_contains_worker=main_contains_worker,
        main_has_worker_patch=main_has_worker_patch,
        merge_conflict=merge_check["conflict"],
        merge_worker_source=merge_worker_source,
    )
    return {
        "record_id": record.record_id,
        "name": record.name,
        "cwd": str(cwd),
        "cwd_exists": cwd_exists,
        "branch": branch,
        "worker_commit": worker_commit,
        "base_ref": base_ref,
        "base_commit": base_commit,
        "main_contains_worker": main_contains_worker,
        "main_has_worker_patch": main_has_worker_patch,
        "worker_contains_main": worker_contains_main,
        "dirty": bool(dirty_paths),
        "dirty_paths": dirty_paths,
        "supervisor_protocol": protocol,
        "merge_worker": merge_worker_source is not None,
        "merge_worker_source": merge_worker_source,
        "merge_conflict": merge_check["conflict"],
        "merge_check": merge_check,
        "group": group,
        "reason": reason,
        "reasons": reasons,
    }


def _protocol_from_record(record: ManagedCodexRecord) -> dict[str, str | None]:
    excerpt = _managed_process_log_excerpt(record.log_path) or ""
    parsed = _supervisor_protocol_from_text(excerpt)
    return {
        "status": parsed.get("status"),
        "summary": parsed.get("summary"),
        "next": parsed.get("next"),
    }


def _classify(
    *,
    cwd_exists: bool,
    protocol: dict[str, str | None],
    dirty_paths: list[dict[str, str]],
    worker_commit: str | None,
    base_commit: str | None,
    main_contains_worker: bool | None,
    main_has_worker_patch: bool | None,
    merge_conflict: bool,
    merge_worker_source: str | None,
) -> tuple[str, str, list[str]]:
    status = (protocol.get("status") or "").strip().lower()
    reasons: list[str] = []
    if status:
        reasons.append(f"worker 汇报 {status}")
    else:
        reasons.append("worker 未汇报 SUPERVISOR_STATUS")

    if merge_worker_source is not None:
        return (
            "merge_workers",
            "这是 integration-review 启动的 merge worker；单独展示，不按普通功能 worker 合入。",
            [*reasons, f"merge worker source: {merge_worker_source}"],
        )
    if not cwd_exists:
        return (
            "needs_review",
            "worker worktree 缺失；先确认登记表和分支是否仍存在。",
            [*reasons, "cwd/worktree 缺失"],
        )
    if dirty_paths:
        return (
            "needs_review",
            "worker worktree 仍有未提交改动；先复查并要求 worker 提交。",
            [*reasons, f"存在 {len(dirty_paths)} 个未提交改动路径"],
        )
    if status != "done":
        return (
            "needs_review",
            "worker 未汇报 done；先按 SUPERVISOR_NEXT 继续或拆分。",
            reasons,
        )
    if not worker_commit or not base_commit:
        return (
            "needs_review",
            "缺少 worker 或 main 提交哈希；先检查 git 分支状态。",
            [*reasons, "git 提交信息不完整"],
        )
    if main_contains_worker:
        return (
            "already_integrated",
            "main 已包含 worker HEAD；可检查后归档。",
            [*reasons, "main 已包含 worker 提交"],
        )
    if main_has_worker_patch:
        return (
            "already_integrated",
            "main 已包含 worker 等价补丁；可检查后归档。",
            [*reasons, "main 已包含 worker 等价补丁"],
        )
    if merge_conflict:
        return (
            "conflict_risk",
            "只读 merge-tree 检测到 conflict；需要人工 rebase/merge 处理。",
            [*reasons, "merge-tree conflict"],
        )
    return (
        "ready_to_integrate",
        "worker 已完成、分支干净、main 尚未包含且未检测到 merge conflict。",
        [*reasons, "main 尚未包含 worker 提交或等价补丁", "未检测到 merge conflict"],
    )


def _main_has_worker_patch(
    *,
    cwd: Path,
    base_ref: str,
    worker_commit: str | None,
    protocol: dict[str, str | None],
    dirty_paths: list[dict[str, str]],
    main_contains_worker: bool | None,
    cwd_exists: bool,
    run: RunCommand,
) -> bool | None:
    if main_contains_worker is True:
        return True
    status = (protocol.get("status") or "").strip().lower()
    if (
        not cwd_exists
        or not worker_commit
        or status != "done"
        or dirty_paths
        or main_contains_worker is not False
    ):
        return None
    completed = _git_completed(cwd, ["cherry", base_ref, worker_commit], run=run)
    if completed is None or completed.returncode != 0:
        return None
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        return None
    return all(line.startswith("-") for line in lines)


def _merge_worker_source(record: ManagedCodexRecord) -> str | None:
    if record.name == MERGE_DISPATCH_TARGET_NAME:
        return "target_name"
    text = "\n".join([record.prompt, *record.command]).lower()
    if "source=integration_review" in text or "source: integration_review" in text:
        return "integration_review"
    if '"source": "integration_review"' in text:
        return "integration_review"
    if "source: supervisor integration-review payload" in text:
        return "integration_review"
    return None


def _parse_status_paths(status_text: str | None) -> list[dict[str, str]]:
    if not status_text:
        return []
    paths: list[dict[str, str]] = []
    for line in status_text.splitlines():
        if not line.strip():
            continue
        status = line[:2].strip() or line[:2]
        path = line[3:] if len(line) > 3 else ""
        paths.append({"status": status, "path": path.strip()})
    return paths


def _merge_tree_check(
    cwd: Path,
    *,
    base_ref: str,
    worker_commit: str,
    run: RunCommand,
) -> dict[str, Any]:
    completed = _git_completed(
        cwd,
        ["merge-tree", "--write-tree", base_ref, worker_commit],
        run=run,
    )
    if completed is None:
        return {
            "available": False,
            "conflict": False,
            "returncode": None,
            "stdout": None,
            "stderr": None,
        }
    return {
        "available": True,
        "conflict": completed.returncode != 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.rstrip(),
        "stderr": completed.stderr.rstrip(),
    }


def _empty_merge_check() -> dict[str, Any]:
    return {
        "available": False,
        "conflict": False,
        "returncode": None,
        "stdout": None,
        "stderr": None,
    }


def _git_success(cwd: Path, args: list[str | None], *, run: RunCommand) -> bool | None:
    if any(arg is None for arg in args):
        return None
    completed = _git_completed(cwd, [str(arg) for arg in args], run=run)
    if completed is None:
        return None
    return completed.returncode == 0


def _git_text(cwd: Path, args: list[str], *, run: RunCommand) -> str | None:
    completed = _git_completed(cwd, args, run=run)
    if completed is None or completed.returncode != 0:
        return None
    text = completed.stdout.rstrip()
    return text or None


def _git_completed(
    cwd: Path,
    args: list[str],
    *,
    run: RunCommand,
) -> subprocess.CompletedProcess[str] | None:
    try:
        return run(
            ["git", "-C", str(cwd), *args],
            check=False,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError, TypeError):
        return None


def _infer_supervisor_branch(cwd: Path) -> str | None:
    parts = cwd.parts
    for index, part in enumerate(parts):
        if part == "supervisor" and index > 0 and parts[index - 1] == ".worktrees":
            if index + 1 < len(parts):
                return f"supervisor/{parts[index + 1]}"
    return None
