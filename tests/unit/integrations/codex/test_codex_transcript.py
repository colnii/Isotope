from __future__ import annotations

import json
from pathlib import Path

from isotope.integrations.codex.transcript import read_codex_transcript_page


def test_transcript_reader_pages_from_start_without_head_tail_truncation(tmp_path):
    path = tmp_path / "rollout.jsonl"
    rows = [
        {
            "type": "session_meta",
            "timestamp": "2026-06-12T00:00:00Z",
            "payload": {"id": "session_1", "cwd": "/repo"},
        },
        {
            "type": "response_item",
            "timestamp": "2026-06-12T00:00:01Z",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"text": "first"}],
            },
        },
        {
            "type": "event_msg",
            "timestamp": "2026-06-12T00:00:02Z",
            "payload": {"type": "status", "message": "middle status"},
        },
        {
            "type": "response_item",
            "timestamp": "2026-06-12T00:00:03Z",
            "payload": {"type": "message", "role": "assistant", "content": "last"},
        },
    ]
    write_jsonl(path, rows)

    page = read_codex_transcript_page(path, offset=0, limit=2, include_raw=True)

    assert page["session_id"] == "session_1"
    assert page["source_path"] == str(path)
    assert page["source_size_bytes"] == path.stat().st_size
    assert page["has_more"] is True
    assert page["next_offset"] == 2
    assert [item["kind"] for item in page["events"]] == ["session_meta", "message"]
    assert page["events"][1]["text"] == "first"
    assert "raw" in page["events"][0]


def test_transcript_reader_pages_middle_and_preserves_late_events(tmp_path):
    path = tmp_path / "large-rollout.jsonl"
    rows = [{"type": "session_meta", "payload": {"id": "session_large"}}]
    rows.extend(
        {
            "type": "response_item",
            "timestamp": f"2026-06-12T00:{index:02d}:00Z",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": f"message-{index}",
            },
        }
        for index in range(40)
    )
    write_jsonl(path, rows)

    page = read_codex_transcript_page(path, offset=35, limit=10, include_raw=False)

    assert page["session_id"] == "session_large"
    assert page["offset"] == 35
    assert page["has_more"] is False
    assert page["events"][0]["text"] == "message-34"
    assert page["events"][-1]["text"] == "message-39"
    assert all("raw" not in item for item in page["events"])


def test_transcript_reader_projects_tool_and_error_events(tmp_path):
    path = tmp_path / "rollout-tools.jsonl"
    write_jsonl(
        path,
        [
            {"type": "session_meta", "payload": {"id": "session_tools"}},
            {
                "type": "response_item",
                "timestamp": "2026-06-12T00:00:01Z",
                "payload": {
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{}",
                },
            },
            {
                "type": "event_msg",
                "timestamp": "2026-06-12T00:00:02Z",
                "payload": {"type": "error", "message": "command failed"},
            },
        ],
    )

    page = read_codex_transcript_page(path, offset=0, limit=10, include_raw=False)

    assert [item["kind"] for item in page["events"]] == [
        "session_meta",
        "tool_call",
        "error",
    ]
    assert page["events"][1]["title"] == "shell"
    assert page["events"][2]["text"] == "command failed"


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
