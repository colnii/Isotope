"""RunState projector boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .projector_checkpoint import RunProjectorCheckpointMixin
from .projector_handlers import RunProjectorHandlersMixin
from .projector_state import RunState
from .projector_validation import RunProjectorValidationMixin


class RunProjector(RunProjectorCheckpointMixin, RunProjectorHandlersMixin, RunProjectorValidationMixin):
    """Project RunState only from canonical events."""

    EXECUTABLE_DECISION_OUTCOMES = {"approved", "modified"}
    KNOWN_DECISION_OUTCOMES = {"approved", "modified", "denied", "pending_user_approval"}
    KNOWN_RUN_STATUSES = {"unknown", "running", "pending_user_approval", "denied", "failed", "completed"}
    CHECKPOINT_STATE_FIELDS = (
        "run_id",
        "session_id",
        "goal",
        "status",
        "created_event_id",
        "completed_event_id",
        "current_agent",
        "agents",
        "delegations",
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
    ACTION_SUMMARY_FORBIDDEN_FIELDS = (
        "content",
        "full_content",
        "artifact_content",
        "raw_content",
        "stdout",
        "stderr",
        "text",
        "argv",
        "args",
        "shell_command",
        "command_line",
    )
    CHECKPOINT_EXTERNAL_OBSERVATION_FORBIDDEN_FIELDS = (
        "content",
        "full_content",
        "artifact_content",
        "raw_content",
    )
    CHECKPOINT_WORKSPACE_FORBIDDEN_FIELDS = (
        "content",
        "full_content",
        "artifact_content",
        "raw_content",
        "workspace_file_content",
        "file_content",
        "binary_content",
    )
    KNOWN_WORKSPACE_LEASE_STATUSES = {
        "created",
        "active",
        "bound",
        "released",
        "expired",
        "revoked",
        "release_failed",
    }
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
        self._proposal_registry_basis: dict[str, dict[str, str]] = {}
        self._proposal_policy_basis: dict[str, dict[str, str]] = {}
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
        self._workspace_statuses: dict[str, str] = {}
        self._workspace_last_event_ids: dict[str, str] = {}
        self._artifact_ref_event_ids: dict[str, str] = {}
        self._run_completed = False


__all__ = ["RunProjector", "RunState"]
