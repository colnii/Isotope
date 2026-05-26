"""RunProjector domain-specific event payload validation helpers."""

from __future__ import annotations

from typing import Any

from ...events.events import CanonicalEvent


class RunProjectorDomainValidationMixin:
    """Validate delegation, worker, workspace, memory, and snapshot payloads."""

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
        if payload["lease_status"] not in {"active", "bound", "released"}:
            raise ValueError("workspace.bound lease_status must be active, bound, or released")
        bound_to = payload["bound_to"]
        self._validate_workspace_bound_to(bound_to, "workspace.bound")
        self._validate_workspace_policy_provenance(
            payload["provenance"],
            payload["mode"],
            "workspace.bound",
        )

    def _validate_workspace_bound_lifecycle(self, payload: dict[str, Any], event: CanonicalEvent) -> None:
        if payload["run_id"] != event.run_id:
            raise ValueError("workspace.bound run_id must match event run_id")
        workspace_id = str(payload["workspace_id"])
        current_status = self._workspace_statuses.get(workspace_id)
        if current_status == "released":
            raise ValueError("workspace.bound after workspace released")
        self._workspace_statuses[workspace_id] = str(payload["lease_status"])
        self._workspace_last_event_ids[workspace_id] = event.event_id

    def _validate_workspace_lease_created_payload(self, payload: dict[str, Any], event: CanonicalEvent) -> None:
        self._require_fields(
            "workspace.lease_created",
            payload,
            (
                "workspace_id",
                "run_id",
                "mode",
                "lease_status",
                "bound_to",
                "granted_by",
                "created_by",
                "provenance",
            ),
        )
        for field_name in ("workspace_id", "run_id", "mode", "lease_status"):
            value = payload[field_name]
            if not isinstance(value, str) or not value:
                raise ValueError(f"workspace.lease_created {field_name} must be a non-empty string")
        if payload["run_id"] != event.run_id:
            raise ValueError("workspace.lease_created run_id must match event run_id")
        if payload["mode"] != "shared_ro":
            raise PermissionError("workspace mode is not supported")
        if payload["lease_status"] != "created":
            raise ValueError("workspace.lease_created lease_status must be created")
        self._validate_workspace_bound_to(payload["bound_to"], "workspace.lease_created")
        granted_by = payload["granted_by"]
        if not isinstance(granted_by, dict):
            raise ValueError("workspace.lease_created granted_by must be a dict")
        decision_id = granted_by.get("decision_id")
        if not isinstance(decision_id, str) or not decision_id:
            raise ValueError("workspace.lease_created granted_by.decision_id is required")
        created_by = payload["created_by"]
        if not isinstance(created_by, dict):
            raise ValueError("workspace.lease_created created_by must be a dict")
        if not any(
            isinstance(created_by.get(field_name), str) and created_by[field_name]
            for field_name in ("execution_id", "proposal_id")
        ):
            raise ValueError("workspace.lease_created created_by must include execution_id or proposal_id")
        self._validate_workspace_policy_provenance(
            payload["provenance"],
            payload["mode"],
            "workspace.lease_created",
        )

    def _validate_workspace_lease_created_lifecycle(self, payload: dict[str, Any], event: CanonicalEvent) -> None:
        workspace_id = str(payload["workspace_id"])
        if workspace_id in self._workspace_statuses:
            raise ValueError("workspace.lease_created duplicate workspace_id")
        self._workspace_statuses[workspace_id] = str(payload["lease_status"])
        self._workspace_last_event_ids[workspace_id] = event.event_id

    def _validate_workspace_released_payload(self, payload: dict[str, Any], event: CanonicalEvent) -> None:
        self._require_fields(
            "workspace.released",
            payload,
            ("workspace_id", "run_id", "lease_status", "released_by", "released_at", "basis_event_id"),
        )
        for field_name in ("workspace_id", "run_id", "lease_status", "released_at", "basis_event_id"):
            value = payload[field_name]
            if not isinstance(value, str) or not value:
                raise ValueError(f"workspace.released {field_name} must be a non-empty string")
        if payload["run_id"] != event.run_id:
            raise ValueError("workspace.released run_id must match event run_id")
        if payload["lease_status"] != "released":
            raise ValueError("workspace.released lease_status must be released")
        released_by = payload["released_by"]
        if not isinstance(released_by, dict):
            raise ValueError("workspace.released released_by must be a dict")
        if not any(
            isinstance(released_by.get(field_name), str) and released_by[field_name]
            for field_name in ("agent_id", "execution_id", "worker_id", "system")
        ):
            raise ValueError("workspace.released released_by must identify a release actor")

    def _validate_workspace_released_lifecycle(self, payload: dict[str, Any], event: CanonicalEvent) -> None:
        workspace_id = str(payload["workspace_id"])
        current_status = self._workspace_statuses.get(workspace_id)
        if current_status is None:
            raise ValueError("workspace.released unknown workspace")
        if current_status == "released":
            raise ValueError("workspace already released")
        if payload["basis_event_id"] != self._workspace_last_event_ids.get(workspace_id):
            raise ValueError("workspace.released basis_event_id must match latest workspace event")
        self._workspace_statuses[workspace_id] = "released"
        self._workspace_last_event_ids[workspace_id] = event.event_id

    def _validate_workspace_artifact_captured_payload(self, payload: dict[str, Any], event: CanonicalEvent) -> None:
        self._require_fields(
            "workspace.artifact_captured",
            payload,
            ("workspace_id", "run_id", "artifact_ref", "captured_by", "provenance"),
        )
        for field_name in self.CHECKPOINT_WORKSPACE_FORBIDDEN_FIELDS:
            if field_name in payload:
                raise ValueError(f"workspace.artifact_captured cannot contain {field_name}")
        for field_name in ("workspace_id", "run_id"):
            value = payload[field_name]
            if not isinstance(value, str) or not value:
                raise ValueError(f"workspace.artifact_captured {field_name} must be a non-empty string")
        if payload["run_id"] != event.run_id:
            raise ValueError("workspace.artifact_captured run_id must match event run_id")
        self._validate_resource_ref_payload(payload["artifact_ref"], "workspace.artifact_captured artifact_ref")
        captured_by = payload["captured_by"]
        if not isinstance(captured_by, dict):
            raise ValueError("workspace.artifact_captured captured_by must be a dict")
        if not any(
            isinstance(captured_by.get(field_name), str) and captured_by[field_name]
            for field_name in ("execution_id", "agent_id", "worker_id")
        ):
            raise ValueError("workspace.artifact_captured captured_by must identify a capture actor")
        provenance = payload["provenance"]
        if not isinstance(provenance, dict):
            raise ValueError("workspace.artifact_captured provenance must be a dict")
        for field_name in self.CHECKPOINT_WORKSPACE_FORBIDDEN_FIELDS:
            if field_name in provenance:
                raise ValueError(f"workspace.artifact_captured provenance cannot contain {field_name}")
        for field_name in ("artifact_event_id", "basis_event_id"):
            value = provenance.get(field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"workspace.artifact_captured provenance.{field_name} is required")

    def _validate_workspace_artifact_captured_lifecycle(self, payload: dict[str, Any], event: CanonicalEvent) -> None:
        workspace_id = str(payload["workspace_id"])
        if workspace_id not in self._workspace_statuses:
            raise ValueError("workspace.artifact_captured requires workspace")
        if self._workspace_statuses[workspace_id] == "released":
            raise ValueError("workspace.artifact_captured after workspace released")
        ref_key = self._stable_json(payload["artifact_ref"])
        artifact_event_id = self._artifact_ref_event_ids.get(ref_key)
        if artifact_event_id is None:
            raise ValueError("workspace.artifact_captured requires artifact.created")
        provenance = payload["provenance"]
        if provenance["artifact_event_id"] != artifact_event_id:
            raise ValueError("workspace.artifact_captured artifact_event_id must match artifact.created")
        if provenance["basis_event_id"] != artifact_event_id:
            raise ValueError("workspace.artifact_captured basis_event_id must match artifact.created")
        self._workspace_last_event_ids[workspace_id] = event.event_id

    def _validate_workspace_bound_to(self, bound_to: Any, label: str) -> None:
        if not isinstance(bound_to, dict):
            raise ValueError(f"{label} bound_to must be a dict")
        if not any(
            isinstance(bound_to.get(field_name), str) and bound_to[field_name]
            for field_name in ("agent_id", "execution_id", "worker_id")
        ):
            raise ValueError(f"{label} bound_to must include agent_id, execution_id, or worker_id")

    def _validate_workspace_policy_provenance(self, provenance: Any, mode: str, label: str) -> None:
        if not isinstance(provenance, dict):
            raise ValueError(f"{label} provenance must be a dict")
        decision_id = provenance.get("decision_id")
        if not isinstance(decision_id, str) or not decision_id:
            raise ValueError(f"{label} provenance.decision_id is required")
        grant_basis = provenance.get("grant_basis")
        if not isinstance(grant_basis, dict):
            raise ValueError(f"{label} provenance.grant_basis must be a dict")
        workspace_grant = grant_basis.get("workspace")
        if not isinstance(workspace_grant, dict):
            raise ValueError(f"{label} provenance.grant_basis.workspace must be a dict")
        if workspace_grant.get("mode") != mode:
            raise PermissionError(f"{label} mode must match workspace grant")

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

    def _validate_action_summary(self, value: Any, label: str) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key in self.ACTION_SUMMARY_FORBIDDEN_FIELDS:
                    raise ValueError(f"{label} cannot contain {key}")
                self._validate_action_summary(nested, f"{label}.{key}")
            return
        if isinstance(value, list):
            for index, nested in enumerate(value):
                self._validate_action_summary(nested, f"{label}[{index}]")
