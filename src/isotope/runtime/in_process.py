"""In-process runtime facade boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from copy import deepcopy
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from ..agents.loop.control import build_agent_loop_control, build_agent_loop_tick_policy
from ..agents.loop.planner_adapter import run_agent_loop_planner_step
from ..agents.loop.planner_contract import run_agent_loop_real_planner_contract_step
from ..agents.loop.step import run_agent_loop_step
from ..execution.executor import Executor, ToolHandler
from ..platform.events.events import CanonicalEvent
from ..platform.errors import IsotopeError, IsotopePermissionError, not_enabled_result
from ..platform.ids import new_id, reserve_ids
from ..platform.registry.actions import ActionTypeRegistry
from ..memory import FileMemoryStore, LocalMemoryQueryService
from ..platform.schemas.actions import ActionExecution, ActionProposal, PolicyDecision
from ..platform.schemas.memory import MemoryRecord
from ..platform.schemas.snapshots import ImportedSnapshot
from ..platform.schemas.refs import ResourceRef
from ..platform.state.event_store import FileEventStore
from ..platform.state.projector import RunProjector
from ..policy import PolicyEngine
from ..rag.retrieval import RetrievalService
from ..workspace import WorkspaceManager
from ..workspace.artifacts import ArtifactStore
from .action_compiler import ActionCompiler


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


class InProcessServer:
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

    def submit_input(
        self,
        run_id: str,
        text: str,
        *,
        requires_approval: bool = False,
    ) -> dict[str, Any]:
        return self.submit_tool_request(
            run_id,
            tool="write_artifact_tool",
            text=text,
            requires_approval=requires_approval,
        )

    def submit_action(
        self,
        run_id: str,
        intent: dict[str, Any],
        requires_approval: bool = False,
        complete_run: bool = True,
    ) -> dict[str, Any]:
        self._validate_action_intent(intent)
        return self._submit_action_internal(
            run_id,
            deepcopy(intent),
            requires_approval=requires_approval,
            complete_run=complete_run,
        )

    def get_model_tool_catalog(self) -> dict[str, Any]:
        return self.registry.model_tool_catalog()

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

    def request_retry(
        self,
        run_id: str,
        *,
        basis_execution_id: str,
        reason: str,
        requested_by: str,
        replacement_intent: dict[str, Any],
        explicit_rerun: bool = False,
    ) -> dict[str, Any]:
        self._validate_existing_run_id(run_id)
        self._validate_non_empty_string("basis_execution_id", basis_execution_id)
        self._validate_non_empty_string("reason", reason)
        self._validate_non_empty_string("requested_by", requested_by)
        self._validate_action_intent(replacement_intent)
        if not isinstance(explicit_rerun, bool):
            raise ValueError("explicit_rerun must be a bool")

        state = self.get_run_state(run_id)
        action = self._require_execution_action(state, basis_execution_id)
        basis_status = action.get("status")
        if basis_status == "completed" and not explicit_rerun:
            raise ValueError("completed action retry requires explicit rerun")
        if basis_status not in {"failed", "completed"}:
            raise ValueError(f"retry requires failed execution or explicit rerun; basis status was {basis_status}")

        original_proposal_id = self._require_action_proposal_id(action)
        retry_id = new_id("retry")
        replacement_proposal_id = new_id("prop")
        replacement_execution_id = new_id("exec")
        request_payload: dict[str, Any] = {
            "retry_id": retry_id,
            "run_id": run_id,
            "original_proposal_id": original_proposal_id,
            "original_execution_id": basis_execution_id,
            "reason": reason,
            "requested_by": requested_by,
        }
        if explicit_rerun:
            request_payload["explicit_rerun"] = True
        request_event = self._append(run_id, "action.retry_requested", request_payload)
        self._append(
            run_id,
            "action.retry_created",
            {
                "retry_id": retry_id,
                "new_proposal_id": replacement_proposal_id,
                "new_execution_id": replacement_execution_id,
                "original_proposal_id": original_proposal_id,
                "basis_event_id": request_event.event_id,
                "policy_basis": {
                    "decision_id": action.get("decision_id"),
                    "mode": "replacement_reference",
                },
            },
        )
        return {
            "status": "created",
            "retry_id": retry_id,
            "basis_execution_id": basis_execution_id,
            "basis_proposal_id": original_proposal_id,
            "replacement_proposal_id": replacement_proposal_id,
            "replacement_execution_id": replacement_execution_id,
            "basis_event_id": request_event.event_id,
        }

    def request_cancel(
        self,
        run_id: str,
        *,
        reason: str,
        requested_by: str,
        basis_proposal_id: str | None = None,
        basis_execution_id: str | None = None,
    ) -> dict[str, Any]:
        self._validate_existing_run_id(run_id)
        self._validate_non_empty_string("reason", reason)
        self._validate_non_empty_string("requested_by", requested_by)
        if basis_execution_id is None and basis_proposal_id is None:
            raise ValueError("cancel requires basis_execution_id or basis_proposal_id")

        state = self.get_run_state(run_id)
        execution_id = ""
        if basis_execution_id is not None:
            self._validate_non_empty_string("basis_execution_id", basis_execution_id)
            action = self._require_execution_action(state, basis_execution_id)
            basis_status = str(action.get("status", ""))
            if basis_status in {"completed", "failed", "denied", "cancelled", "superseded"}:
                raise ValueError(f"cannot cancel terminal action with status {basis_status}")
            if basis_status != "running":
                raise ValueError(f"cancel requires running or pending action; basis status was {basis_status}")
            proposal_id = self._require_action_proposal_id(action)
            execution_id = basis_execution_id
        else:
            self._validate_non_empty_string("basis_proposal_id", basis_proposal_id)
            proposal_id = str(basis_proposal_id)
            action = state.actions.get(proposal_id)
            if action is None:
                raise ValueError("unknown proposal basis")
            basis_status = str(action.get("status", ""))
            if basis_status != "pending_user_approval":
                raise ValueError(f"cancel requires running or pending action; basis status was {basis_status}")

        cancel_id = new_id("cancel")
        payload: dict[str, Any] = {
            "cancel_id": cancel_id,
            "run_id": run_id,
            "proposal_id": proposal_id,
            "reason": reason,
            "requested_by": requested_by,
            "logical_only": True,
            "process_kill": False,
        }
        if execution_id:
            payload["execution_id"] = execution_id
        event = self._append(run_id, "action.cancel_requested", payload)
        return {
            "status": "cancel_requested",
            "cancel_id": cancel_id,
            "basis_proposal_id": proposal_id,
            "basis_execution_id": execution_id or None,
            "basis_event_id": event.event_id,
            "logical_only": True,
            "process_kill": False,
        }

    def request_supersede(
        self,
        run_id: str,
        *,
        old_proposal_id: str,
        reason: str,
        requested_by: str,
        old_execution_id: str | None = None,
        replacement_intent: dict[str, Any] | None = None,
        replacement_proposal_id: str | None = None,
    ) -> dict[str, Any]:
        self._validate_existing_run_id(run_id)
        self._validate_non_empty_string("old_proposal_id", old_proposal_id)
        self._validate_non_empty_string("reason", reason)
        self._validate_non_empty_string("requested_by", requested_by)
        if replacement_intent is None and replacement_proposal_id is None:
            raise ValueError("supersede requires replacement intent or replacement proposal identity")
        if replacement_intent is not None:
            self._validate_action_intent(replacement_intent)
        if replacement_proposal_id is not None:
            self._validate_non_empty_string("replacement_proposal_id", replacement_proposal_id)

        state = self.get_run_state(run_id)
        action = state.actions.get(old_proposal_id)
        if old_execution_id is not None:
            self._validate_non_empty_string("old_execution_id", old_execution_id)
            action = self._require_execution_action(state, old_execution_id)
            if action.get("proposal_id") != old_proposal_id:
                raise ValueError("supersede basis proposal does not match execution")
        if action is None:
            raise ValueError("unknown proposal basis")

        basis_event = self._find_action_started_event(run_id, old_proposal_id)
        if basis_event is None:
            raise ValueError("supersede basis requires started action")

        supersession_id = new_id("supersede")
        new_proposal_id = replacement_proposal_id or new_id("prop")
        new_execution_id = new_id("exec")
        self._append(
            run_id,
            "action.superseded",
            {
                "supersession_id": supersession_id,
                "old_proposal_id": old_proposal_id,
                "old_execution_id": old_execution_id,
                "new_proposal_id": new_proposal_id,
                "new_execution_id": new_execution_id,
                "reason": reason,
                "reason_code": "superseded_by_replacement",
                "requested_by": requested_by,
                "basis_event_id": basis_event.event_id,
                "provenance": {
                    "requested_by": requested_by,
                    "basis_event_id": basis_event.event_id,
                },
            },
        )
        return {
            "status": "created",
            "supersession_id": supersession_id,
            "old_proposal_id": old_proposal_id,
            "old_execution_id": old_execution_id,
            "replacement_proposal_id": new_proposal_id,
            "replacement_execution_id": new_execution_id,
            "reason_code": "superseded_by_replacement",
            "basis_event_id": basis_event.event_id,
        }

    def _submit_action_internal(
        self,
        run_id: str,
        intent: dict[str, Any],
        requires_approval: bool,
        complete_run: bool = True,
    ) -> dict[str, Any]:
        if not isinstance(requires_approval, bool):
            raise ValueError("requires_approval must be a bool")
        if not isinstance(complete_run, bool):
            raise ValueError("complete_run must be a bool")

        run = self._runtime_context_for_write_helper(run_id)
        proposal = self.compiler.compile(
            intent,
            {
                "run_id": run_id,
                "agent_id": run["agent_id"],
                "thread_id": run["thread_id"],
                "requires_approval": requires_approval,
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
                "registry_id": proposal.registry_id,
                "registry_version": proposal.registry_version,
                "registry_basis": proposal.registry_basis,
                "requested_action_summary": self._requested_action_summary(proposal),
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
                policy_profile_id=decision.policy_profile_id,
                policy_version=decision.policy_version,
            )
        self._append(
            run_id,
            "action.decided",
            {
                "decision_id": decision.decision_id,
                "proposal_id": decision.proposal_id,
                "outcome": decision.outcome,
                "reason_codes": list(decision.reason_codes),
                "policy_profile_id": decision.policy_profile_id,
                "policy_version": decision.policy_version,
                "policy_basis": decision.policy_basis,
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
            payload_ref = self._store_pending_approval_payload(
                run_id,
                approval_id,
                proposal.payload,
            )
            self._append(
                run_id,
                "approval.requested",
                {
                    "approval_id": approval_id,
                    "run_id": run_id,
                    "proposal_id": proposal.proposal_id,
                    "decision_id": decision.decision_id,
                    "action_type": proposal.action_type,
                    "resolution_context": {
                        "complete_run": complete_run,
                        "proposal": {
                            "proposal_id": proposal.proposal_id,
                            "run_id": proposal.run_id,
                            "agent_id": proposal.agent_id,
                            "thread_id": proposal.thread_id,
                            "action_type": proposal.action_type,
                            "payload_ref": payload_ref,
                            "requested_capabilities": deepcopy(proposal.requested_capabilities),
                            "registry_id": proposal.registry_id,
                            "registry_version": proposal.registry_version,
                        },
                        "decision": {
                            "decision_id": decision.decision_id,
                            "proposal_id": decision.proposal_id,
                            "outcome": decision.outcome,
                            "grants": deepcopy(decision.grants),
                            "reason_codes": list(decision.reason_codes),
                            "policy_profile_id": decision.policy_profile_id,
                            "policy_version": decision.policy_version,
                        },
                    },
                },
            )
            self._pending_approvals[approval_id] = {
                "run_id": run_id,
                "proposal": proposal,
                "decision": decision,
                "complete_run": complete_run,
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

        if complete_run:
            self._append(run_id, "run.completed", {"status": "completed"})

        state = self.get_run_state(run_id)
        result = {
            **result_base,
            "status": state.status,
            "tool_execution_status": "completed",
            "run_state": state,
            "execution_id": execution.execution_id,
        }
        artifact_ref = self._completed_artifact_ref(run_id, execution.execution_id)
        if artifact_ref is not None:
            result["artifact_ref"] = artifact_ref
        return result

    def _requested_action_summary(self, proposal) -> dict[str, Any]:
        summary: dict[str, Any] = {"action_type": proposal.action_type}
        tool_name = proposal.payload.get("tool")
        if tool_name == "terminal_exec":
            summary["tool"] = tool_name
            argv = proposal.payload.get("argv")
            if isinstance(argv, list) and argv and isinstance(argv[0], str):
                summary["terminal_command"] = argv[0]
                summary["argv_count"] = len(argv)
        return summary

    def resolve_approval(self, approval_id: str, resolution: dict[str, Any]) -> dict[str, Any]:
        self._validate_non_empty_string("approval_id", approval_id)
        body = self._validate_approval_resolution_body(resolution)

        if approval_id in self._resolved_approvals:
            raise ValueError("approval already resolved")

        pending = self._pending_approvals.get(approval_id)
        if pending is None:
            pending = self._recover_pending_approval_context(approval_id)

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
        complete_run = pending.get("complete_run", True)
        if not isinstance(complete_run, bool):
            raise ValueError("complete_run must be a bool")
        executable_decision = PolicyDecision(
            decision_id=original_decision.decision_id,
            proposal_id=original_decision.proposal_id,
            outcome="approved",
            grants=original_decision.grants,
            reason_codes=list(original_decision.reason_codes),
            policy_profile_id=original_decision.policy_profile_id,
            policy_version=original_decision.policy_version,
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

        if complete_run:
            self._append(run_id, "run.completed", {"status": "completed"})
        state = self.get_run_state(run_id)
        result = {
            "status": state.status,
            "tool_execution_status": "completed",
            "run_state": state,
            "execution_id": execution.execution_id,
        }
        artifact_ref = self._completed_artifact_ref(run_id, execution.execution_id)
        if artifact_ref is not None:
            result["artifact_ref"] = artifact_ref
        self._resolved_approvals[approval_id] = result
        return result

    def _recover_pending_approval_context(self, approval_id: str) -> dict[str, Any]:
        approval_event = self._find_approval_requested_event_by_id(approval_id)
        if approval_event is None:
            raise ValueError("unknown approval")
        run_id = approval_event.payload.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("unknown approval")

        state = self.get_run_state(run_id)
        approval_summary = state.approvals.get(approval_id)
        if approval_summary is None:
            raise ValueError("unknown approval")
        if approval_summary.get("status") != "pending":
            raise ValueError("approval already resolved")

        context = approval_event.payload.get("resolution_context")
        if not isinstance(context, dict):
            raise ValueError("approval resolution context unavailable")
        proposal = self._proposal_from_approval_context(context.get("proposal"), run_id)
        decision = self._decision_from_approval_context(context.get("decision"), proposal.proposal_id)
        complete_run = context.get("complete_run", True)
        if not isinstance(complete_run, bool):
            raise ValueError("approval completion context unavailable")
        return {
            "run_id": run_id,
            "proposal": proposal,
            "decision": decision,
            "complete_run": complete_run,
        }

    def _proposal_from_approval_context(self, raw: object, run_id: str) -> ActionProposal:
        if not isinstance(raw, dict):
            raise ValueError("approval proposal context unavailable")
        proposal = ActionProposal(
            proposal_id=self._context_string(raw, "proposal_id"),
            run_id=self._context_string(raw, "run_id"),
            agent_id=self._context_string(raw, "agent_id"),
            thread_id=self._context_string(raw, "thread_id"),
            action_type=self._context_string(raw, "action_type"),
            payload=self._load_pending_approval_payload(run_id, self._context_string(raw, "payload_ref")),
            requested_capabilities=deepcopy(self._context_dict(raw, "requested_capabilities")),
            registry_id=self._context_string(raw, "registry_id"),
            registry_version=self._context_string(raw, "registry_version"),
        )
        if proposal.run_id != run_id:
            raise ValueError("approval proposal context run_id mismatch")
        return proposal

    def _decision_from_approval_context(self, raw: object, proposal_id: str) -> PolicyDecision:
        if not isinstance(raw, dict):
            raise ValueError("approval decision context unavailable")
        decision = PolicyDecision(
            decision_id=self._context_string(raw, "decision_id"),
            proposal_id=self._context_string(raw, "proposal_id"),
            outcome=self._context_string(raw, "outcome"),
            grants=deepcopy(self._context_dict(raw, "grants")),
            reason_codes=list(self._context_list(raw, "reason_codes")),
            policy_profile_id=self._context_string(raw, "policy_profile_id"),
            policy_version=self._context_string(raw, "policy_version"),
        )
        if decision.proposal_id != proposal_id:
            raise ValueError("approval decision context proposal_id mismatch")
        return decision

    def _context_string(self, raw: dict[str, Any], field_name: str) -> str:
        value = raw.get(field_name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"approval context {field_name} unavailable")
        return value

    def _context_dict(self, raw: dict[str, Any], field_name: str) -> dict[str, Any]:
        value = raw.get(field_name)
        if not isinstance(value, dict):
            raise ValueError(f"approval context {field_name} unavailable")
        return value

    def _context_list(self, raw: dict[str, Any], field_name: str) -> list[Any]:
        value = raw.get(field_name)
        if not isinstance(value, list):
            raise ValueError(f"approval context {field_name} unavailable")
        return value

    def _pending_approval_payload_path(self, run_id: str, payload_ref: str) -> Path:
        self._validate_non_empty_string("run_id", run_id)
        self._validate_non_empty_string("payload_ref", payload_ref)
        return self.root / "runs" / run_id / "approval_payloads" / f"{payload_ref}.json"

    def _store_pending_approval_payload(
        self,
        run_id: str,
        approval_id: str,
        payload: dict[str, Any],
    ) -> str:
        if not isinstance(payload, dict):
            raise ValueError("approval payload must be a dict")
        payload_ref = f"{approval_id}_payload"
        path = self._pending_approval_payload_path(run_id, payload_ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"payload": payload}, sort_keys=True), encoding="utf-8")
        return payload_ref

    def _load_pending_approval_payload(self, run_id: str, payload_ref: str) -> dict[str, Any]:
        path = self._pending_approval_payload_path(run_id, payload_ref)
        if not path.exists():
            raise ValueError("approval payload context unavailable")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except JSONDecodeError as exc:
            raise ValueError("malformed approval payload context") from exc
        if not isinstance(data, dict) or not isinstance(data.get("payload"), dict):
            raise ValueError("malformed approval payload context")
        return deepcopy(data["payload"])

    def get_run_state(self, run_id: str):
        self._validate_known_run_id(run_id)
        project = RunProjector()
        if self.checkpoint_store is None:
            return project.rebuild(run_id, self.event_store)
        return project.rebuild_with_checkpoint(run_id, self.event_store, self.checkpoint_store)

    def get_agent_loop_control(self, run_id: str) -> dict[str, Any]:
        return build_agent_loop_control(self.get_run_state(run_id))

    def get_agent_loop_tick_policy(
        self,
        run_id: str,
        *,
        tick_budget: dict[str, Any] | None = None,
        user_pause: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return build_agent_loop_tick_policy(
            self.get_agent_loop_control(run_id),
            tick_budget=tick_budget,
            user_pause=user_pause,
        )

    def run_agent_loop_step(self, run_id: str, request: dict[str, Any]) -> dict[str, Any]:
        return run_agent_loop_step(self, run_id, request)

    def record_agent_loop_turn_memory(self, run_id: str, request: dict[str, Any]) -> dict[str, Any]:
        run = self._runtime_context_for_write_helper(run_id)
        summary = self._dict_string(request, "summary")
        content = request.get("content")
        if not isinstance(content, dict) or not content:
            raise ValueError("memory content must be a non-empty structured dict")
        scope = request.get("scope", "run")
        if scope not in {"thread", "run", "session"}:
            raise ValueError("memory scope must be thread, run, or session")
        source_refs = request.get("source_refs", [])
        if not isinstance(source_refs, list):
            raise ValueError("memory source_refs must be a list")
        supersedes = request.get("supersedes", [])
        if not isinstance(supersedes, list):
            raise ValueError("memory supersedes must be a list")
        quality = request.get("quality", "candidate")
        if not isinstance(quality, str) or not quality:
            raise ValueError("memory quality must be a non-empty string")

        proposal_id = new_id("prop")
        decision_id = new_id("dec")
        execution_id = new_id("exec")
        grants = {
            "tools": ["write_memory"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        }
        self._append(
            run_id,
            "action.proposed",
            {
                "proposal_id": proposal_id,
                "agent_id": run["agent_id"],
                "thread_id": run["thread_id"],
                "action_type": "write_memory",
                "registry_id": "agent_loop_memory",
                "registry_version": "v0.2",
                "requested_action_summary": {"action_type": "write_memory"},
            },
        )
        self._append(
            run_id,
            "action.decided",
            {
                "decision_id": decision_id,
                "proposal_id": proposal_id,
                "outcome": "approved",
                "grants": deepcopy(grants),
                "reason_codes": [],
                "policy_profile_id": self.policy.policy_profile_id,
                "policy_version": self.policy.policy_version,
                "policy_basis": {
                    "policy_profile_id": self.policy.policy_profile_id,
                    "policy_version": self.policy.policy_version,
                    "mode": "agent_loop_turn_memory",
                },
            },
        )
        self._append(
            run_id,
            "action.started",
            {
                "execution_id": execution_id,
                "proposal_id": proposal_id,
                "decision_id": decision_id,
            },
        )
        completed = self._append(
            run_id,
            "action.completed",
            {
                "execution_id": execution_id,
                "status": "completed",
                "artifact_refs": [],
            },
        )
        record = MemoryRecord(
            memory_id=new_id("mem"),
            scope=scope,
            content=deepcopy(content),
            summary=summary,
            source_refs=[dict(ref) for ref in source_refs],
            provenance={
                "run_id": run_id,
                "execution_id": execution_id,
                "action_type": "write_memory",
            },
            created_at="2026-04-27T00:00:00Z",
            supersedes=[str(record_id) for record_id in supersedes],
            quality=quality,
        )
        memory_event = self._build_event(
            run_id,
            "memory.record_created",
            {
                "record_id": record.memory_id,
                "execution_id": execution_id,
                "summary": record.summary,
                "source_refs": [dict(ref) for ref in record.source_refs],
                "provenance": dict(record.provenance),
                "basis_event_id": completed.event_id,
                "quality": record.quality,
            },
        )
        self._project_with_candidate(run_id, memory_event)
        execution = ActionExecution(
            execution_id=execution_id,
            proposal_id=proposal_id,
            decision_id=decision_id,
            action_type="write_memory",
            status="completed",
            effective_grants_snapshot=deepcopy(grants),
        )
        self.memory_store.save_record(record, execution=execution, grants=grants)
        appended = self.event_store.append(memory_event)
        return {
            "step_status": "completed",
            "status": "completed",
            "record_id": record.memory_id,
            "execution_id": execution_id,
            "basis_event_id": appended.event_id,
            "summary": record.summary,
            "scope": record.scope,
            "source_refs": [dict(ref) for ref in record.source_refs],
            "provenance": dict(record.provenance),
            "quality": record.quality,
        }

    def query_agent_loop_memory(self, run_id: str, request: dict[str, Any]) -> dict[str, Any]:
        self._validate_known_run_id(run_id)
        query = self._dict_string(request, "query")
        scope = request.get("scope")
        if scope is not None and scope not in {"thread", "run", "session"}:
            raise ValueError("memory query scope must be thread, run, or session")
        result = self.memory_query_service.query(
            run_id=run_id,
            query=query,
            scope=scope,
            grants={"memory": {"query": True}},
            caller_context={"run_id": run_id, "surface": "agent_loop"},
        )
        return {"step_status": "completed", **result}

    def run_agent_loop_planner_step(self, run_id: str, planner_output: dict[str, Any]) -> dict[str, Any]:
        return run_agent_loop_planner_step(self, run_id, planner_output)

    def run_agent_loop_real_planner_contract_step(
        self,
        run_id: str,
        provider_result: dict[str, Any],
    ) -> dict[str, Any]:
        return run_agent_loop_real_planner_contract_step(self, run_id, provider_result)

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

    def create_workspace_lease(
        self,
        run_id: str,
        decision: PolicyDecision,
        *,
        created_by: dict[str, Any],
        bound_to: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._validate_existing_run_id(run_id)
        if not isinstance(decision, PolicyDecision):
            raise TypeError("decision must be a PolicyDecision")
        if not isinstance(created_by, dict) or not any(
            isinstance(created_by.get(field), str) and created_by[field]
            for field in ("proposal_id", "execution_id")
        ):
            raise ValueError("created_by must include proposal_id or execution_id")
        if bound_to is None:
            bound_to = {"agent_id": self._runs[run_id]["agent_id"]}
        if not isinstance(bound_to, dict) or not any(
            isinstance(bound_to.get(field), str) and bound_to[field]
            for field in ("agent_id", "execution_id", "worker_id")
        ):
            raise ValueError("bound_to must include agent_id, execution_id, or worker_id")

        binding = self.workspace_manager.get_binding(decision.grants)
        workspace_grant = decision.grants["workspace"]
        event = self._build_event(
            run_id,
            "workspace.lease_created",
            {
                "workspace_id": binding.workspace_id,
                "run_id": run_id,
                "mode": binding.mode,
                "lease_status": "created",
                "bound_to": dict(bound_to),
                "granted_by": {"decision_id": decision.decision_id},
                "created_by": dict(created_by),
                "provenance": {
                    "decision_id": decision.decision_id,
                    "grant_basis": {"workspace": dict(workspace_grant)},
                },
            },
        )
        self._project_with_candidate(run_id, event)
        appended = self.event_store.append(event)
        workspace_entry = self.get_run_state(run_id).workspaces.get(binding.workspace_id)
        if workspace_entry is None:
            raise RuntimeError(f"workspace lease was not projected from {appended.event_id}")
        return deepcopy(workspace_entry)

    def capture_workspace_artifact(
        self,
        run_id: str,
        *,
        workspace_id: str,
        artifact_ref: ResourceRef,
        captured_by: dict[str, Any],
    ) -> dict[str, Any]:
        self._validate_existing_run_id(run_id)
        self._validate_non_empty_string("workspace_id", workspace_id)
        if not isinstance(artifact_ref, ResourceRef):
            raise TypeError("artifact_ref must be a structured ResourceRef")
        if artifact_ref.run_id != run_id:
            raise ValueError("artifact_ref run_id must match run_id")
        if not isinstance(captured_by, dict) or not any(
            isinstance(captured_by.get(field), str) and captured_by[field]
            for field in ("execution_id", "agent_id", "worker_id")
        ):
            raise ValueError("captured_by must include execution_id, agent_id, or worker_id")

        artifact_record = self.get_artifact_record(artifact_ref)
        event = self._build_event(
            run_id,
            "workspace.artifact_captured",
            {
                "workspace_id": workspace_id,
                "run_id": run_id,
                "artifact_ref": artifact_ref.to_dict(),
                "captured_by": dict(captured_by),
                "provenance": {
                    "artifact_event_id": artifact_record["basis_event_id"],
                    "basis_event_id": artifact_record["basis_event_id"],
                    "decision_id": artifact_record["provenance"].get("decision_id"),
                },
            },
        )
        self._project_with_candidate(run_id, event)
        appended = self.event_store.append(event)
        workspace_entry = self.get_run_state(run_id).workspaces.get(workspace_id)
        if workspace_entry is None:
            raise RuntimeError(f"workspace capture was not projected from {appended.event_id}")
        return {
            "status": "captured",
            "workspace_id": workspace_id,
            "artifact_ref": artifact_ref.to_dict(),
            "basis_event_id": appended.event_id,
            "workspace": deepcopy(workspace_entry),
            "private_append_required": False,
        }

    def release_workspace(
        self,
        run_id: str,
        *,
        workspace_id: str,
        released_by: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        self._validate_existing_run_id(run_id)
        self._validate_non_empty_string("workspace_id", workspace_id)
        self._validate_non_empty_string("reason", reason)
        if not isinstance(released_by, dict) or not any(
            isinstance(released_by.get(field), str) and released_by[field]
            for field in ("agent_id", "execution_id", "worker_id", "system")
        ):
            raise ValueError("released_by must identify a release actor")
        state = self.get_run_state(run_id)
        workspace_entry = state.workspaces.get(workspace_id)
        if workspace_entry is None:
            raise ValueError("unknown workspace")

        event = self._build_event(
            run_id,
            "workspace.released",
            {
                "workspace_id": workspace_id,
                "run_id": run_id,
                "lease_status": "released",
                "released_by": dict(released_by),
                "released_at": "2026-04-27T00:00:00Z",
                "reason": reason,
                "basis_event_id": workspace_entry["last_event_id"],
            },
        )
        self._project_with_candidate(run_id, event)
        appended = self.event_store.append(event)
        released_workspace = self.get_run_state(run_id).workspaces.get(workspace_id)
        if released_workspace is None:
            raise RuntimeError(f"workspace release was not projected from {appended.event_id}")
        return {
            "status": "released",
            "workspace_id": workspace_id,
            "basis_event_id": appended.event_id,
            "workspace": deepcopy(released_workspace),
            "private_append_required": False,
        }

    def create_source_artifact(
        self,
        run_id: str,
        *,
        summary: str,
        content: str,
        artifact_type: str = "text",
        basis_refs: list[ResourceRef] | None = None,
        source_refs: list[ResourceRef] | None = None,
    ) -> dict[str, Any]:
        run = self._runtime_context_for_write_helper(run_id)
        self._validate_non_empty_string("summary", summary)
        self._validate_non_empty_string("content", content)
        if artifact_type != "text":
            raise ValueError("artifact_type must be text")
        basis_ref_payloads = self._validate_artifact_ref_list("basis_refs", basis_refs, run_id)
        source_ref_payloads = self._validate_artifact_ref_list("source_refs", source_refs, run_id)

        proposal = self.compiler.compile(
            {
                "action": "call_tool",
                "tool": "write_artifact_tool",
                "text": content,
                "summary": summary,
            },
            {
                "run_id": run_id,
                "agent_id": run["agent_id"],
                "thread_id": run["thread_id"],
            },
        )
        if basis_ref_payloads:
            proposal.payload["basis_refs"] = basis_ref_payloads
        if source_ref_payloads:
            proposal.payload["source_refs"] = source_ref_payloads
        self._append(
            run_id,
            "action.proposed",
            {
                "proposal_id": proposal.proposal_id,
                "agent_id": proposal.agent_id,
                "thread_id": proposal.thread_id,
                "action_type": proposal.action_type,
                "registry_id": proposal.registry_id,
                "registry_version": proposal.registry_version,
                "registry_basis": proposal.registry_basis,
            },
        )

        decision = self.policy.decide(proposal)
        self._append(
            run_id,
            "action.decided",
            {
                "decision_id": decision.decision_id,
                "proposal_id": decision.proposal_id,
                "outcome": decision.outcome,
                "reason_codes": list(decision.reason_codes),
                "policy_profile_id": decision.policy_profile_id,
                "policy_version": decision.policy_version,
                "policy_basis": decision.policy_basis,
            },
        )
        if decision.outcome == "denied":
            raise PermissionError("source artifact setup denied by policy")

        execution = self.executor.execute(decision, proposal)
        artifact_ref = self._completed_artifact_ref(run_id, execution.execution_id)
        if artifact_ref is None:
            raise RuntimeError("source artifact setup completed without artifact ref")
        artifact_metadata = self.artifact_store.get_metadata(artifact_ref, include_provenance=True)
        state = self.get_run_state(run_id)
        return {
            "status": execution.status,
            "proposal_id": proposal.proposal_id,
            "decision_id": decision.decision_id,
            "execution_id": execution.execution_id,
            "artifact_ref": artifact_ref,
            "artifact_summary": artifact_metadata["summary"],
            "artifact_type": artifact_metadata["artifact_type"],
            "provenance": dict(artifact_metadata["provenance"]),
            "basis_refs": [dict(ref) for ref in artifact_metadata.get("basis_refs", [])],
            "source_refs": [dict(ref) for ref in artifact_metadata.get("source_refs", [])],
            "run_state": state,
        }

    def get_artifact_record(self, ref: ResourceRef) -> dict[str, Any]:
        if not isinstance(ref, ResourceRef):
            raise TypeError("artifact record requires a structured ResourceRef")
        if ref.ref_type != "artifact":
            raise ValueError("artifact record requires an artifact ResourceRef")

        metadata = self.artifact_store.get_metadata(ref, include_provenance=True)
        basis_event = self._find_artifact_created_event(ref)
        if basis_event is None:
            raise ValueError("artifact.created event not found")
        record = {
            "artifact_id": ref.artifact_id,
            "artifact_type": metadata["artifact_type"],
            "summary": metadata["summary"],
            "ref": ref.to_dict(),
            "provenance": dict(metadata["provenance"]),
            "basis_event_id": basis_event.event_id,
            "basis_event_type": basis_event.event_type,
            "basis_created_at": basis_event.created_at,
        }
        artifact_payload = basis_event.payload["artifact"]
        for field_name in ("basis_refs", "source_refs"):
            refs = artifact_payload.get(field_name, metadata.get(field_name, []))
            if refs:
                record[field_name] = [dict(item) for item in refs]
        return record

    def submit_worker_handoff(
        self,
        run_id: str,
        *,
        delegation_intent: dict[str, Any],
        artifact_ref: ResourceRef,
        summary: str,
    ) -> dict[str, Any]:
        self._runtime_context_for_write_helper(run_id)
        intent = self._validate_worker_handoff_intent(delegation_intent)
        self._validate_non_empty_string("summary", summary)
        try:
            artifact_record = self.get_artifact_record(artifact_ref)
        except FileNotFoundError as exc:
            artifact_id = getattr(artifact_ref, "artifact_id", None)
            artifact_run_id = getattr(artifact_ref, "run_id", None)
            raise IsotopeError(
                "unknown artifact ResourceRef",
                code="worker_handoff_unknown_artifact",
                category="not_found",
                retryable=False,
                http_status=404,
                details={"run_id": artifact_run_id, "artifact_id": artifact_id},
            ) from exc
        if artifact_ref.run_id != run_id:
            raise IsotopeError(
                "artifact_ref run_id must match run_id",
                code="worker_handoff_invalid_artifact_ref",
                category="validation",
                retryable=False,
                http_status=400,
                details={"run_id": run_id, "artifact_run_id": artifact_ref.run_id},
            )

        delegation_id = new_id("deleg")
        decision_id = new_id("dec")
        grants, outcome, reason_codes = self._derive_worker_handoff_grants(intent["requested_capabilities"])
        decision_events = [
            self._build_event(
                run_id,
                "delegation.proposed",
                {
                    "delegation_id": delegation_id,
                    "run_id": run_id,
                    "parent_agent_id": intent["parent_agent_id"],
                    "requested_worker_role": intent["requested_worker_role"],
                    "requested_capabilities": deepcopy(intent["requested_capabilities"]),
                },
            ),
            self._build_event(
                run_id,
                "delegation.decided",
                {
                    "delegation_id": delegation_id,
                    "decision_id": decision_id,
                    "outcome": outcome,
                    "grants": deepcopy(grants),
                    "reason_codes": reason_codes,
                    "policy_profile_id": self.policy.policy_profile_id,
                    "policy_version": self.policy.policy_version,
                    "policy_basis": {
                        "policy_profile_id": self.policy.policy_profile_id,
                        "policy_version": self.policy.policy_version,
                    },
                },
            ),
        ]
        if outcome == "denied":
            existing_events = self.event_store.list_events(run_id)
            RunProjector().project([*existing_events, *decision_events])
            for event in decision_events:
                self.event_store.append(event)
            raise IsotopePermissionError(
                "worker handoff denied by policy",
                code="worker_handoff_denied",
                category="policy",
                retryable=False,
                http_status=403,
                details={"reason_codes": list(reason_codes)},
            )

        worker_id = new_id("worker")
        agent_id = new_id("agent_worker")
        candidate_events = [
            *decision_events,
            self._build_event(
                run_id,
                "worker.created",
                {
                    "worker_id": worker_id,
                    "agent_id": agent_id,
                    "run_id": run_id,
                    "parent_agent_id": intent["parent_agent_id"],
                    "delegation_id": delegation_id,
                    "decision_id": decision_id,
                    "role": intent["requested_worker_role"],
                    "status": "created",
                    "workspace": dict(grants["workspace"]),
                },
            ),
            self._build_event(
                run_id,
                "worker.started",
                {
                    "worker_id": worker_id,
                    "delegation_id": delegation_id,
                    "status": "running",
                },
            ),
            self._build_event(
                run_id,
                "worker.result_handed_off",
                {
                    "worker_id": worker_id,
                    "delegation_id": delegation_id,
                    "artifact_ref": artifact_ref.to_dict(),
                    "summary": summary,
                    "provenance": {
                        "artifact_basis_event_id": artifact_record["basis_event_id"],
                    },
                },
            ),
            self._build_event(
                run_id,
                "worker.completed",
                {
                    "worker_id": worker_id,
                    "delegation_id": delegation_id,
                    "status": "completed",
                },
            ),
        ]

        existing_events = self.event_store.list_events(run_id)
        projected = RunProjector().project([*existing_events, *candidate_events])
        worker_summary = projected.workers.get(worker_id)
        if worker_summary is None:
            raise ValueError("worker handoff did not project worker summary")
        for event in candidate_events:
            self.event_store.append(event)

        return {
            "status": worker_summary["status"],
            "delegation_id": delegation_id,
            "decision_id": decision_id,
            "worker_id": worker_id,
            "result_ref": artifact_ref.to_dict(),
            "worker_summary": deepcopy(worker_summary),
            "basis_event_ids": [event.event_id for event in candidate_events],
            "private_append_required": False,
        }

    def import_external_snapshot(self, run_id: str, snapshot: ImportedSnapshot) -> dict[str, Any]:
        self._validate_existing_run_id(run_id)
        if not isinstance(snapshot, ImportedSnapshot):
            raise TypeError("external snapshot import requires an ImportedSnapshot")

        payload = self._payload_from_imported_snapshot(run_id, snapshot)
        event = CanonicalEvent(
            event_id=new_id("evt"),
            run_id=run_id,
            event_type="snapshot.imported",
            payload=payload,
            created_at="2026-04-27T00:00:00Z",
        )

        # Validate the candidate against the full replay path before append so
        # malformed snapshots cannot leave partial event-log state.
        existing_events = self.event_store.list_events(run_id)
        RunProjector().project([*existing_events, event])
        appended = self.event_store.append(event)
        state = self.get_run_state(run_id)
        observation = self._find_external_observation(state, snapshot.snapshot_id)
        if observation is None:
            raise ValueError("snapshot.imported did not project an external observation")
        return {
            "status": observation["status"],
            "run_id": run_id,
            "snapshot_id": snapshot.snapshot_id,
            "event_type": appended.event_type,
            "basis_event_id": appended.event_id,
            "external_observation": dict(observation),
        }

    def get_events(self, run_id: str) -> list[CanonicalEvent]:
        self._validate_read_run_id(run_id)
        return self.event_store.list_events(run_id)

    def get_artifact_summary(self, ref, grants: dict) -> dict:
        return self.retrieval.get_artifact_summary(ref, grants)

    def ingest_external_input(self, raw_input: dict) -> dict[str, str]:
        return not_enabled_result("external_ingestion")

    def save_checkpoint_for_run(self, run_id: str) -> dict[str, str]:
        self._validate_read_run_id(run_id)
        if self.checkpoint_store is None:
            return not_enabled_result("checkpoint")
        checkpoint = RunProjector().save_checkpoint(run_id, self.event_store, self.checkpoint_store)
        return {
            "status": "saved",
            "run_id": run_id,
            "basis_event_id": checkpoint["basis_event_id"],
        }

    def save_checkpoint_history_for_run(self, run_id: str) -> dict[str, str]:
        self._validate_read_run_id(run_id)
        if self.checkpoint_store is None:
            return not_enabled_result("checkpoint_history")
        checkpoint = RunProjector().save_checkpoint_history(run_id, self.event_store, self.checkpoint_store)
        return {
            "status": "saved",
            "run_id": run_id,
            "basis_event_id": checkpoint["basis_event_id"],
            "checkpoint_kind": "history",
        }

    def create_checkpoint(self, run_id: str) -> dict[str, str]:
        return not_enabled_result("checkpoint")

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

    def _validate_worker_handoff_intent(self, intent: object) -> dict[str, Any]:
        if not isinstance(intent, dict) or not intent:
            raise IsotopeError(
                "delegation intent must be a non-empty dict",
                code="worker_handoff_invalid_intent",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "delegation_intent"},
            )
        if "decision" in intent or "grants" in intent or "effective_grants" in intent:
            raise IsotopeError(
                "delegation intent cannot include forged decision or grants",
                code="worker_handoff_forged_grants",
                category="policy",
                retryable=False,
                http_status=403,
                details={"field": "delegation_intent"},
            )
        parent_agent_id = intent.get("parent_agent_id")
        requested_worker_role = intent.get("requested_worker_role")
        requested_capabilities = intent.get("requested_capabilities")
        self._validate_non_empty_string("parent_agent_id", parent_agent_id)
        self._validate_non_empty_string("requested_worker_role", requested_worker_role)
        if requested_worker_role != "worker":
            raise ValueError("requested_worker_role must be worker")
        if not isinstance(requested_capabilities, dict):
            raise ValueError("delegation intent requested_capabilities must be a dict")
        requested_tools = requested_capabilities.get("tools", [])
        if not isinstance(requested_tools, list):
            raise ValueError("delegation intent tools must be a list")
        requested_workspace = requested_capabilities.get("workspace", {})
        if not isinstance(requested_workspace, dict):
            raise ValueError("delegation intent workspace must be a dict")
        requested_budget = requested_capabilities.get("budget", {})
        if not isinstance(requested_budget, dict):
            raise ValueError("delegation intent budget must be a dict")
        try:
            budget_seconds = int(requested_budget.get("seconds", 30))
        except (TypeError, ValueError) as exc:
            raise ValueError("delegation intent budget.seconds must be int-like") from exc
        if budget_seconds < 0:
            raise ValueError("delegation intent budget.seconds must be non-negative")
        return {
            "parent_agent_id": parent_agent_id,
            "requested_worker_role": requested_worker_role,
            "requested_capabilities": {
                "tools": list(requested_tools),
                "workspace": dict(requested_workspace),
                "budget": {"seconds": budget_seconds},
            },
        }

    def _derive_worker_handoff_grants(self, requested_capabilities: dict[str, Any]) -> tuple[dict[str, Any], str, list[str]]:
        requested_tools = requested_capabilities["tools"]
        if "write_artifact_tool" not in requested_tools:
            return (
                {"tools": [], "workspace": {"mode": "none"}, "budget": {"seconds": 0}},
                "denied",
                ["tool_not_requested"],
            )

        requested_workspace = requested_capabilities["workspace"]
        requested_budget = requested_capabilities["budget"]
        budget_seconds = int(requested_budget["seconds"])
        grants = {
            "tools": ["write_artifact_tool"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": min(budget_seconds, 30)},
        }
        requested_matches = (
            requested_tools == grants["tools"]
            and requested_workspace.get("mode", "shared_ro") == "shared_ro"
            and budget_seconds <= 30
        )
        return grants, "approved" if requested_matches else "modified", [] if requested_matches else ["capabilities_reduced"]

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

    def _find_artifact_created_event(self, ref: ResourceRef) -> CanonicalEvent | None:
        expected_ref = ref.to_dict()
        for event in self.event_store.list_events(ref.run_id):
            if event.event_type != "artifact.created":
                continue
            artifact = event.payload.get("artifact")
            if not isinstance(artifact, dict):
                raise ValueError("malformed artifact.created event")
            if artifact.get("ref") == expected_ref:
                return event
        return None

    def _validate_artifact_ref_list(
        self,
        field_name: str,
        refs: list[ResourceRef] | None,
        run_id: str,
    ) -> list[dict[str, str]]:
        if refs is None:
            return []
        if not isinstance(refs, list):
            raise TypeError(f"{field_name} must be a list of structured ResourceRef")
        if not refs:
            raise ValueError(f"{field_name} must be a non-empty list when provided")
        payloads: list[dict[str, str]] = []
        for index, ref in enumerate(refs):
            if not isinstance(ref, ResourceRef):
                raise TypeError(f"{field_name}[{index}] must be a structured ResourceRef")
            if ref.ref_type != "artifact":
                raise ValueError(f"{field_name}[{index}] must be an artifact ResourceRef")
            if ref.run_id != run_id:
                raise ValueError(f"{field_name}[{index}] run_id must match run_id")
            self.get_artifact_record(ref)
            payloads.append(ref.to_dict())
        return payloads

    def _payload_from_imported_snapshot(self, run_id: str, snapshot: ImportedSnapshot) -> dict[str, Any]:
        self._validate_snapshot_ref_run_id(snapshot.source_ref.to_dict(), run_id, "source_ref")
        provenance = dict(snapshot.provenance)
        self._validate_snapshot_ref_run_id(provenance["raw_artifact_ref"], run_id, "provenance.raw_artifact_ref")
        basis_refs = [dict(ref) for ref in snapshot.basis_refs]
        for index, ref in enumerate(basis_refs):
            self._validate_snapshot_ref_run_id(ref, run_id, f"basis_refs[{index}]")

        observation = dict(snapshot.observation)
        subject = observation.get("subject")
        if subject is not None and subject != {"type": "run", "id": run_id}:
            raise ValueError("snapshot observation.subject must match target run")

        return {
            "snapshot_id": snapshot.snapshot_id,
            "source_system": snapshot.source_system,
            "captured_at": snapshot.captured_at,
            "content_type": snapshot.content_type,
            "source_ref": snapshot.source_ref.to_dict(),
            "summary": snapshot.summary,
            "observation": observation,
            "quality": dict(snapshot.quality),
            "provenance": provenance,
            "basis_refs": basis_refs,
        }

    def _validate_snapshot_ref_run_id(self, ref: dict[str, Any], run_id: str, label: str) -> None:
        ref_run_id = ref.get("run_id")
        if ref_run_id != run_id:
            raise ValueError(f"snapshot {label}.run_id must match target run_id")

    def _find_external_observation(self, state, snapshot_id: str) -> dict[str, Any] | None:
        for observation in state.external_observations:
            if observation.get("snapshot_id") == snapshot_id:
                return observation
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
