from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from isotope.features.supervisor.agent_group.workspace.session_discovery import (
    list_codex_session_candidates,
)
from isotope.features.supervisor.registry import (
    ManagedCodexRecord,
    append_managed_record,
    default_registry_path,
)


def test_lists_cwd_scoped_recent_sessions(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "AI_Camp_RNA_2026"
    workspace.mkdir()
    matching = "019e-rna"
    unrelated = "019e-other"
    _write_session(codex_home, matching, str(workspace / "round2"), "research update")
    _write_session(codex_home, unrelated, str(tmp_path / "other"), "other update")
    _write_session_index(codex_home, [unrelated, matching])
    _write_state_threads(codex_home, [(matching, "RNA Research", 1_768_999_999)])

    payload = list_codex_session_candidates(
        codex_home=codex_home,
        scope="cwd",
        workspace_root=workspace,
        limit=10,
    )

    assert payload["status"] == "ok"
    assert [item["session_id"] for item in payload["sessions"]] == [matching]
    assert payload["sessions"][0]["title"] == "RNA Research"
    assert payload["sessions"][0]["preview"] == ["research update"]


def test_cwd_scoped_sessions_reuse_managed_lane_names(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "AI_Camp_RNA_2026"
    workspace.mkdir()
    matching = "019e-rna"
    _write_session(codex_home, matching, str(workspace), "research update")
    _write_session_index(codex_home, [matching])
    _write_state_threads(codex_home, [(matching, "RNA Research", 1_768_999_999)])
    append_managed_record(
        default_registry_path(codex_home),
        ManagedCodexRecord(
            record_id="managed-research",
            name="科研 Codex",
            cwd=str(workspace),
            prompt="接管已有科研会话",
            command=("codex", "resume", matching),
            pid=0,
            started_at="2026-06-12T00:00:02Z",
            log_path=str(codex_home / "supervisor" / "logs" / "managed-research.log"),
            status="adopted",
            backend="codex_session",
            resume_session_id=matching,
        ),
    )

    payload = list_codex_session_candidates(
        codex_home=codex_home,
        scope="cwd",
        workspace_root=workspace,
        limit=10,
    )

    candidate = payload["sessions"][0]
    assert candidate["title"] == "RNA Research"
    assert candidate["display_title"] == "科研 Codex"
    assert candidate["managed_name"] == "科研 Codex"
    assert candidate["managed_record_id"] == "managed-research"


def test_lists_all_recent_sessions_without_workspace_filter(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "AI_Camp_RNA_2026"
    workspace.mkdir()
    matching = "019e-rna"
    unrelated = "019e-other"
    _write_session(codex_home, matching, str(workspace), "research update")
    _write_session(codex_home, unrelated, str(tmp_path / "other"), "other update")
    _write_session_index(codex_home, [matching, unrelated])

    payload = list_codex_session_candidates(
        codex_home=codex_home,
        scope="all",
        workspace_root=workspace,
        limit=10,
    )

    assert [item["session_id"] for item in payload["sessions"]] == [
        unrelated,
        matching,
    ]


def test_rejects_invalid_scope(tmp_path):
    payload = list_codex_session_candidates(
        codex_home=tmp_path / ".codex",
        scope="project",
        workspace_root=tmp_path,
        limit=10,
    )

    assert payload["status"] == "error"
    assert payload["error"]["message"] == "scope must be cwd or all"


def _write_session(codex_home: Path, session_id: str, cwd: str, text: str) -> None:
    path = (
        codex_home
        / "sessions"
        / "2026"
        / "06"
        / "12"
        / f"rollout-{session_id}.jsonl"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "type": "session_meta",
            "timestamp": "2026-06-12T00:00:00Z",
            "payload": {"id": session_id, "cwd": cwd},
        },
        {
            "type": "response_item",
            "timestamp": "2026-06-12T00:00:01Z",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": text,
            },
        },
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _write_session_index(codex_home: Path, session_ids: list[str]) -> None:
    codex_home.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "id": session_id,
            "thread_name": session_id,
            "updated_at": f"2026-06-12T00:00:0{index}Z",
        }
        for index, session_id in enumerate(session_ids)
    ]
    (codex_home / "session_index.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _write_state_threads(codex_home: Path, rows: list[tuple[str, str, int]]) -> None:
    connection = sqlite3.connect(codex_home / "state_5.sqlite")
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
