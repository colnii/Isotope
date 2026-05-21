"""Product-facing Agent loop run control read model."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from typing import Any

from ...platform.state.projector import RunState


READY_NEXT_ACTIONS = [
    "query_memory",
    "create_source_artifact",
    "record_turn_memory",
    "submit_worker_handoff",
    "submit_approval_gated_action",
    "call_capability",
]
APPROVAL_NEXT_ACTIONS = ["get_approval", "resolve_approval"]
DEFERRED_CAPABILITIES = [
    "real_llm_provider",
    "scheduler",
    "real_worker_runtime",
]


def build_agent_loop_control(state: RunState) -> dict[str, Any]:
    """Build a copied, JSON-friendly control read model from projected state."""
    pending_approvals = [
        deepcopy(approval)
        for approval in state.approvals.values()
        if approval.get("status") == "pending"
    ]
    phase = _phase_for_state(state, pending_approvals)
    waiting_on = [_approval_waiting_item(approval) for approval in pending_approvals]
    return {
        "run_id": state.run_id,
        "session_id": state.session_id,
        "goal": state.goal,
        "status": state.status,
        "phase": phase,
        "current_agent": state.current_agent,
        "waiting_on": waiting_on,
        "next_actions": _next_actions_for_phase(phase),
        "blocked_reason_codes": _blocked_reason_codes(pending_approvals),
        "approvals": {
            "pending_count": len(pending_approvals),
            "pending_ids": [str(approval["approval_id"]) for approval in pending_approvals],
        },
        "progress": _progress(state),
        "deferred_capabilities": list(DEFERRED_CAPABILITIES),
        "last_event_id": state.last_event_id,
    }


def build_agent_loop_tick_policy(
    control: dict[str, Any],
    *,
    tick_budget: dict[str, Any] | None = None,
    user_pause: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a JSON-friendly one-tick continue/stop decision from run control."""
    phase = str(control["phase"])
    next_actions = list(control.get("next_actions", []))
    pending_approval_ids = list(control.get("approvals", {}).get("pending_ids", []))
    budget_summary = _tick_budget_summary(tick_budget)
    pause_summary = _user_pause_summary(user_pause)
    must_stop_reason = _tick_stop_reason(phase, next_actions)
    if must_stop_reason is None:
        if pause_summary["user_paused"]:
            must_stop_reason = "user_paused"
        elif budget_summary is not None and budget_summary["budget_exhausted"]:
            must_stop_reason = "tick_budget_exhausted"
    return {
        "run_id": control["run_id"],
        "phase": phase,
        "should_continue": must_stop_reason is None,
        "must_stop_reason": must_stop_reason,
        "requires_human": phase == "awaiting_approval" or pause_summary["user_paused"],
        "max_next_tick_kind": _max_next_tick_kind(phase, next_actions)
        if must_stop_reason is None or phase == "awaiting_approval"
        else None,
        "next_actions": next_actions,
        "pending_approval_ids": pending_approval_ids,
        "blocked_reason_codes": list(control.get("blocked_reason_codes", [])),
        "deferred_capabilities": list(control.get("deferred_capabilities", [])),
        "tick_budget": budget_summary,
        "user_pause": pause_summary,
        "last_event_id": control.get("last_event_id"),
    }


def _tick_stop_reason(phase: str, next_actions: list[str]) -> str | None:
    if phase == "ready" and next_actions:
        return None
    if phase == "awaiting_approval":
        return "awaiting_approval"
    if phase == "completed":
        return "completed"
    if phase in {"denied", "failed"}:
        return phase
    if not next_actions:
        return "no_next_actions"
    return "blocked"


def _max_next_tick_kind(phase: str, next_actions: list[str]) -> str | None:
    if phase == "ready" and next_actions:
        return "planner_step"
    if phase == "awaiting_approval":
        return "approval_resolution"
    return None


def _tick_budget_summary(tick_budget: dict[str, Any] | None) -> dict[str, Any] | None:
    if tick_budget is None:
        return None
    if not isinstance(tick_budget, dict):
        raise ValueError("tick_budget must be an object")
    max_ticks = _int_field(tick_budget, "max_ticks", required=True)
    ticks_used = _int_field(tick_budget, "ticks_used", required=False)
    if max_ticks <= 0:
        raise ValueError("tick_budget.max_ticks must be greater than zero")
    if ticks_used < 0:
        raise ValueError("tick_budget.ticks_used must be greater than or equal to zero")
    remaining_ticks = max(max_ticks - ticks_used, 0)
    budget_basis = tick_budget.get("budget_basis")
    if budget_basis is not None and not isinstance(budget_basis, str):
        raise ValueError("tick_budget.budget_basis must be a string")
    return {
        "max_ticks": max_ticks,
        "ticks_used": ticks_used,
        "remaining_ticks": remaining_ticks,
        "budget_exhausted": remaining_ticks == 0,
        "budget_basis": budget_basis,
    }


def _user_pause_summary(user_pause: dict[str, Any] | None) -> dict[str, Any]:
    if user_pause is None:
        return {
            "user_paused": False,
            "pause_basis": None,
        }
    if not isinstance(user_pause, dict):
        raise ValueError("user_pause must be an object")
    user_paused = user_pause.get("user_paused", False)
    if not isinstance(user_paused, bool):
        raise ValueError("user_pause.user_paused must be a boolean")
    pause_basis = user_pause.get("pause_basis")
    if pause_basis is not None and not isinstance(pause_basis, str):
        raise ValueError("user_pause.pause_basis must be a string")
    return {
        "user_paused": user_paused,
        "pause_basis": pause_basis,
    }


def _int_field(data: dict[str, Any], name: str, *, required: bool) -> int:
    if name not in data:
        if required:
            raise ValueError(f"tick_budget.{name} is required")
        return 0
    value = data[name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"tick_budget.{name} must be an integer")
    return value


def _phase_for_state(state: RunState, pending_approvals: list[dict[str, Any]]) -> str:
    if pending_approvals:
        return "awaiting_approval"
    if state.status == "completed":
        return "completed"
    if state.status in {"denied", "failed"}:
        return state.status
    return "ready"


def _next_actions_for_phase(phase: str) -> list[str]:
    if phase == "ready":
        return list(READY_NEXT_ACTIONS)
    if phase == "awaiting_approval":
        return list(APPROVAL_NEXT_ACTIONS)
    return []


def _approval_waiting_item(approval: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "approval",
        "approval_id": approval["approval_id"],
        "status": approval["status"],
        "reason_codes": list(approval.get("reason_codes", [])),
        "requested_action_summary": dict(approval.get("requested_action_summary", {})),
    }


def _blocked_reason_codes(pending_approvals: list[dict[str, Any]]) -> list[str]:
    codes: list[str] = []
    for approval in pending_approvals:
        for code in approval.get("reason_codes", []):
            if code not in codes:
                codes.append(code)
    return codes


def _progress(state: RunState) -> dict[str, int]:
    action_summaries = list(asdict(state).get("actions", {}).values())
    return {
        "actions_total": len(action_summaries),
        "actions_completed": _count_status(action_summaries, "completed"),
        "actions_pending_approval": _count_status(action_summaries, "pending_user_approval"),
        "artifacts_total": len(state.artifacts),
        "memory_records_total": len(state.memory_records),
        "workers_total": len(state.workers),
        "workspaces_total": len(state.workspaces),
    }


def _count_status(items: list[dict[str, Any]], status: str) -> int:
    return sum(1 for item in items if item.get("status") == status)
