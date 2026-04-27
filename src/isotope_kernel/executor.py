"""Executor boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from typing import Any

from .events import CanonicalEvent
from .ids import new_id
from .models import ActionExecution, ActionProposal, PolicyDecision


class Executor:
    """Execute authorized proposals using only PolicyDecision.grants."""

    def __init__(self, event_store, artifact_store, workspace_manager):
        self.event_store = event_store
        self.artifact_store = artifact_store
        self.workspace_manager = workspace_manager

    def execute(self, decision: PolicyDecision, proposal: ActionProposal) -> ActionExecution:
        if decision.outcome == "denied":
            raise PermissionError("policy decision denied execution")

        granted_tools = decision.grants.get("tools", [])
        if "write_artifact_tool" not in granted_tools:
            raise PermissionError("write_artifact_tool is not granted")

        # This validates the granted workspace mode without consulting requested capabilities.
        self.workspace_manager.get_binding(decision.grants)

        execution = ActionExecution(
            execution_id=new_id("exec"),
            proposal_id=proposal.proposal_id,
            decision_id=decision.decision_id,
            action_type=proposal.action_type,
            status="completed",
            effective_grants_snapshot={
                "tools": list(decision.grants.get("tools", [])),
                "workspace": dict(decision.grants.get("workspace", {})),
                "budget": dict(decision.grants.get("budget", {})),
            },
        )
        self._append(
            proposal.run_id,
            "action.started",
            {
                "execution_id": execution.execution_id,
                "proposal_id": execution.proposal_id,
                "decision_id": execution.decision_id,
            },
        )
        artifact = self.artifact_store.create_artifact(
            run_id=proposal.run_id,
            execution_id=execution.execution_id,
            artifact_type="text",
            summary="hello artifact",
            content=str(proposal.payload.get("text", "")),
        )
        self._append(
            proposal.run_id,
            "artifact.created",
            {
                "artifact": {
                    "ref": artifact.ref.to_dict(),
                    "artifact_type": artifact.artifact_type,
                    "summary": artifact.summary,
                    "provenance": dict(artifact.provenance),
                }
            },
        )
        self._append(
            proposal.run_id,
            "action.completed",
            {
                "execution_id": execution.execution_id,
                "status": execution.status,
                "artifact_refs": [artifact.ref.to_dict()],
            },
        )
        return execution

    def _append(self, run_id: str, event_type: str, payload: dict[str, Any]) -> CanonicalEvent:
        event = CanonicalEvent(
            event_id=new_id("evt"),
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            created_at="2026-04-27T00:00:00Z",
        )
        return self.event_store.append(event)
