"""Event payload schema registry boundary for the Isotope v0.2 slice."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_EVENT_SCHEMA_VERSION = "v0.2"


@dataclass(frozen=True)
class EventSchemaMetadata:
    """Static payload schema metadata; this is not a JSON Schema implementation."""

    event_type: str
    event_schema_version: str = DEFAULT_EVENT_SCHEMA_VERSION
    required_fields: tuple[str, ...] = ()
    description: str = ""
    validation_owner: str = "projector"

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, str) or not self.event_type:
            raise ValueError("event schema event_type must be a non-empty string")
        if not isinstance(self.event_schema_version, str) or not self.event_schema_version:
            raise ValueError("event_schema_version must be a non-empty string")
        if not isinstance(self.required_fields, tuple):
            raise ValueError("event schema required_fields must be a tuple")
        for field_name in self.required_fields:
            if not isinstance(field_name, str) or not field_name:
                raise ValueError("event schema required field names must be non-empty strings")
        if self.validation_owner not in {"registry", "projector"}:
            raise ValueError("event schema validation_owner must be registry or projector")


class EventSchemaRegistry:
    """In-process static registry for canonical event payload schema metadata."""

    def __init__(
        self,
        entries: tuple[EventSchemaMetadata, ...],
        *,
        registry_id: str = "isotope_kernel",
        registry_version: str = DEFAULT_EVENT_SCHEMA_VERSION,
    ) -> None:
        if not isinstance(registry_id, str) or not registry_id:
            raise ValueError("event schema registry_id must be a non-empty string")
        if not isinstance(registry_version, str) or not registry_version:
            raise ValueError("event schema registry_version must be a non-empty string")
        self.registry_id = registry_id
        self.registry_version = registry_version
        self._entries = {entry.event_type: entry for entry in entries}
        if len(self._entries) != len(entries):
            raise ValueError("duplicate event schema event_type")

    @classmethod
    def default(cls) -> "EventSchemaRegistry":
        return cls(_DEFAULT_EVENT_SCHEMAS)

    def get(self, event_type: str) -> EventSchemaMetadata | None:
        return self._entries.get(event_type)

    def event_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._entries))

    def validate_event(self, event: Any) -> EventSchemaMetadata:
        metadata = self.get(event.event_type)
        if metadata is None:
            raise ValueError(f"unknown event_type: {event.event_type}")

        version = event.payload.get("event_schema_version")
        if version is None:
            return metadata
        if not isinstance(version, str) or not version:
            raise ValueError(f"{event.event_type} event_schema_version must be a non-empty string")
        if version != metadata.event_schema_version:
            raise ValueError(
                f"unsupported event_schema_version for {event.event_type}: {version}"
            )
        return metadata


def _schema(event_type: str, *required_fields: str, description: str = "") -> EventSchemaMetadata:
    return EventSchemaMetadata(
        event_type=event_type,
        required_fields=tuple(required_fields),
        description=description,
    )


_DEFAULT_EVENT_SCHEMAS = (
    _schema("run.created", "run_id"),
    _schema("run.completed", "status"),
    _schema("agent.created", "agent_id"),
    _schema("thread.created", "thread_id", "agent_id"),
    _schema("action.proposed", "proposal_id", "agent_id", "action_type", "registry_id", "registry_version"),
    _schema("action.decided", "proposal_id", "decision_id", "outcome", "policy_profile_id", "policy_version"),
    _schema("action.started", "execution_id", "proposal_id", "decision_id"),
    _schema("action.completed", "execution_id", "status", "artifact_refs"),
    _schema("action.failed", "execution_id", "proposal_id", "decision_id", "status"),
    _schema("artifact.created", "artifact"),
    _schema("approval.requested", "approval_id", "run_id", "proposal_id", "decision_id", "action_type"),
    _schema("approval.resolved", "approval_id", "run_id", "proposal_id", "decision_id", "resolution", "reason", "resolver"),
    _schema("memory.record_created", "record_id", "execution_id", "summary", "source_refs", "provenance", "basis_event_id"),
    _schema("memory.record_superseded", "old_record_id", "new_record_id", "execution_id", "reason", "provenance", "basis_event_id"),
    _schema("snapshot.imported", "snapshot_id", "source_system", "captured_at", "content_type", "source_ref", "summary", "observation", "quality", "provenance", "basis_refs"),
    _schema("delegation.proposed", "delegation_id", "run_id", "parent_agent_id", "requested_worker_role", "requested_capabilities"),
    _schema("delegation.decided", "delegation_id", "decision_id", "outcome", "grants"),
    _schema("worker.created", "worker_id", "agent_id", "run_id", "parent_agent_id", "delegation_id", "decision_id", "role", "status", "workspace"),
    _schema("worker.started", "worker_id", "delegation_id", "status"),
    _schema("worker.completed", "worker_id", "delegation_id", "status"),
    _schema("worker.failed", "worker_id", "delegation_id", "status", "error"),
    _schema("worker.cancelled", "worker_id", "delegation_id", "status", "reason"),
    _schema("worker.result_handed_off", "worker_id", "delegation_id", "artifact_ref", "summary"),
    _schema("workspace.bound", "workspace_id", "run_id", "mode", "bound_to", "lease_status", "provenance"),
    _schema("workspace.lease_created", "workspace_id", "run_id", "mode", "bound_to", "lease_status", "granted_by", "created_by", "provenance"),
    _schema("workspace.released", "workspace_id", "run_id", "lease_status", "released_by", "released_at", "basis_event_id"),
    _schema("workspace.artifact_captured", "workspace_id", "run_id", "artifact_ref", "captured_by", "provenance"),
    _schema("action.retry_requested", "retry_id", "run_id", "original_proposal_id", "original_execution_id", "reason", "requested_by"),
    _schema("action.retry_created", "retry_id", "new_proposal_id", "original_proposal_id", "basis_event_id", "policy_basis"),
    _schema("action.cancel_requested", "cancel_id", "run_id", "proposal_id", "reason", "requested_by"),
    _schema("action.cancelled", "cancel_id", "proposal_id", "execution_id", "status", "basis_event_id", "reason"),
    _schema("action.superseded", "supersession_id", "old_proposal_id", "new_proposal_id", "reason", "basis_event_id"),
)


DEFAULT_EVENT_SCHEMA_REGISTRY = EventSchemaRegistry.default()
