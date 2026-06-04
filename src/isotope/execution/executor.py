"""Executor boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..platform.registry.actions import ActionTypeRegistry
from ..integrations.codex.task import (
    CodexTaskAdapter,
    CodexTaskExecutionError,
    CodexTaskNotConfiguredError,
    CodexTaskProtocolError,
)
from ..platform.ids import new_id
from ..platform.events.events import CanonicalEvent
from ..platform.schemas.actions import ActionExecution, ActionProposal, PolicyDecision
from ..platform.schemas.memory import MemoryRecord
from ..platform.schemas.refs import ResourceRef
from ..platform.schemas.tool_protocol import ToolInvocation, ToolResult
from ..capabilities.tools.terminal import ControlledTerminalRunner
from .screen.backend_adapter import ScreenBackendAdapter
from .screen.backend_types import (
    ScreenBackendExecutionError,
    ScreenBackendNotConfiguredError,
    ScreenBackendProtocolError,
)
from .terminal.runner import (
    TerminalBackendAdapter,
    TerminalBackendExecutionError,
    TerminalBackendNotConfiguredError,
    TerminalBackendProtocolError,
)


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
        terminal_backend=None,
        terminal_backend_config=None,
        codex_task_adapter=None,
        codex_task_adapter_config=None,
        screen_backend=None,
        screen_backend_config=None,
    ):
        self.event_store = event_store
        self.artifact_store = artifact_store
        self.workspace_manager = workspace_manager
        self.registry = registry if registry is not None else ActionTypeRegistry.default()
        self.memory_service = memory_service
        self.tool_handlers = dict(tool_handlers or {})
        self.terminal_runner = ControlledTerminalRunner(self.artifact_store.root)
        self.terminal_backend_config = terminal_backend_config
        self.terminal_backend_adapter = (
            TerminalBackendAdapter(
                artifact_store=self.artifact_store,
                backend=terminal_backend,
                backend_config=terminal_backend_config,
            )
            if terminal_backend is not None
            else None
        )
        self.codex_task_adapter_config = codex_task_adapter_config
        self.codex_task_adapter = (
            CodexTaskAdapter(
                artifact_store=self.artifact_store,
                backend=codex_task_adapter,
                adapter_config=codex_task_adapter_config,
            )
            if codex_task_adapter is not None
            else None
        )
        self.screen_backend_config = screen_backend_config
        self.screen_backend_adapter = (
            ScreenBackendAdapter(
                artifact_store=self.artifact_store,
                backend=screen_backend,
                backend_config=screen_backend_config,
            )
            if screen_backend is not None
            else None
        )

    def execute(self, decision: PolicyDecision, proposal: ActionProposal) -> ActionExecution:
        if decision.outcome == "denied":
            raise PermissionError("policy decision denied execution")

        execution_id = new_id("exec")
        started_event = self._append(
            proposal.run_id,
            "action.started",
            {
                "execution_id": execution_id,
                "proposal_id": proposal.proposal_id,
                "decision_id": decision.decision_id,
            },
        )

        try:
            completion_metadata: dict[str, Any] | None = None
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
            if tool_name == "terminal_exec":
                workspace_binding = self.workspace_manager.get_binding(decision.grants)
                execution = self._new_execution(execution_id, proposal, decision, status="completed")
                if self.terminal_backend_adapter is None:
                    if self.terminal_backend_config is not None:
                        backend_id = getattr(self.terminal_backend_config, "backend_id", None)
                        if isinstance(self.terminal_backend_config, dict):
                            backend_id = self.terminal_backend_config.get("backend_id")
                        raise TerminalBackendNotConfiguredError(details={"backend_id": backend_id})
                    result = self.terminal_runner.run(
                        proposal.payload.get("argv"),
                        grants=decision.grants,
                        timeout_seconds=int(decision.grants.get("budget", {}).get("seconds", 0)),
                    )
                    artifact = self.artifact_store.create_artifact(
                        run_id=proposal.run_id,
                        execution_id=execution.execution_id,
                        artifact_type="terminal_output",
                        summary=str(
                            proposal.payload.get("summary") or f"terminal command completed: {result.argv[0]}"
                        ),
                        content=result.to_artifact_content(),
                        proposal_id=proposal.proposal_id,
                        decision_id=decision.decision_id,
                    )
                    artifact_refs = [artifact.ref]
                else:
                    backend_result = self.terminal_backend_adapter.prepare_and_run(
                        proposal=proposal,
                        decision=decision,
                        execution_id=execution.execution_id,
                        workspace_binding=self._workspace_binding_payload(workspace_binding),
                        basis_event_ids=[started_event.event_id],
                    )
                    if backend_result.status != "completed":
                        raise TerminalBackendExecutionError(
                            backend_result.summary,
                            reason_code=backend_result.reason_code,
                            details={
                                "backend_session_id": backend_result.backend_session_id,
                                "backend_status": backend_result.status,
                                "exit_code": backend_result.exit_code,
                                "retryable": backend_result.retryable,
                            },
                        )
                    if not backend_result.artifact_refs:
                        raise TerminalBackendProtocolError(
                            "terminal backend completed without output artifacts",
                            details={"backend_session_id": backend_result.backend_session_id},
                        )
                    artifact_refs = list(backend_result.artifact_refs)
                    completion_metadata = {"terminal_backend": dict(backend_result.backend_summary)}
            elif tool_name == "codex_task":
                workspace_binding = self.workspace_manager.get_binding(decision.grants)
                execution = self._new_execution(execution_id, proposal, decision, status="completed")
                if self.codex_task_adapter is None:
                    adapter_id = None
                    if isinstance(self.codex_task_adapter_config, dict):
                        adapter_id = self.codex_task_adapter_config.get("adapter_id")
                    else:
                        adapter_id = getattr(self.codex_task_adapter_config, "adapter_id", None)
                    raise CodexTaskNotConfiguredError(details={"adapter_id": adapter_id})
                codex_result = self.codex_task_adapter.prepare_and_run(
                    proposal=proposal,
                    decision=decision,
                    execution_id=execution.execution_id,
                    workspace_binding=self._workspace_binding_payload(workspace_binding),
                    basis_event_ids=[started_event.event_id],
                )
                if codex_result.status != "completed":
                    raise CodexTaskExecutionError(
                        codex_result.summary,
                        reason_code=codex_result.reason_code,
                        details={
                            "adapter_session_id": codex_result.adapter_session_id,
                            "adapter_status": codex_result.status,
                            "retryable": codex_result.retryable,
                        },
                    )
                if not codex_result.artifact_refs:
                    raise CodexTaskProtocolError(
                        "codex task completed without output artifacts",
                        details={"adapter_session_id": codex_result.adapter_session_id},
                    )
                artifact_refs = list(codex_result.artifact_refs)
                completion_metadata = {"codex_task": dict(codex_result.adapter_summary)}
            elif tool_name in {"screen_observe", "screen_control"}:
                workspace_binding = self.workspace_manager.get_binding(decision.grants)
                execution = self._new_execution(execution_id, proposal, decision, status="completed")
                if self.screen_backend_adapter is None:
                    backend_id = None
                    if isinstance(self.screen_backend_config, dict):
                        backend_id = self.screen_backend_config.get("backend_id")
                    else:
                        backend_id = getattr(self.screen_backend_config, "backend_id", None)
                    raise ScreenBackendNotConfiguredError(details={"backend_id": backend_id})
                screen_result = self.screen_backend_adapter.prepare_and_run(
                    proposal=proposal,
                    decision=decision,
                    execution_id=execution.execution_id,
                    workspace_binding=self._workspace_binding_payload(workspace_binding),
                    basis_event_ids=[started_event.event_id],
                )
                if screen_result.status not in {"captured", "metadata_only", "planned", "completed"}:
                    raise ScreenBackendExecutionError(
                        screen_result.summary,
                        reason_code=screen_result.reason_code,
                        details={
                            "backend_session_id": screen_result.backend_session_id,
                            "backend_status": screen_result.status,
                            "retryable": screen_result.retryable,
                        },
                    )
                if not screen_result.artifact_refs:
                    raise ScreenBackendProtocolError(
                        "screen backend completed without output artifacts",
                        details={"backend_session_id": screen_result.backend_session_id},
                    )
                artifact_refs = list(screen_result.artifact_refs)
                completion_metadata = {"screen_backend": dict(screen_result.backend_summary)}
            elif tool_name == "write_memory" and self.memory_service is not None:
                execution = self._new_execution(execution_id, proposal, decision, status="completed")
                record = self._memory_record_from_proposal(proposal, execution_id)
                self.memory_service.write_record(
                    record,
                    execution=execution,
                    grants=decision.grants,
                )
                completed_event = self._append_action_completed(
                    proposal.run_id,
                    execution,
                    artifact_refs=[],
                    metadata={"memory_record_id": record.memory_id},
                )
                self._append_memory_record_created(
                    proposal.run_id,
                    record,
                    basis_event_id=completed_event.event_id,
                )
                return execution
            elif tool_name != "write_artifact_tool":
                handler = self.tool_handlers.get(tool_name)
                if handler is None:
                    raise PermissionError(f"unsupported handler for tool {tool_name}")
                workspace_binding = self.workspace_manager.get_binding(decision.grants)
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
                metadata: dict[str, Any] = {"result_text": tool_result.result_text}
                if tool_result.diagnostics:
                    metadata["diagnostics"] = [dict(diagnostic) for diagnostic in tool_result.diagnostics]
                self._append_action_completed(
                    proposal.run_id,
                    execution,
                    artifact_refs=tool_result.artifact_refs,
                    metadata=metadata,
                )
                return execution
            else:
                # This validates the granted workspace mode without consulting requested capabilities.
                self.workspace_manager.get_binding(decision.grants)

                execution = self._new_execution(execution_id, proposal, decision, status="completed")
                summary = proposal.payload.get("summary", "hello artifact")
                if not isinstance(summary, str) or not summary:
                    summary = "hello artifact"
                artifact_type = proposal.payload.get("artifact_type", "text")
                if not isinstance(artifact_type, str) or not artifact_type:
                    artifact_type = "text"
                artifact = self.artifact_store.create_artifact(
                    run_id=proposal.run_id,
                    execution_id=execution.execution_id,
                    artifact_type=artifact_type,
                    summary=summary,
                    content=str(proposal.payload.get("text", "")),
                    proposal_id=proposal.proposal_id,
                    decision_id=decision.decision_id,
                    basis_refs=proposal.payload.get("basis_refs"),
                    source_refs=proposal.payload.get("source_refs"),
                )
                artifact_refs = [artifact.ref]
        except Exception as exc:
            self._append_failed(proposal, decision, execution_id, exc)
            raise

        self._append_artifacts_created(proposal.run_id, artifact_refs)
        self._append_action_completed(proposal.run_id, execution, artifact_refs, metadata=completion_metadata)
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
        reason_code = str(getattr(exc, "error_reason_code", "tool_execution_failed"))
        structured_error = {
            "reason_code": reason_code,
            "message": str(exc),
        }
        structured_details = getattr(exc, "structured_details", None)
        if isinstance(structured_details, dict) and structured_details:
            structured_error["details"] = dict(structured_details)
        return self._append(
            proposal.run_id,
            "action.failed",
            {
                "execution_id": execution_id,
                "proposal_id": proposal.proposal_id,
                "decision_id": decision.decision_id,
                "status": "failed",
                "error": str(exc),
                "error_reason_code": reason_code,
                "structured_error": structured_error,
            },
        )

    def _append_artifacts_created(self, run_id: str, artifact_refs: list[ResourceRef]) -> list[CanonicalEvent]:
        return [self._append_artifact_ref_created(run_id, artifact_ref) for artifact_ref in artifact_refs]

    def _append_artifact_ref_created(self, run_id: str, artifact_ref: ResourceRef) -> CanonicalEvent:
        if artifact_ref.run_id != run_id:
            raise TerminalBackendProtocolError(
                "artifact_ref run_id must match executor run",
                details={"run_id": run_id, "artifact_run_id": artifact_ref.run_id},
            )
        metadata = self.artifact_store.get_metadata(artifact_ref, include_provenance=True)
        artifact_payload = {
            "ref": artifact_ref.to_dict(),
            "artifact_type": metadata["artifact_type"],
            "summary": metadata["summary"],
            "provenance": dict(metadata.get("provenance", {})),
        }
        if metadata.get("basis_refs"):
            artifact_payload["basis_refs"] = [dict(ref) for ref in metadata["basis_refs"]]
        if metadata.get("source_refs"):
            artifact_payload["source_refs"] = [dict(ref) for ref in metadata["source_refs"]]
        return self._append(run_id, "artifact.created", {"artifact": artifact_payload})

    def _append_action_completed(
        self,
        run_id: str,
        execution: ActionExecution,
        artifact_refs: list[ResourceRef] | list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> CanonicalEvent:
        payload = {
            "execution_id": execution.execution_id,
            "status": execution.status,
            "artifact_refs": self._artifact_ref_payloads(artifact_refs),
        }
        if metadata:
            payload.update(metadata)
        return self._append(
            run_id,
            "action.completed",
            payload,
        )

    def _append_memory_record_created(
        self,
        run_id: str,
        record: MemoryRecord,
        *,
        basis_event_id: str,
    ) -> CanonicalEvent:
        provenance = dict(record.provenance)
        provenance["basis_event_id"] = basis_event_id
        return self._append(
            run_id,
            "memory.record_created",
            {
                "record_id": record.memory_id,
                "execution_id": record.provenance["execution_id"],
                "summary": record.summary,
                "source_refs": [dict(ref) for ref in record.source_refs],
                "provenance": provenance,
                "basis_event_id": basis_event_id,
                "quality": record.quality,
            },
        )

    def _workspace_binding_payload(self, binding) -> dict[str, Any]:
        return {
            "workspace_id": binding.workspace_id,
            "mode": binding.mode,
        }

    def _artifact_ref_payloads(
        self,
        artifact_refs: list[ResourceRef] | list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for index, artifact_ref in enumerate(artifact_refs):
            if isinstance(artifact_ref, ResourceRef):
                payloads.append(artifact_ref.to_dict())
            elif isinstance(artifact_ref, dict):
                payloads.append(dict(artifact_ref))
            else:
                raise TypeError(f"artifact_refs[{index}] must be a ResourceRef or dict")
        return payloads
