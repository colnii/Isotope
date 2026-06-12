"""Project Codex CLI JSONL output into Isotope runtime data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from .events import CodexRuntimeEvent
from .summary import CodexRuntimeSummary, summarize_codex_runtime_events


TEXT_PREVIEW_LIMIT = 2000
SENSITIVE_KEYS = {
    "api_key",
    "full_content",
    "full_text",
    "messages",
    "model_prompt",
    "model_request",
    "model_response",
    "prompt",
    "raw_content",
    "raw_prompt",
    "raw_response",
    "secret",
    "stderr",
    "stdin",
    "stdout",
    "token",
}
TOOL_CALL_ITEM_TYPES = {"function_call", "tool_call", "custom_tool_call"}
TOOL_OUTPUT_ITEM_TYPES = {
    "function_call_output",
    "tool_call_output",
    "custom_tool_call_output",
}


@dataclass(frozen=True)
class CodexRuntimeProjection:
    events: list[CodexRuntimeEvent]
    summary: CodexRuntimeSummary

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "codex_runtime_projection",
            "events": [event.to_dict() for event in self.events],
            "summary": self.summary.to_dict(),
        }


def project_codex_jsonl_stdout(
    *,
    stdout: str,
    stderr: str,
    status: str,
    reason_code: str,
) -> CodexRuntimeProjection:
    if not isinstance(stdout, str):
        raise ValueError("stdout must be a string")
    if not isinstance(stderr, str):
        raise ValueError("stderr must be a string")
    if not isinstance(status, str) or not status:
        raise ValueError("status must be a non-empty string")
    if not isinstance(reason_code, str) or not reason_code:
        raise ValueError("reason_code must be a non-empty string")

    events: list[CodexRuntimeEvent] = []
    malformed_event_count = 0
    for event_index, line in enumerate(_non_empty_lines(stdout)):
        try:
            raw_event = json.loads(line)
        except json.JSONDecodeError:
            malformed_event_count += 1
            continue
        if not isinstance(raw_event, dict):
            malformed_event_count += 1
            continue
        event = _project_event(raw_event, event_index=event_index)
        if event is not None:
            events.append(event)

    summary = summarize_codex_runtime_events(
        events=events,
        status=status,
        reason_code=reason_code,
        malformed_event_count=malformed_event_count,
        stderr_preview=_bounded_text(stderr),
    )
    return CodexRuntimeProjection(events=events, summary=summary)


def _non_empty_lines(stdout: str) -> list[str]:
    return [line for line in stdout.splitlines() if line.strip()]


def _project_event(
    event: Mapping[str, Any],
    *,
    event_index: int,
) -> CodexRuntimeEvent | None:
    event_type = _string(event.get("type")) or "unknown"
    item = _event_item(event)
    item_type = _string(item.get("type")) if isinstance(item, Mapping) else None

    if isinstance(item, Mapping) and item_type in {"message", "agent_message"}:
        role = _message_role(item, item_type=item_type)
        text = _message_text(item)
        return CodexRuntimeEvent(
            kind="message",
            title=role or "message",
            text=_bounded_text(text),
            event_index=event_index,
            event_type=event_type,
            item_type=item_type,
            role=role,
        )
    if isinstance(item, Mapping) and item_type == "reasoning":
        return CodexRuntimeEvent(
            kind="reasoning",
            title="reasoning",
            text=_bounded_text(_content_text(item.get("summary"))),
            event_index=event_index,
            event_type=event_type,
            item_type=item_type,
        )
    if isinstance(item, Mapping) and item_type in TOOL_CALL_ITEM_TYPES:
        return CodexRuntimeEvent(
            kind="tool_call",
            title=_string(item.get("name")) or item_type,
            text=_bounded_text(
                _short_text(_redact_sensitive_value(item.get("arguments", item.get("input"))))
            ),
            event_index=event_index,
            event_type=event_type,
            item_type=item_type,
        )
    if isinstance(item, Mapping) and item_type in TOOL_OUTPUT_ITEM_TYPES:
        return CodexRuntimeEvent(
            kind="tool_output",
            title="tool output",
            text=_bounded_text(_short_text(_redact_sensitive_value(item.get("output")))),
            event_index=event_index,
            event_type=event_type,
            item_type=item_type,
        )
    if _is_error_event(event, item):
        return CodexRuntimeEvent(
            kind="error",
            title="error",
            text=_bounded_text(_error_text(event, item)),
            event_index=event_index,
            event_type=event_type,
            item_type=item_type,
        )
    if event_type == "event_msg" or _string(event.get("message")):
        return CodexRuntimeEvent(
            kind="status",
            title=_event_title(event, item),
            text=_bounded_text(_status_text(event, item)),
            event_index=event_index,
            event_type=event_type,
            item_type=item_type,
        )
    return CodexRuntimeEvent(
        kind="unknown",
        title=event_type,
        text="",
        event_index=event_index,
        event_type=event_type,
        item_type=item_type,
    )


def _event_item(event: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for key in ("payload", "item"):
        value = event.get(key)
        if isinstance(value, Mapping):
            return value
    return event


def _message_role(item: Mapping[str, Any], *, item_type: str | None) -> str | None:
    role = _string(item.get("role"))
    if role:
        return role
    if item_type == "agent_message":
        return "assistant"
    return None


def _message_text(item: Mapping[str, Any]) -> str:
    text = _string(item.get("text"))
    if text is not None:
        return text
    message = _string(item.get("message"))
    if message is not None:
        return message
    return _content_text(item.get("content"))


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, Mapping):
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def _is_error_event(event: Mapping[str, Any], item: Mapping[str, Any] | None) -> bool:
    if event.get("type") == "error":
        return True
    if isinstance(item, Mapping) and item.get("type") == "error":
        return True
    return False


def _error_text(event: Mapping[str, Any], item: Mapping[str, Any] | None) -> str:
    for source in (item, event):
        if not isinstance(source, Mapping):
            continue
        for key in ("message", "error"):
            value = source.get(key)
            if isinstance(value, str):
                return value
    return ""


def _event_title(event: Mapping[str, Any], item: Mapping[str, Any] | None) -> str:
    if isinstance(item, Mapping):
        title = _string(item.get("type"))
        if title is not None:
            return title
    return _string(event.get("type")) or "status"


def _status_text(event: Mapping[str, Any], item: Mapping[str, Any] | None) -> str:
    for source in (item, event):
        if not isinstance(source, Mapping):
            continue
        for key in ("message", "text"):
            value = source.get(key)
            if isinstance(value, str):
                return value
    return ""


def _short_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _redact_sensitive_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in SENSITIVE_KEYS:
                redacted[key_text] = "[redacted]"
            else:
                redacted[key_text] = _redact_sensitive_value(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive_value(item) for item in value]
    return value


def _bounded_text(value: str) -> str:
    if len(value) <= TEXT_PREVIEW_LIMIT:
        return value
    return value[:TEXT_PREVIEW_LIMIT] + "...[truncated]"


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) else None
