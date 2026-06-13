"""Desktop snapshot adapter for the Isotope desktop frontend."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from isotope.features.supervisor.long_task.runtime import list_long_tasks
from isotope.features.supervisor.state.projection import (
    build_supervisor_state_snapshot,
)
from isotope.features.supervisor.state.worker_lifecycle import (
    worker_lifecycle_projection_payload,
)
from isotope.platform.ids import new_id
from isotope.platform.state.event_store import FileEventStore
from isotope.platform.state.projector import RunProjector


def build_desktop_snapshot(*, state_root: Path | str) -> dict[str, Any]:
    root = Path(state_root).expanduser()
    supervisor = build_supervisor_state_snapshot(codex_home=root)
    summary = supervisor.get("summary", {})
    active_goals = list(supervisor.get("active_goals", []))
    active_decisions = list(supervisor.get("active_decisions", []))
    root_status = _supervisor_root_status(summary)
    source = _supervisor_source(root)
    supervisor_agent = _supervisor_agent(source, status=root_status)
    supervisor_activity = _supervisor_activity(source, status=root_status)
    goal_activities = [
        _goal_activity(goal, index=index + 1, parent_id=supervisor_activity["id"])
        for index, goal in enumerate(active_goals)
    ]
    active_goal = _goal_summary(active_goals[0]) if active_goals else None
    approvals = [
        *[_approval_card(decision) for decision in active_decisions],
        *_runtime_pending_approval_cards(root),
    ]

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
            "runningAgents": int(root_status == "running"),
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
    snapshot["longTasks"] = list_long_tasks(root)
    if active_goal is not None:
        snapshot["activeGoal"] = active_goal
    worker_lifecycle = worker_lifecycle_projection_payload(state_snapshot=supervisor)
    if worker_lifecycle.get("status") == "ok":
        snapshot["workerLifecycle"] = worker_lifecycle
    return snapshot


def _supervisor_source(root: Path) -> dict[str, Any]:
    return {
        "kind": "real",
        "label": "supervisor_state_projection",
        "backendRef": f"supervisor_state:{root}",
    }


def _supervisor_agent(source: dict[str, Any], *, status: str) -> dict[str, Any]:
    return {
        "id": "supervisor_root",
        "title": "Isotope Supervisor",
        "status": status,
        "kind": "supervisor",
        "role": "coordinator",
        "source": source,
    }


def _supervisor_activity(source: dict[str, Any], *, status: str) -> dict[str, Any]:
    return {
        "id": "activity_supervisor_root",
        "kind": "supervisor",
        "title": "Isotope Supervisor",
        "status": status,
        "source": source,
        "sourceRef": {
            "kind": "agent",
            "id": "supervisor_root",
            "label": "Isotope Supervisor",
        },
        "order": 0,
        "summary": "Supervisor 状态投影已连接。",
    }


def _supervisor_root_status(summary: dict[str, Any]) -> str:
    if int(summary.get("failed_lanes", 0) or 0) > 0:
        return "error"
    if int(summary.get("active_decisions", 0) or 0) > 0:
        return "needs_attention"
    if int(summary.get("goals_needs_user", 0) or 0) > 0:
        return "needs_attention"
    if int(summary.get("goals_blocked", 0) or 0) > 0:
        return "blocked"
    if int(summary.get("active_goals", 0) or 0) > 0:
        return "running"
    return "idle"


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
    summary = _public_metadata_preview(goal.get("last_summary") or title)
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


def _approval_card(decision: dict[str, Any]) -> dict[str, Any]:
    request_id = str(decision["request_id"])
    title = _public_metadata_preview(decision.get("question") or "需要 Supervisor 审批")
    title = title or "需要 Supervisor 审批"
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


def _runtime_pending_approval_cards(root: Path) -> list[dict[str, Any]]:
    runs_root = root / "runs"
    if not runs_root.exists():
        return []
    event_store = FileEventStore(root)
    projector = RunProjector()
    approvals: list[dict[str, Any]] = []
    for event_path in sorted(runs_root.glob("*/events.jsonl")):
        run_id = event_path.parent.name
        state = projector.rebuild(run_id, event_store)
        for approval in state.approvals.values():
            if approval.get("status") != "pending":
                continue
            approvals.append(_runtime_approval_card(approval))
    return approvals


def _runtime_approval_card(approval: dict[str, Any]) -> dict[str, Any]:
    approval_id = str(approval["approval_id"])
    requested_label = _public_metadata_mapping(
        approval.get("requested_action_label"),
    )
    requested_summary = _runtime_approval_summary(requested_label)
    title = _runtime_approval_title(requested_label)
    source_ref = {"kind": "approval", "id": approval_id, "label": title}
    return _omit_none({
        "id": approval_id,
        "title": title,
        "status": "pending",
        "riskLevel": "medium",
        "runId": approval.get("run_id"),
        "proposalId": approval.get("proposal_id"),
        "decisionId": approval.get("decision_id"),
        "reasonCodes": list(approval.get("reason_codes", [])),
        "requestedActionLabel": requested_label,
        "requestedActionSummary": requested_summary,
        "source": {
            "kind": "derived",
            "label": "runtime_approval_request",
            "sourceRef": source_ref,
        },
    })


def _runtime_approval_summary(requested_label: dict[str, Any] | None) -> dict[str, Any] | None:
    tool = _label_string(requested_label, "tool")
    if tool == "local_file_read":
        path = _label_string(requested_label, "path")
        max_excerpt_chars = (
            requested_label.get("max_excerpt_chars")
            if isinstance(requested_label, dict)
            else None
        )
        summary: dict[str, Any] = {"tool": tool, "scope": "local_file"}
        if path:
            summary["path"] = path
        if isinstance(max_excerpt_chars, int) and not isinstance(max_excerpt_chars, bool):
            summary["max_excerpt_chars"] = max_excerpt_chars
        return summary
    if requested_label is None:
        return None
    return dict(requested_label)


def _runtime_approval_title(requested_label: dict[str, Any] | None) -> str:
    tool = _label_string(requested_label, "tool")
    if tool == "local_file_read":
        return "读取本地文件"
    if tool == "terminal_exec":
        command = _label_string(requested_label, "terminal_command")
        if command:
            return f"需要批准 terminal_exec: {command}"
        return "需要批准 terminal_exec"
    if tool:
        return f"需要批准 {tool}"
    action_type = _label_string(requested_label, "action_type")
    if action_type:
        return f"需要批准 {action_type}"
    return "需要批准运行时操作"


def _label_string(label: dict[str, Any] | None, key: str) -> str | None:
    if label is None:
        return None
    value = label.get(key)
    if not isinstance(value, str) or not value:
        return None
    return _public_metadata_preview(value)


def _goal_status(goal: dict[str, Any]) -> str:
    status = goal.get("last_status")
    if status == "needs_user":
        return "needs_attention"
    if status in {"done", "blocked", "needs_attention", "error", "running"}:
        return str(status)
    return "running"


def _public_metadata_preview(value: object) -> str | None:
    text = str(value)
    lowered = text.lower()
    if len(text) > 2000:
        return None
    if any(marker in lowered for marker in ("api_key", "api-key", "secret", "token=", "sk-")):
        return None
    return text


def _public_metadata_mapping(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    sanitized: dict[str, Any] = {}
    for key, nested in value.items():
        if not isinstance(key, str):
            continue
        clean = _public_metadata_value(nested)
        if clean is not None:
            sanitized[key] = clean
    return sanitized


def _public_metadata_value(value: object) -> Any:
    if isinstance(value, str):
        return _public_metadata_preview(value)
    if isinstance(value, bool) or isinstance(value, int) or isinstance(value, float):
        return value
    if isinstance(value, list):
        sanitized = [_public_metadata_value(item) for item in value]
        return [item for item in sanitized if item is not None]
    if isinstance(value, dict):
        return _public_metadata_mapping(value)
    return None


def _omit_none(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}
