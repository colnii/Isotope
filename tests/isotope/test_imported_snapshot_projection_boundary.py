from __future__ import annotations

import pytest

import isotope.workspace.artifacts as artifact_store
import isotope.platform.state.event_store as event_store
import isotope.platform.schemas.models as models
import isotope.platform.state.projector as projector
import isotope.platform.schemas.refs as refs
from isotope.platform.events.events import CanonicalEvent


def _artifact_ref() -> refs.ResourceRef:
    return refs.make_artifact_ref("run_001", "artifact_raw_001")


def _event(event_id: str, event_type: str, payload: dict) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        run_id="run_001",
        event_type=event_type,
        payload=payload,
        created_at="2026-01-01T00:00:00Z",
    )


def _run_created() -> CanonicalEvent:
    return _event(
        "evt_001",
        "run.created",
        {"run_id": "run_001", "session_id": "session_001", "goal": "import snapshot"},
    )


def _snapshot_payload(
    snapshot_id: str = "snapshot_001",
    *,
    claimed_status: str = "completed",
    source_ref: dict | str | None = None,
    confidence: float = 0.8,
    basis_refs: list[dict] | None = None,
) -> dict:
    ref = _artifact_ref().to_dict() if source_ref is None else source_ref
    return {
        "snapshot_id": snapshot_id,
        "source_system": "example_provider",
        "captured_at": "2026-01-01T00:00:01Z",
        "content_type": "run_status",
        "source_ref": ref,
        "summary": f"provider claims run is {claimed_status}",
        "observation": {"run_status": claimed_status},
        "quality": {
            "confidence": confidence,
            "coverage": "partial",
            "freshness": "fresh",
        },
        "provenance": {
            "provider": "example_provider",
            "capture_id": f"capture_{snapshot_id}",
            "raw_artifact_ref": ref,
        },
        "basis_refs": [_artifact_ref().to_dict()] if basis_refs is None else basis_refs,
    }


def _snapshot_imported(
    event_id: str = "evt_002",
    snapshot_id: str = "snapshot_001",
    *,
    claimed_status: str = "completed",
    source_ref: dict | str | None = None,
    confidence: float = 0.8,
    basis_refs: list[dict] | None = None,
) -> CanonicalEvent:
    return _event(
        event_id,
        "snapshot.imported",
        _snapshot_payload(
            snapshot_id,
            claimed_status=claimed_status,
            source_ref=source_ref,
            confidence=confidence,
            basis_refs=basis_refs,
        ),
    )


def _external_observations(state) -> list[dict]:
    observations = getattr(state, "external_observations", None)
    if observations is None:
        observations = getattr(state, "observations", None)
    assert isinstance(observations, list)
    return observations


def test_imported_snapshot_slice_model_exists_and_requires_boundary_fields():
    assert hasattr(models, "ImportedSnapshot")

    snapshot = models.ImportedSnapshot(
        snapshot_id="snapshot_001",
        source_system="example_provider",
        captured_at="2026-01-01T00:00:01Z",
        content_type="run_status",
        source_ref=_artifact_ref(),
        summary="provider claims run is completed",
        observation={"run_status": "completed"},
        quality={"confidence": 0.8, "coverage": "partial", "freshness": "fresh"},
        provenance={"raw_artifact_ref": _artifact_ref().to_dict()},
        basis_refs=[_artifact_ref().to_dict()],
    )

    assert snapshot.snapshot_id == "snapshot_001"
    assert snapshot.source_system == "example_provider"
    assert snapshot.quality["confidence"] == 0.8
    assert snapshot.provenance["raw_artifact_ref"]["ref_type"] == "artifact"


def test_imported_snapshot_rejects_uri_string_ref():
    assert hasattr(models, "ImportedSnapshot")

    with pytest.raises((TypeError, ValueError), match="ResourceRef|structured|source_ref|URI"):
        models.ImportedSnapshot(
            snapshot_id="snapshot_001",
            source_system="example_provider",
            captured_at="2026-01-01T00:00:01Z",
            content_type="run_status",
            source_ref="artifact://run_001/artifact_raw_001",
            summary="provider claims run is completed",
            observation={"run_status": "completed"},
            quality={"confidence": 0.8, "coverage": "partial", "freshness": "fresh"},
            provenance={"raw_artifact_ref": "artifact://run_001/artifact_raw_001"},
            basis_refs=[_artifact_ref().to_dict()],
        )


def test_snapshot_imported_canonical_event_projects_observation_only():
    state = projector.RunProjector().project([_run_created(), _snapshot_imported()])

    observations = _external_observations(state)
    assert state.status == "running"
    assert state.actions == {}
    assert observations == [
        {
            "snapshot_id": "snapshot_001",
            "source_system": "example_provider",
            "content_type": "run_status",
            "summary": "provider claims run is completed",
            "observation": {"run_status": "completed"},
            "quality": {"confidence": 0.8, "coverage": "partial", "freshness": "fresh"},
            "basis_refs": [_artifact_ref().to_dict()],
            "conflict_status": "none",
        }
    ]


def test_projector_does_not_read_raw_artifact_content_for_imported_snapshot(monkeypatch):
    def fail_on_content_read(*args, **kwargs):
        raise AssertionError("projector must not read raw artifact content for snapshot.imported")

    monkeypatch.setattr(artifact_store.ArtifactStore, "get_content", fail_on_content_read)

    projector.RunProjector().project([_run_created(), _snapshot_imported()])


def test_imported_observation_preserves_quality_freshness_and_basis_refs():
    state = projector.RunProjector().project([_run_created(), _snapshot_imported()])

    observation = _external_observations(state)[0]
    assert observation["quality"]["confidence"] == 0.8
    assert observation["quality"]["coverage"] == "partial"
    assert observation["quality"]["freshness"] == "fresh"
    assert observation["basis_refs"] == [_artifact_ref().to_dict()]


def test_native_canonical_event_status_wins_over_imported_snapshot_claim():
    state = projector.RunProjector().project([_run_created(), _snapshot_imported(claimed_status="completed")])

    assert state.status == "running"
    observation = _external_observations(state)[0]
    assert observation["observation"]["run_status"] == "completed"
    assert observation["native_status"] == "running"


def test_conflicting_snapshots_are_marked_conflict_not_merged_to_certainty():
    state = projector.RunProjector().project(
        [
            _run_created(),
            _snapshot_imported("evt_002", "snapshot_001", claimed_status="completed", confidence=0.8),
            _snapshot_imported("evt_003", "snapshot_002", claimed_status="failed", confidence=0.7),
        ]
    )

    observations = _external_observations(state)
    assert {observation["snapshot_id"] for observation in observations} == {"snapshot_001", "snapshot_002"}
    assert {observation["conflict_status"] for observation in observations} == {"conflict"}
    assert state.status == "running"


def test_snapshot_imported_rejects_uri_string_source_ref():
    with pytest.raises((TypeError, ValueError), match="ResourceRef|structured|source_ref|URI"):
        projector.RunProjector().project(
            [
                _run_created(),
                _snapshot_imported(source_ref="artifact://run_001/artifact_raw_001"),
            ]
        )


def test_replay_from_event_log_restores_imported_observation_read_model(tmp_path):
    store = event_store.FileEventStore(tmp_path)
    store.append(_run_created())
    store.append(_snapshot_imported())

    rebuilt = projector.RunProjector().rebuild("run_001", store)

    observations = _external_observations(rebuilt)
    assert len(observations) == 1
    assert observations[0]["snapshot_id"] == "snapshot_001"
    assert observations[0]["basis_refs"] == [_artifact_ref().to_dict()]
