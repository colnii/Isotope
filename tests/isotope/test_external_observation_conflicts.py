from __future__ import annotations

from dataclasses import asdict

import isotope.workspace.artifacts as artifact_store
import isotope.platform.state.event_store as event_store
import isotope.platform.state.projector as projector
import isotope.platform.schemas.refs as refs
from isotope.platform.events.events import CanonicalEvent


def _artifact_ref(artifact_id: str) -> dict:
    return refs.make_artifact_ref("run_001", artifact_id).to_dict()


def _event(event_id: str, event_type: str, payload: dict) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        run_id="run_001",
        event_type=event_type,
        payload=payload,
        created_at=f"2026-05-01T00:01:{event_id[-2:]}Z",
    )


def _run_created() -> CanonicalEvent:
    return _event("evt_001", "run.created", {"run_id": "run_001", "session_id": "session_001"})


def _completed_run_events() -> list[CanonicalEvent]:
    return [
        _run_created(),
        _event(
            "evt_002",
            "action.proposed",
            {
                "proposal_id": "proposal_001",
                "agent_id": "agent_supervisor",
                "action_type": "write_artifact_tool",
                "registry_id": "default",
                "registry_version": "v0.2",
                "payload": {"tool": "write_artifact_tool"},
            },
        ),
        _event(
            "evt_003",
            "action.decided",
            {
                "proposal_id": "proposal_001",
                "decision_id": "decision_001",
                "outcome": "approved",
                "policy_profile_id": "default",
                "policy_version": "v0.2",
            },
        ),
        _event(
            "evt_004",
            "action.started",
            {
                "execution_id": "execution_001",
                "proposal_id": "proposal_001",
                "decision_id": "decision_001",
            },
        ),
        _event(
            "evt_005",
            "action.completed",
            {
                "execution_id": "execution_001",
                "status": "completed",
                "artifact_refs": [],
            },
        ),
        _event("evt_006", "run.completed", {"run_id": "run_001", "status": "completed"}),
    ]


def _snapshot_payload(
    snapshot_id: str,
    *,
    claimed_status: str,
    artifact_id: str,
    subject_id: str = "run_001",
) -> dict:
    ref = _artifact_ref(artifact_id)
    return {
        "snapshot_id": snapshot_id,
        "source_system": "example_provider",
        "captured_at": "2026-05-01T00:01:07Z",
        "content_type": "run_status",
        "source_ref": ref,
        "summary": f"provider claims run is {claimed_status}",
        "observation": {
            "subject": {"type": "run", "id": subject_id},
            "run_status": claimed_status,
        },
        "quality": {
            "confidence": 0.7,
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


def _snapshot_imported(
    event_id: str,
    snapshot_id: str,
    *,
    claimed_status: str,
    artifact_id: str,
    subject_id: str = "run_001",
) -> CanonicalEvent:
    return _event(
        event_id,
        "snapshot.imported",
        _snapshot_payload(
            snapshot_id,
            claimed_status=claimed_status,
            artifact_id=artifact_id,
            subject_id=subject_id,
        ),
    )


def _observations(state) -> list[dict]:
    observations = getattr(state, "external_observations")
    assert isinstance(observations, list)
    return observations


def test_duplicate_snapshot_identity_is_controlled_without_duplicate_read_model_entry():
    state = projector.RunProjector().project(
        [
            _run_created(),
            _snapshot_imported("evt_002", "snapshot_001", claimed_status="completed", artifact_id="artifact_raw_001"),
            _snapshot_imported("evt_003", "snapshot_001", claimed_status="failed", artifact_id="artifact_raw_002"),
        ]
    )

    observations = _observations(state)
    assert [observation["snapshot_id"] for observation in observations].count("snapshot_001") == 1
    observation = observations[0]
    assert observation["conflict_status"] == "conflict"
    assert observation["status"] == "conflict"
    assert {ref["artifact_id"] for ref in observation["basis_refs"]} == {
        "artifact_raw_001",
        "artifact_raw_002",
    }
    assert state.status == "running"


def test_same_external_subject_conflict_is_marked_without_native_status_override():
    state = projector.RunProjector().project(
        [
            _run_created(),
            _snapshot_imported("evt_002", "snapshot_001", claimed_status="completed", artifact_id="artifact_raw_001"),
            _snapshot_imported("evt_003", "snapshot_002", claimed_status="failed", artifact_id="artifact_raw_002"),
        ]
    )

    observations = _observations(state)
    assert {observation["snapshot_id"] for observation in observations} == {"snapshot_001", "snapshot_002"}
    assert {observation["conflict_status"] for observation in observations} == {"conflict"}
    assert {observation["status"] for observation in observations} == {"conflict"}
    assert all(observation["basis_refs"] for observation in observations)
    assert state.status == "running"


def test_native_completed_status_wins_over_imported_failed_observation():
    state = projector.RunProjector().project(
        [
            *_completed_run_events(),
            _snapshot_imported("evt_007", "snapshot_001", claimed_status="failed", artifact_id="artifact_raw_001"),
        ]
    )

    observations = _observations(state)
    assert state.status == "completed"
    assert state.actions["execution_001"]["status"] == "completed"
    assert observations[0]["observation"]["run_status"] == "failed"
    assert observations[0]["native_status"] == "completed"
    assert observations[0]["status"] == "imported"


def test_conflicting_imported_observations_do_not_merge_into_native_fact():
    state = projector.RunProjector().project(
        [
            _run_created(),
            _snapshot_imported("evt_002", "snapshot_001", claimed_status="completed", artifact_id="artifact_raw_001"),
            _snapshot_imported("evt_003", "snapshot_002", claimed_status="failed", artifact_id="artifact_raw_002"),
        ]
    )

    assert state.status == "running"
    assert state.actions == {}
    assert "run_status" not in asdict(state)


def test_conflict_read_model_replays_consistently_from_event_log(tmp_path):
    store = event_store.FileEventStore(tmp_path)
    for canonical_event in [
        _run_created(),
        _snapshot_imported("evt_002", "snapshot_001", claimed_status="completed", artifact_id="artifact_raw_001"),
        _snapshot_imported("evt_003", "snapshot_002", claimed_status="failed", artifact_id="artifact_raw_002"),
    ]:
        store.append(canonical_event)

    projected = projector.RunProjector().project(store.list_events("run_001"))
    rebuilt = projector.RunProjector().rebuild("run_001", store)

    assert asdict(rebuilt)["external_observations"] == asdict(projected)["external_observations"]
    assert {observation["conflict_status"] for observation in rebuilt.external_observations} == {"conflict"}


def test_conflict_projection_does_not_read_raw_artifact_content(monkeypatch):
    def fail_on_content_read(*args, **kwargs):
        raise AssertionError("projector must not read raw artifact content")

    monkeypatch.setattr(artifact_store.ArtifactStore, "get_content", fail_on_content_read)

    state = projector.RunProjector().project(
        [
            _run_created(),
            _snapshot_imported("evt_002", "snapshot_001", claimed_status="completed", artifact_id="artifact_raw_001"),
            _snapshot_imported("evt_003", "snapshot_002", claimed_status="failed", artifact_id="artifact_raw_002"),
        ]
    )
    assert {observation["conflict_status"] for observation in state.external_observations} == {"conflict"}
