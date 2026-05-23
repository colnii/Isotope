"""External snapshot import helpers for the in-process runtime."""

from __future__ import annotations

from typing import Any

from ..platform.events.events import CanonicalEvent
from ..platform.ids import new_id
from ..platform.schemas.snapshots import ImportedSnapshot
from ..platform.state.projector import RunProjector


class InProcessSnapshotMixin:
    """Import external snapshots through canonical event projection."""

    def import_external_snapshot(self, run_id: str, snapshot: ImportedSnapshot) -> dict[str, Any]:
        self._validate_existing_run_id(run_id)
        if not isinstance(snapshot, ImportedSnapshot):
            raise TypeError("external snapshot import requires an ImportedSnapshot")

        payload = self._payload_from_imported_snapshot(run_id, snapshot)
        event = CanonicalEvent(
            event_id=new_id("evt"),
            run_id=run_id,
            event_type="snapshot.imported",
            payload=payload,
            created_at="2026-04-27T00:00:00Z",
        )

        # Validate the candidate against the full replay path before append so
        # malformed snapshots cannot leave partial event-log state.
        existing_events = self.event_store.list_events(run_id)
        RunProjector().project([*existing_events, event])
        appended = self.event_store.append(event)
        state = self.get_run_state(run_id)
        observation = self._find_external_observation(state, snapshot.snapshot_id)
        if observation is None:
            raise ValueError("snapshot.imported did not project an external observation")
        return {
            "status": observation["status"],
            "run_id": run_id,
            "snapshot_id": snapshot.snapshot_id,
            "event_type": appended.event_type,
            "basis_event_id": appended.event_id,
            "external_observation": dict(observation),
        }

    def _payload_from_imported_snapshot(self, run_id: str, snapshot: ImportedSnapshot) -> dict[str, Any]:
        self._validate_snapshot_ref_run_id(snapshot.source_ref.to_dict(), run_id, "source_ref")
        provenance = dict(snapshot.provenance)
        self._validate_snapshot_ref_run_id(provenance["raw_artifact_ref"], run_id, "provenance.raw_artifact_ref")
        basis_refs = [dict(ref) for ref in snapshot.basis_refs]
        for index, ref in enumerate(basis_refs):
            self._validate_snapshot_ref_run_id(ref, run_id, f"basis_refs[{index}]")

        observation = dict(snapshot.observation)
        subject = observation.get("subject")
        if subject is not None and subject != {"type": "run", "id": run_id}:
            raise ValueError("snapshot observation.subject must match target run")

        return {
            "snapshot_id": snapshot.snapshot_id,
            "source_system": snapshot.source_system,
            "captured_at": snapshot.captured_at,
            "content_type": snapshot.content_type,
            "source_ref": snapshot.source_ref.to_dict(),
            "summary": snapshot.summary,
            "observation": observation,
            "quality": dict(snapshot.quality),
            "provenance": provenance,
            "basis_refs": basis_refs,
        }

    def _validate_snapshot_ref_run_id(self, ref: dict[str, Any], run_id: str, label: str) -> None:
        ref_run_id = ref.get("run_id")
        if ref_run_id != run_id:
            raise ValueError(f"snapshot {label}.run_id must match target run_id")

    def _find_external_observation(self, state, snapshot_id: str) -> dict[str, Any] | None:
        for observation in state.external_observations:
            if observation.get("snapshot_id") == snapshot_id:
                return observation
        return None
