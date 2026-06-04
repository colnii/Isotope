"""Read-only Supervisor state projection for dashboard and loop inputs."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from isotope.features.notifications.flow import NotificationFlow, NotificationSummary
from isotope.features.supervisor.agent_group.store import AgentGroupStore
from isotope.platform.schemas.memory import MemoryRecord
from isotope.platform.state.memory_store import FileMemoryStore
from isotope.platform.state.active_goal import SupervisorActiveGoal
from isotope.platform.state.decision_request import SupervisorDecisionRequest
from isotope.platform.state.notification_summary import SupervisorNotificationSummary
from isotope.platform.state.supervisor_snapshot import SupervisorStateSnapshot
from isotope.platform.state.worker_event_channel import list_worker_events
from isotope.platform.state.worker_event_summary import SupervisorWorkerEventSummary
from isotope.rag.retrieval import RetrievalService
from isotope.workspace.artifacts import ArtifactStore

from ..planner.decision_requests import read_active_decision_requests
from ..planner.goal_queue import (
    SupervisorGoal,
    read_active_supervisor_goals,
    read_latest_supervisor_goal_statuses,
)
from ..state.lane_state import LaneState, default_lane_state_path, read_lane_states
from ..state.worker_lifecycle import (
    read_latest_worker_lifecycle,
    worker_lifecycle_projection_payload,
)


def build_supervisor_state_snapshot(
    *,
    codex_home: Path | str,
    decision_limit: int = 20,
    worker_event_limit: int = 20,
    notification_limit: int = 20,
    goal_limit: int = 20,
) -> dict[str, Any]:
    """Build a public read model from existing Supervisor ledgers."""
    codex_home_path = Path(codex_home).expanduser()
    active_goals = _active_goal_payloads(codex_home_path, limit=goal_limit)
    active_decisions = [
        _decision_request_payload(request)
        for request in read_active_decision_requests(
            codex_home=codex_home_path,
            limit=decision_limit,
        )
    ]
    failed_lanes = _failed_lane_payloads(codex_home_path)
    worker_events = list_worker_events(
        root=codex_home_path,
        limit=worker_event_limit,
    )
    notifications = _notification_payload(
        codex_home_path,
        limit=notification_limit,
    )
    memory = _memory_payload(codex_home_path, limit=worker_event_limit)
    artifacts = _artifact_payload(codex_home_path, limit=worker_event_limit)
    agent_groups = _agent_group_payload(codex_home_path, limit=worker_event_limit)
    worker_lifecycle = read_latest_worker_lifecycle(codex_home=codex_home_path)
    worker_event_summary = worker_events.get("summary", {})
    total_worker_events = (
        worker_event_summary.get("total", 0)
        if isinstance(worker_event_summary, dict)
        else 0
    )

    snapshot = SupervisorStateSnapshot(
        codex_home=str(codex_home_path),
        summary={
            "active_goals": len(active_goals),
            "goals_done": _goal_status_count(active_goals, "done"),
            "goals_blocked": _goal_status_count(active_goals, "blocked"),
            "goals_needs_user": _goal_status_count(active_goals, "needs_user"),
            "active_decisions": len(active_decisions),
            "failed_lanes": len(failed_lanes),
            "worker_events": total_worker_events,
            "notifications": notifications["total"],
            "unread_notifications": notifications["unread"],
            "memory_records": memory["total"],
            "artifact_summaries": artifacts["total"],
            "agent_groups": agent_groups["total"],
        },
        active_goals=active_goals,
        active_decisions=active_decisions,
        failed_lanes=failed_lanes,
        recent_worker_events=[
            _worker_event_payload(item) for item in worker_events.get("events") or []
        ],
        notifications=notifications,
        memory=memory,
        artifacts=artifacts,
        agent_groups=agent_groups,
        worker_lifecycle=worker_lifecycle,
    ).to_dict()
    return snapshot


def _active_goal_payloads(codex_home: Path, *, limit: int) -> list[dict[str, Any]]:
    statuses = read_latest_supervisor_goal_statuses(codex_home=codex_home)
    return [
        _active_goal_payload(goal, latest_status=statuses.get(goal.goal_id))
        for goal in read_active_supervisor_goals(codex_home=codex_home, limit=limit)
    ]


def _active_goal_payload(
    goal: SupervisorGoal,
    *,
    latest_status: dict[str, Any] | None,
) -> dict[str, Any]:
    return SupervisorActiveGoal.from_scheduler_goal(goal).to_state_payload(
        latest_status=latest_status
    )


def _goal_status_count(goals: list[dict[str, Any]], status: str) -> int:
    return sum(1 for goal in goals if goal.get("last_status") == status)


def _decision_request_payload(request: Any) -> dict[str, Any]:
    return SupervisorDecisionRequest.from_ledger_request(request).to_state_payload()


def _failed_lane_payloads(codex_home: Path) -> list[dict[str, Any]]:
    states = read_lane_states(default_lane_state_path(codex_home))
    failed = [
        state
        for state in states.values()
        if state.last_status == "failed" and state.last_failure_reason
    ]
    return [_failed_lane_payload(state) for state in sorted(failed, key=lambda item: item.name)]


def _failed_lane_payload(state: LaneState) -> dict[str, Any]:
    return state.to_failed_lane_payload()


def _worker_event_payload(event: dict[str, Any]) -> dict[str, Any]:
    return SupervisorWorkerEventSummary.from_payload(event).to_state_payload()


def _notification_payload(codex_home: Path, *, limit: int) -> dict[str, Any]:
    notifications = NotificationFlow.in_process(codex_home).list_notifications()
    recent = notifications[:limit]
    unread_count = sum(1 for item in notifications if item.unread)
    return {
        "total": len(notifications),
        "unread": unread_count,
        "recent": [_notification_summary_payload(item) for item in recent],
    }


def _notification_summary_payload(summary: NotificationSummary) -> dict[str, Any]:
    return SupervisorNotificationSummary.from_payload(summary.to_dict()).to_state_payload()


def _memory_payload(codex_home: Path, *, limit: int) -> dict[str, Any]:
    records = FileMemoryStore(codex_home).list_records()
    by_scope = Counter(record.scope for record in records)
    sorted_records = sorted(
        records,
        key=lambda record: (record.created_at, record.memory_id),
        reverse=True,
    )
    return {
        "total": len(records),
        "by_scope": {
            "thread": by_scope.get("thread", 0),
            "run": by_scope.get("run", 0),
            "session": by_scope.get("session", 0),
        },
        "recent": [_memory_record_payload(record) for record in sorted_records[:limit]],
    }


def _memory_record_payload(record: MemoryRecord) -> dict[str, Any]:
    return {
        "record_id": record.memory_id,
        "scope": record.scope,
        "summary": record.summary,
        "source_refs": [dict(ref) for ref in record.source_refs],
        "provenance": dict(record.provenance),
        "created_at": record.created_at,
        "supersedes": list(record.supersedes),
        "quality": record.quality,
    }


def _artifact_payload(codex_home: Path, *, limit: int) -> dict[str, Any]:
    store = ArtifactStore(codex_home)
    retrieval = RetrievalService(store)
    summaries: list[dict[str, Any]] = []
    for artifact in _list_artifacts_safely(store, codex_home):
        try:
            summaries.append(
                retrieval.get_artifact_summary(
                    artifact.ref,
                    {"artifact": {"read": "summary"}},
                )
            )
        except (OSError, TypeError, ValueError, KeyError, PermissionError):
            continue
    sorted_summaries = sorted(
        summaries,
        key=lambda item: (
            str((item.get("ref") or {}).get("run_id", "")),
            str((item.get("ref") or {}).get("artifact_id", "")),
        ),
        reverse=True,
    )
    return {"total": len(summaries), "recent": sorted_summaries[:limit]}


def _agent_group_payload(codex_home: Path, *, limit: int) -> dict[str, Any]:
    try:
        groups = AgentGroupStore(codex_home).list_groups()
    except (OSError, TypeError, ValueError):
        groups = []
    recent = sorted(
        groups,
        key=lambda group: (group.updated_at, group.group_id),
        reverse=True,
    )[:limit]
    return {
        "total": len(groups),
        "recent": [group.to_public_dict() for group in recent],
    }


def _list_artifacts_safely(store: ArtifactStore, codex_home: Path) -> list[Any]:
    artifacts: list[Any] = []
    for run_dir in sorted((codex_home / "runs").glob("*")):
        if not run_dir.is_dir():
            continue
        try:
            artifacts.extend(store.list_artifacts(run_dir.name))
        except (OSError, TypeError, ValueError, KeyError):
            continue
    return artifacts
