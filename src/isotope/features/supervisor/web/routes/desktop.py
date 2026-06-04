"""Desktop route parsing and payload input helpers."""

from __future__ import annotations

from urllib.parse import unquote


def desktop_approval_resolve_id(path: str) -> str | None:
    prefix = "/desktop/approvals/"
    suffix = "/resolve"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    approval_id = unquote(path[len(prefix) : -len(suffix)])
    if "/" in approval_id or not approval_id:
        return None
    return approval_id


def desktop_chat_history(value: object) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("history must be a list")
    history: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"}:
            continue
        if not isinstance(content, str):
            continue
        clean_content = content.strip()
        if not clean_content:
            continue
        history.append({"role": role, "content": clean_content})
    return history[-12:]
