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
        "current_plan_id",
        "action_form",
        "pending_tool_calls",
        "awaiting_approval",
        "action_outcomes",
    )

    def __init__(self) -> None:
        self._supported_event_types: set[str] | None = None

    @property
    def supported_event_types(self) -> set[str]:
        if self._supported_event_types is None:
            from ...events.events import EVENT_TYPES

            self._supported_event_types = EVENT_TYPES
        return self._supported_event_types

    def rebuild(self, run_id: str, event_store: Any) -> RunState:
        state = RunState(run_id=run_id)
        for event in event_store.list_events(run_id):
            super().rebuild(state, event)
        return state
