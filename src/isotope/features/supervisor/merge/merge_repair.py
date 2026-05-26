"""Blocked merge-worker repair helpers for Supervisor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .merge_dispatch import DEFAULT_TARGET_NAME


def blocked_merge_worker_cwd(
    item: dict[str, Any],
    *,
    record: Any | None,
) -> Path | None:
    candidates = [item.get("cwd"), getattr(record, "cwd", None)]
    for candidate in candidates:
        text = _non_empty_text(candidate)
        if text is None:
            continue
        cwd = Path(text).expanduser()
        if cwd.is_dir():
            return cwd
    return None


def merge_dispatch_conflict_repair_prompt(
    *,
    item: dict[str, Any],
    cwd: Path,
) -> str:
    protocol = item.get("supervisor_protocol")
    protocol = protocol if isinstance(protocol, dict) else {}
    summary = _non_empty_text(protocol.get("summary")) or "merge worker 汇报 blocked"
    next_step = _non_empty_text(protocol.get("next")) or "继续处理当前 merge worktree"
    return "\n".join(
        [
            "修复 merge-dispatch worker 在当前 worktree 中留下的阻塞状态。",
            f"cwd: {cwd}",
            f"merge worker: {_non_empty_text(item.get('name')) or DEFAULT_TARGET_NAME}",
            f"record_id: {_non_empty_text(item.get('record_id')) or 'unknown'}",
            f"branch: {_non_empty_text(item.get('branch')) or 'unknown'}",
            f"worker_commit: {_non_empty_text(item.get('worker_commit')) or 'unknown'}",
            "source: integration_review",
            f"blocked summary: {summary}",
            f"blocked next: {next_step}",
            "要求：先运行 git status，确认是否处于 cherry-pick/merge 冲突。",
            (
                "如果是 cherry-pick 冲突，最小化解决冲突后运行 "
                "git cherry-pick --continue；如果不是 cherry-pick，按 git status "
                "显示的真实状态继续。"
            ),
            "继续原 merge worker 的合并目标，不切换到无关任务，不删除分支或 worktree。",
            "修复后运行相关测试，推送当前 merge 分支并观察 CI；失败时说明 run id 和关键错误。",
            "完成后严格按 SUPERVISOR_STATUS、SUPERVISOR_SUMMARY、SUPERVISOR_NEXT 汇报。",
        ]
    )


def _non_empty_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


__all__ = [
    "blocked_merge_worker_cwd",
    "merge_dispatch_conflict_repair_prompt",
]
