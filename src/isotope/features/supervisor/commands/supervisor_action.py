"""Shared Supervisor action payload helpers."""

from __future__ import annotations

from typing import Any


def set_supervisor_action_payload(
    payload: dict[str, Any],
    action: dict[str, Any],
) -> None:
    payload["llm_action"] = action
    payload["supervisor_action"] = action
