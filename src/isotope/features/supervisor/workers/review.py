"""Review summaries for Supervisor-managed Codex workers."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable

from ..flow import (
    _managed_process_log_excerpt,
    _pid_is_running,
    _supervisor_protocol_from_text,
)
from ..registry import ManagedCodexRecord, default_registry_path, read_managed_records
from .test_gate import collect_worker_test_gate


RunCommand = Callable[..., subprocess.CompletedProcess[str]]
ProcessChecker = Callable[[int], bool]
LIGHTWEIGHT_WORKER_LIMIT = 40


def collect_worker_reviews(
    *,
    codex_home: Path | str,
    lightweight: bool = False,
    run: RunCommand = subprocess.run,
    process_checker: ProcessChecker | None = None,
) -> dict[str, Any]:
    """Build a no-side-effect review payload for Supervisor-managed workers."""
    records = read_managed_records(default_registry_path(codex_home))
    review_records = (
        records[-LIGHTWEIGHT_WORKER_LIMIT:]
        if lightweight and len(records) > LIGHTWEIGHT_WORKER_LIMIT
        else records
    )
    workers = [
        _worker_review(
            record,
            lightweight=lightweight,
            run=run,
            process_checker=process_checker or _pid_is_running,
        )
        for record in review_records
    ]
    hidden_workers = len(records) - len(review_records)
    return {
        "status": "ok",
        "summary": {
            "total": len(records),
            "visible": len(workers),
            "hidden_by_lightweight_limit": hidden_workers,
            "existing_cwd": sum(
                1 for record in records if Path(record.cwd).expanduser().is_dir()
            ),
            "missing_cwd": sum(
                1 for record in records if not Path(record.cwd).expanduser().is_dir()
            ),
        },
        "decision_summary": _decision_summary(workers),
        "automation_candidates": _automation_candidates(workers, lightweight=lightweight),
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
    decision_summary = payload.get("decision_summary", {})
    lines.append(
        "决策汇总：合并候选 {merge_candidates} / 继续拆任务 {continue_or_split_tasks} / "
        "缺失 worktree {missing_worktrees} / 需 fresh review {needs_fresh_review}".format(
            merge_candidates=decision_summary.get("merge_candidates", 0),
            continue_or_split_tasks=decision_summary.get("continue_or_split_tasks", 0),
            missing_worktrees=decision_summary.get("missing_worktrees", 0),
            needs_fresh_review=decision_summary.get("needs_fresh_review", 0),
        )
    )
    for worker in payload.get("workers", []):
        protocol = worker.get("supervisor_protocol", {})
        changes = worker.get("changes", {})
        worktree = worker.get("worktree", {})
        next_decision = worker.get("next_decision", {})
        lines.extend(
            [
                "",
                f"- {worker.get('name')} / {worker.get('record_id')}",
                f"  cwd：{worker.get('cwd')} ({'存在' if worker.get('cwd_exists') else '缺失'})",
                f"  branch：{worktree.get('branch') or '未知'}",
                f"  状态协议：{protocol.get('status') or '未汇报'} / {protocol.get('summary') or '无摘要'}",
                "  测试门控：{status} / passed={passed} / exit_code={exit_code}".format(
                    status=worker.get("test_status") or "unknown",
                    passed=worker.get("test_passed"),
                    exit_code=worker.get("test_exit_code"),
                ),
                f"  改动：{changes.get('summary')}",
                f"  下一步决策：{next_decision.get('summary') or '无'}",
                "  决策标记：适合合并：{merge_suitable} / 继续拆任务：{continue_or_split} / 风险：{risk_level}".format(
                    merge_suitable="是" if next_decision.get("merge_suitable") else "否",
                    continue_or_split="是"
                    if next_decision.get("continue_or_split_task")
                    else "否",
                    risk_level=next_decision.get("risk_level") or "未知",
                ),
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
    lightweight: bool,
    run: RunCommand,
    process_checker: ProcessChecker,
) -> dict[str, Any]:
    cwd = Path(record.cwd).expanduser()
    cwd_exists = cwd.is_dir()
    protocol = _protocol_from_record(record)
    branch = (
        _infer_supervisor_branch(cwd)
        if lightweight
        else _branch_for_record(record, cwd_exists=cwd_exists, run=run)
    )
    worktree = {
        "exists": cwd_exists,
        "cwd": str(cwd),
        "root": None
        if lightweight or not cwd_exists
        else _git_text(cwd, ["rev-parse", "--show-toplevel"], run=run),
        "branch": branch,
        "inferred_branch": _infer_supervisor_branch(cwd) if not cwd_exists else None,
    }
    changes = (
        _lightweight_changes(cwd_exists=cwd_exists)
        if lightweight
        else (_changes_for_cwd(cwd, run=run) if cwd_exists else _missing_changes())
    )
    validation_commands = _validation_commands(cwd, cwd_exists=cwd_exists)
    test_gate = (
        _skipped_test_gate("loop 快速状态跳过 pytest gate；运行 worker-review 可做重审。")
        if lightweight
        else collect_worker_test_gate(
            record,
            protocol=protocol,
            cwd=cwd,
            cwd_exists=cwd_exists,
            run=run,
        )
    )
    next_decision = _next_decision(
        protocol=protocol,
        cwd_exists=cwd_exists,
        changes=changes,
        validation_commands=validation_commands,
        test_gate=test_gate,
    )
    reviewer = _reviewer_suggestion(
        record=record,
        cwd=cwd,
        cwd_exists=cwd_exists,
        branch=branch,
        changes=changes,
        validation_commands=validation_commands,
    )
    payload = {
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
        **test_gate,
        "changes": changes,
        "validation_commands": validation_commands,
        "next_decision": next_decision,
        "reviewer": reviewer,
        "merge_hint": _merge_hint(branch=branch, cwd_exists=cwd_exists, changes=changes),
    }
    if lightweight:
        payload.pop("prompt", None)
        payload.pop("validation_commands", None)
        payload["reviewer"] = {
            "needed": bool(reviewer.get("needed")),
            "reason": reviewer.get("reason"),
        }
        if isinstance(payload.get("changes"), dict):
            payload["changes"] = {
                "status": payload["changes"].get("status"),
                "summary": payload["changes"].get("summary"),
            }
    return payload


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


def _lightweight_changes(*, cwd_exists: bool) -> dict[str, Any]:
    if not cwd_exists:
        return _missing_changes()
    return {
        "status": "unknown",
        "files": [],
        "stat": None,
        "summary": "loop 快速状态未读取 diff",
    }


def _skipped_test_gate(reason: str) -> dict[str, Any]:
    return {
        "test_status": "skipped",
        "test_passed": None,
        "test_exit_code": None,
        "test_output_tail": reason,
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
        f"cd {quoted_cwd} && PYTHONPATH=src .venv/bin/python -m pytest tests -q",
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


def _next_decision(
    *,
    protocol: dict[str, str | None],
    cwd_exists: bool,
    changes: dict[str, Any],
    validation_commands: list[str],
    test_gate: dict[str, Any],
) -> dict[str, Any]:
    status = (protocol.get("status") or "").strip().lower()
    changed_files = changes.get("files") or []
    change_count = len(changed_files)
    reasons = _decision_reasons(
        status=status,
        change_count=change_count,
        has_untracked=_has_untracked_files(changed_files),
        needs_validation=bool(validation_commands) and changes.get("status") == "modified",
        test_passed=test_gate.get("test_passed"),
    )

    if not cwd_exists:
        return {
            "recommendation": "recover_or_archive_missing_worktree",
            "summary": "worker worktree 缺失；先确认分支和登记表，再决定恢复或归档。",
            "merge_suitable": False,
            "continue_or_split_task": False,
            "risk_level": "high",
            "reasons": reasons or ["cwd/worktree 缺失"],
            "next_actions": [
                "运行 git worktree list --porcelain",
                "确认 worker 分支是否仍存在",
                "人工决定恢复 worktree 或归档登记",
            ],
        }

    if changes.get("status") == "clean":
        return {
            "recommendation": "archive_or_wait",
            "summary": "worker 没有本地改动；可检查汇报后归档或等待下一次状态。",
            "merge_suitable": False,
            "continue_or_split_task": False,
            "risk_level": "low",
            "reasons": reasons or ["无本地改动"],
            "next_actions": [
                "检查 worker 状态协议和日志",
                "无需合并时归档登记",
            ],
        }

    if status == "done":
        if test_gate.get("test_passed") is False:
            return {
                "recommendation": "continue_or_split_task",
                "summary": "worker 已汇报完成但测试门控失败；先复查测试输出并修复后再考虑合并。",
                "merge_suitable": False,
                "continue_or_split_task": True,
                "risk_level": "high",
                "reasons": reasons,
                "next_actions": [
                    "阅读 worker 的 pytest 输出尾部",
                    "要求 worker 修复失败测试或说明误报",
                    "重新运行 worker-review 和 integration-review",
                ],
            }
        return {
            "recommendation": "review_then_merge_candidate",
            "summary": "worker 已完成且有本地改动；建议先复查 diff 并跑验证，通过后再人工合并。",
            "merge_suitable": True,
            "continue_or_split_task": False,
            "risk_level": "medium",
            "reasons": reasons,
            "next_actions": [
                "审查 git diff 和 worker 汇报",
                "运行建议验证命令",
                "验证通过后由主控/人工处理合并",
            ],
        }

    return {
        "recommendation": "continue_or_split_task",
        "summary": "worker 未完成但已有改动；不适合合并，建议按汇报继续推进或拆成后续任务。",
        "merge_suitable": False,
        "continue_or_split_task": True,
        "risk_level": "high",
        "reasons": reasons,
        "next_actions": [
            "阅读 worker 的 SUPERVISOR_NEXT",
            "判断是否继续当前 worker 或拆出新任务",
            "暂不合并该 worktree",
        ],
    }


def _decision_reasons(
    *,
    status: str,
    change_count: int,
    has_untracked: bool,
    needs_validation: bool,
    test_passed: bool | None,
) -> list[str]:
    reasons: list[str] = []
    if status:
        reasons.append(f"worker 汇报 {status}")
    else:
        reasons.append("worker 未汇报 SUPERVISOR_STATUS")
    if change_count:
        reasons.append(f"存在 {change_count} 个改动路径")
    if has_untracked:
        reasons.append("包含未跟踪文件")
    if needs_validation:
        reasons.append("需要先运行建议验证命令")
    if test_passed is False:
        reasons.append("pytest gate failed")
    return reasons


def _has_untracked_files(files: list[dict[str, str]]) -> bool:
    return any(item.get("status") == "??" for item in files)


def _decision_summary(workers: list[dict[str, Any]]) -> dict[str, int]:
    decisions = [worker.get("next_decision", {}) for worker in workers]
    return {
        "merge_candidates": sum(1 for item in decisions if item.get("merge_suitable")),
        "continue_or_split_tasks": sum(
            1 for item in decisions if item.get("continue_or_split_task")
        ),
        "missing_worktrees": sum(
            1
            for item in decisions
            if item.get("recommendation") == "recover_or_archive_missing_worktree"
        ),
        "needs_fresh_review": sum(
            1 for worker in workers if worker.get("reviewer", {}).get("needed")
        ),
    }


def _automation_candidates(
    workers: list[dict[str, Any]],
    *,
    lightweight: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    candidates: dict[str, list[dict[str, Any]]] = {
        "review_then_merge": [],
        "continue_or_split": [],
        "archive_or_wait": [],
        "recover_or_archive": [],
    }
    for worker in workers:
        decision = worker.get("next_decision", {})
        bucket = _automation_candidate_bucket(decision.get("recommendation"))
        if not bucket:
            continue
        worktree = worker.get("worktree", {})
        reviewer = worker.get("reviewer", {})
        candidate = {
            "record_id": worker.get("record_id"),
            "name": worker.get("name"),
            "cwd": worker.get("cwd"),
            "branch": worktree.get("branch"),
            "recommendation": decision.get("recommendation"),
            "risk_level": decision.get("risk_level"),
            "reason": decision.get("summary"),
        }
        if not lightweight:
            candidate.update(
                {
                    "reasons": decision.get("reasons", []),
                    "next_actions": decision.get("next_actions", []),
                    "validation_commands": worker.get("validation_commands", []),
                    "test_status": worker.get("test_status"),
                    "test_passed": worker.get("test_passed"),
                    "test_exit_code": worker.get("test_exit_code"),
                    "test_output_tail": worker.get("test_output_tail"),
                    "reviewer_command": reviewer.get("command"),
                }
            )
        candidates[bucket].append(candidate)
    return candidates


def _automation_candidate_bucket(recommendation: str | None) -> str | None:
    if recommendation == "review_then_merge_candidate":
        return "review_then_merge"
    if recommendation == "continue_or_split_task":
        return "continue_or_split"
    if recommendation == "archive_or_wait":
        return "archive_or_wait"
    if recommendation == "recover_or_archive_missing_worktree":
        return "recover_or_archive"
    return None


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
