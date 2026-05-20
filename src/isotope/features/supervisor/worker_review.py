"""Review summaries for Supervisor-managed Codex workers."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable

from .flow import (
    _managed_process_log_excerpt,
    _pid_is_running,
    _supervisor_protocol_from_text,
)
from .registry import ManagedCodexRecord, default_registry_path, read_managed_records


RunCommand = Callable[..., subprocess.CompletedProcess[str]]
ProcessChecker = Callable[[int], bool]


def collect_worker_reviews(
    *,
    codex_home: Path | str,
    run: RunCommand = subprocess.run,
    process_checker: ProcessChecker | None = None,
) -> dict[str, Any]:
    """Build a no-side-effect review payload for Supervisor-managed workers."""
    records = read_managed_records(default_registry_path(codex_home))
    workers = [
        _worker_review(
            record,
            run=run,
            process_checker=process_checker or _pid_is_running,
        )
        for record in records
    ]
    return {
        "status": "ok",
        "summary": {
            "total": len(workers),
            "existing_cwd": sum(1 for item in workers if item["cwd_exists"]),
            "missing_cwd": sum(1 for item in workers if not item["cwd_exists"]),
        },
        "workers": workers,
        "safety": {
            "auto_merge": False,
            "delete_branch": False,
            "note": "只汇总审查信息，不自动合并、不删除 worktree 或分支。",
        },
    }


def render_worker_review_plain(payload: dict[str, Any]) -> str:
    lines = ["[Supervisor Worker Review]"]
    summary = payload.get("summary", {})
    lines.append(
        "总数：{total} / cwd 存在：{existing_cwd} / cwd 缺失：{missing_cwd}".format(
            total=summary.get("total", 0),
            existing_cwd=summary.get("existing_cwd", 0),
            missing_cwd=summary.get("missing_cwd", 0),
        )
    )
    for worker in payload.get("workers", []):
        protocol = worker.get("supervisor_protocol", {})
        changes = worker.get("changes", {})
        worktree = worker.get("worktree", {})
        lines.extend(
            [
                "",
                f"- {worker.get('name')} / {worker.get('record_id')}",
                f"  cwd：{worker.get('cwd')} ({'存在' if worker.get('cwd_exists') else '缺失'})",
                f"  branch：{worktree.get('branch') or '未知'}",
                f"  状态协议：{protocol.get('status') or '未汇报'} / {protocol.get('summary') or '无摘要'}",
                f"  改动：{changes.get('summary')}",
                f"  合并提示：{worker.get('merge_hint')}",
            ]
        )
        commands = worker.get("validation_commands", [])
        if commands:
            lines.append("  建议验证：")
            lines.extend(f"    {command}" for command in commands)
        reviewer = worker.get("reviewer", {})
        if reviewer.get("needed"):
            lines.append("  Fresh Codex 复查建议：")
            lines.append(f"    {reviewer.get('command')}")
            lines.append("    必查风险：")
            lines.extend(f"      - {risk}" for risk in reviewer.get("must_check_risks", []))
        elif reviewer.get("reason"):
            lines.append(f"  Fresh Codex 复查：{reviewer.get('reason')}")
    return "\n".join(lines)


def _worker_review(
    record: ManagedCodexRecord,
    *,
    run: RunCommand,
    process_checker: ProcessChecker,
) -> dict[str, Any]:
    cwd = Path(record.cwd).expanduser()
    cwd_exists = cwd.is_dir()
    protocol = _protocol_from_record(record)
    branch = _branch_for_record(record, cwd_exists=cwd_exists, run=run)
    worktree = {
        "exists": cwd_exists,
        "cwd": str(cwd),
        "root": _git_text(cwd, ["rev-parse", "--show-toplevel"], run=run)
        if cwd_exists
        else None,
        "branch": branch,
        "inferred_branch": _infer_supervisor_branch(cwd) if not cwd_exists else None,
    }
    changes = _changes_for_cwd(cwd, run=run) if cwd_exists else _missing_changes()
    validation_commands = _validation_commands(cwd, cwd_exists=cwd_exists)
    reviewer = _reviewer_suggestion(
        record=record,
        cwd=cwd,
        cwd_exists=cwd_exists,
        branch=branch,
        changes=changes,
        validation_commands=validation_commands,
    )
    return {
        "record_id": record.record_id,
        "name": record.name,
        "backend": record.backend,
        "pid": record.pid,
        "process_running": process_checker(record.pid)
        if record.backend != "tmux" and record.pid
        else None,
        "registry_status": record.status,
        "cwd": str(cwd),
        "cwd_exists": cwd_exists,
        "prompt": record.prompt,
        "started_at": record.started_at,
        "log_path": record.log_path,
        "worktree": worktree,
        "supervisor_protocol": protocol,
        "changes": changes,
        "validation_commands": validation_commands,
        "reviewer": reviewer,
        "merge_hint": _merge_hint(branch=branch, cwd_exists=cwd_exists, changes=changes),
    }


def _protocol_from_record(record: ManagedCodexRecord) -> dict[str, str | None]:
    excerpt = _managed_process_log_excerpt(record.log_path) or ""
    parsed = _supervisor_protocol_from_text(excerpt)
    return {
        "status": parsed.get("status"),
        "summary": parsed.get("summary"),
        "next": parsed.get("next"),
    }


def _branch_for_record(
    record: ManagedCodexRecord,
    *,
    cwd_exists: bool,
    run: RunCommand,
) -> str | None:
    cwd = Path(record.cwd).expanduser()
    if cwd_exists:
        return _git_text(cwd, ["rev-parse", "--abbrev-ref", "HEAD"], run=run)
    return _infer_supervisor_branch(cwd)


def _changes_for_cwd(cwd: Path, *, run: RunCommand) -> dict[str, Any]:
    status_text = _git_text(cwd, ["status", "--short"], run=run)
    stat_text = _git_text(cwd, ["diff", "--stat"], run=run)
    if not status_text:
        return {
            "status": "clean",
            "files": [],
            "stat": None,
            "summary": "无本地改动",
        }
    files = [_parse_status_line(line) for line in status_text.splitlines() if line.strip()]
    return {
        "status": "modified",
        "files": files,
        "stat": stat_text,
        "summary": f"{len(files)} 个路径有改动",
    }


def _missing_changes() -> dict[str, Any]:
    return {
        "status": "unavailable",
        "files": [],
        "stat": None,
        "summary": "cwd/worktree 缺失，无法读取改动",
    }


def _parse_status_line(line: str) -> dict[str, str]:
    status = line[:2].strip() or line[:2]
    path = line[3:] if len(line) > 3 else ""
    return {"status": status, "path": path.strip()}


def _validation_commands(cwd: Path, *, cwd_exists: bool) -> list[str]:
    if not cwd_exists:
        return [
            f"test -d {shlex.quote(str(cwd))}",
            "git worktree list --porcelain",
        ]
    quoted_cwd = shlex.quote(str(cwd))
    return [
        f"git -C {quoted_cwd} status --short --branch",
        f"git -C {quoted_cwd} diff --stat",
        f"cd {quoted_cwd} && PYTHONPATH=src .venv/bin/python -m pytest tests/isotope -q",
    ]


def _reviewer_suggestion(
    *,
    record: ManagedCodexRecord,
    cwd: Path,
    cwd_exists: bool,
    branch: str | None,
    changes: dict[str, Any],
    validation_commands: list[str],
) -> dict[str, Any]:
    if not cwd_exists:
        return {
            "needed": False,
            "reason": "cwd/worktree 缺失，无法生成可执行复查建议",
        }
    if changes.get("status") != "modified":
        return {
            "needed": False,
            "reason": "无本地改动，无需 fresh Codex 复查",
        }

    goal = record.prompt or record.name
    branch_text = branch or "未知"
    risks = [
        "只复查 diff、测试和 worker 汇报，不自动启动新 worker。",
        "不自动合并、不删除 worktree、不重写分支。",
        "确认改动是否越过原目标范围，尤其是未跟踪文件和 Supervisor 入口行为。",
        "验证命令失败时先记录证据，避免用合并掩盖失败。",
    ]
    prompt = _reviewer_prompt(
        goal=goal,
        cwd=cwd,
        branch=branch_text,
        changes=changes,
        validation_commands=validation_commands,
        risks=risks,
    )
    return {
        "needed": True,
        "goal": goal,
        "cwd": str(cwd),
        "branch": branch_text,
        "change_summary": changes.get("summary"),
        "changed_files": changes.get("files", []),
        "diff_stat": changes.get("stat"),
        "validation_commands": validation_commands,
        "must_check_risks": risks,
        "prompt": prompt,
        "command": f"codex exec -C {shlex.quote(str(cwd))} {shlex.quote(prompt)}",
    }


def _reviewer_prompt(
    *,
    goal: str,
    cwd: Path,
    branch: str,
    changes: dict[str, Any],
    validation_commands: list[str],
    risks: list[str],
) -> str:
    files = changes.get("files", [])
    file_lines = [
        f"- {item.get('status')}: {item.get('path')}"
        for item in files
        if item.get("path")
    ]
    lines = [
        "请作为 fresh Codex 复查这个 worker 的结果，只审查和汇报，不自动启动、不自动合并、不删除 worktree。",
        "",
        f"目标：{goal}",
        f"cwd：{cwd}",
        f"branch：{branch}",
        f"改动摘要：{changes.get('summary')}",
    ]
    if file_lines:
        lines.append("改动文件：")
        lines.extend(file_lines)
    if changes.get("stat"):
        lines.extend(["diff stat：", str(changes["stat"])])
    lines.append("建议验证命令：")
    lines.extend(f"- {command}" for command in validation_commands)
    lines.append("必须检查的风险：")
    lines.extend(f"- {risk}" for risk in risks)
    lines.append("请最终用中文给出发现、验证证据和是否建议主控人工合并。")
    return "\n".join(lines)


def _merge_hint(
    *,
    branch: str | None,
    cwd_exists: bool,
    changes: dict[str, Any],
) -> str:
    if not cwd_exists:
        return "worktree 已不存在；先用 git worktree list 和 git branch 确认分支，再决定是否人工恢复或归档。"
    if changes.get("status") == "clean":
        return "无本地改动；主控 Codex 可检查状态协议和日志后归档，不需要合并。"
    branch_text = branch or "<worker-branch>"
    return (
        "不自动合并；主控 Codex/人工应先审查 diff、运行建议验证命令，"
        f"确认后再从集成工作区处理 {branch_text}。"
    )


def _infer_supervisor_branch(cwd: Path) -> str | None:
    parts = cwd.parts
    for index, part in enumerate(parts):
        if part == "supervisor" and index > 0 and parts[index - 1] == ".worktrees":
            if index + 1 < len(parts):
                return f"supervisor/{parts[index + 1]}"
    return None


def _git_text(cwd: Path, args: list[str], *, run: RunCommand) -> str | None:
    try:
        completed = run(
            ["git", "-C", str(cwd), *args],
            check=False,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError, TypeError):
        return None
    if completed.returncode != 0:
        return None
    text = completed.stdout.rstrip()
    return text or None
