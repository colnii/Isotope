"""Shared validation helpers for Codex CLI integration modules."""

from __future__ import annotations

from typing import Any


def non_empty_string(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    if "\x00" in value:
        raise ValueError(f"{field_name} cannot contain NUL")
    return value


def stripped_non_empty_string(field_name: str, value: Any) -> str:
    raw = non_empty_string(field_name, value)
    stripped = raw.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be a non-empty string")
    return stripped


__all__ = [
    "non_empty_string",
    "stripped_non_empty_string",
]
