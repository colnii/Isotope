"""Screen control action builders for the smoke runner."""

from __future__ import annotations

from typing import Any


def _build_click_action(*, x: int, y: int, button: str) -> dict[str, Any]:
    return {
        "type": "click",
        "button": button,
        "x": x,
        "y": y,
    }


def _build_double_click_action(*, x: int, y: int, button: str) -> dict[str, Any]:
    return {
        "type": "double_click",
        "button": button,
        "x": x,
        "y": y,
    }


def _build_drag_action(
    *,
    x: int,
    y: int,
    to_x: int,
    to_y: int,
    button: str,
    duration_ms: int,
) -> dict[str, Any]:
    return {
        "type": "drag",
        "button": button,
        "x": x,
        "y": y,
        "to_x": to_x,
        "to_y": to_y,
        "duration_ms": duration_ms,
    }


def _build_restore_window_action() -> dict[str, Any]:
    return {"type": "restore_window"}
