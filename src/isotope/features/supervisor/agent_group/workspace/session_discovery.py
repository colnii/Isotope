"""Recent Codex session discovery for agent workspaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from isotope.features.supervisor.flow import CodexSupervisorFlow, CodexSessionSummary


def list_codex_session_candidates(
    *,
    codex_home: Path | str,
    scope: str,
    workspace_root: Path | str,
    limit: int = 50,
) -> dict[str, Any]:
    if scope not in {"cwd", "all"}:
        return {"status": "error", "error": {"message": "scope must be cwd or all"}}
    root = Path(codex_home).expanduser()
    workspace_path = Path(workspace_root).expanduser()
    report = CodexSupervisorFlow(
        codex_home=root,
        branch_resolver=lambda _cwd: None,
    ).scan(limit=max(limit * 2, limit + 10, 10))
    candidates: list[dict[str, Any]] = []
    managed_by_resume_session_id = _managed_summaries_by_resume_session_id(
        report.sessions
    )
    for summary in report.sessions:
        if summary.managed:
            continue
        if scope == "cwd" and not _is_under_workspace(summary.cwd, workspace_path):
            continue
        candidates.append(
            _candidate_dict(
                summary,
                managed_summary=managed_by_resume_session_id.get(summary.session_id),
            )
        )
        if len(candidates) >= limit:
            break
    return {
        "status": "ok",
        "scope": scope,
        "workspace_root": str(workspace_path),
        "sessions": candidates,
    }


def _candidate_dict(
    summary: CodexSessionSummary,
    *,
    managed_summary: CodexSessionSummary | None = None,
) -> dict[str, Any]:
    title = summary.thread_name or summary.initial_user_title or summary.short_session_id
    managed_name = managed_summary.managed_name if managed_summary is not None else None
    return {
        "session_id": summary.session_id,
        "short_session_id": summary.short_session_id,
        "title": title,
        "display_title": managed_name or summary.display_title,
        "managed_name": managed_name,
        "managed_record_id": _managed_record_id(managed_summary),
        "managed_backend": managed_summary.managed_backend if managed_summary else None,
        "cwd": summary.cwd,
        "source_path": summary.source_path,
        "source_size_bytes": summary.source_size_bytes,
        "last_event_at": summary.last_event_at,
        "preview": _preview(summary),
    }


def _managed_summaries_by_resume_session_id(
    summaries: tuple[CodexSessionSummary, ...],
) -> dict[str, CodexSessionSummary]:
    managed_by_resume_session_id: dict[str, CodexSessionSummary] = {}
    for summary in summaries:
        if summary.managed and summary.managed_resume_session_id:
            managed_by_resume_session_id[summary.managed_resume_session_id] = summary
    return managed_by_resume_session_id


def _managed_record_id(summary: CodexSessionSummary | None) -> str | None:
    if summary is None or not summary.session_id.startswith("managed:"):
        return None
    return summary.session_id.removeprefix("managed:")


def _preview(summary: CodexSessionSummary) -> list[str]:
    preview: list[str] = []
    for message in (summary.last_user_message, summary.last_assistant_message):
        if message and message not in preview:
            preview.append(message)
    return preview


def _is_under_workspace(cwd: str, workspace_root: Path) -> bool:
    if not cwd:
        return False
    try:
        session_path = Path(cwd).expanduser().resolve(strict=False)
        root_path = workspace_root.expanduser().resolve(strict=False)
    except OSError:
        return False
    return session_path == root_path or root_path in session_path.parents
