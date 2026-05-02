"""In-process server facade boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .action_compiler import ActionCompiler
from .action_registry import ActionTypeRegistry
from .artifact_store import ArtifactStore
from .event_store import FileEventStore
from .events import CanonicalEvent
from .executor import Executor
from .ids import new_id
from .models import PolicyDecision
from .policy import PolicyEngine
from .projector import RunProjector
from .retrieval import RetrievalService
from .workspace import WorkspaceManager


class InProcessServer:
    """Minimal in-process facade; this is not a real HTTP API."""

    def __init__(
        self,
        root: Path,
        checkpoint_store=None,
        registry: ActionTypeRegistry | None = None,
    ):
        self.root = Path(root)
        self.event_store = FileEventStore(self.root)
        self.checkpoint_store = checkpoint_store
        self.artifact_store = ArtifactStore(self.root)
        self.registry = registry if registry is not None else ActionTypeRegistry.default()
        self.compiler = ActionCompiler(registry=self.registry)
        self.policy = PolicyEngine(registry=self.registry)
        self.workspace_manager = WorkspaceManager()
        self.executor = Executor(
            event_store=self.event_store,
            artifact_store=self.artifact_store,
            workspace_manager=self.workspace_manager,
            registry=self.registry,
        )
        self.retrieval = RetrievalService(self.artifact_store)
        self._sessions: dict[str, dict[str, Any]] = {}
        self._runs: dict[str, dict[str, Any]] = {}
        self._pending_approvals: dict[str, dict[str, Any]] = {}
        self._resolved_approvals: dict[str, dict[str, Any]] = {}

    def create_session(self) -> dict[str, str]:
        session_id = new_id("session")
        self._sessions[session_id] = {"session_id": session_id}
        return {"session_id": session_id}

    def create_run(self, session_id: str, goal: str) -> dict[str, str]:
        self._validate_existing_session_id(session_id)
        self._validate_non_empty_string("goal", goal)

        run_id = new_id("run")
        agent_id = "agent_supervisor"
        thread_id = "thread_main"
        self._runs[run_id] = {
            "run_id": run_id,
            "session_id": session_id,
            "goal": goal,
            "agent_id": agent_id,
            "thread_id": thread_id,
        }
        self._append(run_id, "run.created", {"run_id": run_id, "session_id": session_id, "goal": goal})
        self._append(run_id, "agent.created", {"agent_id": agent_id})
        self._append(run_id, "thread.created", {"thread_id": thread_id, "agent_id": agent_id})
        return {"run_id": run_id}

    def submit_input(self, run_id: str, text: str) -> dict[str, Any]:
        return self.submit_tool_request(run_id, tool="write_artifact_tool", text=text)

    def submit_action(
        self,
        run_id: str,
        intent: dict[str, Any],
        requires_approval: bool = False,
    ) -> dict[str, Any]:
        self._validate_action_intent(intent)
        return self._submit_action_internal(
            run_id,
            deepcopy(intent),
            requires_approval=requires_approval,
        )

    def submit_tool_request(
        self,
        run_id: str,
        tool: str,
        text: str,
        requires_approval: bool = False,
    ) -> dict[str, Any]:
        self._validate_existing_run_id(run_id)
        self._validate_non_empty_string("tool", tool)
        self._validate_non_empty_string("text", text)
        if not isinstance(requires_approval, bool):
            raise ValueError("requires_approval must be a bool")

        return self._submit_action_internal(
            run_id,
            {
                "action": "call_tool",
                "tool": tool,
                "text": text,
                "requested_tools": [tool],
            },
            requires_approval=requires_approval,
        )

    def _submit_action_internal(
        self,
        run_id: str,
        intent: dict[str, Any],
        requires_approval: bool,
    ) -> dict[str, Any]:
        self._validate_existing_run_id(run_id)
        if not isinstance(requires_approval, bool):
            raise ValueError("requires_approval must be a bool")

        run = self._runs[run_id]
        proposal = self.compiler.compile(
            intent,
            {
                "run_id": run_id,
                "agent_id": run["agent_id"],
                "thread_id": run["thread_id"],
            },
        )
        self._append(
            run_id,
            "action.proposed",
            {
                "proposal_id": proposal.proposal_id,
                "agent_id": proposal.agent_id,
                "thread_id": proposal.thread_id,
                "action_type": proposal.action_type,
            },
        )

        decision = self.policy.decide(proposal)
        if requires_approval and decision.outcome != "denied":
            decision = PolicyDecision(
                decision_id=new_id("dec"),
                proposal_id=proposal.proposal_id,
                outcome="pending_user_approval",
                grants=decision.grants,
                reason_codes=["approval_required"],
            )
        self._append(
            run_id,
            "action.decided",
            {
                "decision_id": decision.decision_id,
                "proposal_id": decision.proposal_id,
                "outcome": decision.outcome,
                "reason_codes": list(decision.reason_codes),
            },
        )
        result_base = {
            "proposal_id": proposal.proposal_id,
            "decision_id": decision.decision_id,
            "decision": decision,
        }

        if decision.outcome == "denied":
            return {
                **result_base,
                "status": "denied",
                "execution": None,
                "run_state": self.get_run_state(run_id),
            }
        if decision.outcome == "pending_user_approval":
            approval_id = new_id("approval")
            self._append(
                run_id,
                "approval.requested",
                {
                    "approval_id": approval_id,
                    "run_id": run_id,
                    "proposal_id": proposal.proposal_id,
                    "decision_id": decision.decision_id,
                    "action_type": proposal.action_type,
                },
            )
            self._pending_approvals[approval_id] = {
                "run_id": run_id,
                "proposal": proposal,
                "decision": decision,
            }
            return {
                **result_base,
                "status": "pending_user_approval",
                "approval_id": approval_id,
                "execution": None,
                "run_state": self.get_run_state(run_id),
            }

        try:
            execution = self.executor.execute(decision, proposal)
        except Exception as exc:
            execution_id = self._latest_failed_execution_id(
                run_id,
                proposal_id=proposal.proposal_id,
                decision_id=decision.decision_id,
            )
            if not execution_id:
                raise RuntimeError("executor failed without action.failed event") from exc
            return {
                **result_base,
                "status": "failed",
                "execution": None,
                "execution_id": execution_id,
                "run_state": self.get_run_state(run_id),
            }

        artifact = self.artifact_store.list_artifacts(run_id)[-1]
        self._append(run_id, "run.completed", {"status": "completed"})

        state = self.get_run_state(run_id)
        return {
            **result_base,
            "status": state.status,
            "run_state": state,
            "artifact_ref": artifact.ref,
            "execution_id": execution.execution_id,
        }

    def resolve_approval(self, approval_id: str, resolution: dict[str, Any]) -> dict[str, Any]:
        self._validate_non_empty_string("approval_id", approval_id)
        body = self._validate_approval_resolution_body(resolution)

        if approval_id in self._resolved_approvals:
            raise ValueError("approval already resolved")

        pending = self._pending_approvals.get(approval_id)
        if pending is None:
            raise ValueError("unknown approval")

        run_id = pending["run_id"]
        approval_event = self._find_approval_requested_event(run_id, approval_id)
        if approval_event is None:
            raise ValueError("unknown approval")
        approval_payload = approval_event.payload

        self._append(
            run_id,
            "approval.resolved",
            {
                "approval_id": approval_id,
                "run_id": run_id,
                "proposal_id": approval_payload["proposal_id"],
                "decision_id": approval_payload["decision_id"],
                "resolution": body["resolution"],
                "reason": body["reason"],
                "resolver": body["resolver"],
                "basis_event_id": approval_event.event_id,
            },
        )

        if body["resolution"] == "denied":
            result = {
                "status": "denied",
                "run_state": self.get_run_state(run_id),
            }
            self._resolved_approvals[approval_id] = result
            return result

        original_decision: PolicyDecision = pending["decision"]
        proposal = pending["proposal"]
        executable_decision = PolicyDecision(
            decision_id=original_decision.decision_id,
            proposal_id=original_decision.proposal_id,
            outcome="approved",
            grants=original_decision.grants,
            reason_codes=list(original_decision.reason_codes),
        )

        try:
            execution = self.executor.execute(executable_decision, proposal)
        except Exception as exc:
            execution_id = self._latest_failed_execution_id(
                run_id,
                proposal_id=proposal.proposal_id,
                decision_id=executable_decision.decision_id,
            )
            if not execution_id:
                raise RuntimeError("executor failed without action.failed event") from exc
            result = {
                "status": "failed",
                "execution": None,
                "execution_id": execution_id,
                "run_state": self.get_run_state(run_id),
            }
            self._resolved_approvals[approval_id] = result
            return result

        artifact = self.artifact_store.list_artifacts(run_id)[-1]
        self._append(run_id, "run.completed", {"status": "completed"})
        state = self.get_run_state(run_id)
        result = {
            "status": state.status,
            "run_state": state,
            "artifact_ref": artifact.ref,
            "execution_id": execution.execution_id,
        }
        self._resolved_approvals[approval_id] = result
        return result

    def get_run_state(self, run_id: str):
        self._validate_read_run_id(run_id)
        project = RunProjector()
        if self.checkpoint_store is None:
            return project.rebuild(run_id, self.event_store)
        return project.rebuild_with_checkpoint(run_id, self.event_store, self.checkpoint_store)

    def get_pending_approvals(self, run_id: str) -> list[dict[str, Any]]:
        state = self._get_approval_read_state(run_id)
        return [
            deepcopy(approval)
            for approval in state.approvals.values()
            if approval.get("status") == "pending"
        ]

    def get_approval(self, run_id: str, approval_id: str) -> dict[str, Any]:
        self._validate_non_empty_string("approval_id", approval_id)
        state = self._get_approval_read_state(run_id)
        approval = state.approvals.get(approval_id)
        if approval is None:
            raise ValueError("unknown approval")
        return deepcopy(approval)

    def bind_workspace(
        self,
        run_id: str,
        decision: PolicyDecision,
        bound_to: dict[str, Any] | None = None,
        lease_status: str = "active",
    ) -> dict[str, Any]:
        self._validate_existing_run_id(run_id)
        if not isinstance(decision, PolicyDecision):
            raise TypeError("decision must be a PolicyDecision")
        if bound_to is None:
            bound_to = {"agent_id": self._runs[run_id]["agent_id"]}
        if not isinstance(bound_to, dict) or not bound_to:
            raise ValueError("bound_to must be a non-empty dict")
        has_binding_subject = any(
            isinstance(bound_to.get(field), str) and bound_to.get(field)
            for field in ("agent_id", "execution_id")
        )
        if not has_binding_subject:
            raise ValueError("bound_to must include agent_id or execution_id")
        if lease_status not in {"active", "released"}:
            raise ValueError("lease_status must be active or released")

        binding = self.workspace_manager.get_binding(decision.grants)
        workspace_grant = decision.grants["workspace"]
        event = self._append(
            run_id,
            "workspace.bound",
            {
                "workspace_id": binding.workspace_id,
                "run_id": run_id,
                "mode": binding.mode,
                "bound_to": dict(bound_to),
                "lease_status": lease_status,
                "provenance": {
                    "decision_id": decision.decision_id,
                    "grant_basis": {
                        "workspace": dict(workspace_grant),
                    },
                },
            },
        )
        state = self.get_run_state(run_id)
        workspace_binding = state.workspaces.get(binding.workspace_id)
        if workspace_binding is None:
            raise RuntimeError(f"workspace binding was not projected from {event.event_id}")
        return deepcopy(workspace_binding)

    def get_events(self, run_id: str) -> list[CanonicalEvent]:
        self._validate_read_run_id(run_id)
        return self.event_store.list_events(run_id)

    def get_artifact_summary(self, ref, grants: dict) -> dict:
        return self.retrieval.get_artifact_summary(ref, grants)

    def ingest_external_input(self, raw_input: dict) -> dict[str, str]:
        return {"status": "not_enabled", "capability": "external_ingestion"}

    def save_checkpoint_for_run(self, run_id: str) -> dict[str, str]:
        self._validate_read_run_id(run_id)
        if self.checkpoint_store is None:
            return {"status": "not_enabled", "capability": "checkpoint"}
        checkpoint = RunProjector().save_checkpoint(run_id, self.event_store, self.checkpoint_store)
        return {
            "status": "saved",
            "run_id": run_id,
            "basis_event_id": checkpoint["basis_event_id"],
        }

    def save_checkpoint_history_for_run(self, run_id: str) -> dict[str, str]:
        self._validate_read_run_id(run_id)
        if self.checkpoint_store is None:
            return {"status": "not_enabled", "capability": "checkpoint_history"}
        checkpoint = RunProjector().save_checkpoint_history(run_id, self.event_store, self.checkpoint_store)
        return {
            "status": "saved",
            "run_id": run_id,
            "basis_event_id": checkpoint["basis_event_id"],
            "checkpoint_kind": "history",
        }

    def create_checkpoint(self, run_id: str) -> dict[str, str]:
        return {"status": "not_enabled", "capability": "checkpoint"}

    def _validate_approval_resolution_body(self, body: object) -> dict[str, str]:
        if not isinstance(body, dict):
            raise ValueError("resolution body must be a dict")
        resolution = body.get("resolution")
        if resolution not in {"approved", "denied"}:
            raise ValueError("resolution must be approved or denied")
        reason = body.get("reason")
        if not isinstance(reason, str) or not reason:
            raise ValueError("reason must be a non-empty string")
        resolver = body.get("resolver")
        if not isinstance(resolver, str) or not resolver:
            raise ValueError("resolver must be a non-empty string")
        return {
            "resolution": resolution,
            "reason": reason,
            "resolver": resolver,
        }

    def _validate_action_intent(self, intent: object) -> None:
        if not isinstance(intent, dict):
            raise ValueError("intent must be a dict")
        if not intent:
            raise ValueError("intent must be a non-empty dict")

    def _validate_non_empty_string(self, field_name: str, value: object) -> None:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field_name} must be a non-empty string")

    def _validate_existing_session_id(self, session_id: object) -> None:
        self._validate_non_empty_string("session_id", session_id)
        if session_id not in self._sessions:
            raise ValueError("unknown session_id")

    def _validate_existing_run_id(self, run_id: object) -> None:
        self._validate_non_empty_string("run_id", run_id)
        if run_id not in self._runs:
            raise ValueError("unknown run_id")

    def _validate_read_run_id(self, run_id: object) -> None:
        self._validate_non_empty_string("run_id", run_id)

    def _get_approval_read_state(self, run_id: str):
        self._validate_known_run_id(run_id)
        return self.get_run_state(run_id)

    def _validate_known_run_id(self, run_id: object) -> None:
        self._validate_non_empty_string("run_id", run_id)
        if not isinstance(run_id, str):
            raise ValueError("run_id must be a non-empty string")
        if run_id not in self._runs and not self.event_store.event_path(run_id).exists():
            raise ValueError("unknown run_id")

    def _append(self, run_id: str, event_type: str, payload: dict[str, Any]) -> CanonicalEvent:
        event = CanonicalEvent(
            event_id=new_id("evt"),
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            created_at="2026-04-27T00:00:00Z",
        )
        return self.event_store.append(event)

    def _find_approval_requested_event(self, run_id: str, approval_id: str) -> CanonicalEvent | None:
        for event in self.event_store.list_events(run_id):
            if event.event_type == "approval.requested" and event.payload.get("approval_id") == approval_id:
                return event
        return None

    def _latest_failed_execution_id(self, run_id: str, proposal_id: str, decision_id: str) -> str:
        for event in reversed(self.event_store.list_events(run_id)):
            if event.event_type != "action.failed":
                continue
            payload = event.payload
            if payload.get("proposal_id") == proposal_id and payload.get("decision_id") == decision_id:
                return str(payload["execution_id"])
        return ""
