"""Helpers for Codex CLI JSONL event output."""

from __future__ import annotations

import json
from typing import Any


def extract_codex_agent_message_text(stdout: str) -> str | None:
    """Return the latest completed Codex agent message from JSONL stdout."""
    if not isinstance(stdout, str):
        return None
    latest_text: str | None = None
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "agent_message":
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            latest_text = text.strip()
    return latest_text


def codex_jsonl_diagnostics(stdout: str, *, timeout_seconds: int) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "codex_event_counts": {},
        "codex_error_messages": [],
        "codex_has_agent_message": False,
        "codex_timeout_seconds": timeout_seconds,
    }
    if not isinstance(stdout, str):
        return diagnostics
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = event.get("type")
        if isinstance(event_type, str) and event_type:
            counts = diagnostics["codex_event_counts"]
            counts[event_type] = counts.get(event_type, 0) + 1
        if event_type == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                diagnostics["codex_has_agent_message"] = True
        if event_type != "error":
            continue
        message = event.get("message")
        if isinstance(message, str) and message.strip():
            diagnostics["codex_error_messages"].append(message.strip())
    return diagnostics
