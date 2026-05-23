"""Workspace scoping helpers for Supervisor command payloads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from isotope.features.supervisor.flow import CodexSupervisorReport


def action_report_for_workspace(args: Any, report: Any) -> Any:
    root = workspace_root(args)
    if root is None:
        return report
    sessions = tuple(
        session for session in report.sessions if session_in_workspace(session, root)
    )
    if not sessions and not getattr(args, "workspace_root", None):
        return report
    return CodexSupervisorReport(
        generated_at=report.generated_at,
        sessions=sessions,
    )


def workspace_scope_payload(
    args: Any,
    report: Any,
    action_report: Any,
) -> dict[str, Any]:
    root = workspace_root(args)
    return {
        "mode": "all" if root is None else "workspace",
        "workspace_root": str(root) if root is not None else None,
        "total_sessions": len(report.sessions),
        "candidate_sessions": len(action_report.sessions),
    }


def workspace_root(args: Any) -> Path | None:
    if getattr(args, "all_workspaces", False):
        return None
    raw = getattr(args, "workspace_root", None)
    return Path(raw).expanduser().resolve() if raw else Path.cwd().resolve()


def session_in_workspace(session: Any, root: Path) -> bool:
    cwd = getattr(session, "cwd", None)
    if not isinstance(cwd, str) or not cwd:
        return False
    session_cwd = Path(cwd).expanduser().resolve()
    return session_cwd == root or root in session_cwd.parents


def context_cwd_for_report(report: Any) -> str | None:
    for session in report.sessions:
        cwd = getattr(session, "cwd", None)
        if isinstance(cwd, str) and cwd:
            return cwd
    return None
