"""RunState projector boundary for the Isotope v0.1 slice."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from .events import EVENT_ENVELOPE_VERSION, CanonicalEvent


@dataclass
class RunState:
    """In-memory read model for the v0.1 slice, not a source of truth."""

    run_id: str = ""
    status: str = "unknown"
    current_agent: str = ""
    agents: dict[str, dict[str, Any]] = field(default_factory=dict)
    workers: dict[str, dict[str, Any]] = field(default_factory=dict)
    workspaces: dict[str, dict[str, Any]] = field(default_factory=dict)
    actions: dict[str, dict[str, Any]] = field(default_factory=dict)
    action_retries: dict[str, dict[str, Any]] = field(default_factory=dict)
    action_cancellations: dict[str, dict[str, Any]] = field(default_factory=dict)
    action_supersessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    approvals: dict[str, dict[str, Any]] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    memory_records: list[dict[str, Any]] = field(default_factory=list)
    external_observations: list[dict[str, Any]] = field(default_factory=list)
    last_event_id: str = ""


class RunProjector:
    """Project RunState only from canonical events."""

    EXECUTABLE_DECISION_OUTCOMES = {"approved", "modified"}
    KNOWN_DECISION_OUTCOMES = {"approved", "modified", "denied", "pending_user_approval"}
    KNOWN_RUN_STATUSES = {"unknown", "running", "pending_user_approval", "denied", "failed", "completed"}
    CHECKPOINT_STATE_FIELDS = (
        "run_id",
        "status",
        "current_agent",
        "agents",
        "workers",
        "workspaces",
        "actions",
        "action_retries",
        "action_cancellations",
        "action_supersessions",
        "approvals",
        "artifacts",
        "memory_records",
        "external_observations",
        "last_event_id",
    )
    CHECKPOINT_REQUIRED_STATE_FIELDS = ("run_id", "status", "current_agent", "actions", "artifacts", "last_event_id")
    CHECKPOINT_ARTIFACT_FIELDS = ("ref", "artifact_type", "summary", "provenance")
    CHECKPOINT_MEMORY_RECORD_FIELDS = ("record_id", "summary", "source_refs", "provenance")
    CHECKPOINT_MEMORY_RECORD_FORBIDDEN_FIELDS = ("content", "full_content", "artifact_content", "raw_content")
    CHECKPOINT_EXTERNAL_OBSERVATION_FORBIDDEN_FIELDS = (
        "content",
        "full_content",
        "artifact_content",
        "raw_content",
    )
    CHECKPOINT_EXTERNAL_OBSERVATION_FIELDS = (
        "snapshot_id",
        "snapshot_type",
        "source_system",
        "captured_at",
        "source_ref",
        "summary",
        "observation",
        "quality",
        "provenance",
        "basis_refs",
        "status",
        "conflict_status",
    )
    CHECKPOINT_MEMORY_RECORD_ALLOWED_FIELDS = {
        "record_id",
        "execution_id",
        "summary",
        "source_refs",
        "provenance",
        "basis_event_id",
        "quality",
        "status",
        "superseded_by",
        "superseded_event_id",
        "superseded_reason",
    }
    PROJECTOR_VERSION = "run_projector@v1"

    def __init__(self) -> None:
        self._proposal_outcomes: dict[str, str] = {}
        self._proposal_action_types: dict[str, str] = {}
        self._proposal_reason_codes: dict[str, list[str]] = {}
        self._proposal_summaries: dict[str, dict[str, Any]] = {}
        self._proposal_agents: dict[str, str] = {}
        self._proposal_grants: dict[str, dict[str, Any]] = {}
        self._execution_statuses: dict[str, str] = {}
        self._execution_action_types: dict[str, str] = {}
        self._execution_proposals: dict[str, str] = {}
        self._proposal_execution_ids: dict[str, str] = {}
        self._proposal_start_event_ids: dict[str, str] = {}
        self._retry_requests: dict[str, dict[str, Any]] = {}
        self._cancel_requests: dict[str, dict[str, Any]] = {}
        self._approval_proposals: dict[str, str] = {}
        self._approval_resolutions: set[str] = set()
        self._delegation_proposals: dict[str, dict[str, Any]] = {}
        self._delegation_decisions: dict[str, dict[str, Any]] = {}
        self._workers: dict[str, dict[str, Any]] = {}
        self._worker_agent_ids: set[str] = set()
        self._memory_record_ids: set[str] = set()
        self._run_completed = False

    def _validate_lifecycle(self, event: CanonicalEvent) -> None:
        payload = event.payload
        self._validate_event_payload(event)
        if self._run_completed and event.event_type in {
            "action.decided",
            "action.started",
            "action.failed",
            "action.completed",
            "action.retry_requested",
            "action.retry_created",
            "action.cancel_requested",
            "action.cancelled",
            "action.superseded",
            "artifact.created",
            "memory.record_created",
            "memory.record_superseded",
            "workspace.bound",
        }:
            raise ValueError("event after run.completed")

        if event.event_type == "action.proposed":
            proposal_id = payload.get("proposal_id")
            action_type = payload.get("action_type")
            if isinstance(proposal_id, str) and isinstance(action_type, str):
                self._proposal_action_types[proposal_id] = action_type
                self._proposal_summaries[proposal_id] = {"action_type": action_type}
                agent_id = payload.get("agent_id")
                if isinstance(agent_id, str) and agent_id:
                    self._proposal_agents[proposal_id] = agent_id
        elif event.event_type == "action.decided":
            proposal_id = str(payload["proposal_id"])
            self._proposal_outcomes[proposal_id] = str(payload["outcome"])
            reason_codes = payload.get("reason_codes", [])
            self._proposal_reason_codes[proposal_id] = list(reason_codes) if isinstance(reason_codes, list) else []
            grants = payload.get("grants")
            if isinstance(grants, dict):
                self._proposal_grants[proposal_id] = dict(grants)
        elif event.event_type == "action.started":
            proposal_id = str(payload["proposal_id"])
            outcome = self._proposal_outcomes.get(proposal_id)
            if outcome == "denied":
                raise ValueError("action.started after denied decision")
            if outcome == "pending_user_approval":
                raise ValueError("action.started after pending approval")
            if outcome not in self.EXECUTABLE_DECISION_OUTCOMES:
                raise ValueError("action.started before approved decision")
            agent_id = self._proposal_agents.get(proposal_id, "")
            if agent_id in self._worker_agent_ids and proposal_id not in self._proposal_grants:
                raise ValueError("worker action requires policy grants")
            self._execution_statuses[str(payload["execution_id"])] = "running"
            self._execution_action_types[str(payload["execution_id"])] = self._proposal_action_types.get(proposal_id, "")
            self._execution_proposals[str(payload["execution_id"])] = proposal_id
            self._proposal_execution_ids[proposal_id] = str(payload["execution_id"])
            self._proposal_start_event_ids[proposal_id] = event.event_id
        elif event.event_type == "delegation.proposed":
            self._delegation_proposals[str(payload["delegation_id"])] = dict(payload)
        elif event.event_type == "delegation.decided":
            delegation_id = str(payload["delegation_id"])
            if delegation_id not in self._delegation_proposals:
                raise ValueError("delegation.decided requires delegation.proposed")
            self._delegation_decisions[delegation_id] = dict(payload)
        elif event.event_type == "worker.created":
            delegation_id = str(payload["delegation_id"])
            if delegation_id not in self._delegation_proposals:
                raise ValueError("worker.created requires approved delegation via delegation.proposed")
            decision = self._delegation_decisions.get(delegation_id)
            if decision is None:
                raise ValueError("worker.created requires delegation.decided")
            outcome = decision.get("outcome")
            if outcome == "denied":
                raise ValueError("denied delegation cannot create worker")
            if outcome not in self.EXECUTABLE_DECISION_OUTCOMES:
                raise ValueError("worker.created requires approved delegation")
            if payload.get("decision_id") != decision.get("decision_id"):
                raise ValueError("worker.created decision_id must match delegation.decided")
            worker_id = str(payload["worker_id"])
            self._workers[worker_id] = dict(payload)
            self._worker_agent_ids.add(str(payload["agent_id"]))
        elif event.event_type in {"worker.started", "worker.completed", "worker.failed", "worker.cancelled"}:
            self._validate_worker_lifecycle_transition(payload, event.event_type)
        elif event.event_type == "worker.result_handed_off":
            self._validate_worker_lifecycle_transition(payload, event.event_type)
        elif event.event_type == "workspace.bound":
            self._validate_workspace_bound_lifecycle(payload, event)
        elif event.event_type == "action.completed":
            execution_id = str(payload["execution_id"])
            status = self._execution_statuses.get(execution_id)
            if status is None:
                raise ValueError("action.completed before action.started")
            if status == "failed":
                raise ValueError("terminal execution already failed")
            if status == "cancelled":
                raise ValueError("action.completed after action.cancelled")
            if status == "superseded":
                raise ValueError("action.completed after action.superseded")
            self._execution_statuses[execution_id] = "completed"
        elif event.event_type == "action.failed":
            execution_id = str(payload["execution_id"])
            status = self._execution_statuses.get(execution_id)
            if status == "completed":
                raise ValueError("terminal execution already completed")
            self._execution_statuses[execution_id] = "failed"
        elif event.event_type == "action.retry_requested":
            original_execution_id = str(payload["original_execution_id"])
            if self._execution_statuses.get(original_execution_id) != "failed":
                raise ValueError("action.retry_requested requires failed execution")
            if self._execution_proposals.get(original_execution_id) != payload["original_proposal_id"]:
                raise ValueError("action.retry_requested original_proposal_id must match original execution")
            retry_request = dict(payload)
            retry_request["_request_event_id"] = event.event_id
            self._retry_requests[str(payload["retry_id"])] = retry_request
        elif event.event_type == "action.retry_created":
            retry_id = str(payload["retry_id"])
            retry_request = self._retry_requests.get(retry_id)
            if retry_request is None:
                raise ValueError("action.retry_created requires action.retry_requested")
            if payload["original_proposal_id"] != retry_request["original_proposal_id"]:
                raise ValueError("action.retry_created original_proposal_id must match retry request")
            if payload["basis_event_id"] != retry_request["_request_event_id"]:
                raise ValueError("action.retry_created basis_event_id must match action.retry_requested")
            if payload["new_proposal_id"] == payload["original_proposal_id"]:
                raise ValueError("action.retry_created new_proposal_id must differ from original_proposal_id")
        elif event.event_type == "action.cancel_requested":
            execution_id = str(payload["execution_id"])
            status = self._execution_statuses.get(execution_id)
            if status in {"completed", "failed", "cancelled", "superseded"}:
                raise ValueError("action.cancel_requested after terminal action state")
            if status != "running":
                raise ValueError("action.cancel_requested requires running action")
            if self._execution_proposals.get(execution_id) != payload["proposal_id"]:
                raise ValueError("action.cancel_requested proposal_id must match execution proposal")
            cancel_request = dict(payload)
            cancel_request["_request_event_id"] = event.event_id
            self._cancel_requests[str(payload["cancel_id"])] = cancel_request
        elif event.event_type == "action.cancelled":
            cancel_request = self._cancel_requests.get(str(payload["cancel_id"]))
            if cancel_request is None:
                raise ValueError("action.cancelled requires action.cancel_requested")
            if payload["basis_event_id"] != cancel_request["_request_event_id"]:
                raise ValueError("action.cancelled basis_event_id must match action.cancel_requested")
            if payload["proposal_id"] != cancel_request["proposal_id"]:
                raise ValueError("action.cancelled proposal_id must match action.cancel_requested")
            if payload["execution_id"] != cancel_request["execution_id"]:
                raise ValueError("action.cancelled execution_id must match action.cancel_requested")
            execution_id = str(payload["execution_id"])
            if self._execution_statuses.get(execution_id) != "running":
                raise ValueError("action.cancelled requires running action")
            self._execution_statuses[execution_id] = "cancelled"
        elif event.event_type == "action.superseded":
            old_proposal_id = str(payload["old_proposal_id"])
            if payload["new_proposal_id"] == payload["old_proposal_id"]:
                raise ValueError("action.superseded new_proposal_id must differ from old_proposal_id")
            if payload["basis_event_id"] != self._proposal_start_event_ids.get(old_proposal_id):
                raise ValueError("action.superseded basis_event_id must match old action start event")
            execution_id = self._proposal_execution_ids.get(old_proposal_id)
            if execution_id is None:
                raise ValueError("action.superseded requires started action")
            if self._execution_statuses.get(execution_id) != "running":
                raise ValueError("action.superseded requires running action")
            self._execution_statuses[execution_id] = "superseded"
        elif event.event_type == "approval.requested":
            self._approval_proposals[str(payload["approval_id"])] = str(payload["proposal_id"])
        elif event.event_type == "approval.resolved":
            approval_id = str(payload["approval_id"])
            proposal_id = str(payload["proposal_id"])
            if approval_id in self._approval_resolutions:
                raise ValueError("approval.resolved duplicate approval_id")
            if self._approval_proposals.get(approval_id) != proposal_id:
                raise ValueError("approval.resolved requires pending approval")
            if self._proposal_outcomes.get(proposal_id) != "pending_user_approval":
                raise ValueError("approval.resolved requires pending approval")
            resolution = str(payload["resolution"])
            if resolution == "approved":
                self._proposal_outcomes[proposal_id] = "approved"
            elif resolution == "denied":
                self._proposal_outcomes[proposal_id] = "denied"
            self._approval_resolutions.add(approval_id)
        elif event.event_type == "memory.record_created":
            self._validate_memory_record_lifecycle(payload)
            self._memory_record_ids.add(str(payload["record_id"]))
        elif event.event_type == "memory.record_superseded":
            self._validate_memory_record_superseded_lifecycle(payload)
        elif event.event_type == "run.completed":
            self._validate_run_completed()
            self._run_completed = True

    def _validate_worker_lifecycle_transition(self, payload: dict[str, Any], event_type: str) -> None:
        worker_id = str(payload["worker_id"])
        worker = self._workers.get(worker_id)
        if worker is None:
            raise ValueError(f"{event_type} requires worker.created")
        if payload.get("delegation_id") != worker.get("delegation_id"):
            raise ValueError(f"{event_type} delegation_id must match worker.created")

    def _validate_run_completed(self) -> None:
        statuses = set(self._execution_statuses.values())
        if "failed" in statuses:
            raise ValueError("run.completed after failed execution")
        if "running" in statuses:
            raise ValueError("run.completed while executions are still running")
        if "pending_user_approval" in set(self._proposal_outcomes.values()):
            raise ValueError("run.completed while approval is pending")
        if "completed" not in statuses:
            raise ValueError("run.completed requires a completed execution")

    def _validate_event_payload(self, event: CanonicalEvent) -> None:
        payload = event.payload
        if event.event_type == "agent.created":
            self._require_fields(event.event_type, payload, ("agent_id",))
        elif event.event_type == "action.decided":
            self._require_fields(event.event_type, payload, ("proposal_id", "decision_id", "outcome"))
            if payload["outcome"] not in self.KNOWN_DECISION_OUTCOMES:
                raise ValueError("action.decided has unknown outcome")
            grants = payload.get("grants")
            if grants is not None and not isinstance(grants, dict):
                raise ValueError("action.decided grants must be a dict")
        elif event.event_type == "action.started":
            self._require_fields(event.event_type, payload, ("execution_id", "proposal_id", "decision_id"))
        elif event.event_type == "action.completed":
            self._require_fields(event.event_type, payload, ("execution_id", "status", "artifact_refs"))
            if payload["status"] != "completed":
                raise ValueError("action.completed status must be completed")
            if not isinstance(payload["artifact_refs"], list):
                raise ValueError("action.completed artifact_refs must be a list")
        elif event.event_type == "action.failed":
            self._require_fields(event.event_type, payload, ("execution_id", "proposal_id", "decision_id", "status"))
            if payload["status"] != "failed":
                raise ValueError("action.failed status must be failed")
        elif event.event_type == "action.retry_requested":
            self._require_fields(
                event.event_type,
                payload,
                ("retry_id", "run_id", "original_proposal_id", "original_execution_id", "reason", "requested_by"),
            )
        elif event.event_type == "action.retry_created":
            self._require_fields(
                event.event_type,
                payload,
                ("retry_id", "new_proposal_id", "original_proposal_id", "basis_event_id", "policy_basis"),
            )
            if not isinstance(payload["policy_basis"], dict):
                raise ValueError("action.retry_created policy_basis must be a dict")
        elif event.event_type == "action.cancel_requested":
            self._require_fields(
                event.event_type,
                payload,
                ("cancel_id", "run_id", "proposal_id", "execution_id", "reason", "requested_by"),
            )
        elif event.event_type == "action.cancelled":
            self._require_fields(
                event.event_type,
                payload,
                ("cancel_id", "proposal_id", "execution_id", "status", "basis_event_id", "reason"),
            )
            if payload["status"] != "cancelled":
                raise ValueError("action.cancelled status must be cancelled")
        elif event.event_type == "action.superseded":
            self._require_fields(
                event.event_type,
                payload,
                ("supersession_id", "old_proposal_id", "new_proposal_id", "reason", "basis_event_id"),
            )
        elif event.event_type == "artifact.created":
            self._require_fields(event.event_type, payload, ("artifact",))
            artifact = payload["artifact"]
            if not isinstance(artifact, dict):
                raise ValueError("artifact.created artifact must be a dict")
            self._require_fields(
                "artifact.created artifact",
                artifact,
                ("ref", "artifact_type", "summary", "provenance"),
            )
            if "content" in artifact:
                raise ValueError("artifact.created artifact cannot contain content")
        elif event.event_type == "approval.requested":
            self._require_fields(
                event.event_type,
                payload,
                ("approval_id", "run_id", "proposal_id", "decision_id", "action_type"),
            )
        elif event.event_type == "approval.resolved":
            self._require_fields(
                event.event_type,
                payload,
                ("approval_id", "run_id", "proposal_id", "decision_id", "resolution", "reason", "resolver"),
            )
            if payload["resolution"] not in {"approved", "denied"}:
                raise ValueError("approval.resolved resolution must be approved or denied")
        elif event.event_type == "memory.record_created":
            self._validate_memory_record_created_payload(payload)
        elif event.event_type == "memory.record_superseded":
            self._validate_memory_record_superseded_payload(payload)
        elif event.event_type == "snapshot.imported":
            self._validate_snapshot_imported_payload(payload)
        elif event.event_type == "delegation.proposed":
            self._validate_delegation_proposed_payload(payload)
        elif event.event_type == "delegation.decided":
            self._validate_delegation_decided_payload(payload)
        elif event.event_type == "worker.created":
            self._validate_worker_created_payload(payload)
        elif event.event_type in {"worker.started", "worker.completed", "worker.failed", "worker.cancelled"}:
            self._validate_worker_status_payload(payload, event.event_type)
        elif event.event_type == "worker.result_handed_off":
            self._validate_worker_result_handoff_payload(payload)
        elif event.event_type == "workspace.bound":
            self._validate_workspace_bound_payload(payload, event)

    def _require_fields(self, label: str, payload: dict[str, Any], fields: tuple[str, ...]) -> None:
        for field in fields:
            if field not in payload:
                raise ValueError(f"{label} missing required field: {field}")

    def _validate_delegation_proposed_payload(self, payload: dict[str, Any]) -> None:
        self._require_fields(
            "delegation.proposed",
            payload,
            ("delegation_id", "run_id", "parent_agent_id", "requested_worker_role", "requested_capabilities"),
        )
        if not isinstance(payload["requested_capabilities"], dict):
            raise ValueError("delegation.proposed requested_capabilities must be a dict")

    def _validate_delegation_decided_payload(self, payload: dict[str, Any]) -> None:
        self._require_fields(
            "delegation.decided",
            payload,
            ("delegation_id", "decision_id", "outcome", "grants"),
        )
        if payload["outcome"] not in {"approved", "modified", "denied"}:
            raise ValueError("delegation.decided outcome must be approved, modified, or denied")
        if not isinstance(payload["grants"], dict):
            raise ValueError("delegation.decided grants must be a dict")

    def _validate_worker_created_payload(self, payload: dict[str, Any]) -> None:
        self._require_fields(
            "worker.created",
            payload,
            (
                "worker_id",
                "agent_id",
                "run_id",
                "parent_agent_id",
                "delegation_id",
                "decision_id",
                "role",
                "status",
                "workspace",
            ),
        )
        if payload["status"] != "created":
            raise ValueError("worker.created status must be created")
        if not isinstance(payload["workspace"], dict):
            raise ValueError("worker.created workspace must be a dict")

    def _validate_worker_status_payload(self, payload: dict[str, Any], event_type: str) -> None:
        self._require_fields(event_type, payload, ("worker_id", "delegation_id", "status"))
        expected_status = {
            "worker.started": "running",
            "worker.completed": "completed",
            "worker.failed": "failed",
            "worker.cancelled": "cancelled",
        }[event_type]
        if payload["status"] != expected_status:
            raise ValueError(f"{event_type} status must be {expected_status}")
        if event_type == "worker.failed" and "error" not in payload:
            raise ValueError("worker.failed missing required field: error")
        if event_type == "worker.cancelled" and "reason" not in payload:
            raise ValueError("worker.cancelled missing required field: reason")

    def _validate_worker_result_handoff_payload(self, payload: dict[str, Any]) -> None:
        self._require_fields(
            "worker.result_handed_off",
            payload,
            ("worker_id", "delegation_id", "artifact_ref", "summary"),
        )
        self._validate_resource_ref_payload(payload["artifact_ref"], "worker.result_handed_off artifact_ref")

    def _validate_workspace_bound_payload(self, payload: dict[str, Any], event: CanonicalEvent) -> None:
        self._require_fields(
            "workspace.bound",
            payload,
            ("workspace_id", "run_id", "mode", "bound_to", "lease_status", "provenance"),
        )
        for field_name in ("workspace_id", "run_id", "mode", "lease_status"):
            value = payload[field_name]
            if not isinstance(value, str) or not value:
                raise ValueError(f"workspace.bound {field_name} must be a non-empty string")
        if payload["run_id"] != event.run_id:
            raise ValueError("workspace.bound run_id must match event run_id")
        if payload["mode"] != "shared_ro":
            raise PermissionError("workspace mode is not supported")
        if payload["lease_status"] not in {"active", "released"}:
            raise ValueError("workspace.bound lease_status must be active or released")
        bound_to = payload["bound_to"]
        if not isinstance(bound_to, dict):
            raise ValueError("workspace.bound bound_to must be a dict")
        if not any(isinstance(bound_to.get(field_name), str) and bound_to[field_name] for field_name in ("agent_id", "execution_id")):
            raise ValueError("workspace.bound bound_to must include agent_id or execution_id")
        provenance = payload["provenance"]
        if not isinstance(provenance, dict):
            raise ValueError("workspace.bound provenance must be a dict")
        decision_id = provenance.get("decision_id")
        if not isinstance(decision_id, str) or not decision_id:
            raise ValueError("workspace.bound provenance.decision_id is required")
        grant_basis = provenance.get("grant_basis")
        if not isinstance(grant_basis, dict):
            raise ValueError("workspace.bound provenance.grant_basis must be a dict")
        workspace_grant = grant_basis.get("workspace")
        if not isinstance(workspace_grant, dict):
            raise ValueError("workspace.bound provenance.grant_basis.workspace must be a dict")
        if workspace_grant.get("mode") != payload["mode"]:
            raise PermissionError("workspace.bound mode must match workspace grant")

    def _validate_workspace_bound_lifecycle(self, payload: dict[str, Any], event: CanonicalEvent) -> None:
        if payload["run_id"] != event.run_id:
            raise ValueError("workspace.bound run_id must match event run_id")

    def _validate_memory_record_created_payload(self, payload: dict[str, Any]) -> None:
        self._require_fields(
            "memory.record_created",
            payload,
            ("record_id", "execution_id", "summary", "source_refs", "provenance", "basis_event_id"),
        )
        for field_name in ("content", "full_content", "artifact_content", "raw_content"):
            if field_name in payload:
                raise ValueError(f"memory.record_created cannot contain {field_name}")
        if not isinstance(payload["source_refs"], list):
            raise ValueError("memory.record_created source_refs must be a list")
        if not isinstance(payload["provenance"], dict):
            raise ValueError("memory.record_created provenance must be a dict")

    def _validate_memory_record_lifecycle(self, payload: dict[str, Any]) -> None:
        execution_id = str(payload["execution_id"])
        status = self._execution_statuses.get(execution_id)
        if status is None:
            outcomes = set(self._proposal_outcomes.values())
            if "denied" in outcomes:
                raise ValueError("memory.record_created after denied decision")
            if "pending_user_approval" in outcomes:
                raise ValueError("memory.record_created after pending decision")
            raise ValueError("memory.record_created requires completed write_memory execution")
        if status != "completed":
            raise ValueError(f"memory.record_created requires completed write_memory execution, got {status}")
        action_type = self._execution_action_types.get(execution_id)
        if action_type != "write_memory":
            raise ValueError("memory.record_created requires completed write_memory execution")

    def _validate_memory_record_superseded_payload(self, payload: dict[str, Any]) -> None:
        self._require_fields(
            "memory.record_superseded",
            payload,
            ("old_record_id", "new_record_id", "execution_id", "reason", "provenance", "basis_event_id"),
        )
        for field_name in ("content", "full_content", "artifact_content", "raw_content"):
            if field_name in payload:
                raise ValueError(f"memory.record_superseded cannot contain {field_name}")
        if not isinstance(payload["provenance"], dict):
            raise ValueError("memory.record_superseded provenance must be a dict")

    def _validate_memory_record_superseded_lifecycle(self, payload: dict[str, Any]) -> None:
        old_record_id = str(payload["old_record_id"])
        new_record_id = str(payload["new_record_id"])
        if old_record_id == new_record_id:
            raise ValueError("memory.record_superseded old_record_id and new_record_id must not be the same")
        if old_record_id not in self._memory_record_ids:
            raise ValueError("memory.record_superseded old_record_id must reference an existing record")
        if new_record_id not in self._memory_record_ids:
            raise ValueError("memory.record_superseded new_record_id must reference an existing record")

        execution_id = str(payload["execution_id"])
        status = self._execution_statuses.get(execution_id)
        if status is None:
            outcomes = set(self._proposal_outcomes.values())
            if "denied" in outcomes:
                raise ValueError("memory.record_superseded after denied decision")
            if "pending_user_approval" in outcomes:
                raise ValueError("memory.record_superseded after pending decision")
            raise ValueError("memory.record_superseded requires completed write_memory execution")
        if status != "completed":
            raise ValueError(f"memory.record_superseded requires completed write_memory execution, got {status}")
        action_type = self._execution_action_types.get(execution_id)
        if action_type != "write_memory":
            raise ValueError("memory.record_superseded requires completed write_memory execution")

    def _validate_snapshot_imported_payload(self, payload: dict[str, Any]) -> None:
        self._require_fields(
            "snapshot.imported",
            payload,
            (
                "snapshot_id",
                "source_system",
                "captured_at",
                "content_type",
                "source_ref",
                "summary",
                "observation",
                "quality",
                "provenance",
                "basis_refs",
            ),
        )
        for field_name in ("snapshot_id", "source_system", "captured_at", "content_type", "summary"):
            value = payload[field_name]
            if not isinstance(value, str) or not value:
                raise ValueError(f"snapshot.imported {field_name} must be a non-empty string")
        self._validate_resource_ref_payload(payload["source_ref"], "snapshot.imported source_ref")
        if not isinstance(payload["observation"], dict):
            raise ValueError("snapshot.imported observation must be a dict")
        quality = payload["quality"]
        if not isinstance(quality, dict):
            raise ValueError("snapshot.imported quality must be a dict")
        for field_name in ("confidence", "coverage", "freshness"):
            if field_name not in quality:
                raise ValueError(f"snapshot.imported quality missing required field: {field_name}")
        provenance = payload["provenance"]
        if not isinstance(provenance, dict):
            raise ValueError("snapshot.imported provenance must be a dict")
        raw_artifact_ref = provenance.get("raw_artifact_ref")
        if not isinstance(raw_artifact_ref, dict):
            raise ValueError("snapshot.imported provenance.raw_artifact_ref must be a structured ResourceRef")
        self._validate_resource_ref_payload(raw_artifact_ref, "snapshot.imported provenance.raw_artifact_ref")
        basis_refs = payload["basis_refs"]
        if not isinstance(basis_refs, list) or not basis_refs:
            raise ValueError("snapshot.imported basis_refs must be a non-empty list")
        for index, ref in enumerate(basis_refs):
            self._validate_resource_ref_payload(ref, f"snapshot.imported basis_refs[{index}]")
        for field_name in self.CHECKPOINT_EXTERNAL_OBSERVATION_FORBIDDEN_FIELDS:
            if field_name in payload:
                raise ValueError(f"snapshot.imported cannot contain {field_name}")
            if field_name in payload["observation"]:
                raise ValueError(f"snapshot.imported observation cannot contain {field_name}")
            if field_name in provenance:
                raise ValueError(f"snapshot.imported provenance cannot contain {field_name}")

    def _validate_resource_ref_payload(self, ref: Any, label: str) -> None:
        if not isinstance(ref, dict):
            raise TypeError(f"{label} must be a structured ResourceRef")
        for field_name in ("ref_type", "scope", "run_id", "artifact_id"):
            value = ref.get(field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{label}.{field_name} must be a non-empty string")
        if ref["ref_type"] != "artifact":
            raise ValueError(f"{label} must be an artifact ResourceRef")

    def apply(self, state: RunState, event: CanonicalEvent) -> None:
        state.last_event_id = event.event_id
        if not state.run_id:
            state.run_id = event.run_id

        payload = event.payload
        if event.event_type == "run.created":
            state.run_id = str(payload.get("run_id", event.run_id))
            state.status = "running"
        elif event.event_type == "agent.created":
            agent_id = str(payload["agent_id"])
            state.current_agent = agent_id
            state.agents[agent_id] = {
                "agent_id": agent_id,
                "run_id": payload.get("run_id", event.run_id),
                "role": payload.get("role", "supervisor"),
                "status": payload.get("status", "created"),
                "created_event_id": event.event_id,
                "last_event_id": event.event_id,
            }
        elif event.event_type == "action.started":
            execution_id = str(payload["execution_id"])
            proposal_id = str(payload.get("proposal_id", ""))
            state.actions[execution_id] = {
                "execution_id": execution_id,
                "proposal_id": proposal_id,
                "decision_id": payload.get("decision_id"),
                "agent_id": self._proposal_agents.get(proposal_id),
                "status": "running",
            }
        elif event.event_type == "delegation.proposed":
            pass
        elif event.event_type == "delegation.decided":
            pass
        elif event.event_type == "worker.created":
            self._apply_worker_created(state, payload, event)
        elif event.event_type in {"worker.started", "worker.completed", "worker.failed", "worker.cancelled"}:
            self._apply_worker_status(state, payload, event)
        elif event.event_type == "worker.result_handed_off":
            self._apply_worker_result_handoff(state, payload, event)
        elif event.event_type == "workspace.bound":
            self._apply_workspace_bound(state, payload, event)
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
            approval_id = str(payload["approval_id"])
            state.approvals[approval_id] = {
                "approval_id": approval_id,
                "run_id": payload.get("run_id", event.run_id),
                "proposal_id": proposal_id,
                "decision_id": payload.get("decision_id"),
                "status": "pending",
                "reason_codes": list(self._proposal_reason_codes.get(proposal_id, [])),
                "requested_action_summary": dict(
                    self._proposal_summaries.get(
                        proposal_id,
                        {"action_type": payload.get("action_type")},
                    )
                ),
            }
            state.status = "pending_user_approval"
        elif event.event_type == "approval.resolved":
            proposal_id = str(payload["proposal_id"])
            action = state.actions.setdefault(proposal_id, {"proposal_id": proposal_id})
            action["decision_id"] = payload.get("decision_id")
            approval_id = str(payload["approval_id"])
            action["approval_id"] = approval_id
            action["approval_resolution"] = payload.get("resolution")
            action["approval_resolved_event_id"] = event.event_id
            action["approval_reason"] = payload.get("reason")
            resolution = payload.get("resolution")
            action["status"] = "approved" if resolution == "approved" else "denied"
            approval = state.approvals.setdefault(
                approval_id,
                {
                    "approval_id": approval_id,
                    "run_id": payload.get("run_id", event.run_id),
                    "proposal_id": proposal_id,
                    "decision_id": payload.get("decision_id"),
                },
            )
            approval.update(
                {
                    "status": resolution,
                    "resolution": resolution,
                    "reason": payload.get("reason"),
                    "resolver": payload.get("resolver"),
                    "resolved_event_id": event.event_id,
                    "basis_event_id": payload.get("basis_event_id"),
                }
            )
            if resolution == "approved":
                state.status = "running"
            else:
                state.status = "denied"
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
        elif event.event_type == "action.retry_requested":
            retry_id = str(payload["retry_id"])
            state.action_retries[retry_id] = {
                "retry_id": retry_id,
                "original_proposal_id": payload["original_proposal_id"],
                "original_execution_id": payload["original_execution_id"],
                "status": "requested",
                "basis_event_id": event.event_id,
            }
        elif event.event_type == "action.retry_created":
            retry_id = str(payload["retry_id"])
            retry = state.action_retries.setdefault(retry_id, {"retry_id": retry_id})
            retry.update(
                {
                    "original_proposal_id": payload["original_proposal_id"],
                    "original_execution_id": retry.get("original_execution_id"),
                    "new_proposal_id": payload["new_proposal_id"],
                    "status": "created",
                    "basis_event_id": payload["basis_event_id"],
                }
            )
        elif event.event_type == "action.cancel_requested":
            cancel_id = str(payload["cancel_id"])
            state.action_cancellations[cancel_id] = {
                "cancel_id": cancel_id,
                "proposal_id": payload["proposal_id"],
                "execution_id": payload["execution_id"],
                "status": "requested",
                "basis_event_id": event.event_id,
            }
        elif event.event_type == "action.cancelled":
            cancel_id = str(payload["cancel_id"])
            cancellation = state.action_cancellations.setdefault(cancel_id, {"cancel_id": cancel_id})
            cancellation.update(
                {
                    "proposal_id": payload["proposal_id"],
                    "execution_id": payload["execution_id"],
                    "status": "cancelled",
                    "basis_event_id": payload["basis_event_id"],
                }
            )
            execution_id = str(payload["execution_id"])
            action = state.actions.setdefault(execution_id, {"execution_id": execution_id})
            action["status"] = "cancelled"
        elif event.event_type == "action.superseded":
            supersession_id = str(payload["supersession_id"])
            state.action_supersessions[supersession_id] = {
                "supersession_id": supersession_id,
                "old_proposal_id": payload["old_proposal_id"],
                "new_proposal_id": payload["new_proposal_id"],
                "status": "created",
                "basis_event_id": payload["basis_event_id"],
            }
            execution_id = self._proposal_execution_ids.get(str(payload["old_proposal_id"]))
            if execution_id is not None:
                action = state.actions.setdefault(execution_id, {"execution_id": execution_id})
                action["status"] = "superseded"
        elif event.event_type == "memory.record_created":
            state.memory_records.append(
                {
                    "record_id": payload["record_id"],
                    "execution_id": payload["execution_id"],
                    "summary": payload["summary"],
                    "source_refs": list(payload["source_refs"]),
                    "provenance": dict(payload["provenance"]),
                    "basis_event_id": payload["basis_event_id"],
                    "quality": payload.get("quality"),
                }
            )
        elif event.event_type == "memory.record_superseded":
            old_record_id = str(payload["old_record_id"])
            for record in state.memory_records:
                if record["record_id"] == old_record_id:
                    record["status"] = "superseded"
                    record["superseded_by"] = payload["new_record_id"]
                    record["superseded_event_id"] = event.event_id
                    record["superseded_reason"] = payload["reason"]
                    break
        elif event.event_type == "snapshot.imported":
            self._apply_snapshot_imported(state, payload)
        elif event.event_type == "run.completed":
            state.status = str(payload.get("status", "completed"))

    def _apply_worker_created(self, state: RunState, payload: dict[str, Any], event: CanonicalEvent) -> None:
        worker_id = str(payload["worker_id"])
        delegation_id = str(payload["delegation_id"])
        proposal = self._delegation_proposals[delegation_id]
        decision = self._delegation_decisions[delegation_id]
        grants = dict(decision["grants"])
        workspace = dict(grants.get("workspace", payload["workspace"]))
        worker = {
            "worker_id": worker_id,
            "agent_id": payload["agent_id"],
            "run_id": payload.get("run_id", event.run_id),
            "parent_agent_id": payload["parent_agent_id"],
            "delegation_id": delegation_id,
            "decision_id": payload["decision_id"],
            "role": payload["role"],
            "status": "created",
            "requested_capabilities": dict(proposal["requested_capabilities"]),
            "grants": grants,
            "workspace": workspace,
            "result_refs": [],
            "created_event_id": event.event_id,
            "last_event_id": event.event_id,
        }
        state.workers[worker_id] = worker
        agent_id = str(payload["agent_id"])
        state.agents[agent_id] = {
            "agent_id": agent_id,
            "run_id": payload.get("run_id", event.run_id),
            "role": payload["role"],
            "status": "created",
            "parent_agent_id": payload["parent_agent_id"],
            "delegation_id": delegation_id,
            "worker_id": worker_id,
            "created_event_id": event.event_id,
            "last_event_id": event.event_id,
        }

    def _apply_worker_status(self, state: RunState, payload: dict[str, Any], event: CanonicalEvent) -> None:
        worker_id = str(payload["worker_id"])
        worker = state.workers.setdefault(worker_id, {"worker_id": worker_id})
        status = str(payload["status"])
        worker["status"] = status
        worker["last_event_id"] = event.event_id
        if "error" in payload:
            worker["error"] = payload["error"]
        if "reason" in payload:
            worker["reason"] = payload["reason"]
        agent_id = worker.get("agent_id")
        if isinstance(agent_id, str) and agent_id in state.agents:
            state.agents[agent_id]["status"] = status
            state.agents[agent_id]["last_event_id"] = event.event_id

    def _apply_worker_result_handoff(self, state: RunState, payload: dict[str, Any], event: CanonicalEvent) -> None:
        worker_id = str(payload["worker_id"])
        worker = state.workers.setdefault(worker_id, {"worker_id": worker_id})
        result_refs = worker.setdefault("result_refs", [])
        result_refs.append(dict(payload["artifact_ref"]))
        worker["result_summary"] = payload["summary"]
        worker["last_event_id"] = event.event_id

    def _apply_workspace_bound(self, state: RunState, payload: dict[str, Any], event: CanonicalEvent) -> None:
        workspace_id = str(payload["workspace_id"])
        state.workspaces[workspace_id] = {
            "workspace_id": workspace_id,
            "run_id": payload["run_id"],
            "mode": payload["mode"],
            "bound_to": dict(payload["bound_to"]),
            "lease_status": payload["lease_status"],
            "provenance": dict(payload["provenance"]),
            "basis_event_id": event.event_id,
        }

    def _apply_snapshot_imported(self, state: RunState, payload: dict[str, Any]) -> None:
        source_ref = dict(payload["source_ref"])
        provenance = dict(payload["provenance"])
        observation = _ObservationDict(
            {
                "snapshot_id": payload["snapshot_id"],
                "snapshot_type": payload["content_type"],
                "source_system": payload["source_system"],
                "captured_at": payload["captured_at"],
                "content_type": payload["content_type"],
                "source_ref": source_ref,
                "summary": payload["summary"],
                "observation": dict(payload["observation"]),
                "quality": dict(payload["quality"]),
                "provenance": provenance,
                "basis_refs": [dict(ref) for ref in payload["basis_refs"]],
                "status": "imported",
                "conflict_status": "none",
            }
        )
        if "run_status" in observation["observation"]:
            observation["native_status"] = state.status
        existing = self._find_external_observation(state.external_observations, observation["snapshot_id"])
        if existing is not None:
            self._merge_duplicate_external_observation(existing, observation)
            self._mark_snapshot_conflicts(state.external_observations)
            return
        state.external_observations.append(observation)
        self._mark_snapshot_conflicts(state.external_observations)

    def _find_external_observation(
        self,
        observations: list[dict[str, Any]],
        snapshot_id: Any,
    ) -> dict[str, Any] | None:
        for observation in observations:
            if observation.get("snapshot_id") == snapshot_id:
                return observation
        return None

    def _merge_duplicate_external_observation(
        self,
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> None:
        if existing.get("observation") != incoming.get("observation"):
            existing["conflict_status"] = "conflict"
            existing["status"] = "conflict"
        self._merge_basis_refs(existing, incoming.get("basis_refs", []))

    def _merge_basis_refs(self, observation: dict[str, Any], refs: list[Any]) -> None:
        existing_refs = observation.setdefault("basis_refs", [])
        seen = {self._stable_json(ref) for ref in existing_refs}
        for ref in refs:
            key = self._stable_json(ref)
            if key not in seen:
                existing_refs.append(dict(ref))
                seen.add(key)

    def _stable_json(self, value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def _mark_snapshot_conflicts(self, observations: list[dict[str, Any]]) -> None:
        by_subject: dict[str, dict[str, Any]] = {}
        conflicted_subjects: set[str] = set()
        for observation in observations:
            subject_key = self._external_observation_subject_key(observation)
            previous = by_subject.get(subject_key)
            if previous is not None and previous.get("observation") != observation.get("observation"):
                conflicted_subjects.add(subject_key)
            else:
                by_subject.setdefault(subject_key, observation)
        for observation in observations:
            if observation.get("conflict_status") == "conflict":
                observation["status"] = "conflict"
            elif observation.get("status") != "conflict":
                observation["status"] = "imported"
            if self._external_observation_subject_key(observation) in conflicted_subjects:
                observation["conflict_status"] = "conflict"
                observation["status"] = "conflict"

    def _external_observation_subject_key(self, observation: dict[str, Any]) -> str:
        observed = observation.get("observation")
        subject = observed.get("subject") if isinstance(observed, dict) else None
        return self._stable_json(
            {
                "snapshot_type": observation.get("snapshot_type") or observation.get("content_type"),
                "subject": subject if subject is not None else observation.get("content_type"),
            }
        )

    def project(self, events: Iterable[CanonicalEvent]) -> RunState:
        self._proposal_outcomes = {}
        self._proposal_action_types = {}
        self._proposal_reason_codes = {}
        self._proposal_summaries = {}
        self._proposal_agents = {}
        self._proposal_grants = {}
        self._execution_statuses = {}
        self._execution_action_types = {}
        self._execution_proposals = {}
        self._proposal_execution_ids = {}
        self._proposal_start_event_ids = {}
        self._retry_requests = {}
        self._cancel_requests = {}
        self._approval_proposals = {}
        self._approval_resolutions = set()
        self._delegation_proposals = {}
        self._delegation_decisions = {}
        self._workers = {}
        self._worker_agent_ids = set()
        self._memory_record_ids = set()
        self._run_completed = False
        state = RunState()
        for event in events:
            self._validate_lifecycle(event)
            self.apply(state, event)
        return state

    def rebuild(self, run_id: str, event_store) -> RunState:
        return self.project(event_store.list_events(run_id))

    def save_checkpoint(
        self,
        run_id: str,
        event_store,
        checkpoint_store,
        projector_version: str = PROJECTOR_VERSION,
    ) -> dict[str, Any]:
        canonical_events = event_store.list_events(run_id)
        checkpoint = self.create_checkpoint(run_id, canonical_events, projector_version)
        return checkpoint_store.save_checkpoint(run_id, checkpoint)

    def save_checkpoint_history(
        self,
        run_id: str,
        event_store,
        checkpoint_store,
        projector_version: str = PROJECTOR_VERSION,
    ) -> dict[str, Any]:
        canonical_events = event_store.list_events(run_id)
        checkpoint = self.create_checkpoint(run_id, canonical_events, projector_version)
        return checkpoint_store.save_checkpoint_history(run_id, checkpoint)

    def create_checkpoint(
        self,
        run_id: str,
        events: Iterable[CanonicalEvent],
        projector_version: str = PROJECTOR_VERSION,
    ) -> dict[str, Any]:
        canonical_events = list(events)
        if not canonical_events:
            raise ValueError("cannot create checkpoint from empty events")

        state = self.project(canonical_events)
        if state.run_id and state.run_id != run_id:
            raise ValueError("checkpoint state run_id must match checkpoint run_id")

        checkpoint = {
            "run_id": run_id,
            "projector_version": projector_version,
            "basis_event_id": canonical_events[-1].event_id,
            "state": self._checkpoint_state_payload(state),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        checkpoint["integrity"] = {
            "algorithm": "sha256",
            "checkpoint_hash": self._checkpoint_hash(self._checkpoint_payload_for_hash(checkpoint)),
            "event_digest_algorithm": "sha256",
            "event_prefix_digest": self._event_prefix_digest(canonical_events),
            "event_digest_basis_event_id": checkpoint["basis_event_id"],
            "event_digest_event_count": len(canonical_events),
            "event_digest_event_envelope_version": EVENT_ENVELOPE_VERSION,
        }
        return checkpoint

    def rebuild_with_checkpoint(
        self,
        run_id: str,
        event_store,
        checkpoint_store,
        projector_version: str = PROJECTOR_VERSION,
    ) -> RunState:
        candidates = self._load_checkpoint_candidates(run_id, checkpoint_store)
        if not candidates:
            return self.rebuild(run_id, event_store)

        canonical_events = event_store.list_events(run_id)
        for checkpoint in candidates:
            state = self._try_rebuild_from_checkpoint(
                run_id,
                canonical_events,
                checkpoint,
                projector_version,
            )
            if state is not None:
                return state
        return self.rebuild(run_id, event_store)

    def _load_checkpoint_candidates(self, run_id: str, checkpoint_store) -> list[dict[str, Any]]:
        if hasattr(checkpoint_store, "load_checkpoint_candidates"):
            return checkpoint_store.load_checkpoint_candidates(run_id)
        checkpoint = checkpoint_store.load_latest_checkpoint(run_id)
        return [] if checkpoint is None else [checkpoint]

    def _try_rebuild_from_checkpoint(
        self,
        run_id: str,
        canonical_events: list[CanonicalEvent],
        checkpoint: dict[str, Any],
        projector_version: str,
    ) -> RunState | None:
        if not self._is_compatible_projector_version(checkpoint, projector_version):
            return None
        if checkpoint["run_id"] != run_id:
            return None
        if not self._validate_checkpoint_integrity(checkpoint):
            return None

        basis_index = self._find_basis_index(canonical_events, checkpoint["basis_event_id"])
        if not self._validate_event_prefix_digest(checkpoint, canonical_events, basis_index):
            return None

        # Validate prefix from canonical events before trusting the checkpoint state.
        prefix_state = self.project(canonical_events[: basis_index + 1])
        state = self._run_state_from_checkpoint(checkpoint["state"], run_id, checkpoint["basis_event_id"])
        if state != prefix_state:
            return None

        for event in canonical_events[basis_index + 1 :]:
            self._validate_lifecycle(event)
            self.apply(state, event)
        return state

    def _checkpoint_payload_for_hash(self, checkpoint: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in checkpoint.items()
            if key not in {"integrity", "checkpoint_hash"}
        }

    def _checkpoint_state_payload(self, state: RunState) -> dict[str, Any]:
        state_payload = asdict(state)
        return {field_name: state_payload[field_name] for field_name in self.CHECKPOINT_STATE_FIELDS}

    def _is_compatible_projector_version(self, checkpoint: dict[str, Any], projector_version: Any) -> bool:
        checkpoint_version = checkpoint.get("projector_version")
        if not isinstance(checkpoint_version, str) or not checkpoint_version:
            return False
        if not isinstance(projector_version, str) or not projector_version:
            return False
        return checkpoint_version == projector_version

    def _checkpoint_hash(self, checkpoint_without_integrity: dict[str, Any]) -> str:
        encoded = json.dumps(
            checkpoint_without_integrity,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _validate_checkpoint_integrity(self, checkpoint: dict[str, Any]) -> bool:
        integrity = checkpoint.get("integrity")
        if integrity is None:
            return True
        if not isinstance(integrity, dict):
            return False
        if integrity.get("algorithm") != "sha256":
            return False
        checkpoint_hash = integrity.get("checkpoint_hash")
        if not isinstance(checkpoint_hash, str) or not checkpoint_hash:
            return False
        expected = self._checkpoint_hash(self._checkpoint_payload_for_hash(checkpoint))
        return checkpoint_hash == expected

    def _event_prefix_payload(self, canonical_events: list[CanonicalEvent]) -> list[dict[str, Any]]:
        return [
            {
                "event_id": event.event_id,
                "run_id": event.run_id,
                "event_type": event.event_type,
                "payload": event.payload,
                "created_at": event.created_at,
                "event_envelope_version": event.event_envelope_version,
            }
            for event in canonical_events
        ]

    def _event_prefix_digest(self, canonical_events: list[CanonicalEvent]) -> str:
        encoded = json.dumps(
            self._event_prefix_payload(canonical_events),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _validate_event_prefix_digest(
        self,
        checkpoint: dict[str, Any],
        canonical_events: list[CanonicalEvent],
        basis_index: int,
    ) -> bool:
        integrity = checkpoint.get("integrity")
        if not isinstance(integrity, dict):
            return True
        if "event_prefix_digest" not in integrity:
            return True
        if integrity.get("event_digest_algorithm") != "sha256":
            return False
        event_prefix_digest = integrity.get("event_prefix_digest")
        if not isinstance(event_prefix_digest, str) or not event_prefix_digest:
            return False
        if integrity.get("event_digest_basis_event_id") != checkpoint["basis_event_id"]:
            return False
        event_count = integrity.get("event_digest_event_count")
        if not isinstance(event_count, int) or isinstance(event_count, bool):
            return False
        if event_count != basis_index + 1:
            return False
        event_envelope_version = integrity.get("event_digest_event_envelope_version")
        if event_envelope_version is not None and event_envelope_version != EVENT_ENVELOPE_VERSION:
            return False
        expected = self._event_prefix_digest(canonical_events[: basis_index + 1])
        return event_prefix_digest == expected

    def _find_basis_index(self, canonical_events: list[CanonicalEvent], basis_event_id: str) -> int:
        for index, event in enumerate(canonical_events):
            if event.event_id == basis_event_id:
                return index
        raise ValueError("checkpoint basis_event_id not found")

    def _run_state_from_checkpoint(self, state: dict[str, Any], run_id: str, basis_event_id: str) -> RunState:
        if not isinstance(state, dict):
            raise ValueError("checkpoint state must be a dict")
        for field in self.CHECKPOINT_REQUIRED_STATE_FIELDS:
            if field not in state:
                raise ValueError(f"checkpoint state missing required field: {field}")
        if state["run_id"] != run_id:
            raise ValueError("checkpoint state run_id must match rebuild run_id")
        if state["last_event_id"] != basis_event_id:
            raise ValueError("checkpoint state last_event_id must match basis_event_id")
        if state["status"] not in self.KNOWN_RUN_STATUSES:
            raise ValueError("checkpoint state status must be known")
        agents = state.get("agents", {})
        if not isinstance(agents, dict):
            raise ValueError("checkpoint state agents must be a dict")
        workers = state.get("workers", {})
        if not isinstance(workers, dict):
            raise ValueError("checkpoint state workers must be a dict")
        workspaces = state.get("workspaces", {})
        if not isinstance(workspaces, dict):
            raise ValueError("checkpoint state workspaces must be a dict")
        if not isinstance(state["actions"], dict):
            raise ValueError("checkpoint state actions must be a dict")
        action_retries = state.get("action_retries", {})
        if not isinstance(action_retries, dict):
            raise ValueError("checkpoint state action_retries must be a dict")
        action_cancellations = state.get("action_cancellations", {})
        if not isinstance(action_cancellations, dict):
            raise ValueError("checkpoint state action_cancellations must be a dict")
        action_supersessions = state.get("action_supersessions", {})
        if not isinstance(action_supersessions, dict):
            raise ValueError("checkpoint state action_supersessions must be a dict")
        approvals = state.get("approvals", {})
        if not isinstance(approvals, dict):
            raise ValueError("checkpoint state approvals must be a dict")
        if not isinstance(state["artifacts"], list):
            raise ValueError("checkpoint state artifacts must be a list")
        memory_records = state.get("memory_records", [])
        if not isinstance(memory_records, list):
            raise ValueError("checkpoint state memory_records must be a list")
        external_observations = state.get("external_observations", [])
        if not isinstance(external_observations, list):
            raise ValueError("checkpoint state external_observations must be a list")
        for artifact in state["artifacts"]:
            self._validate_checkpoint_artifact(artifact)
        for agent_id, agent in agents.items():
            self._validate_checkpoint_agent(agent_id, agent)
        for worker_id, worker in workers.items():
            self._validate_checkpoint_worker(worker_id, worker)
        for workspace_id, workspace in workspaces.items():
            self._validate_checkpoint_workspace(workspace_id, workspace)
        for approval_id, approval in approvals.items():
            self._validate_checkpoint_approval(approval_id, approval)
        for record in memory_records:
            self._validate_checkpoint_memory_record(record)
        for observation in external_observations:
            self._validate_checkpoint_external_observation(observation)
        return RunState(
            run_id=str(state.get("run_id", "")),
            status=str(state.get("status", "unknown")),
            current_agent=str(state.get("current_agent", "")),
            agents=dict(agents),
            workers=dict(workers),
            workspaces=dict(workspaces),
            actions=dict(state.get("actions", {})),
            action_retries=dict(action_retries),
            action_cancellations=dict(action_cancellations),
            action_supersessions=dict(action_supersessions),
            approvals=dict(approvals),
            artifacts=list(state.get("artifacts", [])),
            memory_records=list(memory_records),
            external_observations=list(external_observations),
            last_event_id=str(state.get("last_event_id", "")),
        )

    def _validate_checkpoint_agent(self, agent_id: Any, agent: Any) -> None:
        if not isinstance(agent_id, str) or not agent_id:
            raise ValueError("checkpoint agent id must be a non-empty string")
        if not isinstance(agent, dict):
            raise ValueError("checkpoint agent entry must be a dict")
        if agent.get("agent_id") != agent_id:
            raise ValueError("checkpoint agent id must match entry agent_id")
        if not isinstance(agent.get("role"), str) or not agent["role"]:
            raise ValueError("checkpoint agent role must be a non-empty string")
        if agent.get("status") not in {"created", "running", "completed", "failed", "cancelled"}:
            raise ValueError("checkpoint agent status must be known")

    def _validate_checkpoint_worker(self, worker_id: Any, worker: Any) -> None:
        if not isinstance(worker_id, str) or not worker_id:
            raise ValueError("checkpoint worker id must be a non-empty string")
        if not isinstance(worker, dict):
            raise ValueError("checkpoint worker entry must be a dict")
        for field_name in (
            "worker_id",
            "agent_id",
            "parent_agent_id",
            "delegation_id",
            "decision_id",
            "status",
            "grants",
            "workspace",
        ):
            if field_name not in worker:
                raise ValueError(f"checkpoint worker entry missing required field: {field_name}")
        if worker["worker_id"] != worker_id:
            raise ValueError("checkpoint worker id must match entry worker_id")
        if worker["status"] not in {"created", "running", "completed", "failed", "cancelled"}:
            raise ValueError("checkpoint worker status must be known")
        if not isinstance(worker["grants"], dict):
            raise ValueError("checkpoint worker grants must be a dict")
        if not isinstance(worker["workspace"], dict):
            raise ValueError("checkpoint worker workspace must be a dict")
        result_refs = worker.get("result_refs", [])
        if not isinstance(result_refs, list):
            raise ValueError("checkpoint worker result_refs must be a list")
        for index, ref in enumerate(result_refs):
            self._validate_resource_ref_payload(ref, f"checkpoint worker result_refs[{index}]")

    def _validate_checkpoint_workspace(self, workspace_id: Any, workspace: Any) -> None:
        if not isinstance(workspace_id, str) or not workspace_id:
            raise ValueError("checkpoint workspace id must be a non-empty string")
        if not isinstance(workspace, dict):
            raise ValueError("checkpoint workspace entry must be a dict")
        for field_name in ("workspace_id", "run_id", "mode", "bound_to", "lease_status", "provenance", "basis_event_id"):
            if field_name not in workspace:
                raise ValueError(f"checkpoint workspace entry missing required field: {field_name}")
        if workspace["workspace_id"] != workspace_id:
            raise ValueError("checkpoint workspace id must match entry workspace_id")
        if workspace["mode"] != "shared_ro":
            raise ValueError("checkpoint workspace mode must be shared_ro")
        if workspace["lease_status"] not in {"active", "released"}:
            raise ValueError("checkpoint workspace lease_status must be known")
        if not isinstance(workspace["bound_to"], dict):
            raise ValueError("checkpoint workspace bound_to must be a dict")
        if not any(
            isinstance(workspace["bound_to"].get(field_name), str) and workspace["bound_to"][field_name]
            for field_name in ("agent_id", "execution_id")
        ):
            raise ValueError("checkpoint workspace bound_to must include agent_id or execution_id")
        if not isinstance(workspace["provenance"], dict):
            raise ValueError("checkpoint workspace provenance must be a dict")
        if not isinstance(workspace["basis_event_id"], str) or not workspace["basis_event_id"]:
            raise ValueError("checkpoint workspace basis_event_id must be a non-empty string")

    def _validate_checkpoint_artifact(self, artifact: Any) -> None:
        if not isinstance(artifact, dict):
            raise ValueError("checkpoint artifact entry must be a dict")
        if "content" in artifact:
            raise ValueError("checkpoint artifact entry cannot contain content")
        for field in self.CHECKPOINT_ARTIFACT_FIELDS:
            if field not in artifact:
                raise ValueError(f"checkpoint artifact entry missing required field: {field}")

    def _validate_checkpoint_approval(self, approval_id: Any, approval: Any) -> None:
        if not isinstance(approval_id, str) or not approval_id:
            raise ValueError("checkpoint approval id must be a non-empty string")
        if not isinstance(approval, dict):
            raise ValueError("checkpoint approval entry must be a dict")
        for field_name in ("approval_id", "run_id", "proposal_id", "decision_id", "status"):
            if field_name not in approval:
                raise ValueError(f"checkpoint approval entry missing required field: {field_name}")
        if approval["approval_id"] != approval_id:
            raise ValueError("checkpoint approval id must match entry approval_id")
        status = approval["status"]
        if status not in {"pending", "approved", "denied"}:
            raise ValueError("checkpoint approval status must be known")
        if status == "pending":
            reason_codes = approval.get("reason_codes")
            if not isinstance(reason_codes, list):
                raise ValueError("checkpoint pending approval reason_codes must be a list")
            if not isinstance(approval.get("requested_action_summary"), dict):
                raise ValueError("checkpoint pending approval requested_action_summary must be a dict")
        else:
            if approval.get("resolution") != status:
                raise ValueError("checkpoint resolved approval resolution must match status")
            for field_name in ("reason", "resolver", "resolved_event_id"):
                value = approval.get(field_name)
                if not isinstance(value, str) or not value:
                    raise ValueError(f"checkpoint resolved approval missing required field: {field_name}")

    def _validate_checkpoint_memory_record(self, record: Any) -> None:
        if not isinstance(record, dict):
            raise ValueError("checkpoint memory record entry must be a dict")
        for field_name in self.CHECKPOINT_MEMORY_RECORD_FORBIDDEN_FIELDS:
            if field_name in record:
                raise ValueError(f"checkpoint memory record entry cannot contain {field_name}")
        for field_name in self.CHECKPOINT_MEMORY_RECORD_FIELDS:
            if field_name not in record:
                raise ValueError(f"checkpoint memory record entry missing required field: {field_name}")
        if not isinstance(record["source_refs"], list):
            raise ValueError("checkpoint memory record source_refs must be a list")
        if not isinstance(record["provenance"], dict):
            raise ValueError("checkpoint memory record provenance must be a dict")
        unexpected_fields = set(record) - self.CHECKPOINT_MEMORY_RECORD_ALLOWED_FIELDS
        if unexpected_fields:
            field_name = sorted(unexpected_fields)[0]
            raise ValueError(f"checkpoint memory record entry has unknown field: {field_name}")
        self._validate_checkpoint_memory_supersession(record)

    def _validate_checkpoint_memory_supersession(self, record: dict[str, Any]) -> None:
        supersession_fields = ("superseded_by", "superseded_event_id", "superseded_reason")
        has_supersession = record.get("status") == "superseded" or any(field in record for field in supersession_fields)
        if not has_supersession:
            return
        for field_name in supersession_fields:
            if field_name not in record:
                raise ValueError(f"checkpoint superseded memory record missing required field: {field_name}")
        if not isinstance(record["superseded_by"], str):
            raise ValueError("checkpoint superseded_by must be a string")
        if not isinstance(record["superseded_event_id"], str):
            raise ValueError("checkpoint superseded_event_id must be a string")
        if not isinstance(record["superseded_reason"], str) or not record["superseded_reason"]:
            raise ValueError("checkpoint superseded_reason must be a non-empty string")

    def _validate_checkpoint_external_observation(self, observation: Any) -> None:
        if not isinstance(observation, dict):
            raise ValueError("checkpoint external observation entry must be a dict")
        for field_name in self.CHECKPOINT_EXTERNAL_OBSERVATION_FORBIDDEN_FIELDS:
            if field_name in observation:
                raise ValueError(f"checkpoint external observation entry cannot contain {field_name}")
        for field_name in self.CHECKPOINT_EXTERNAL_OBSERVATION_FIELDS:
            if field_name not in observation:
                raise ValueError(f"checkpoint external observation entry missing required field: {field_name}")
        if observation["status"] not in {"imported", "conflict"}:
            raise ValueError("checkpoint external observation status must be imported or conflict")
        if observation["conflict_status"] not in {"none", "conflict"}:
            raise ValueError("checkpoint external observation conflict_status must be known")
        self._validate_resource_ref_payload(observation["source_ref"], "checkpoint external observation source_ref")
        if not isinstance(observation["observation"], dict):
            raise ValueError("checkpoint external observation observation must be a dict")
        for field_name in self.CHECKPOINT_EXTERNAL_OBSERVATION_FORBIDDEN_FIELDS:
            if field_name in observation["observation"]:
                raise ValueError(f"checkpoint external observation observation cannot contain {field_name}")
        quality = observation["quality"]
        if not isinstance(quality, dict):
            raise ValueError("checkpoint external observation quality must be a dict")
        for field_name in ("confidence", "coverage", "freshness"):
            if field_name not in quality:
                raise ValueError(f"checkpoint external observation quality missing required field: {field_name}")
        provenance = observation["provenance"]
        if not isinstance(provenance, dict):
            raise ValueError("checkpoint external observation provenance must be a dict")
        for field_name in self.CHECKPOINT_EXTERNAL_OBSERVATION_FORBIDDEN_FIELDS:
            if field_name in provenance:
                raise ValueError(f"checkpoint external observation provenance cannot contain {field_name}")
        raw_artifact_ref = provenance.get("raw_artifact_ref")
        self._validate_resource_ref_payload(raw_artifact_ref, "checkpoint external observation raw_artifact_ref")
        basis_refs = observation["basis_refs"]
        if not isinstance(basis_refs, list) or not basis_refs:
            raise ValueError("checkpoint external observation basis_refs must be a non-empty list")
        for index, ref in enumerate(basis_refs):
            self._validate_resource_ref_payload(ref, f"checkpoint external observation basis_refs[{index}]")


class _ObservationDict(dict):
    """Dict that tolerates optional diagnostic fields in equality checks."""

    OPTIONAL_COMPAT_FIELDS = {
        "snapshot_type",
        "captured_at",
        "source_ref",
        "provenance",
        "status",
        "native_status",
    }

    def __eq__(self, other: object) -> bool:
        if isinstance(other, dict):
            left = dict(self)
            right = dict(other)
            for field_name in self.OPTIONAL_COMPAT_FIELDS:
                if field_name not in right:
                    left.pop(field_name, None)
            return left == right
        return super().__eq__(other)
