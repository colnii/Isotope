"""Executor boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from typing import Any

from .action_registry import ActionTypeRegistry
from .events import CanonicalEvent
from .ids import new_id
from .models import ActionExecution, ActionProposal, MemoryRecord, PolicyDecision


class Executor:
    """Execute authorized proposals using only PolicyDecision.grants."""

    def __init__(
        self,
        event_store,
        artifact_store,
        workspace_manager,
        registry: ActionTypeRegistry | None = None,
        memory_service=None,
    ):
        self.event_store = event_store
        self.artifact_store = artifact_store
        self.workspace_manager = workspace_manager
        self.registry = registry if registry is not None else ActionTypeRegistry.default()
        self.memory_service = memory_service

    def execute(self, decision: PolicyDecision, proposal: ActionProposal) -> ActionExecution:
        if decision.outcome == "denied":
            raise PermissionError("policy decision denied execution")

        execution_id = new_id("exec")
        self._append(
            proposal.run_id,
            "action.started",
            {
                "execution_id": execution_id,
                "proposal_id": proposal.proposal_id,
                "decision_id": decision.decision_id,
            },
        )

        try:
            granted_tools = decision.grants.get("tools", [])
            tool_name = proposal.payload.get("tool")
            if not isinstance(tool_name, str) or not tool_name:
                raise PermissionError("unknown tool")
            try:
                entry = self.registry.get_tool(tool_name)
            except KeyError as exc:
                raise PermissionError(f"unknown tool {tool_name}") from exc
            if not entry.enabled:
                raise PermissionError(f"disabled tool {tool_name}")
            if tool_name not in granted_tools:
                raise PermissionError(f"{tool_name} is not granted")
            if tool_name == "write_memory" and self.memory_service is not None:
                execution = self._new_execution(execution_id, proposal, decision, status="started")
                record = self._memory_record_from_proposal(proposal, execution_id)
                self.memory_service.write_record(
                    record,
                    execution=execution,
                    grants=decision.grants,
                )
                raise PermissionError("memory_write success not enabled")
            if tool_name != "write_artifact_tool":
                raise PermissionError(f"unsupported handler for tool {tool_name}")

            # This validates the granted workspace mode without consulting requested capabilities.
            self.workspace_manager.get_binding(decision.grants)

            execution = self._new_execution(execution_id, proposal, decision, status="completed")
            artifact = self.artifact_store.create_artifact(
                run_id=proposal.run_id,
                execution_id=execution.execution_id,
                artifact_type="text",
                summary="hello artifact",
                content=str(proposal.payload.get("text", "")),
            )
        except Exception as exc:
            self._append_failed(proposal, decision, execution_id, exc)
            raise

        self._append_artifact_created(proposal.run_id, artifact)
        self._append_action_completed(proposal.run_id, execution, artifact)
        return execution

    def _new_execution(
        self,
        execution_id: str,
        proposal: ActionProposal,
        decision: PolicyDecision,
        *,
        status: str,
    ) -> ActionExecution:
        return ActionExecution(
            execution_id=execution_id,
            proposal_id=proposal.proposal_id,
            decision_id=decision.decision_id,
            action_type=proposal.action_type,
            status=status,
            effective_grants_snapshot={
                "tools": list(decision.grants.get("tools", [])),
                "workspace": dict(decision.grants.get("workspace", {})),
                "budget": dict(decision.grants.get("budget", {})),
            },
        )

    def _memory_record_from_proposal(
        self,
        proposal: ActionProposal,
        execution_id: str,
    ) -> MemoryRecord:
        payload = proposal.payload
        provenance = dict(payload.get("provenance", {}))
        provenance.update(
            {
                "run_id": proposal.run_id,
                "execution_id": execution_id,
                "action_type": proposal.action_type,
            }
        )
        return MemoryRecord(
            memory_id=new_id("mem"),
            scope=str(payload.get("scope", "run")),
            content=payload.get("content"),
            summary=str(payload.get("summary", "")),
            source_refs=payload.get("source_refs"),
            provenance=provenance,
            created_at="2026-04-27T00:00:00Z",
            supersedes=list(payload.get("supersedes", [])),
            quality=str(payload.get("quality", "unverified")),
        )

    def _append(self, run_id: str, event_type: str, payload: dict[str, Any]) -> CanonicalEvent:
        event = CanonicalEvent(
            event_id=new_id("evt"),
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            created_at="2026-04-27T00:00:00Z",
        )
        return self.event_store.append(event)

    def _append_failed(
        self,
        proposal: ActionProposal,
        decision: PolicyDecision,
        execution_id: str,
        exc: Exception,
    ) -> CanonicalEvent:
        return self._append(
            proposal.run_id,
            "action.failed",
            {
                "execution_id": execution_id,
                "proposal_id": proposal.proposal_id,
                "decision_id": decision.decision_id,
                "status": "failed",
                "error": str(exc),
            },
        )

    def _append_artifact_created(self, run_id: str, artifact) -> CanonicalEvent:
        return self._append(
            run_id,
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

    def _append_action_completed(self, run_id: str, execution: ActionExecution, artifact) -> CanonicalEvent:
        return self._append(
            run_id,
            "action.completed",
            {
                "execution_id": execution.execution_id,
                "status": execution.status,
                "artifact_refs": [artifact.ref.to_dict()],
            },
        )
