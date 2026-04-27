"""In-process server facade boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .action_compiler import ActionCompiler
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

    def __init__(self, root: Path):
        self.root = Path(root)
        self.event_store = FileEventStore(self.root)
        self.artifact_store = ArtifactStore(self.root)
        self.compiler = ActionCompiler()
        self.policy = PolicyEngine()
        self.workspace_manager = WorkspaceManager()
        self.executor = Executor(
            event_store=self.event_store,
            artifact_store=self.artifact_store,
            workspace_manager=self.workspace_manager,
        )
        self.retrieval = RetrievalService(self.artifact_store)
        self._sessions: dict[str, dict[str, Any]] = {}
        self._runs: dict[str, dict[str, Any]] = {}

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

        run = self._runs[run_id]
        proposal = self.compiler.compile(
            {
                "action": "call_tool",
                "tool": tool,
                "text": text,
                "requested_tools": [tool],
            },
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

        if decision.outcome == "denied":
            return {
                "status": "denied",
                "decision": decision,
                "execution": None,
                "run_state": self.get_run_state(run_id),
            }
        if decision.outcome == "pending_user_approval":
            self._append(
                run_id,
                "approval.requested",
                {
                    "approval_id": new_id("approval"),
                    "run_id": run_id,
                    "proposal_id": proposal.proposal_id,
                    "decision_id": decision.decision_id,
                    "action_type": proposal.action_type,
                },
            )
            return {
                "status": "pending_user_approval",
                "decision": decision,
                "execution": None,
                "run_state": self.get_run_state(run_id),
            }

        try:
            execution = self.executor.execute(decision, proposal)
        except Exception as exc:
            execution_id = new_id("exec")
            self._append(
                run_id,
                "action.started",
                {
                    "execution_id": execution_id,
                    "proposal_id": proposal.proposal_id,
                    "decision_id": decision.decision_id,
                },
            )
            self._append(
                run_id,
                "action.failed",
                {
                    "execution_id": execution_id,
                    "proposal_id": proposal.proposal_id,
                    "decision_id": decision.decision_id,
                    "status": "failed",
                    "error": str(exc),
                },
            )
            return {
                "status": "failed",
                "decision": decision,
                "execution": None,
                "execution_id": execution_id,
                "run_state": self.get_run_state(run_id),
            }

        artifact = self.artifact_store.list_artifacts(run_id)[-1]
        self._append(
            run_id,
            "action.started",
            {
                "execution_id": execution.execution_id,
                "proposal_id": execution.proposal_id,
                "decision_id": execution.decision_id,
            },
        )
        self._append(
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
        self._append(
            run_id,
            "action.completed",
            {
                "execution_id": execution.execution_id,
                "status": execution.status,
                "artifact_refs": [artifact.ref.to_dict()],
            },
        )
        self._append(run_id, "run.completed", {"status": "completed"})

        state = self.get_run_state(run_id)
        return {
            "status": state.status,
            "run_state": state,
            "artifact_ref": artifact.ref,
            "execution_id": execution.execution_id,
        }

    def get_run_state(self, run_id: str):
        self._validate_read_run_id(run_id)
        return RunProjector().rebuild(run_id, self.event_store)

    def get_events(self, run_id: str) -> list[CanonicalEvent]:
        self._validate_read_run_id(run_id)
        return self.event_store.list_events(run_id)

    def get_artifact_summary(self, ref, grants: dict) -> dict:
        return self.retrieval.get_artifact_summary(ref, grants)

    def ingest_external_input(self, raw_input: dict) -> dict[str, str]:
        return {"status": "not_enabled", "capability": "external_ingestion"}

    def create_checkpoint(self, run_id: str) -> dict[str, str]:
        return {"status": "not_enabled", "capability": "checkpoint"}

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

    def _append(self, run_id: str, event_type: str, payload: dict[str, Any]) -> CanonicalEvent:
        event = CanonicalEvent(
            event_id=new_id("evt"),
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            created_at="2026-04-27T00:00:00Z",
        )
        return self.event_store.append(event)
