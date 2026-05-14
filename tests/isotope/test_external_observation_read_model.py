from __future__ import annotations

from dataclasses import asdict

import pytest

from isotope import artifact_store, checkpoint_store, event_store, projector, refs
from isotope.events import CanonicalEvent


def _artifact_ref(artifact_id: str = "artifact_raw_001") -> dict:
    return refs.make_artifact_ref("run_001", artifact_id).to_dict()


def _event(event_id: str, event_type: str, payload: dict) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        run_id="run_001",
        event_type=event_type,
        payload=payload,
        created_at=f"2026-05-01T00:00:{event_id[-2:]}Z",
    )


def _run_created() -> CanonicalEvent:
    return _event("evt_001", "run.created", {"run_id": "run_001", "session_id": "session_001"})


def _snapshot_payload(
    snapshot_id: str = "snapshot_001",
    *,
    claimed_status: str = "completed",
    artifact_id: str = "artifact_raw_001",
    overrides: dict | None = None,
) -> dict:
    ref = _artifact_ref(artifact_id)
    payload = {
        "snapshot_id": snapshot_id,
        "source_system": "example_provider",
        "captured_at": "2026-05-01T00:00:02Z",
        "content_type": "run_status",
        "source_ref": ref,
        "summary": f"provider claims run is {claimed_status}",
        "observation": {
            "subject": {"type": "run", "id": "run_001"},
            "run_status": claimed_status,
        },
        "quality": {
            "confidence": 0.8,
            "coverage": "partial",
            "freshness": "fresh",
        },
        "provenance": {
            "provider": "example_provider",
            "capture_id": f"capture_{snapshot_id}",
            "raw_artifact_ref": ref,
        },
        "basis_refs": [ref],
    }
    if overrides:
        payload.update(overrides)
    return payload


def _snapshot_imported(
    event_id: str = "evt_002",
    snapshot_id: str = "snapshot_001",
    *,
    claimed_status: str = "completed",
    artifact_id: str = "artifact_raw_001",
    overrides: dict | None = None,
) -> CanonicalEvent:
    return _event(
        event_id,
        "snapshot.imported",
        _snapshot_payload(
            snapshot_id,
            claimed_status=claimed_status,
            artifact_id=artifact_id,
            overrides=overrides,
        ),
    )


def _external_observations(state) -> list[dict]:
    observations = getattr(state, "external_observations")
    assert isinstance(observations, list)
    return observations


def test_external_observation_read_model_exposes_stable_summary_shape():
    state = projector.RunProjector().project([_run_created(), _snapshot_imported()])

    observations = _external_observations(state)
    assert len(observations) == 1
    observation = observations[0]
    assert observation["snapshot_id"] == "snapshot_001"
    assert observation["snapshot_type"] == "run_status"
    assert observation["source_system"] == "example_provider"
    assert observation["captured_at"] == "2026-05-01T00:00:02Z"
    assert observation["status"] == "imported"
    assert observation["quality"]["confidence"] == 0.8
    assert observation["quality"]["coverage"] == "partial"
    assert observation["quality"]["freshness"] == "fresh"
    assert observation["provenance"]["raw_artifact_ref"] == _artifact_ref()
    assert observation["source_ref"] == _artifact_ref()
    assert observation["basis_refs"] == [_artifact_ref()]
    assert observation["native_status"] == "running"
    assert state.status == "running"


def test_external_observation_never_contains_raw_artifact_full_content():
    state = projector.RunProjector().project([_run_created(), _snapshot_imported()])

    observation = _external_observations(state)[0]
    forbidden_fields = {"content", "full_content", "artifact_content", "raw_content"}
    assert forbidden_fields.isdisjoint(observation)
    assert forbidden_fields.isdisjoint(observation["observation"])
    assert forbidden_fields.isdisjoint(observation["provenance"])


def test_snapshot_imported_rejects_raw_content_payload_without_partial_observation():
    raw_ref = _artifact_ref()
    malformed = _snapshot_imported(
        overrides={
            "observation": {
                "subject": {"type": "run", "id": "run_001"},
                "run_status": "completed",
                "raw_content": "provider raw transcript must stay in artifact storage",
            },
            "provenance": {
                "provider": "example_provider",
                "raw_artifact_ref": raw_ref,
            },
        }
    )

    with pytest.raises(ValueError, match="raw_content|full content|artifact content"):
        projector.RunProjector().project([_run_created(), malformed])


def test_external_observation_replay_from_event_log_restores_same_read_model(tmp_path):
    store = event_store.FileEventStore(tmp_path)
    for canonical_event in [_run_created(), _snapshot_imported()]:
        store.append(canonical_event)

    projected = projector.RunProjector().project(store.list_events("run_001"))
    rebuilt = projector.RunProjector().rebuild("run_001", store)

    assert asdict(rebuilt)["external_observations"] == asdict(projected)["external_observations"]


def test_checkpoint_includes_and_restores_external_observation_read_model(tmp_path):
    store = event_store.FileEventStore(tmp_path / "events")
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path / "checkpoints")
    for canonical_event in [_run_created(), _snapshot_imported()]:
        store.append(canonical_event)

    created_checkpoint = projector.RunProjector().create_checkpoint("run_001", store.list_events("run_001"))

    assert "external_observations" in created_checkpoint["state"]
    assert created_checkpoint["state"]["external_observations"][0]["snapshot_id"] == "snapshot_001"
    checkpoints.save_checkpoint("run_001", created_checkpoint)
    rebuilt = projector.RunProjector().rebuild_with_checkpoint("run_001", store, checkpoints)
    assert asdict(rebuilt)["external_observations"] == created_checkpoint["state"]["external_observations"]


def test_malformed_external_observation_checkpoint_state_is_rejected(tmp_path):
    store = event_store.FileEventStore(tmp_path / "events")
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path / "checkpoints")
    for canonical_event in [_run_created(), _snapshot_imported()]:
        store.append(canonical_event)
    created_checkpoint = projector.RunProjector().create_checkpoint("run_001", store.list_events("run_001"))
    created_checkpoint["state"]["external_observations"] = [{"snapshot_id": "snapshot_001"}]

    checkpoints.save_checkpoint("run_001", created_checkpoint)

    rebuilt = projector.RunProjector().rebuild_with_checkpoint("run_001", store, checkpoints)
    assert rebuilt.external_observations[0]["snapshot_type"] == "run_status"


def test_projector_does_not_read_raw_artifact_content_for_external_observation(monkeypatch):
    def fail_on_content_read(*args, **kwargs):
        raise AssertionError("projector must not read raw artifact content")

    monkeypatch.setattr(artifact_store.ArtifactStore, "get_content", fail_on_content_read)

    state = projector.RunProjector().project([_run_created(), _snapshot_imported()])
    assert _external_observations(state)[0]["snapshot_id"] == "snapshot_001"
