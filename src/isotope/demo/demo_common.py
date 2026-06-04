"""Shared helpers for developer demo scenarios."""

from __future__ import annotations

from typing import Any


def _route_status(response: Any) -> str:
    if response.status_code == 200:
        return "active"
    if response.status_code in {400, 404, 405}:
        return "validation_error"
    if response.status_code == 501:
        return "unavailable"
    return "unknown"


def _latest_action_status(actions: dict[str, dict[str, Any]]) -> str:
    for action in reversed(list(actions.values())):
        status = action.get("status")
        if isinstance(status, str) and status:
            return status
    return "unknown"
