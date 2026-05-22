"""Read-only Codex session file and index readers."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAX_FULL_SESSION_READ_BYTES = 2 * 1024 * 1024
SESSION_HEAD_READ_BYTES = 64 * 1024
SESSION_TAIL_READ_BYTES = 1024 * 1024


@dataclass(frozen=True)
class CodexSessionMessage:
    role: str | None
    text: str


@dataclass(frozen=True)
class CodexThreadUpdate:
    thread_name: str
    thread_id: str | None = None


@dataclass(frozen=True)
class CodexSessionIndex:
    titles: dict[str, str]
    recent_session_ids: tuple[str, ...]


@dataclass(frozen=True)
class CodexSessionSnapshot:
    session_id: str
    cwd: str
    source_path: Path
    source_size_bytes: int | None
    last_event_at: datetime | None
    meta: dict[str, Any]
    messages: tuple[CodexSessionMessage, ...]
    thread_updates: tuple[CodexThreadUpdate, ...]


def read_codex_session(path: Path) -> CodexSessionSnapshot | None:
    """Read one Codex JSONL session without mutating Codex state."""

    try:
        lines = _read_session_lines(path)
    except OSError:
        return None

    meta: dict[str, Any] = {}
    messages: list[CodexSessionMessage] = []
    thread_updates: list[CodexThreadUpdate] = []
    last_event_at: datetime | None = None
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_time = _parse_timestamp(event.get("timestamp"))
        if event_time is not None:
            last_event_at = event_time
        if event.get("type") == "session_meta":
            payload = event.get("payload")
            if isinstance(payload, dict):
                meta.update(payload)
            continue
        thread_update = _thread_update_from_event(event)
        if thread_update is not None:
            thread_updates.append(thread_update)
        message = _message_from_event(event)
        if message is not None:
            messages.append(message)

    if not meta and last_event_at is None:
        return None
    if last_event_at is None:
        last_event_at = _parse_timestamp(meta.get("timestamp"))
    return CodexSessionSnapshot(
        session_id=str(meta.get("id") or path.stem),
        cwd=str(meta.get("cwd") or ""),
        source_path=path,
        source_size_bytes=_path_size_bytes(path),
        last_event_at=last_event_at,
        meta=meta,
        messages=tuple(messages),
        thread_updates=tuple(thread_updates),
    )


def read_codex_session_index(path: Path) -> CodexSessionIndex:
    titles: dict[str, str] = {}
    updated_at: dict[str, datetime] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return CodexSessionIndex(titles=titles, recent_session_ids=())
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        session_id = _optional_string(item.get("id"))
        thread_name = _optional_string(item.get("thread_name"))
        if session_id and thread_name:
            titles[session_id] = thread_name
        if session_id:
            updated_at[session_id] = _parse_timestamp(
                item.get("updated_at")
            ) or datetime.min.replace(tzinfo=timezone.utc)
    recent_session_ids = tuple(
        sorted(updated_at, key=lambda session_id: updated_at[session_id], reverse=True)
    )
    return CodexSessionIndex(titles=titles, recent_session_ids=recent_session_ids)


def read_codex_state_threads(path: Path) -> CodexSessionIndex:
    if not path.exists():
        return CodexSessionIndex(titles={}, recent_session_ids=())
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return CodexSessionIndex(titles={}, recent_session_ids=())
    try:
        rows = connection.execute("select id, title, updated_at from threads").fetchall()
    except sqlite3.Error:
        return CodexSessionIndex(titles={}, recent_session_ids=())
    finally:
        connection.close()
    titles: dict[str, str] = {}
    updated_at: dict[str, int] = {}
    for session_id_value, title_value, updated_at_value in rows:
        session_id = _optional_string(session_id_value)
        title = _optional_string(title_value)
        if session_id and title:
            titles[session_id] = title
        if session_id and isinstance(updated_at_value, int):
            updated_at[session_id] = updated_at_value
    recent_session_ids = tuple(
        sorted(updated_at, key=lambda session_id: updated_at[session_id], reverse=True)
    )
    return CodexSessionIndex(titles=titles, recent_session_ids=recent_session_ids)


def merge_recent_session_ids(*groups: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for session_id in group:
            if session_id in seen:
                continue
            merged.append(session_id)
            seen.add(session_id)
    return tuple(merged)


def find_codex_session_paths(
    codex_home: Path,
    *,
    limit: int,
    recent_session_ids: tuple[str, ...] = (),
) -> list[Path]:
    sessions_root = codex_home / "sessions"
    if not sessions_root.exists():
        return []
    paths = sorted(sessions_root.rglob("*.jsonl"))
    candidate_limit = max(4, limit + 3)
    if len(paths) <= candidate_limit:
        return paths
    selected: list[Path] = []
    seen: set[Path] = set()
    paths_by_id = {
        session_id: path
        for path in paths
        if (session_id := _session_id_from_path(path)) is not None
    }
    for session_id in recent_session_ids[:candidate_limit]:
        if path := paths_by_id.get(session_id):
            selected.append(path)
            seen.add(path)
    for path in sorted(paths, key=_path_mtime_ns, reverse=True):
        if len(selected) >= candidate_limit:
            break
        if path in seen:
            continue
        selected.append(path)
        seen.add(path)
    return selected


def _thread_update_from_event(event: dict[str, Any]) -> CodexThreadUpdate | None:
    if event.get("type") != "event_msg":
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "thread_name_updated":
        return None
    thread_name = _optional_string(payload.get("thread_name"))
    if not thread_name:
        return None
    return CodexThreadUpdate(
        thread_name=thread_name,
        thread_id=_optional_string(payload.get("thread_id")),
    )


def _message_from_event(event: dict[str, Any]) -> CodexSessionMessage | None:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    if event.get("type") == "event_msg":
        text = _optional_string(payload.get("message"))
        return CodexSessionMessage(role=None, text=text) if text else None
    if event.get("type") != "response_item" or payload.get("type") != "message":
        return None
    text = _content_text(payload.get("content"))
    if not text:
        return None
    return CodexSessionMessage(role=_optional_string(payload.get("role")), text=text)


def _content_text(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text:
            parts.append(text)
    return "\n".join(parts) if parts else None


def _session_id_from_path(path: Path) -> str | None:
    match = re.search(
        r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        path.name,
    )
    return match.group(1) if match else None


def _path_mtime_ns(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _path_size_bytes(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def _read_session_lines(path: Path) -> list[str]:
    size = path.stat().st_size
    if size <= MAX_FULL_SESSION_READ_BYTES:
        return path.read_text(encoding="utf-8").splitlines()
    with path.open("rb") as handle:
        head = handle.read(SESSION_HEAD_READ_BYTES)
        tail_offset = max(0, size - SESSION_TAIL_READ_BYTES)
        handle.seek(tail_offset)
        tail = handle.read(SESSION_TAIL_READ_BYTES)
    data = head + b"\n" + tail
    return data.decode("utf-8", errors="ignore").splitlines()


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
