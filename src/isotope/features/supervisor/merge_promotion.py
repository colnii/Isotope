"""Merge-promotion helpers for Supervisor."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any


def merge_promotion_repair_prompt(
    *,
    item: dict[str, Any],
    branch_ci: dict[str, Any],
    decision_answer: dict[str, Any] | None,
) -> str:
    answer_text = (
        str(decision_answer.get("answer"))
        if isinstance(decision_answer, dict) and decision_answer.get("answer") is not None
        else ""
    ).strip()
    return "\n".join(
        [
            "修复 merge promotion 失败，并在修复后汇报状态。",
            f"merge worker: {_non_empty_text(item.get('name')) or 'unknown'}",
            f"record_id: {_non_empty_text(item.get('record_id')) or 'unknown'}",
            f"branch: {_non_empty_text(item.get('branch')) or 'unknown'}",
            f"worker_commit: {_non_empty_text(item.get('worker_commit')) or 'unknown'}",
            f"用户拍板: {answer_text or '修复后重试'}",
            "失败 CI:",
            json.dumps(branch_ci, ensure_ascii=False, sort_keys=True),
            "要求：检查失败原因，做必要代码修复和相关测试。",
            "不要 force push，不要改写共享历史；完成后按 SUPERVISOR_STATUS 协议汇报。",
        ]
    )


def merge_promotion_decision_intent(answer: dict[str, Any] | None) -> str | None:
    if not isinstance(answer, dict):
        return None
    text = str(answer.get("answer") or "").strip().lower()
    if not text:
        return None
    if any(token in text for token in ("放弃", "不再", "不要合", "丢弃", "abandon", "drop")):
        return "abandon"
    if any(token in text for token in ("修复", "fix", "repair")):
        return "repair"
    if any(token in text for token in ("重试", "再试", "retry", "rerun")):
        return "retry"
    return "unknown"


def check_main_promotion_preconditions(repo_root: Path, *, run: Any) -> str | None:
    branch = git_text(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"], run=run)
    if branch != "main":
        return f"workspace branch is {branch or 'unknown'}, expected main"
    status = git_text(repo_root, ["status", "--short"], run=run)
    if status is None:
        return "unable to read git status"
    if status.strip():
        return "main worktree is dirty"
    return None


def latest_ci_run_for_ref(*, branch: str, commit: str, run: Any) -> dict[str, Any]:
    completed = run(
        [
            "gh",
            "run",
            "list",
            "--workflow",
            "CI",
            "--branch",
            branch,
            "--commit",
            commit,
            "--limit",
            "1",
            "--json",
            "databaseId,headSha,status,conclusion,url",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        return {
            "status": "unavailable",
            "conclusion": "failure",
            "stderr": _tail_text(completed.stderr),
        }
    try:
        runs = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError:
        return {"status": "invalid_json", "conclusion": "failure"}
    if not isinstance(runs, list) or not runs:
        return {"status": "missing", "conclusion": None}
    first = runs[0]
    return first if isinstance(first, dict) else {"status": "invalid_item"}


def view_ci_run(run_id: str, *, run: Any) -> dict[str, Any]:
    completed = run(
        [
            "gh",
            "run",
            "view",
            run_id,
            "--json",
            "databaseId,headSha,status,conclusion,url",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        return {}
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def ci_run_succeeded(run_payload: dict[str, Any], *, expected_commit: str) -> bool:
    return (
        run_payload.get("status") == "completed"
        and run_payload.get("conclusion") == "success"
        and run_payload.get("headSha") == expected_commit
    )


def ci_run_is_terminal(run_payload: dict[str, Any]) -> bool:
    return run_payload.get("status") == "completed" or run_payload.get("conclusion") in {
        "failure",
        "cancelled",
        "timed_out",
        "action_required",
    }


def run_checked(command: list[str], *, run: Any) -> str | None:
    completed = run(command, check=False, text=True, capture_output=True)
    if completed.returncode == 0:
        return None
    detail = _tail_text(completed.stderr) or _tail_text(completed.stdout)
    return f"{shlex.join(command)} failed" + (f": {detail}" if detail else "")


def git_text(repo_root: Path, args: list[str], *, run: Any) -> str | None:
    completed = run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        return None
    return (completed.stdout or "").strip()


def _non_empty_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _tail_text(text: str | None, *, limit: int = 1200) -> str:
    if text is None:
        return ""
    return text.strip()[-limit:]


__all__ = [
    "check_main_promotion_preconditions",
    "ci_run_is_terminal",
    "ci_run_succeeded",
    "git_text",
    "latest_ci_run_for_ref",
    "merge_promotion_decision_intent",
    "merge_promotion_repair_prompt",
    "run_checked",
    "view_ci_run",
]
