"""Loop state helpers for the Supervisor CLI."""

from __future__ import annotations

import argparse
from typing import Any


IDLE_LOOP_REASON = "当前没有可控的 Supervisor 目标，先继续监控。"


def _default_api() -> Any:
    from isotope.features.supervisor import runner as api

    return api


def target_session(report: Any, session_id: str | None) -> Any | None:
    if session_id is None:
        return None
    for session in report.sessions:
        if session.session_id == session_id:
            return session
    return None


def loop_without_autonomous_scope(
    args: argparse.Namespace,
    report: Any,
    active_goals: list[dict[str, Any]],
    explicit_goal: str | None,
    *,
    api: Any | None = None,
) -> bool:
    if api is None:
        api = _default_api()
    if getattr(args, "command", None) != "loop":
        return False
    if getattr(args, "name", None):
        return False
    if explicit_goal or active_goals:
        return False
    return not has_loop_managed_scope(report, api=api)


def loop_allows_workspace_actions(
    args: argparse.Namespace,
    active_goals: list[dict[str, Any]],
    explicit_goal: str | None,
) -> bool:
    if getattr(args, "command", None) != "loop":
        return True
    return bool(getattr(args, "name", None) or explicit_goal or active_goals)


def has_loop_managed_scope(
    report: Any,
    *,
    api: Any | None = None,
) -> bool:
    if api is None:
        api = _default_api()
    for session in report.sessions:
        if api._is_active_managed_tmux_session(session):
            return True
        if api._is_active_managed_process_session(session):
            return True
    return False


def idle_loop_llm_action() -> dict[str, Any]:
    return {
        "kind": "monitor",
        "target_name": None,
        "reason": IDLE_LOOP_REASON,
        "command_suggestion": None,
    }


def has_llm_action_target(
    report: Any,
    command_suggestions: Any = None,
    delete_worktree_candidates: Any = None,
    *,
    api: Any | None = None,
) -> bool:
    if api is None:
        api = _default_api()
    if isinstance(delete_worktree_candidates, list) and delete_worktree_candidates:
        return True
    if any(
        (
            session.managed_name
            and session.managed_tmux_session
            and not session_marks_terminal_done(session, api=api)
        )
        or api._is_resume_capable_session(session)
        for session in report.sessions
    ):
        return True
    if context_cwd_for_actionable_report(report, api=api) is not None:
        return True
    if not isinstance(command_suggestions, list):
        return False
    return any(
        isinstance(item, dict)
        and item.get("kind") in {"request_context", "launch_session"}
        and isinstance(item.get("cwd"), str)
        for item in command_suggestions
    )


def session_marks_terminal_done(
    session: Any,
    *,
    api: Any | None = None,
) -> bool:
    if api is None:
        api = _default_api()
    return api._is_completed_session(session) and api._supervisor_next_marks_terminal_done(
        session
    )


def context_cwd_for_actionable_report(
    report: Any,
    *,
    api: Any | None = None,
) -> str | None:
    if api is None:
        api = _default_api()
    for session in report.sessions:
        if session_marks_terminal_done(session, api=api):
            continue
        cwd = getattr(session, "cwd", None)
        if isinstance(cwd, str) and cwd:
            return cwd
    return None
