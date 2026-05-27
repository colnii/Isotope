"""Desktop snapshot adapter for the Isotope desktop frontend."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from isotope.features.supervisor.state.projection import build_supervisor_state_snapshot
from isotope.platform.ids import new_id


def build_desktop_snapshot(*, codex_home: Path | str) -> dict[str, Any]:
    root = Path(codex_home).expanduser()
    supervisor = build_supervisor_state_snapshot(codex_home=root)
    summary = supervisor.get("summary", {})
    source = _supervisor_source(root)
    supervisor_agent = _supervisor_agent(source)
    supervisor_activity = _supervisor_activity(source)
    active_goals = list(supervisor.get("active_goals", []))
    active_decisions = list(supervisor.get("active_decisions", []))
    goal_activities = [
        _goal_activity(goal, index=index + 1, parent_id=supervisor_activity["id"])
        for index, goal in enumerate(active_goals)
    ]
    active_goal = _goal_summary(active_goals[0]) if active_goals else None
    approvals = [_approval_summary(decision) for decision in active_decisions]

    snapshot = {
        "schemaVersion": 1,
        "snapshotId": new_id("desktop_snapshot"),
        "generatedAt": datetime.now(UTC).isoformat(),
        "source": source,
        # activeActivity is backend-authored and remains the supervisor root
        # for now; user-selected activity context is tracked locally in the
        # desktop frontend.
        "activeActivity": _activity_summary(supervisor_activity),
        "activeAgent": supervisor_agent,
        "counts": {
            "runningAgents": 0,
            "needsAttention": len(approvals)
            + int(summary.get("failed_lanes", 0) or 0),
            "approvals": len(approvals),
            "artifacts": 0,
            "errors": int(summary.get("failed_lanes", 0) or 0),
        },
        "agents": [supervisor_agent],
        "activities": [supervisor_activity, *goal_activities],
        "approvals": approvals,
        "artifacts": [],
        "runningToolCalls": [],
    }
    if active_goal is not None:
        snapshot["activeGoal"] = active_goal
    return snapshot


def _supervisor_source(root: Path) -> dict[str, Any]:
    return {
        "kind": "real",
        "label": "supervisor_state_projection",
        "backendRef": f"codex_home:{root}",
    }


def _supervisor_agent(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "supervisor_root",
        "title": "Isotope Supervisor",
        "status": "idle",
        "kind": "supervisor",
        "role": "coordinator",
        "source": source,
    }


def _supervisor_activity(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "activity_supervisor_root",
        "kind": "supervisor",
        "title": "Isotope Supervisor",
        "status": "idle",
        "source": source,
        "sourceRef": {
            "kind": "agent",
            "id": "supervisor_root",
            "label": "Isotope Supervisor",
        },
        "order": 0,
        "summary": "Supervisor state projection is connected.",
    }


def _activity_summary(activity: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": activity["id"],
        "kind": activity["kind"],
        "title": activity["title"],
        "status": activity["status"],
        "source": activity["source"],
    }


def _goal_activity(
    goal: dict[str, Any],
    *,
    index: int,
    parent_id: str,
) -> dict[str, Any]:
    goal_id = str(goal["goal_id"])
    title = str(goal["goal"])
    source_ref = {"kind": "goal", "id": goal_id, "label": title}
    summary = _low_sensitive_preview(goal.get("last_summary") or title)
    return _omit_none({
        "id": f"activity_goal_{goal_id}",
        "kind": "goal",
        "title": title,
        "status": _goal_status(goal),
        "source": {
            "kind": "derived",
            "label": "supervisor_active_goal",
            "sourceRef": source_ref,
        },
        "parentId": parent_id,
        "sourceRef": source_ref,
        "order": index,
        "createdAt": goal.get("created_at"),
        "updatedAt": goal.get("last_status_at") or goal.get("created_at"),
        "summary": summary,
    })


def _goal_summary(goal: dict[str, Any]) -> dict[str, Any]:
    goal_id = str(goal["goal_id"])
    title = str(goal["goal"])
    source_ref = {"kind": "goal", "id": goal_id, "label": title}
    return _omit_none({
        "id": goal_id,
        "title": title,
        "status": _goal_status(goal),
        "source": {
            "kind": "derived",
            "label": "supervisor_active_goal",
            "sourceRef": source_ref,
        },
        "updatedAt": goal.get("last_status_at") or goal.get("created_at"),
    })


def _approval_summary(decision: dict[str, Any]) -> dict[str, Any]:
    request_id = str(decision["request_id"])
    title = _low_sensitive_preview(decision.get("question") or "Supervisor approval required")
    title = title or "Supervisor approval required"
    source_ref = {"kind": "approval", "id": request_id, "label": title}
    return _omit_none({
        "id": request_id,
        "title": title,
        "status": "pending",
        "source": {
            "kind": "derived",
            "label": "supervisor_decision_request",
            "sourceRef": source_ref,
        },
    })


def _goal_status(goal: dict[str, Any]) -> str:
    status = goal.get("last_status")
    if status == "needs_user":
        return "needs_attention"
    if status in {"done", "blocked", "needs_attention", "error", "running"}:
        return str(status)
    return "running"


def _low_sensitive_preview(value: object) -> str | None:
    text = str(value)
    lowered = text.lower()
    if len(text) > 2000:
        return None
    if any(marker in lowered for marker in ("api_key", "api-key", "secret", "token=", "sk-")):
        return None
    return text


def _omit_none(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}
