"""LLM action target and permission guard helpers."""

from __future__ import annotations

from typing import Any

TERMINAL_DONE_NEXT_MARKERS = (
    "可结束",
    "可以结束",
    "任务结束",
    "可归档",
    "可以归档",
    "等待归档",
    "等待 supervisor 归档",
    "归档或下发新任务",
    "无需继续",
    "不需要继续",
    "不用继续",
)

USER_DECISION_MARKERS = (
    "用户",
    "确认",
    "选择",
    "决定",
    "拍板",
    "提供",
    "是否",
    "人工",
)


def has_any_llm_target(
    report: Any,
    command_suggestions: list[dict[str, str]] | None = None,
    *,
    delete_worktree_candidates: list[dict[str, Any]] | None = None,
    available_workspaces: list[str] | None = None,
) -> bool:
    if delete_worktree_candidates:
        return True
    return any(is_llm_candidate_target(session) for session in report.sessions) or bool(
        available_workspaces
        if available_workspaces is not None
        else _available_workspace_values(report, command_suggestions)
    )


def has_resume_target(report: Any, session_id: str) -> bool:
    return any(
        can_resume_session(session) and session.session_id == session_id
        for session in report.sessions
    )


def ask_user_target(report: Any, session_id: str) -> Any | None:
    for session in report.sessions:
        if session.session_id == session_id and session_requests_user_decision(session):
            return session
    return None


def ask_user_goal(
    active_goals: list[dict[str, Any]] | None,
    goal_id: str,
) -> dict[str, Any] | None:
    for goal in active_goals or []:
        if not isinstance(goal, dict) or goal.get("goal_id") != goal_id:
            continue
        if goal_requests_user_decision(goal):
            return goal
    return None


def goal_requests_user_decision(goal: dict[str, Any]) -> bool:
    status = str(goal.get("last_status") or "").lower()
    if status == "needs_user":
        return True
    if status != "blocked":
        return False
    text = " ".join(
        str(goal.get(key) or "")
        for key in ("last_summary", "last_next", "goal")
    )
    return any(marker in text for marker in USER_DECISION_MARKERS)


def session_requests_user_decision(session: Any) -> bool:
    status = (getattr(session, "supervisor_status", None) or "").lower()
    if status == "needs_user":
        return True
    if status != "blocked" and getattr(session, "status", None) != "needs_user":
        return False
    text = " ".join(
        str(value)
        for value in (
            getattr(session, "supervisor_summary", None),
            getattr(session, "supervisor_next", None),
            getattr(session, "reason", None),
            getattr(session, "last_assistant_message", None),
        )
        if value
    )
    return any(marker in text for marker in USER_DECISION_MARKERS)


def has_context_check_for_target(
    recent_context_results: list[dict[str, Any]] | None,
    target: Any,
) -> bool:
    if not recent_context_results:
        return False
    target_cwd = getattr(target, "cwd", None)
    for result in recent_context_results:
        if not isinstance(result, dict):
            continue
        if isinstance(target_cwd, str) and target_cwd:
            if result.get("cwd") != target_cwd:
                continue
        return True
    return False


def has_context_check_for_goal(
    recent_context_results: list[dict[str, Any]] | None,
    goal: dict[str, Any],
) -> bool:
    if not recent_context_results:
        return False
    target_cwd = goal.get("cwd")
    for result in recent_context_results:
        if not isinstance(result, dict):
            continue
        if isinstance(target_cwd, str) and target_cwd:
            if result.get("cwd") != target_cwd:
                continue
        return True
    return False


def delete_worktree_candidate(
    candidates: list[dict[str, Any]] | None,
    *,
    target_name: str,
    record_id: str | None,
) -> dict[str, Any] | None:
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue
        if record_id is not None and candidate.get("record_id") != record_id:
            continue
        if (
            candidate.get("name") == target_name
            or candidate.get("target_name") == target_name
        ):
            return candidate
    return None


def is_llm_candidate_target(
    session: Any,
    *,
    resumable_session_ids: set[str] | None = None,
) -> bool:
    return (
        has_managed_send_target(session)
        or has_managed_process_target(session)
        or can_resume_session(session, resumable_session_ids=resumable_session_ids)
    )


def has_managed_send_target(session: Any) -> bool:
    return bool(session.managed_name and session.managed_tmux_session)


def has_managed_process_target(session: Any) -> bool:
    return bool(
        getattr(session, "managed", False)
        and getattr(session, "managed_name", None)
        and getattr(session, "managed_backend", None) != "tmux"
        and not is_completed_session(session)
        and not is_terminal_done_session(session)
    )


def has_running_managed_worker(report: Any, target_name: str) -> bool:
    for session in report.sessions:
        if suggested_target_name(session) != target_name:
            continue
        if not getattr(session, "managed", False):
            continue
        if is_terminal_done_session(session):
            continue
        if getattr(session, "status", None) == "working":
            return True
    return False


def can_resume_session(
    session: Any,
    *,
    resumable_session_ids: set[str] | None = None,
) -> bool:
    session_id = getattr(session, "session_id", None)
    if resumable_session_ids is not None and session_id not in resumable_session_ids:
        return False
    return (
        isinstance(session_id, str)
        and bool(session_id)
        and not session_id.startswith("managed:")
        and not is_completed_session(session)
    )


def suggested_target_name(session: Any) -> str:
    if session.managed_name:
        return session.managed_name
    return "resume-" + session.short_session_id


def goal_target_name(goal: dict[str, Any] | None) -> str | None:
    if not isinstance(goal, dict):
        return None
    target_name = goal.get("target_name")
    if isinstance(target_name, str) and target_name:
        return target_name
    goal_id = goal.get("goal_id")
    return goal_id if isinstance(goal_id, str) and goal_id else None


def is_completed_session(session: Any) -> bool:
    return (
        getattr(session, "status", None) in {"done", "archived"}
        or getattr(session, "supervisor_status", None) == "done"
    )


def is_terminal_done_session(session: Any) -> bool:
    if not is_completed_session(session):
        return False
    next_text = normalize_match_text(getattr(session, "supervisor_next", None))
    return any(marker in next_text for marker in TERMINAL_DONE_NEXT_MARKERS)


def normalize_match_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.lower().split())


def _available_workspace_values(
    report: Any,
    command_suggestions: list[dict[str, str]] | None,
) -> list[str]:
    values: list[str] = []
    for session in report.sessions:
        cwd = getattr(session, "cwd", None)
        if isinstance(cwd, str) and cwd:
            values.append(cwd)
    for suggestion in command_suggestions or []:
        cwd = suggestion.get("cwd")
        if isinstance(cwd, str) and cwd:
            values.append(cwd)
    return values
