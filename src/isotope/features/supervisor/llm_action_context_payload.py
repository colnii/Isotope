"""LLM action decision 的上下文 payload 构建工具.

包含 worker review 压缩、候选目标 payload、活跃 goal payload、context request helpers 等。
"""

from __future__ import annotations

from typing import Any

from .llm_action_constants import LARGE_RESUME_SOURCE_BYTES
from .llm_action_guards import (
    can_resume_session,
    has_managed_send_target,
    is_llm_candidate_target,
    suggested_target_name,
)


# ---------------------------------------------------------------------------
# worker review payload 压缩
# ---------------------------------------------------------------------------


def _worker_review_context_payload(
    worker_reviews: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(worker_reviews, dict):
        return {}
    workers = [
        _worker_review_prompt_item(worker)
        for worker in worker_reviews.get("workers", [])
        if isinstance(worker, dict)
    ]
    return {
        "status": worker_reviews.get("status"),
        "summary": worker_reviews.get("summary") or {},
        "decision_summary": worker_reviews.get("decision_summary") or {},
        "automation_candidates": _worker_review_automation_candidates_payload(
            worker_reviews.get("automation_candidates")
        ),
        "safety": worker_reviews.get("safety") or {},
        "workers": workers,
    }


def _worker_review_automation_candidates_payload(
    raw: Any,
) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(raw, dict):
        return {}
    payload: dict[str, list[dict[str, Any]]] = {}
    for bucket in (
        "review_then_merge",
        "continue_or_split",
        "archive_or_wait",
        "recover_or_archive",
    ):
        items = raw.get(bucket)
        if not isinstance(items, list):
            continue
        compact_items = [
            _worker_review_automation_candidate_item(item)
            for item in items[:5]
            if isinstance(item, dict)
        ]
        if compact_items:
            payload[bucket] = compact_items
    return payload


def _worker_review_automation_candidate_item(
    item: dict[str, Any],
) -> dict[str, Any]:
    return {
        "record_id": item.get("record_id"),
        "name": item.get("name"),
        "cwd": item.get("cwd"),
        "branch": item.get("branch"),
        "recommendation": item.get("recommendation"),
        "risk_level": item.get("risk_level"),
        "reason": _clip(item.get("reason")),
        "next_actions": item.get("next_actions") or [],
        "validation_commands": (item.get("validation_commands") or [])[:3],
        "reviewer_command": _clip(item.get("reviewer_command")),
    }


def _worker_review_prompt_item(worker: dict[str, Any]) -> dict[str, Any]:
    reviewer = worker.get("reviewer")
    reviewer_payload = reviewer if isinstance(reviewer, dict) else {}
    worktree = worker.get("worktree")
    worktree_payload = worktree if isinstance(worktree, dict) else {}
    changes = worker.get("changes")
    changes_payload = changes if isinstance(changes, dict) else {}
    protocol = worker.get("supervisor_protocol")
    protocol_payload = protocol if isinstance(protocol, dict) else {}
    return {
        "record_id": worker.get("record_id"),
        "name": worker.get("name"),
        "backend": worker.get("backend"),
        "process_running": worker.get("process_running"),
        "registry_status": worker.get("registry_status"),
        "cwd": worker.get("cwd"),
        "cwd_exists": worker.get("cwd_exists"),
        "worktree": {
            "exists": worktree_payload.get("exists"),
            "branch": worktree_payload.get("branch"),
            "inferred_branch": worktree_payload.get("inferred_branch"),
        },
        "supervisor_protocol": {
            "status": protocol_payload.get("status"),
            "summary": _clip(protocol_payload.get("summary")),
            "next": _clip(protocol_payload.get("next")),
        },
        "changes": {
            "status": changes_payload.get("status"),
            "summary": changes_payload.get("summary"),
            "files": changes_payload.get("files") or [],
            "stat": _clip(changes_payload.get("stat")),
        },
        "validation_commands": worker.get("validation_commands") or [],
        "next_decision": worker.get("next_decision") or {},
        "reviewer": {
            "needed": reviewer_payload.get("needed"),
            "reason": reviewer_payload.get("reason"),
            "command": reviewer_payload.get("command"),
            "must_check_risks": reviewer_payload.get("must_check_risks") or [],
        },
        "merge_hint": worker.get("merge_hint"),
    }


# ---------------------------------------------------------------------------
# 候选目标 payload
# ---------------------------------------------------------------------------


def _candidate_target_payloads(
    report: Any,
    *,
    resumable_session_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    return [
        {
            "target_name": suggested_target_name(session),
            "session_id": session.session_id,
            "cwd": session.cwd,
            "status": session.supervisor_status or session.status,
            "reason": session.supervisor_summary or session.reason,
            "source_size_bytes": session.source_size_bytes,
            "resume_context_hint": _resume_context_hint(
                session,
                resumable_session_ids=resumable_session_ids,
            ),
            "can_send_to_tmux": has_managed_send_target(session),
            "can_resume": can_resume_session(
                session,
                resumable_session_ids=resumable_session_ids,
            ),
            "tmux_session": session.managed_tmux_session,
            "managed_terminal_ready": session.managed_terminal_ready,
            "managed_bell": session.managed_bell,
            "managed_bell_event_at": session.managed_bell_event_at,
            "supervisor_status": session.supervisor_status,
            "supervisor_summary": _clip(session.supervisor_summary),
            "supervisor_next": _clip(session.supervisor_next),
        }
        for session in report.sessions
        if is_llm_candidate_target(
            session,
            resumable_session_ids=resumable_session_ids,
        )
    ]


def _resume_context_hint(
    session: Any,
    *,
    resumable_session_ids: set[str] | None = None,
) -> str | None:
    if not can_resume_session(session, resumable_session_ids=resumable_session_ids):
        return None
    source_size = getattr(session, "source_size_bytes", None)
    if isinstance(source_size, int) and source_size >= LARGE_RESUME_SOURCE_BYTES:
        return "large_session_file"
    return "normal_session_file"


# ---------------------------------------------------------------------------
# 活跃 goal payload
# ---------------------------------------------------------------------------


def _active_goal_payload(
    active_goals: list[dict[str, Any]] | None,
    candidate_targets: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    runtime_by_name = {
        target["target_name"]: target
        for target in candidate_targets or []
        if isinstance(target.get("target_name"), str)
    }
    items: list[dict[str, Any]] = []
    for goal in active_goals or []:
        if not isinstance(goal, dict):
            continue
        item: dict[str, Any] = {}
        for key in (
            "goal_id",
            "goal",
            "cwd",
            "target_name",
            "last_status",
            "last_summary",
            "last_next",
            "last_status_at",
        ):
            value = goal.get(key)
            if isinstance(value, str) and value:
                item[key] = _clip(value)
        target_name = item.get("target_name")
        runtime = (
            runtime_by_name.get(target_name) if isinstance(target_name, str) else None
        )
        if runtime is not None:
            item["worker_status"] = runtime.get("status")
            item["worker_session_id"] = runtime.get("session_id")
            reason = runtime.get("reason")
            if isinstance(reason, str) and reason:
                item["worker_reason"] = _clip(reason)
        if item:
            items.append(item)
    return items


# ---------------------------------------------------------------------------
# 共享工具
# ---------------------------------------------------------------------------


def _clip(text: str | None, *, limit: int = 160) -> str | None:
    if text is None:
        return None
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "\u2026"


# ---------------------------------------------------------------------------
# context request history 和 blocked context priority
# ---------------------------------------------------------------------------


def _context_request_history(
    recent_context_results: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for result in recent_context_results or []:
        if not isinstance(result, dict):
            continue
        cwd = result.get("cwd")
        query = result.get("query")
        if not isinstance(cwd, str) or not isinstance(query, str):
            continue
        item_count = result.get("items")
        history.append(
            {
                "cwd": cwd,
                "query": query,
                "items": str(len(item_count) if isinstance(item_count, list) else 0),
            }
        )
    return history


def _blocked_context_priority(
    active_goals: list[dict[str, Any]] | None,
    command_suggestions: list[dict[str, str]],
    context_request_history: list[dict[str, str]],
) -> list[dict[str, str]]:
    history_keys = {
        (item.get("cwd"), item.get("query"))
        for item in context_request_history
        if isinstance(item.get("cwd"), str) and isinstance(item.get("query"), str)
    }
    priorities: list[dict[str, str]] = []
    for goal in active_goals or []:
        if not isinstance(goal, dict):
            continue
        status = str(goal.get("last_status") or "").lower()
        if status not in {"blocked", "needs_user"}:
            continue
        suggestion = _request_context_suggestion_for_goal(goal, command_suggestions)
        if suggestion is None:
            continue
        cwd = suggestion["cwd"]
        query = suggestion["query"]
        if (cwd, query) in history_keys:
            continue
        priority: dict[str, str] = {
            "kind": "request_context",
            "reason": "context_first_for_blocked_goal",
            "cwd": cwd,
            "query": query,
            "message": "blocked/needs_user 目标缺上下文时先检索，再判断是否 ask_user。",
        }
        for key in ("goal_id", "target_name"):
            value = goal.get(key)
            if isinstance(value, str) and value:
                priority[key] = value
        priorities.append(priority)
    return priorities


def _request_context_suggestion_for_goal(
    goal: dict[str, Any],
    command_suggestions: list[dict[str, str]],
) -> dict[str, str] | None:
    goal_cwd = goal.get("cwd")
    if not isinstance(goal_cwd, str) or not goal_cwd:
        return None
    goal_text = goal.get("goal")
    for suggestion in command_suggestions:
        if suggestion.get("kind") != "request_context":
            continue
        if suggestion.get("cwd") != goal_cwd:
            continue
        if isinstance(goal_text, str) and suggestion.get("query") == goal_text:
            return suggestion
    for suggestion in command_suggestions:
        if (
            suggestion.get("kind") == "request_context"
            and suggestion.get("cwd") == goal_cwd
        ):
            return suggestion
    return None
