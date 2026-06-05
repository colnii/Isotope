"""Shared Supervisor action payload and display helpers."""

from __future__ import annotations

from typing import Any


SUPERVISOR_ACTION_SECTION_TITLE = "Supervisor 白名单动作"
SUPERVISOR_FOLLOWUP_ACTION_SECTION_TITLE = "Supervisor 同轮后续动作"
PROGRAM_ROUTED_ACTION_SECTION_TITLE = "程序路由动作"
LEGACY_LLM_ACTION_SECTION_TITLE = "LLM 白名单动作"


def set_supervisor_action_payload(
    payload: dict[str, Any],
    action: dict[str, Any],
) -> None:
    payload["llm_action"] = action
    payload["supervisor_action"] = action


def set_supervisor_followup_action_payload(
    payload: dict[str, Any],
    action: dict[str, Any],
) -> None:
    payload["llm_followup_action"] = action
    payload["supervisor_followup_action"] = action


def supervisor_action_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("supervisor_action")
    if isinstance(action, dict):
        return action
    legacy_action = payload["llm_action"]
    if not isinstance(legacy_action, dict):
        raise TypeError("llm_action must be a dict")
    return legacy_action


def supervisor_followup_action_from_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    action = payload.get("supervisor_followup_action")
    if isinstance(action, dict):
        return action
    legacy_action = payload["llm_followup_action"]
    if not isinstance(legacy_action, dict):
        raise TypeError("llm_followup_action must be a dict")
    return legacy_action
