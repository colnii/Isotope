"""Recent Codex session discovery for agent workspaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from isotope.integrations.codex.session_reader import (
    CodexSessionSnapshot,
    find_codex_session_paths,
    merge_recent_session_ids,
    read_codex_session,
    read_codex_session_index,
    read_codex_state_threads,
)


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
    session_index = read_codex_session_index(root / "session_index.jsonl")
    state_threads = read_codex_state_threads(root / "state_5.sqlite")
    titles = {**session_index.titles, **state_threads.titles}
    recent_ids = merge_recent_session_ids(
        state_threads.recent_session_ids,
        session_index.recent_session_ids,
    )
    candidates: list[dict[str, Any]] = []
    for path in find_codex_session_paths(
        root,
        limit=max(limit, 1),
        recent_session_ids=recent_ids,
    ):
        snapshot = read_codex_session(path)
        if snapshot is None:
            continue
        if scope == "cwd" and not _is_under_workspace(snapshot.cwd, workspace_path):
            continue
        candidates.append(_candidate_dict(snapshot, titles=titles))
        if len(candidates) >= limit:
            break
    return {
        "status": "ok",
        "scope": scope,
        "workspace_root": str(workspace_path),
        "sessions": candidates,
    }


def _candidate_dict(
    snapshot: CodexSessionSnapshot,
    *,
    titles: dict[str, str],
) -> dict[str, Any]:
    return {
        "session_id": snapshot.session_id,
        "short_session_id": _short_session_id(snapshot.session_id),
        "title": (
            titles.get(snapshot.session_id)
            or _latest_thread_name(snapshot)
            or snapshot.session_id
        ),
        "cwd": snapshot.cwd,
        "source_path": str(snapshot.source_path),
        "source_size_bytes": snapshot.source_size_bytes,
        "last_event_at": (
            snapshot.last_event_at.isoformat() if snapshot.last_event_at else None
        ),
        "preview": [message.text for message in snapshot.messages[-3:]],
    }


def _is_under_workspace(cwd: str, workspace_root: Path) -> bool:
    if not cwd:
        return False
    try:
        session_path = Path(cwd).expanduser().resolve(strict=False)
        root_path = workspace_root.expanduser().resolve(strict=False)
    except OSError:
        return False
    return session_path == root_path or root_path in session_path.parents


def _latest_thread_name(snapshot: CodexSessionSnapshot) -> str | None:
    if not snapshot.thread_updates:
        return None
    return snapshot.thread_updates[-1].thread_name


def _short_session_id(session_id: str) -> str:
    parts = session_id.split("-")
    return parts[0] if parts and parts[0] else session_id
