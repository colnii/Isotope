"""Context compaction helpers for desktop chat history."""

from __future__ import annotations

import json


DESKTOP_CHAT_HISTORY_TOKEN_BUDGET = 12_000
DESKTOP_CHAT_HISTORY_RECENT_TOKEN_BUDGET = 5_000
DESKTOP_CHAT_HISTORY_SUMMARY_TOKEN_BUDGET = 1_500


def compact_desktop_chat_history_messages(
    messages: list[dict[str, str]],
    *,
    token_budget: int = DESKTOP_CHAT_HISTORY_TOKEN_BUDGET,
    recent_token_budget: int = DESKTOP_CHAT_HISTORY_RECENT_TOKEN_BUDGET,
) -> list[dict[str, str]]:
    """Replace oversized history with a compact summary plus recent raw turns."""

    if not messages:
        return []
    if _messages_token_count(messages) <= token_budget:
        return messages

    recent_messages = _recent_messages_within_budget(
        messages,
        token_budget=min(recent_token_budget, token_budget),
    )
    summarized_count = len(messages) - len(recent_messages)
    if summarized_count <= 0:
        summarized_count = len(messages)
        recent_messages = []

    summary_message = _history_compaction_message(
        messages[:summarized_count],
        original_message_count=len(messages),
        recent_message_count=len(recent_messages),
    )
    return [summary_message, *recent_messages]


def _recent_messages_within_budget(
    messages: list[dict[str, str]],
    *,
    token_budget: int,
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    remaining = token_budget
    for message in reversed(messages):
        tokens = _message_token_count(message)
        if tokens > remaining:
            break
        selected.append(message)
        remaining -= tokens
    selected.reverse()
    return selected


def _history_compaction_message(
    messages: list[dict[str, str]],
    *,
    original_message_count: int,
    recent_message_count: int,
) -> dict[str, str]:
    return {
        "role": "system",
        "content": _json_context_message(
            "desktop_chat_history_compaction",
            {
                "kind": "desktop_chat_history_compaction",
                "original_message_count": original_message_count,
                "summarized_message_count": len(messages),
                "recent_message_count": recent_message_count,
                "summary": _history_summary(messages),
            },
        ),
    }


def _history_summary(messages: list[dict[str, str]]) -> str:
    if not messages:
        return "(no prior history to summarize)"
    lines: list[str] = []
    remaining = DESKTOP_CHAT_HISTORY_SUMMARY_TOKEN_BUDGET
    for index, message in enumerate(messages, start=1):
        role = message["role"]
        content = " ".join(message["content"].split())
        line = f"{index}. {role}: {content}"
        tokens = _approx_token_count(line)
        if tokens <= remaining:
            lines.append(line)
            remaining -= tokens
            continue
        if remaining > 0:
            lines.append(_clip_to_token_budget(line, remaining))
        break
    return "\n".join(lines)


def _json_context_message(label: str, value: dict[str, object]) -> str:
    return f"{label}:\n" + json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
    )


def _messages_token_count(messages: list[dict[str, str]]) -> int:
    return sum(_message_token_count(message) for message in messages)


def _message_token_count(message: dict[str, str]) -> int:
    return _approx_token_count(message["role"]) + _approx_token_count(message["content"])


def _approx_token_count(text: str) -> int:
    ascii_chars = 0
    non_ascii_chars = 0
    for char in text:
        if ord(char) < 128:
            ascii_chars += 1
        else:
            non_ascii_chars += 1
    return max(1, ((ascii_chars + 3) // 4) + non_ascii_chars)


def _clip_to_token_budget(text: str, token_budget: int) -> str:
    if token_budget <= 0:
        return ""
    used = 0.0
    chars: list[str] = []
    for char in text:
        token_cost = 1.0 if ord(char) >= 128 else 0.25
        if used + token_cost > token_budget:
            break
        chars.append(char)
        used += token_cost
    clipped = "".join(chars).rstrip()
    if len(clipped) < len(text):
        return clipped + "\n[summary clipped to fit context budget]"
    return clipped
