"""RunState read-model types for canonical event projection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass
class RunState:
    """In-memory read model for the v0.1 slice, not a source of truth."""

    run_id: str = ""
    session_id: str = ""
    goal: str = ""
    status: str = "unknown"
    created_event_id: str = ""
    completed_event_id: str = ""
    current_agent: str = ""
    agents: dict[str, dict[str, Any]] = field(default_factory=dict)
    delegations: dict[str, dict[str, Any]] = field(default_factory=dict)
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
