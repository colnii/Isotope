from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from isotope.integrations.codex.session_reader import (
    find_codex_session_paths,
    merge_recent_session_ids,
    read_codex_session,
    read_codex_session_index,
    read_codex_state_threads,
)


def test_codex_session_reader_reads_jsonl_session_without_supervisor_flow(tmp_path):
    path = tmp_path / ".codex" / "sessions" / "2026" / "05" / "16" / "rollout.jsonl"
    path.parent.mkdir(parents=True)
    session_id = "019e3205-b9cc-7012-804c-ca2ac38e0d32"
    _write_jsonl(
        path,
        [
            {
                "type": "session_meta",
                "timestamp": "2026-05-16T11:58:00Z",
                "payload": {
                    "id": session_id,
                    "cwd": "/home/lumber/Github/isotope",
                    "agent_nickname": "Curie",
                    "agent_role": "worker",
                    "cli_version": "0.42.0",
                    "model_provider": "openai",
                },
            },
            {
                "type": "event_msg",
                "timestamp": "2026-05-16T11:59:00Z",
                "payload": {
                    "type": "thread_name_updated",
                    "thread_id": session_id,
                    "thread_name": "Reader migration",
                    "message": "thread renamed",
                },
            },
            {
                "type": "response_item",
                "timestamp": "2026-05-16T11:59:20Z",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "继续迁移 reader。"}],
                },
            },
            {
                "type": "response_item",
                "timestamp": "2026-05-16T11:59:50Z",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": "正在运行测试。",
                },
            },
        ],
    )

    session = read_codex_session(path)

    assert session is not None
    assert session.session_id == session_id
    assert session.cwd == "/home/lumber/Github/isotope"
    assert session.source_path == path
    assert session.source_size_bytes == path.stat().st_size
    assert session.last_event_at.isoformat() == "2026-05-16T11:59:50+00:00"
    assert session.meta["agent_nickname"] == "Curie"
    assert session.thread_updates[0].thread_name == "Reader migration"
    assert session.thread_updates[0].thread_id == session_id
    assert [(message.role, message.text) for message in session.messages] == [
        (None, "thread renamed"),
        ("user", "继续迁移 reader。"),
        ("assistant", "正在运行测试。"),
    ]


def test_codex_session_reader_reads_index_and_state_threads_readonly(tmp_path):
    codex_home = tmp_path / ".codex"
    index_path = codex_home / "session_index.jsonl"
    index_path.parent.mkdir(parents=True)
    _write_jsonl(
        index_path,
        [
            {
                "id": "old-session",
                "thread_name": "旧窗口",
                "updated_at": "2026-05-16T10:00:00Z",
            },
            {
                "id": "recent-session",
                "thread_name": "最近窗口",
                "updated_at": "2026-05-16T11:59:00Z",
            },
        ],
    )
    state_path = codex_home / "state_5.sqlite"
    _write_state_threads(
        state_path,
        [
            ("state-old", "状态旧窗口", 1_768_900_000),
            ("state-recent", "状态最近窗口", 1_768_999_999),
        ],
    )

    index = read_codex_session_index(index_path)
    state = read_codex_state_threads(state_path)

    assert index.titles == {
        "old-session": "旧窗口",
        "recent-session": "最近窗口",
    }
    assert index.recent_session_ids == ("recent-session", "old-session")
    assert state.titles == {
        "state-old": "状态旧窗口",
        "state-recent": "状态最近窗口",
    }
    assert state.recent_session_ids == ("state-recent", "state-old")
    assert merge_recent_session_ids(
        state.recent_session_ids,
        index.recent_session_ids,
        ("recent-session", "fallback-session"),
    ) == (
        "state-recent",
        "state-old",
        "recent-session",
        "old-session",
        "fallback-session",
    )


def test_codex_session_reader_selects_recent_index_paths_before_mtime(tmp_path):
    codex_home = tmp_path / ".codex"
    recent_session_id = "019e2fff-0000-7000-8000-000000000000"
    old_paths: list[Path] = []
    for index in range(12):
        session_id = f"019e2f{index:02x}-0000-7000-8000-000000000000"
        path = codex_home / "sessions" / "2026" / "05" / "16" / f"rollout-{session_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_jsonl(path, [{"type": "session_meta", "payload": {"id": session_id}}])
        os.utime(path, (1_768_900_000 + index, 1_768_900_000 + index))
        old_paths.append(path)
    recent_path = (
        codex_home
        / "sessions"
        / "2026"
        / "05"
        / "16"
        / f"rollout-{recent_session_id}.jsonl"
    )
    _write_jsonl(recent_path, [{"type": "session_meta", "payload": {"id": recent_session_id}}])
    os.utime(recent_path, (1_768_800_000, 1_768_800_000))

    selected = find_codex_session_paths(
        codex_home,
        limit=1,
        recent_session_ids=(recent_session_id,),
    )

    assert selected[0] == recent_path
    assert len(selected) < len(old_paths) + 1


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _write_state_threads(path: Path, rows: list[tuple[str, str, int]]) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "create table threads (id text primary key, title text, updated_at integer)"
        )
        connection.executemany(
            "insert into threads (id, title, updated_at) values (?, ?, ?)",
            rows,
        )
        connection.commit()
    finally:
        connection.close()
