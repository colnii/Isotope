from __future__ import annotations

import json

from isotope.integrations.codex.runtime import (
    codex_runtime_summary_artifact_payload,
    project_codex_jsonl_stdout,
)


def _line(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def test_projection_normalizes_messages_tools_reasoning_and_errors() -> None:
    stdout = "\n".join(
        [
            _line({"type": "session.created", "message": "started"}),
            _line(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"text": "请检查仓库"}],
                    },
                }
            ),
            _line(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "reasoning",
                        "summary": [{"text": "需要查看状态"}],
                    },
                }
            ),
            _line(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "name": "exec_command",
                        "arguments": {"cmd": "git status", "api_key": "secret"},
                    },
                }
            ),
            _line(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "function_call_output",
                        "output": "## main...origin/main\n",
                    },
                }
            ),
            _line(
                {
                    "type": "event_msg",
                    "payload": {"type": "error", "message": "command failed"},
                }
            ),
            _line(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "最终答复"},
                }
            ),
        ]
    )

    projection = project_codex_jsonl_stdout(
        stdout=stdout,
        stderr="diagnostic stderr",
        status="completed",
        reason_code="codex_cli_completed",
    )

    events = [event.to_dict() for event in projection.events]
    assert [event["kind"] for event in events] == [
        "status",
        "message",
        "reasoning",
        "tool_call",
        "tool_output",
        "error",
        "message",
    ]
    assert events[1]["role"] == "user"
    assert events[1]["text"] == "请检查仓库"
    assert events[3]["title"] == "exec_command"
    assert "secret" not in events[3]["text"]
    assert "[redacted]" in events[3]["text"]
    assert projection.summary.last_agent_message == "最终答复"
    assert projection.summary.error_messages == ["command failed"]
    assert projection.summary.event_counts["tool_call"] == 1
    assert projection.summary.stderr_preview == "diagnostic stderr"


def test_projection_counts_malformed_lines_without_raising() -> None:
    projection = project_codex_jsonl_stdout(
        stdout='{"type":"event_msg","payload":{"type":"status","message":"ok"}}\nnot json\n',
        stderr="",
        status="completed",
        reason_code="codex_cli_completed",
    )

    assert projection.summary.malformed_event_count == 1
    assert [event.kind for event in projection.events] == ["status"]


def test_summary_artifact_payload_is_low_sensitive() -> None:
    projection = project_codex_jsonl_stdout(
        stdout=_line(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": "完成",
                },
            }
        ),
        stderr="stderr raw text",
        status="completed",
        reason_code="codex_cli_completed",
    )

    payload = codex_runtime_summary_artifact_payload(projection)

    assert payload["kind"] == "codex_runtime_summary"
    assert payload["summary"]["last_agent_message"] == "完成"
    assert "stdout" not in json.dumps(payload, ensure_ascii=False)
    assert "stderr raw text" in json.dumps(payload, ensure_ascii=False)
