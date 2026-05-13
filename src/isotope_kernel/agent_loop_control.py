"""Product-facing Agent loop run control read model."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from typing import Any

from .projector import RunState


READY_NEXT_ACTIONS = [
    "create_source_artifact",
    "submit_worker_handoff",
    "submit_approval_gated_action",
]
APPROVAL_NEXT_ACTIONS = ["get_approval", "resolve_approval"]
DEFERRED_CAPABILITIES = [
    "real_llm_provider",
    "scheduler",
    "real_worker_runtime",
    "memory_query_engine",
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
        "workers_total": len(state.workers),
        "workspaces_total": len(state.workspaces),
    }


def _count_status(items: list[dict[str, Any]], status: str) -> int:
    return sum(1 for item in items if item.get("status") == status)
