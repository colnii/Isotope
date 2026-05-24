"""LLM action decision 中 workspace 发现和验证的工具."""

from __future__ import annotations

from pathlib import Path

from .flow import CodexSupervisorReport
from .llm_action_guards import (
    is_terminal_done_session,
    suggested_target_name,
)


def _available_workspaces(
    report: CodexSupervisorReport,
    command_suggestions: list[dict[str, str]] | None = None,
) -> list[str]:
    seen: set[str] = set()
    workspaces: list[str] = []
    for session in report.sessions:
        if is_terminal_done_session(session):
            continue
        cwd = getattr(session, "cwd", None)
        if not isinstance(cwd, str) or not cwd or cwd in seen:
            continue
        if not _workspace_exists(cwd):
            continue
        seen.add(cwd)
        workspaces.append(cwd)
    for suggestion in command_suggestions or []:
        cwd = suggestion.get("cwd")
        if not isinstance(cwd, str) or not cwd or cwd in seen:
            continue
        if not _workspace_exists(cwd):
            continue
        seen.add(cwd)
        workspaces.append(cwd)
    return workspaces


def _workspace_exists(cwd: str) -> bool:
    return Path(cwd).expanduser().is_dir()


def _default_workspace(
    report: CodexSupervisorReport,
    command_suggestions: list[dict[str, str]] | None = None,
) -> str | None:
    workspaces = _available_workspaces(report, command_suggestions)
    return workspaces[0] if workspaces else None


def _has_workspace_action_suggestion(
    command_suggestions: list[dict[str, str]],
    kind: str,
    cwd: str,
) -> bool:
    return any(
        suggestion.get("kind") == kind and suggestion.get("cwd") == cwd
        for suggestion in command_suggestions
    )


def _requires_workspace_action_suggestion(cwd: str) -> bool:
    return Path(cwd).expanduser().is_dir()


def _has_managed_target(report: CodexSupervisorReport, target_name: str) -> bool:
    from .llm_action_guards import has_managed_send_target

    return any(
        has_managed_send_target(session) and session.managed_name == target_name
        for session in report.sessions
    )


def _delete_worktree_target_cwd(
    report: CodexSupervisorReport,
    target_name: str,
) -> str | None:
    for session in report.sessions:
        if suggested_target_name(session) == target_name:
            cwd = getattr(session, "cwd", None)
            return cwd if isinstance(cwd, str) and cwd else None
    return None


def _is_known_missing_worktree_target(
    report: CodexSupervisorReport,
    target_name: str,
    cwd: str,
) -> bool:
    if Path(cwd).expanduser().is_dir():
        return False
    return any(
        suggested_target_name(session) == target_name
        and getattr(session, "cwd", None) == cwd
        for session in report.sessions
    )
