"""In-process runtime facade boundary for the Isotope v0.1 slice."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from ..execution.executor import Executor, ToolHandler
from ..platform.events.events import CanonicalEvent
from ..platform.errors import IsotopeError, not_enabled_result
from ..platform.ids import new_id, reserve_ids
from ..platform.registry.actions import ActionTypeRegistry
from ..memory import FileMemoryStore, LocalMemoryQueryService
from ..platform.schemas.refs import ResourceRef
from ..platform.state.event_store import FileEventStore
from ..platform.state.projector import RunProjector
from ..policy import PolicyEngine
from ..rag.retrieval import RetrievalService
from ..workspace import WorkspaceManager
from ..workspace.artifacts import ArtifactStore
from .action_compiler import ActionCompiler
from .in_process_actions import InProcessActionMixin
from .in_process_agent_loop import InProcessAgentLoopMixin
from .in_process_approvals import InProcessApprovalMixin
from .in_process_checkpoints import InProcessCheckpointMixin
from .in_process_snapshots import InProcessSnapshotMixin
from .in_process_workspace import InProcessWorkspaceMixin


def _existing_id_strings(root: Path) -> list[str]:
    values: list[str] = []
    for relative_path in (
        Path("projects/index.json"),
        Path("tasks/index.json"),
        Path("files/index.json"),
    ):
        values.extend(_json_id_strings(root / relative_path))
    for event_path in sorted((root / "runs").glob("*/events.jsonl")):
        if not event_path.exists():
            continue
        for line in event_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                values.extend(_walk_id_strings(json.loads(line)))
            except JSONDecodeError:
                continue
    return values


def _json_id_strings(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        return list(_walk_id_strings(json.loads(path.read_text(encoding="utf-8"))))
    except JSONDecodeError:
        return []


def _walk_id_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _walk_id_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_id_strings(nested)




class InProcessServer(
    InProcessActionMixin,
    InProcessApprovalMixin,
    InProcessAgentLoopMixin,
    InProcessWorkspaceMixin,
    InProcessSnapshotMixin,
    InProcessCheckpointMixin,
):
    """Minimal in-process runtime facade; this is not a real HTTP API."""

    def __init__(
        self,
        root: Path,
        checkpoint_store=None,
        registry: ActionTypeRegistry | None = None,
        tool_handlers: dict[str, ToolHandler] | None = None,
        terminal_backend=None,
        terminal_backend_config=None,
        codex_task_adapter=None,
        codex_task_adapter_config=None,
        screen_backend=None,
        screen_backend_config=None,
        memory_store=None,
        memory_query_service=None,
        *,
        policy_profile_id: str = "default",
        policy_version: str = "v0.2",
    ):
        self.root = Path(root)
        reserve_ids(_existing_id_strings(self.root))
        self.event_store = FileEventStore(self.root)
        self.checkpoint_store = checkpoint_store
        self.artifact_store = ArtifactStore(self.root)
        self.memory_store = memory_store if memory_store is not None else FileMemoryStore(self.root)
        self.memory_query_service = (
            memory_query_service
            if memory_query_service is not None
            else LocalMemoryQueryService(self.memory_store)
        )
        self.registry = registry if registry is not None else ActionTypeRegistry.default()
        self.compiler = ActionCompiler(registry=self.registry)
        self.policy = PolicyEngine(
            registry=self.registry,
            policy_profile_id=policy_profile_id,
            policy_version=policy_version,
        )
        self.workspace_manager = WorkspaceManager()
        self.executor = Executor(
            event_store=self.event_store,
            artifact_store=self.artifact_store,
            workspace_manager=self.workspace_manager,
            registry=self.registry,
            tool_handlers=tool_handlers,
            terminal_backend=terminal_backend,
            terminal_backend_config=terminal_backend_config,
            codex_task_adapter=codex_task_adapter,
            codex_task_adapter_config=codex_task_adapter_config,
            screen_backend=screen_backend,
            screen_backend_config=screen_backend_config,
        )
        self.retrieval = RetrievalService(self.artifact_store)
        self._sessions: dict[str, dict[str, Any]] = {}
        self._runs: dict[str, dict[str, Any]] = {}
        self._pending_approvals: dict[str, dict[str, Any]] = {}
        self._resolved_approvals: dict[str, dict[str, Any]] = {}

    def create_session(self) -> dict[str, str]:
        session_id = new_id("session")
        self._sessions[session_id] = {"session_id": session_id}
        self._append(session_id, "session.created", {"session_id": session_id, "status": "active"})
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

    def get_session_state(self, session_id: str) -> dict[str, Any]:
        self._validate_non_empty_string("session_id", session_id)
        session_state: dict[str, Any] | None = None
        run_ids: list[str] = []
        for event_path in sorted((self.root / "runs").glob("*/events.jsonl")):
            for event in self.event_store.list_events(event_path.parent.name):
                if event.event_type == "session.created" and event.payload.get("session_id") == session_id:
                    session_state = {
                        "session_id": session_id,
                        "status": event.payload.get("status", "active"),
                        "run_ids": [],
                    }
                elif event.event_type == "run.created" and event.payload.get("session_id") == session_id:
                    run_id = str(event.payload["run_id"])
                    if run_id not in run_ids:
                        run_ids.append(run_id)
        if session_state is None:
            raise IsotopeError(
                "unknown session_id",
                code="unknown_session",
                category="not_found",
                retryable=False,
                http_status=404,
                details={"session_id": session_id},
            )
        session_state["run_ids"] = run_ids
        return session_state


    def get_run_state(self, run_id: str):
        self._validate_known_run_id(run_id)
        project = RunProjector()
        if self.checkpoint_store is None:
            return project.rebuild(run_id, self.event_store)
        return project.rebuild_with_checkpoint(run_id, self.event_store, self.checkpoint_store)

    def get_events(self, run_id: str) -> list[CanonicalEvent]:
        self._validate_read_run_id(run_id)
        return self.event_store.list_events(run_id)

    def get_artifact_summary(self, ref, grants: dict) -> dict:
        return self.retrieval.get_artifact_summary(ref, grants)

    def ingest_external_input(self, raw_input: dict) -> dict[str, str]:
        return not_enabled_result("external_ingestion")

    def _validate_non_empty_string(self, field_name: str, value: object) -> None:
        if not isinstance(value, str) or not value:
            raise IsotopeError(
                f"{field_name} must be a non-empty string",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": field_name},
            )

    def _validate_existing_session_id(self, session_id: object) -> None:
        self._validate_non_empty_string("session_id", session_id)
        if session_id not in self._sessions:
            session_state = self.get_session_state(session_id)
            self._sessions[session_id] = {"session_id": session_state["session_id"]}

    def _validate_existing_run_id(self, run_id: object) -> None:
        self._validate_non_empty_string("run_id", run_id)
        if run_id not in self._runs:
            raise IsotopeError(
                "unknown run_id",
                code="unknown_run",
                category="not_found",
                retryable=False,
                http_status=404,
                details={"run_id": run_id},
            )

    def _validate_run_accepts_ordinary_input(self, run_id: str) -> None:
        state = self.get_run_state(run_id)
        if state.status in {"completed", "failed", "denied"}:
            raise IsotopeError(
                f"run is terminal: {state.status}",
                code="run_terminal",
                category="conflict",
                retryable=False,
                http_status=409,
                details={"run_id": run_id, "status": state.status},
            )

    def _runtime_context_for_write_helper(self, run_id: object) -> dict[str, str]:
        self._validate_non_empty_string("run_id", run_id)
        if not isinstance(run_id, str):
            raise IsotopeError(
                "run_id must be a non-empty string",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "run_id"},
            )
        if run_id in self._runs:
            self._validate_run_accepts_ordinary_input(run_id)
            return dict(self._runs[run_id])

        state = self.get_run_state(run_id)
        if state.status in {"completed", "failed", "denied"}:
            raise IsotopeError(
                f"run is terminal: {state.status}",
                code="run_terminal",
                category="conflict",
                retryable=False,
                http_status=409,
                details={"run_id": run_id, "status": state.status},
            )

        run_payload: dict[str, Any] | None = None
        agent_id = ""
        thread_id = ""
        for event in self.event_store.list_events(run_id):
            if event.event_type == "run.created" and run_payload is None:
                run_payload = dict(event.payload)
            elif event.event_type == "agent.created" and not agent_id:
                raw_agent_id = event.payload.get("agent_id")
                if isinstance(raw_agent_id, str):
                    agent_id = raw_agent_id
            elif event.event_type == "thread.created" and not thread_id:
                raw_thread_id = event.payload.get("thread_id")
                if isinstance(raw_thread_id, str):
                    thread_id = raw_thread_id

        if run_payload is None or not agent_id or not thread_id:
            raise IsotopeError(
                "run context cannot be recovered from events",
                code="run_context_unavailable",
                category="internal",
                retryable=False,
                http_status=500,
                details={"run_id": run_id},
            )

        session_id = run_payload.get("session_id", "")
        goal = run_payload.get("goal", "")
        if not isinstance(session_id, str):
            session_id = ""
        if not isinstance(goal, str):
            goal = ""
        return {
            "run_id": run_id,
            "session_id": session_id,
            "goal": goal,
            "agent_id": agent_id,
            "thread_id": thread_id,
        }

    def _validate_read_run_id(self, run_id: object) -> None:
        self._validate_non_empty_string("run_id", run_id)

    def _dict_string(self, data: dict[str, Any], field_name: str) -> str:
        value = data.get(field_name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field_name} must be a non-empty string")
        return value

    def _get_approval_read_state(self, run_id: str):
        self._validate_known_run_id(run_id)
        return self.get_run_state(run_id)

    def _validate_known_run_id(self, run_id: object) -> None:
        self._validate_non_empty_string("run_id", run_id)
        if not isinstance(run_id, str):
            raise IsotopeError(
                "run_id must be a non-empty string",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "run_id"},
            )
        if run_id not in self._runs and not self.event_store.event_path(run_id).exists():
            raise IsotopeError(
                "unknown run_id",
                code="unknown_run",
                category="not_found",
                retryable=False,
                http_status=404,
                details={"run_id": run_id},
            )

    def _append(self, run_id: str, event_type: str, payload: dict[str, Any]) -> CanonicalEvent:
        event = self._build_event(run_id, event_type, payload)
        return self.event_store.append(event)

    def _build_event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> CanonicalEvent:
        return CanonicalEvent(
            event_id=new_id("evt"),
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            created_at="2026-04-27T00:00:00Z",
        )

    def _project_with_candidate(self, run_id: str, event: CanonicalEvent):
        existing_events = self.event_store.list_events(run_id)
        return RunProjector().project([*existing_events, event])

    def _find_approval_requested_event(self, run_id: str, approval_id: str) -> CanonicalEvent | None:
        for event in self.event_store.list_events(run_id):
            if event.event_type == "approval.requested" and event.payload.get("approval_id") == approval_id:
                return event
        return None

    def _find_approval_requested_event_by_id(self, approval_id: str) -> CanonicalEvent | None:
        runs_root = self.root / "runs"
        if not runs_root.exists():
            return None
        for event_path in sorted(runs_root.glob("*/events.jsonl")):
            run_id = event_path.parent.name
            for event in self.event_store.list_events(run_id):
                if event.event_type == "approval.requested" and event.payload.get("approval_id") == approval_id:
                    return event
        return None


    def _find_action_started_event(self, run_id: str, proposal_id: str) -> CanonicalEvent | None:
        for event in self.event_store.list_events(run_id):
            if event.event_type != "action.started":
                continue
            if event.payload.get("proposal_id") == proposal_id:
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

    def _completed_artifact_ref(self, run_id: str, execution_id: str) -> ResourceRef | None:
        for event in reversed(self.event_store.list_events(run_id)):
            if event.event_type != "action.completed":
                continue
            payload = event.payload
            if payload.get("execution_id") != execution_id:
                continue
            artifact_refs = payload.get("artifact_refs", [])
            if not artifact_refs:
                return None
            ref = artifact_refs[-1]
            if not isinstance(ref, dict):
                return None
            return ResourceRef(
                ref_type=str(ref.get("ref_type", "")),
                scope=str(ref.get("scope", "")),
                run_id=str(ref.get("run_id", "")),
                artifact_id=str(ref.get("artifact_id", "")),
            )
        return None

    def _require_execution_action(self, state, execution_id: str) -> dict[str, Any]:
        action = state.actions.get(execution_id)
        if action is None:
            raise ValueError("unknown execution basis")
        return action

    def _require_action_proposal_id(self, action: dict[str, Any]) -> str:
        proposal_id = action.get("proposal_id")
        if not isinstance(proposal_id, str) or not proposal_id:
            raise ValueError("action basis is missing proposal_id")
        return proposal_id
