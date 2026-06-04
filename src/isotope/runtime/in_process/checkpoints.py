"""Checkpoint helpers for the in-process runtime facade."""

from __future__ import annotations

from ...platform.state.projector import RunProjector


class InProcessCheckpointMixin:
    """Save runtime checkpoints through the projector boundary."""

    def save_checkpoint_for_run(self, run_id: str) -> dict[str, str]:
        self._validate_known_run_id(run_id)
        checkpoint = RunProjector().save_checkpoint(run_id, self.event_store, self.checkpoint_store)
        return {
            "status": "saved",
            "run_id": run_id,
            "basis_event_id": checkpoint["basis_event_id"],
        }

    def save_checkpoint_history_for_run(self, run_id: str) -> dict[str, str]:
        self._validate_known_run_id(run_id)
        checkpoint = RunProjector().save_checkpoint_history(run_id, self.event_store, self.checkpoint_store)
        return {
            "status": "saved",
            "run_id": run_id,
            "basis_event_id": checkpoint["basis_event_id"],
            "checkpoint_kind": "history",
        }

    def create_checkpoint(self, run_id: str) -> dict[str, str]:
        return self.save_checkpoint_for_run(run_id)
