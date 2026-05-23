"""Checkpoint helpers for the in-process runtime facade."""

from __future__ import annotations

from ..platform.errors import not_enabled_result
from ..platform.state.projector import RunProjector


class InProcessCheckpointMixin:
    """Save runtime checkpoints through the projector boundary."""

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
