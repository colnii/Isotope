"""RunState projector boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .events import CanonicalEvent


@dataclass
class RunState:
    """In-memory read model for the v0.1 slice, not a source of truth."""

    run_id: str = ""
    status: str = "unknown"
    current_agent: str = ""
    actions: dict[str, dict[str, Any]] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    last_event_id: str = ""


class RunProjector:
    """Project RunState only from canonical events."""

    def __init__(self) -> None:
        self._proposal_outcomes: dict[str, str] = {}
        self._execution_statuses: dict[str, str] = {}

    def _validate_lifecycle(self, event: CanonicalEvent) -> None:
        payload = event.payload

        if event.event_type == "action.decided":
            self._proposal_outcomes[str(payload["proposal_id"])] = str(payload.get("outcome", ""))
        elif event.event_type == "action.started":
            proposal_id = str(payload["proposal_id"])
            outcome = self._proposal_outcomes.get(proposal_id)
            if outcome == "denied":
                raise ValueError("action.started after denied decision")
            if outcome == "pending_user_approval":
                raise ValueError("action.started after pending approval")
            if outcome != "approved":
                raise ValueError("action.started before approved decision")
            self._execution_statuses[str(payload["execution_id"])] = "running"
        elif event.event_type == "action.completed":
            execution_id = str(payload["execution_id"])
            status = self._execution_statuses.get(execution_id)
            if status is None:
                raise ValueError("action.completed before action.started")
            if status == "failed":
                raise ValueError("terminal execution already failed")
            self._execution_statuses[execution_id] = "completed"
        elif event.event_type == "action.failed":
            execution_id = str(payload["execution_id"])
            status = self._execution_statuses.get(execution_id)
            if status == "completed":
                raise ValueError("terminal execution already completed")
            self._execution_statuses[execution_id] = "failed"

    def apply(self, state: RunState, event: CanonicalEvent) -> None:
        state.last_event_id = event.event_id
        if not state.run_id:
            state.run_id = event.run_id

        payload = event.payload
        if event.event_type == "run.created":
            state.run_id = str(payload.get("run_id", event.run_id))
            state.status = "running"
        elif event.event_type == "agent.created":
            state.current_agent = str(payload.get("agent_id", ""))
        elif event.event_type == "action.started":
            execution_id = str(payload["execution_id"])
            state.actions[execution_id] = {
                "execution_id": execution_id,
                "proposal_id": payload.get("proposal_id"),
                "decision_id": payload.get("decision_id"),
                "status": "running",
            }
        elif event.event_type == "action.decided":
            outcome = str(payload.get("outcome", ""))
            if outcome in {"denied", "pending_user_approval"}:
                proposal_id = str(payload["proposal_id"])
                state.actions[proposal_id] = {
                    "proposal_id": proposal_id,
                    "decision_id": payload.get("decision_id"),
                    "status": outcome,
                }
                if outcome == "pending_user_approval":
                    state.status = "pending_user_approval"
        elif event.event_type == "approval.requested":
            proposal_id = str(payload["proposal_id"])
            action = state.actions.setdefault(proposal_id, {"proposal_id": proposal_id})
            action["decision_id"] = payload.get("decision_id")
            action["approval_id"] = payload.get("approval_id")
            action["status"] = "pending_user_approval"
            state.status = "pending_user_approval"
        elif event.event_type == "artifact.created":
            artifact = dict(payload["artifact"])
            state.artifacts.append(
                {
                    "ref": dict(artifact["ref"]),
                    "artifact_type": artifact["artifact_type"],
                    "summary": artifact["summary"],
                    "provenance": dict(artifact["provenance"]),
                }
            )
        elif event.event_type == "action.completed":
            execution_id = str(payload["execution_id"])
            action = state.actions.setdefault(execution_id, {"execution_id": execution_id})
            action["status"] = payload.get("status", "completed")
        elif event.event_type == "action.failed":
            execution_id = str(payload["execution_id"])
            action = state.actions.setdefault(execution_id, {"execution_id": execution_id})
            action["proposal_id"] = payload.get("proposal_id")
            action["decision_id"] = payload.get("decision_id")
            action["status"] = payload.get("status", "failed")
            state.status = "failed"
        elif event.event_type == "run.completed":
            state.status = str(payload.get("status", "completed"))

    def project(self, events: Iterable[CanonicalEvent]) -> RunState:
        self._proposal_outcomes = {}
        self._execution_statuses = {}
        state = RunState()
        for event in events:
            self._validate_lifecycle(event)
            self.apply(state, event)
        return state

    def rebuild(self, run_id: str, event_store) -> RunState:
        return self.project(event_store.list_events(run_id))
