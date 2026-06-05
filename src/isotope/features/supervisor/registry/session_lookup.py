"""Lookup helpers for local Codex rollout sessions."""

from __future__ import annotations

from pathlib import Path

from isotope.integrations.codex.session_reader import (
    CodexSessionSnapshot,
    read_codex_session,
)


def find_codex_session_snapshot(
    *,
    codex_home: Path | str,
    session_id: str,
) -> CodexSessionSnapshot | None:
    sessions_root = Path(codex_home).expanduser() / "sessions"
    if not sessions_root.exists():
        return None
    for path in sorted(sessions_root.rglob("*.jsonl")):
        snapshot = read_codex_session(path)
        if snapshot is not None and snapshot.session_id == session_id:
            return snapshot
    return None
