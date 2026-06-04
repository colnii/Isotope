"""RunProjector base event payload validation helpers."""

from __future__ import annotations

from typing import Any

from ...events.event_schema import DEFAULT_EVENT_SCHEMA_REGISTRY
from ...events.events import CanonicalEvent


class RunProjectorPayloadValidationMixin:
    """Validate common canonical event payload shapes."""

    def _validate_event_payload(self, event: CanonicalEvent) -> None:
        DEFAULT_EVENT_SCHEMA_REGISTRY.validate_event(event)
        payload = event.payload
        if event.event_type == "run.created":
            self._require_fields(event.event_type, payload, ("run_id",))
            if payload["run_id"] != event.run_id:
                raise ValueError("run.created run_id must match event run_id")
            if "goal" in payload:
                self._require_fields(event.event_type, payload, ("session_id",))
                self._metadata_string(payload, "goal", event.event_type)
            if "session_id" in payload:
                self._metadata_string(payload, "session_id", event.event_type)
        elif event.event_type == "agent.created":
            self._require_fields(event.event_type, payload, ("agent_id",))
        elif event.event_type == "action.proposed":
            self._require_fields(
                event.event_type,
                payload,
                ("proposal_id", "agent_id", "action_type", "registry_id", "registry_version"),
            )
            self._metadata_string(payload, "registry_id", event.event_type)
            self._metadata_string(payload, "registry_version", event.event_type)
            registry_basis = payload.get("registry_basis")
            if registry_basis is not None:
                if not isinstance(registry_basis, dict):
                    raise ValueError("action.proposed registry_basis must be a dict")
                if registry_basis.get("registry_id") != payload["registry_id"]:
                    raise ValueError("action.proposed registry_basis.registry_id must match registry_id")
                if registry_basis.get("registry_version") != payload["registry_version"]:
                    raise ValueError("action.proposed registry_basis.registry_version must match registry_version")
            requested_label = payload.get("requested_action_label")
            if requested_label is not None:
                if not isinstance(requested_label, dict):
                    raise ValueError("action.proposed requested_action_label must be a dict")
                self._validate_action_label(requested_label, "action.proposed requested_action_label")
        elif event.event_type == "action.decided":
            self._require_fields(
                event.event_type,
                payload,
                ("proposal_id", "decision_id", "outcome", "policy_profile_id", "policy_version"),
            )
            if payload["outcome"] not in self.KNOWN_DECISION_OUTCOMES:
                raise ValueError("action.decided has unknown outcome")
            grants = payload.get("grants")
            if grants is not None and not isinstance(grants, dict):
                raise ValueError("action.decided grants must be a dict")
            self._metadata_string(payload, "policy_profile_id", event.event_type)
            self._metadata_string(payload, "policy_version", event.event_type)
            policy_basis = payload.get("policy_basis")
            if policy_basis is not None:
                if not isinstance(policy_basis, dict):
                    raise ValueError("action.decided policy_basis must be a dict")
                if policy_basis.get("policy_profile_id") != payload["policy_profile_id"]:
                    raise ValueError("action.decided policy_basis.policy_profile_id must match policy_profile_id")
                if policy_basis.get("policy_version") != payload["policy_version"]:
                    raise ValueError("action.decided policy_basis.policy_version must match policy_version")
            reason_codes = payload.get("reason_codes", [])
            if not isinstance(reason_codes, list):
                raise ValueError("action.decided reason_codes must be a list")
            for reason_code in reason_codes:
                if not isinstance(reason_code, str) or not reason_code or not reason_code.replace("_", "").isalnum() or reason_code != reason_code.lower():
                    raise ValueError("action.decided reason_codes must be stable identifiers")
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
            self._require_fields(event.event_type, payload, ("error_reason_code", "structured_error"))
            self._validate_structured_error(payload["error_reason_code"], payload["structured_error"])
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
                ("cancel_id", "run_id", "proposal_id", "reason", "requested_by"),
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
            self._validate_resource_ref_payload(artifact["ref"], "artifact.created artifact ref")
            if "content" in artifact:
                raise ValueError("artifact.created artifact cannot contain content")
            provenance = artifact["provenance"]
            if not isinstance(provenance, dict):
                raise ValueError("artifact.created artifact provenance must be a dict")
            for field_name in ("execution_id", "proposal_id", "decision_id"):
                value = provenance.get(field_name)
                if not isinstance(value, str) or not value:
                    raise ValueError(f"artifact.created artifact provenance.{field_name} must be a non-empty string")
            for field_name in ("basis_refs", "source_refs"):
                refs = artifact.get(field_name, [])
                if not isinstance(refs, list):
                    raise ValueError(f"artifact.created artifact {field_name} must be a list")
                for index, ref in enumerate(refs):
                    self._validate_resource_ref_payload(ref, f"artifact.created artifact {field_name}[{index}]")
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
        elif event.event_type == "workspace.lease_created":
            self._validate_workspace_lease_created_payload(payload, event)
        elif event.event_type == "workspace.released":
            self._validate_workspace_released_payload(payload, event)
        elif event.event_type == "workspace.artifact_captured":
            self._validate_workspace_artifact_captured_payload(payload, event)

    def _require_fields(self, label: str, payload: dict[str, Any], fields: tuple[str, ...]) -> None:
        for field in fields:
            if field not in payload:
                raise ValueError(f"{label} missing required field: {field}")

    def _metadata_string(self, payload: dict[str, Any], field_name: str, label: str) -> str:
        value = payload.get(field_name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{label} {field_name} must be a non-empty string")
        return value

    def _validate_structured_error(self, reason_code: Any, structured_error: Any) -> None:
        if not isinstance(reason_code, str) or not reason_code:
            raise ValueError("action.failed error_reason_code must be a non-empty string")
        if reason_code != reason_code.lower() or not reason_code.replace("_", "").isalnum():
            raise ValueError("action.failed error_reason_code must be a stable identifier")
        if not isinstance(structured_error, dict):
            raise ValueError("action.failed structured_error must be a dict")
        if structured_error.get("reason_code") != reason_code:
            raise ValueError("action.failed structured_error.reason_code must match error_reason_code")
        message = structured_error.get("message")
        if not isinstance(message, str) or not message:
            raise ValueError("action.failed structured_error.message must be a non-empty string")

    def _registry_basis_from_payload(self, payload: dict[str, Any]) -> dict[str, str]:
        return {
            "registry_id": str(payload["registry_id"]),
            "registry_version": str(payload["registry_version"]),
        }

    def _policy_basis_from_payload(self, payload: dict[str, Any]) -> dict[str, str]:
        return {
            "policy_profile_id": str(payload["policy_profile_id"]),
            "policy_version": str(payload["policy_version"]),
        }
