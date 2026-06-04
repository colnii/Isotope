"""Dashboard route payload builders."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...daemon import supervisor_daemon_status, supervisor_watcher_status
from ...notifications.context import read_recent_context_results
from ...planner.decision_requests import (
    read_active_decision_requests,
    read_recent_decision_answers,
)
from ...runner import _dashboard_payload
from ...state.multi_worker import build_multi_worker_status_payload
from ...state.projection import build_supervisor_state_snapshot


def build_dashboard_web_payload(
    report: Any,
    *,
    codex_home: Path,
    workspace_cwd: Path,
    state_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the `/dashboard.json` payload used by the local web page."""
    if state_snapshot is None:
        state_snapshot = build_supervisor_state_snapshot(codex_home=codex_home)
    payload = _dashboard_payload(
        report,
        active_goals=state_snapshot["active_goals"],
        decision_requests=state_snapshot["active_decisions"],
        notifications=state_snapshot["notifications"]["recent"],
        multi_worker=build_multi_worker_status_payload(root=codex_home),
        state_snapshot=state_snapshot,
    )
    payload["daemon"] = supervisor_daemon_status(codex_home=codex_home)
    payload["watcher"] = supervisor_watcher_status(codex_home=codex_home)
    payload["workspace_cwd"] = str(workspace_cwd)
    return payload


def active_goal_dicts_for_codex_home(
    codex_home: Path,
    *,
    limit: int = 20,
    include_status: bool = False,
) -> list[dict[str, Any]]:
    return list(
        build_supervisor_state_snapshot(
            codex_home=codex_home,
            goal_limit=limit,
        )["active_goals"]
    )


def recent_context_results_for_report(
    *,
    codex_home: Path,
    report: Any,
) -> list[dict[str, Any]]:
    cwd = _context_cwd_for_report(report)
    results = read_recent_context_results(
        codex_home=codex_home,
        cwd=Path(cwd) if cwd else None,
    )
    return [result.to_dict() for result in results]


def decision_request_dicts(codex_home: Path) -> list[dict[str, Any]]:
    return [
        request.to_dict()
        for request in read_active_decision_requests(codex_home=codex_home)
    ]


def decision_answer_dicts(codex_home: Path) -> list[dict[str, Any]]:
    return [
        dict(answer)
        for answer in read_recent_decision_answers(codex_home=codex_home)
    ]


def _context_cwd_for_report(report: Any) -> str | None:
    for session in report.sessions:
        cwd = getattr(session, "cwd", None)
        if isinstance(cwd, str) and cwd:
            return cwd
    return None
