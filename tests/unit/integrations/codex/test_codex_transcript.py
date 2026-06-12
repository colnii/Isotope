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


def test_transcript_reader_can_return_latest_page_for_long_sessions(tmp_path):
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
        for index in range(1200)
    )
    write_jsonl(path, rows)

    page = read_codex_transcript_page(path, limit=1000, latest=True)

    assert page["offset"] == 201
    assert page["next_offset"] == 1201
    assert page["has_more"] is False
    assert page["total_events"] == 1201
    assert page["events"][0]["text"] == "message-200"
    assert page["events"][-1]["text"] == "message-1199"


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


def test_transcript_reader_projects_thread_rollback_event(tmp_path):
    path = tmp_path / "rollout-rollback.jsonl"
    write_jsonl(
        path,
        [
            {"type": "session_meta", "payload": {"id": "session_rollback"}},
            {
                "type": "response_item",
                "timestamp": "2026-06-12T00:00:01Z",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": "旧分支回复。",
                },
            },
            {
                "type": "event_msg",
                "timestamp": "2026-06-12T00:00:02Z",
                "payload": {
                    "type": "thread_rolled_back",
                    "num_turns": 2,
                    "reason": "user selected an earlier turn",
                },
            },
        ],
    )

    page = read_codex_transcript_page(path, offset=0, limit=10, include_raw=False)

    rollback = page["events"][2]
    assert rollback["kind"] == "rollback"
    assert rollback["title"] == "thread rolled back"
    assert rollback["text"] == "Rolled back 2 turns: user selected an earlier turn"
    assert rollback["num_turns"] == 2
    assert rollback["reason"] == "user selected an earlier turn"
    assert page["terminal_events"][-1] == {
        "event_index": 2,
        "event_type": "event_msg",
        "timestamp": "2026-06-12T00:00:02Z",
        "kind": "rollback",
        "title": "thread rolled back",
        "text": "Rolled back 2 turns: user selected an earlier turn",
        "num_turns": 2,
        "reason": "user selected an earlier turn",
    }


def test_transcript_reader_builds_terminal_view_without_empty_status_noise(tmp_path):
    path = tmp_path / "rollout-terminal.jsonl"
    write_jsonl(
        path,
        [
            {"type": "session_meta", "payload": {"id": "session_terminal"}},
            {
                "type": "event_msg",
                "timestamp": "2026-06-11T20:40:39.542Z",
                "payload": {"type": "task_started", "turn_id": "turn_1"},
            },
            {
                "type": "response_item",
                "timestamp": "2026-06-11T20:40:39.602Z",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "继续科研"}],
                },
            },
            {
                "type": "event_msg",
                "timestamp": "2026-06-11T20:40:39.602Z",
                "payload": {"type": "user_message", "message": "继续科研"},
            },
            {
                "type": "event_msg",
                "timestamp": "2026-06-11T20:40:42.613Z",
                "payload": {"type": "token_count", "info": {}},
            },
            {
                "type": "response_item",
                "timestamp": "2026-06-11T20:40:43.000Z",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "arguments": {"cmd": "git status"},
                },
            },
            {
                "type": "response_item",
                "timestamp": "2026-06-11T20:40:44.000Z",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": "## main...origin/main\n",
                },
            },
            {
                "type": "event_msg",
                "timestamp": "2026-06-11T20:40:45.000Z",
                "payload": {"type": "agent_message", "message": "科研继续推进。"},
            },
            {
                "type": "response_item",
                "timestamp": "2026-06-11T20:40:45.001Z",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": "科研继续推进。",
                },
            },
            {
                "type": "response_item",
                "timestamp": "2026-06-11T20:40:46.000Z",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "apply_patch",
                    "input": "*** Begin Patch\n*** End Patch",
                },
            },
            {
                "type": "response_item",
                "timestamp": "2026-06-11T20:40:47.000Z",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "call_2",
                    "output": "Success.",
                },
            },
            {
                "type": "event_msg",
                "timestamp": "2026-06-11T20:40:48.000Z",
                "payload": {
                    "type": "task_complete",
                    "last_agent_message": "科研继续推进。",
                },
            },
        ],
    )

    page = read_codex_transcript_page(path, offset=0, limit=20, include_raw=True)

    assert [event["kind"] for event in page["terminal_events"]] == [
        "message",
        "tool_call",
        "tool_output",
        "message",
        "tool_call",
        "tool_output",
    ]
    assert [event["title"] for event in page["terminal_events"]] == [
        "user",
        "exec_command",
        "tool output",
        "assistant",
        "apply_patch",
        "tool output",
    ]
    assert page["terminal_events"][0]["text"] == "继续科研"
    assert page["terminal_events"][1]["text"] == '{"cmd": "git status"}'
    assert page["terminal_events"][2]["text"] == "## main...origin/main\n"
    assert page["terminal_events"][3]["text"] == "科研继续推进。"
    assert all(event["text"].strip() for event in page["terminal_events"])
    assert len(page["events"]) == 12


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
