"""Paged transcript reader for local Codex JSONL sessions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_codex_transcript_page(
    path: Path | str,
    *,
    offset: int = 0,
    limit: int = 200,
    include_raw: bool = False,
    latest: bool = False,
) -> dict[str, Any]:
    source_path = Path(path).expanduser()
    clean_offset = max(int(offset), 0)
    clean_limit = min(max(int(limit), 1), 1000)
    raw_events: list[dict[str, Any]] = []
    session_id = source_path.stem
    last_event_at: str | None = None

    with source_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            event = _loads_event(line)
            if event is None:
                continue
            raw_events.append(event)
            timestamp = event.get("timestamp")
            if isinstance(timestamp, str) and timestamp:
                last_event_at = timestamp
            if event.get("type") == "session_meta":
                payload = event.get("payload")
                if isinstance(payload, dict) and isinstance(payload.get("id"), str):
                    session_id = payload["id"]

    total_events = len(raw_events)
    if latest:
        clean_offset = max(total_events - clean_limit, 0)
    page_events = raw_events[clean_offset : clean_offset + clean_limit]
    parsed_events = [
        _project_event(
            event,
            event_index=event_index,
            include_raw=include_raw,
        )
        for event_index, event in enumerate(page_events, start=clean_offset)
    ]
    terminal_events = [
        terminal_event
        for event_index, event in enumerate(page_events, start=clean_offset)
        if (
            terminal_event := _project_terminal_event(
                event,
                event_index=event_index,
            )
        )
        is not None
    ]

    next_offset = clean_offset + len(parsed_events)
    return {
        "status": "ok",
        "session_id": session_id,
        "source_path": str(source_path),
        "source_size_bytes": source_path.stat().st_size,
        "last_event_at": last_event_at,
        "offset": clean_offset,
        "limit": clean_limit,
        "latest": bool(latest),
        "next_offset": next_offset,
        "has_more": next_offset < total_events,
        "total_events": total_events,
        "events": parsed_events,
        "terminal_events": terminal_events,
    }


def _loads_event(line: str) -> dict[str, Any] | None:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None


def _project_event(
    event: dict[str, Any],
    *,
    event_index: int,
    include_raw: bool,
) -> dict[str, Any]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    base: dict[str, Any] = {
        "event_index": event_index,
        "event_type": event.get("type") if isinstance(event.get("type"), str) else "unknown",
        "timestamp": event.get("timestamp") if isinstance(event.get("timestamp"), str) else None,
    }
    if event.get("type") == "session_meta":
        projected = {
            **base,
            "kind": "session_meta",
            "title": "session metadata",
            "text": str(payload.get("cwd") or payload.get("id") or ""),
        }
    elif event.get("type") == "response_item" and payload.get("type") == "message":
        projected = {
            **base,
            "kind": "message",
            "title": str(payload.get("role") or "message"),
            "role": payload.get("role") if isinstance(payload.get("role"), str) else None,
            "text": _content_text(payload.get("content")),
        }
    elif event.get("type") == "response_item" and payload.get("type") in {
        "function_call",
        "tool_call",
        "custom_tool_call",
    }:
        projected = {
            **base,
            "kind": "tool_call",
            "title": str(payload.get("name") or payload.get("type") or "tool_call"),
            "text": _short_text(payload.get("arguments") or payload.get("input")),
        }
    elif event.get("type") == "response_item" and payload.get("type") in {
        "function_call_output",
        "tool_call_output",
        "custom_tool_call_output",
    }:
        projected = {
            **base,
            "kind": "tool_output",
            "title": "tool output",
            "text": _short_text(payload.get("output")),
        }
    elif event.get("type") == "event_msg" and payload.get("type") == "error":
        projected = {
            **base,
            "kind": "error",
            "title": "error",
            "text": str(payload.get("message") or ""),
        }
    elif event.get("type") == "event_msg":
        projected = {
            **base,
            "kind": "status",
            "title": str(payload.get("type") or "event"),
            "text": str(payload.get("message") or ""),
        }
    else:
        projected = {
            **base,
            "kind": "raw_event",
            "title": str(event.get("type") or "event"),
            "text": "",
        }
    if include_raw:
        projected["raw"] = event
    return projected


def _project_terminal_event(
    event: dict[str, Any],
    *,
    event_index: int,
) -> dict[str, Any] | None:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    timestamp = event.get("timestamp") if isinstance(event.get("timestamp"), str) else None
    base: dict[str, Any] = {
        "event_index": event_index,
        "event_type": event.get("type") if isinstance(event.get("type"), str) else "unknown",
        "timestamp": timestamp,
    }
    if event.get("type") == "response_item" and payload.get("type") == "message":
        text = _content_text(payload.get("content"))
        if not text.strip():
            return None
        role = payload.get("role") if isinstance(payload.get("role"), str) else "message"
        return {
            **base,
            "kind": "message",
            "title": role,
            "role": role,
            "text": text,
        }
    if event.get("type") == "response_item" and payload.get("type") in {
        "function_call",
        "tool_call",
        "custom_tool_call",
    }:
        text = _short_text(payload.get("arguments") or payload.get("input"))
        if not text.strip():
            return None
        return {
            **base,
            "kind": "tool_call",
            "title": str(payload.get("name") or payload.get("type") or "tool_call"),
            "text": text,
        }
    if event.get("type") == "response_item" and payload.get("type") in {
        "function_call_output",
        "tool_call_output",
        "custom_tool_call_output",
    }:
        text = _short_text(payload.get("output"))
        if not text.strip():
            return None
        return {
            **base,
            "kind": "tool_output",
            "title": "tool output",
            "text": text,
        }
    if event.get("type") == "response_item" and payload.get("type") == "reasoning":
        text = _content_text(payload.get("summary"))
        if not text.strip():
            return None
        return {**base, "kind": "reasoning", "title": "reasoning", "text": text}
    if event.get("type") == "event_msg" and payload.get("type") == "error":
        text = str(payload.get("message") or "")
        if not text.strip():
            return None
        return {**base, "kind": "error", "title": "error", "text": text}
    return None


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts)


def _short_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
