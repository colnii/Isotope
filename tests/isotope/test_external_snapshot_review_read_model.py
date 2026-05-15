from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

import isotope.workspace.artifacts as artifact_store
import isotope.platform.state.checkpoint_store as checkpoint_store
import isotope.platform.state.event_store as event_store
import isotope.platform.state.projector as projector
import isotope.platform.schemas.refs as refs
from isotope.demo import run_demo
from isotope.platform.events.events import CanonicalEvent


SCENARIO = "external-snapshot-review"

FORBIDDEN_CONTENT_KEYS = {
    "artifact_content",
    "content",
    "full_content",
    "provider_body",
    "raw_artifact_content",
    "raw_content",
    "raw_external_content",
    "raw_provider_body",
}


def _artifact_ref(artifact_id: str) -> dict[str, Any]:
    return refs.make_artifact_ref("run_001", artifact_id).to_dict()


def _event(event_id: str, event_type: str, payload: dict[str, Any]) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        run_id="run_001",
        event_type=event_type,
        payload=payload,
        created_at=f"2026-05-01T00:02:{event_id[-2:]}Z",
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
) -> dict[str, Any]:
    ref = _artifact_ref(artifact_id)
    return {
        "snapshot_id": snapshot_id,
        "source_system": "example_provider",
        "captured_at": "2026-05-01T00:02:07Z",
        "content_type": "run_status",
        "source_ref": ref,
        "summary": f"provider claims run is {claimed_status}",
        "observation": {
            "subject": {"type": "run", "id": "run_001"},
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
) -> CanonicalEvent:
    return _event(
        event_id,
        "snapshot.imported",
        _snapshot_payload(
            snapshot_id,
            claimed_status=claimed_status,
            artifact_id=artifact_id,
        ),
    )


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        assert FORBIDDEN_CONTENT_KEYS.isdisjoint(value)
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def _conflicting_snapshot_events() -> list[CanonicalEvent]:
    return [
        _run_created(),
        _snapshot_imported(
            "evt_002",
            "snapshot_001",
            claimed_status="completed",
            artifact_id="artifact_raw_001",
        ),
        _snapshot_imported(
            "evt_003",
            "snapshot_002",
            claimed_status="failed",
            artifact_id="artifact_raw_002",
        ),
    ]


def test_external_snapshot_review_run_demo_projects_observations_and_conflicts(tmp_path):
    data = run_demo(tmp_path, scenario=SCENARIO)

    assert data["scenario"] == SCENARIO
    assert data["snapshot_imported_ok"] is True
    assert data["external_observation_count"] >= 2
    assert data["conflict_diagnostics_count"] >= 1
    assert data["native_state_preserved"] is True
    assert data["provider_status"] == "boundary_only"
    assert isinstance(data["external_observations"], list)
    assert all(observation["status"] in {"imported", "conflict"} for observation in data["external_observations"])


def test_external_snapshot_review_replay_and_checkpoint_restore_same_read_model(tmp_path):
    data = run_demo(tmp_path, scenario=SCENARIO)

    assert data["replay_ok"] is True
    assert data["checkpoint_ok"] is True
    assert data["replay_external_observations"] == data["external_observations"]
    assert data["checkpoint_external_observations"] == data["external_observations"]


def test_external_snapshot_review_diagnostics_exclude_raw_provider_content(tmp_path):
    data = run_demo(tmp_path, scenario=SCENARIO)

    assert data["conflict_diagnostics_count"] >= 1
    assert "raw provider body" not in json.dumps(data, sort_keys=True).lower()
    _assert_no_forbidden_content_keys(data)


def test_conflicting_snapshot_events_preserve_native_status_in_projector():
    state = projector.RunProjector().project(_conflicting_snapshot_events())

    assert state.status == "running"
    assert state.actions == {}
    assert {observation["status"] for observation in state.external_observations} == {"conflict"}
    assert {observation["conflict_status"] for observation in state.external_observations} == {"conflict"}


def test_native_completed_state_wins_over_external_snapshot_review_claim():
    state = projector.RunProjector().project(
        [
            *_completed_run_events(),
            _snapshot_imported(
                "evt_007",
                "snapshot_001",
                claimed_status="failed",
                artifact_id="artifact_raw_001",
            ),
        ]
    )

    assert state.status == "completed"
    assert state.actions["execution_001"]["status"] == "completed"
    observation = state.external_observations[0]
    assert observation["observation"]["run_status"] == "failed"
    assert observation["native_status"] == "completed"
    assert observation["status"] == "imported"


def test_external_snapshot_review_checkpoint_assisted_rebuild_preserves_observations(tmp_path):
    store = event_store.FileEventStore(tmp_path / "events")
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path / "checkpoints")
    for canonical_event in _conflicting_snapshot_events():
        store.append(canonical_event)

    projected = projector.RunProjector().rebuild("run_001", store)
    checkpoint = projector.RunProjector().save_checkpoint("run_001", store, checkpoints)
    rebuilt = projector.RunProjector().rebuild_with_checkpoint("run_001", store, checkpoints)

    assert "external_observations" in checkpoint["state"]
    assert asdict(rebuilt)["external_observations"] == asdict(projected)["external_observations"]
    assert {observation["status"] for observation in rebuilt.external_observations} == {"conflict"}


def test_external_snapshot_review_projector_does_not_read_raw_artifact_content(monkeypatch):
    def fail_on_content_read(*args, **kwargs):
        raise AssertionError("projector must not read raw artifact content")

    monkeypatch.setattr(artifact_store.ArtifactStore, "get_content", fail_on_content_read)

    state = projector.RunProjector().project(_conflicting_snapshot_events())
    assert len(state.external_observations) == 2
