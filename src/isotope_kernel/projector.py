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
        elif event.event_type == "run.completed":
            state.status = str(payload.get("status", "completed"))

    def project(self, events: Iterable[CanonicalEvent]) -> RunState:
        state = RunState()
        for event in events:
            self.apply(state, event)
        return state

    def rebuild(self, run_id: str, event_store) -> RunState:
        return self.project(event_store.list_events(run_id))
