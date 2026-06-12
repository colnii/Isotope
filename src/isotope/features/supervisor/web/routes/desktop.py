"""Desktop route parsing and payload input helpers."""

from __future__ import annotations

from urllib.parse import unquote

from isotope.capabilities.tools.terminal import (
    DEFAULT_ALLOWED_COMMANDS,
    DEFAULT_TERMINAL_APPROVAL_MODE,
    TERMINAL_APPROVAL_MODES,
)


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


def desktop_terminal_approval_mode(value: object) -> str:
    if value is None:
        return DEFAULT_TERMINAL_APPROVAL_MODE
    if isinstance(value, str) and value in TERMINAL_APPROVAL_MODES:
        return value
    raise ValueError("terminal_approval_mode must be single_approval, allowlist, or yolo")


def desktop_terminal_allowed_commands(value: object) -> list[str]:
    if value is None:
        return list(DEFAULT_ALLOWED_COMMANDS)
    if not isinstance(value, list):
        raise ValueError("terminal_allowed_commands must be a list")
    commands: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"terminal_allowed_commands[{index}] must be a non-empty string")
        command = item.strip()
        if command not in commands:
            commands.append(command)
    return commands
