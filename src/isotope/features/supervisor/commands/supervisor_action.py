"""Shared Supervisor action payload helpers."""

from __future__ import annotations

from typing import Any


def set_supervisor_action_payload(
    payload: dict[str, Any],
    action: dict[str, Any],
) -> None:
    payload["llm_action"] = action
    payload["supervisor_action"] = action


def supervisor_action_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("supervisor_action")
    if isinstance(action, dict):
        return action
    legacy_action = payload["llm_action"]
    if not isinstance(legacy_action, dict):
        raise TypeError("llm_action must be a dict")
    return legacy_action
