"""Executor boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .action_registry import ActionTypeRegistry
from .events import CanonicalEvent
from .ids import new_id
from .models import ActionExecution, ActionProposal, MemoryRecord, PolicyDecision
from .tool_protocol import ToolInvocation, ToolResult


ToolHandler = Callable[[ToolInvocation], ToolResult]


class Executor:
    """Execute authorized proposals using only PolicyDecision.grants."""

    def __init__(
        self,
        event_store,
        artifact_store,
        workspace_manager,
        registry: ActionTypeRegistry | None = None,
        memory_service=None,
        tool_handlers: dict[str, ToolHandler] | None = None,
    ):
        self.event_store = event_store
        self.artifact_store = artifact_store
        self.workspace_manager = workspace_manager
        self.registry = registry if registry is not None else ActionTypeRegistry.default()
        self.memory_service = memory_service
        self.tool_handlers = dict(tool_handlers or {})

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
            # This validates the granted workspace mode without consulting requested capabilities.
            workspace_binding = self.workspace_manager.get_binding(decision.grants)

            if tool_name != "write_artifact_tool":
                handler = self.tool_handlers.get(tool_name)
                if handler is None:
                    raise PermissionError(f"unsupported handler for tool {tool_name}")

                execution = self._new_execution(execution_id, proposal, decision, status="completed")
                invocation = self._new_tool_invocation(
                    execution_id,
                    proposal,
                    decision,
                    workspace_binding,
                )
                tool_result = handler(invocation)
                if not isinstance(tool_result, ToolResult):
                    raise TypeError("tool handler must return ToolResult")
                self._append_action_completed(
                    proposal.run_id,
                    execution,
                    artifact_refs=tool_result.artifact_refs,
                    result_summary=tool_result.result_summary,
                    diagnostics=tool_result.diagnostics,
                )
                return execution

            execution = self._new_execution(execution_id, proposal, decision, status="completed")
            summary = proposal.payload.get("summary", "hello artifact")
            if not isinstance(summary, str) or not summary:
                summary = "hello artifact"
            artifact = self.artifact_store.create_artifact(
                run_id=proposal.run_id,
                execution_id=execution.execution_id,
                artifact_type="text",
                summary=summary,
                content=str(proposal.payload.get("text", "")),
                proposal_id=proposal.proposal_id,
                decision_id=decision.decision_id,
                basis_refs=proposal.payload.get("basis_refs"),
                source_refs=proposal.payload.get("source_refs"),
            )
        except Exception as exc:
            self._append_failed(proposal, decision, execution_id, exc)
            raise

        self._append_artifact_created(proposal.run_id, artifact)
        self._append_action_completed(proposal.run_id, execution, artifact_refs=[artifact.ref.to_dict()])
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

    def _new_tool_invocation(
        self,
        execution_id: str,
        proposal: ActionProposal,
        decision: PolicyDecision,
        workspace_binding,
    ) -> ToolInvocation:
        provenance = {
            "execution_id": execution_id,
            "proposal_id": proposal.proposal_id,
            "decision_id": decision.decision_id,
        }
        effective_grants = {
            "tools": list(decision.grants.get("tools", [])),
            "workspace": dict(decision.grants.get("workspace", {})),
            "budget": dict(decision.grants.get("budget", {})),
        }
        return ToolInvocation(
            tool_name=str(proposal.payload.get("tool")),
            input_payload=dict(proposal.payload),
            execution_id=execution_id,
            proposal_id=proposal.proposal_id,
            decision_id=decision.decision_id,
            grants_snapshot=effective_grants,
            budget=dict(effective_grants.get("budget", {})),
            workspace_binding={
                "workspace_id": workspace_binding.workspace_id,
                "mode": workspace_binding.mode,
            },
            requested_capabilities=self._cap_requested_capabilities(
                proposal.requested_capabilities,
                effective_grants,
            ),
            provenance=provenance,
        )

    def _cap_requested_capabilities(
        self,
        requested: dict[str, Any],
        grants: dict[str, Any],
    ) -> dict[str, Any]:
        requested_tools = requested.get("tools", [])
        granted_tools = grants.get("tools", [])
        if isinstance(requested_tools, list) and isinstance(granted_tools, list):
            tools = [tool for tool in requested_tools if tool in granted_tools]
        else:
            tools = []

        capped = {"tools": tools}
        requested_workspace = requested.get("workspace")
        granted_workspace = grants.get("workspace", {})
        if (
            isinstance(requested_workspace, dict)
            and isinstance(granted_workspace, dict)
            and requested_workspace.get("mode") == granted_workspace.get("mode")
        ):
            capped["workspace"] = dict(granted_workspace)

        requested_budget = requested.get("budget")
        granted_budget = grants.get("budget", {})
        if isinstance(requested_budget, dict) and isinstance(granted_budget, dict):
            budget = {}
            for key, granted_value in granted_budget.items():
                requested_value = requested_budget.get(key)
                if isinstance(requested_value, (int, float)) and isinstance(granted_value, (int, float)):
                    budget[key] = min(requested_value, granted_value)
                elif requested_value == granted_value:
                    budget[key] = granted_value
            if budget:
                capped["budget"] = budget

        return capped

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
                "error_reason_code": "tool_execution_failed",
                "structured_error": {
                    "reason_code": "tool_execution_failed",
                    "message": str(exc),
                },
            },
        )

    def _append_artifact_created(self, run_id: str, artifact) -> CanonicalEvent:
        artifact_payload = {
            "ref": artifact.ref.to_dict(),
            "artifact_type": artifact.artifact_type,
            "summary": artifact.summary,
            "provenance": dict(artifact.provenance),
        }
        if artifact.basis_refs:
            artifact_payload["basis_refs"] = [dict(ref) for ref in artifact.basis_refs]
        if artifact.source_refs:
            artifact_payload["source_refs"] = [dict(ref) for ref in artifact.source_refs]
        return self._append(run_id, "artifact.created", {"artifact": artifact_payload})

    def _append_action_completed(
        self,
        run_id: str,
        execution: ActionExecution,
        *,
        artifact_refs: list[dict[str, Any]],
        result_summary: str | None = None,
        diagnostics: list[dict[str, Any]] | None = None,
    ) -> CanonicalEvent:
        payload = {
            "execution_id": execution.execution_id,
            "status": execution.status,
            "artifact_refs": [dict(ref) for ref in artifact_refs],
        }
        if result_summary is not None:
            payload["result_summary"] = result_summary
        if diagnostics is not None:
            payload["diagnostics"] = [dict(diagnostic) for diagnostic in diagnostics]
        return self._append(
            run_id,
            "action.completed",
            payload,
        )
