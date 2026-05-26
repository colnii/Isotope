"""RunProjector rebuild and checkpoint helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Iterable

from ...events.events import EVENT_ENVELOPE_VERSION, CanonicalEvent
from .checkpoint_validation import RunProjectorCheckpointValidationMixin
from .state import RunState


PROJECTOR_VERSION = "run_projector@v1"


def _facade_datetime():
    from datetime import datetime as _dt

    return _dt


class RunProjectorCheckpointMixin(RunProjectorCheckpointValidationMixin):
    """Rebuild RunState from events and checkpoint snapshots."""

    def project(self, events: Iterable[CanonicalEvent]) -> RunState:
        self._proposal_outcomes = {}
        self._proposal_action_types = {}
        self._proposal_reason_codes = {}
        self._proposal_summaries = {}
        self._proposal_agents = {}
        self._proposal_grants = {}
        self._proposal_registry_basis = {}
        self._proposal_policy_basis = {}
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
        self._workspace_statuses = {}
        self._workspace_last_event_ids = {}
        self._artifact_ref_event_ids = {}
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
            "created_at": _facade_datetime().now(timezone.utc).isoformat(),
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
