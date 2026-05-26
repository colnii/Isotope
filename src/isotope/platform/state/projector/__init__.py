"""RunState projector boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .checkpoint import RunProjectorCheckpointMixin
from .handlers import RunProjectorHandlersMixin
from .state import RunState
from .validation import RunProjectorValidationMixin


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
        "stdout",
        "stderr",
        "text",
        "argv",
        "args",
        "shell_command",
        "command_line",
    )
    CHECKPOINT_WORKSPACE_FORBIDDEN_FIELDS = (
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
    KNOWN_WORKSPACE_LEASE_STATUSES = {
        "created",
        "active",
        "bound",
        "released",
        "expired",
        "revoked",
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
        self._supported_event_types: set[str] | None = None

    @property
    def supported_event_types(self) -> set[str]:
        if self._supported_event_types is None:
            from ...events.events import EVENT_TYPES

            self._supported_event_types = EVENT_TYPES
        return self._supported_event_types

    def rebuild(self, run_id: str, event_store: Any) -> RunState:
        return self.project(event_store.list_events(run_id))
