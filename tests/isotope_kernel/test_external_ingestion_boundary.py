from __future__ import annotations

import importlib
import socket

import pytest

from isotope_kernel import artifact_store, event_store, http_api, projector, server
from isotope_kernel.events import CanonicalEvent


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
        {"run_id": "run_001", "session_id": "session_001", "goal": "ingest external observation"},
    )


def _ingestion_module():
    return importlib.import_module("isotope_kernel.ingestion")


def _service(tmp_path):
    ingestion = _ingestion_module()
    assert hasattr(ingestion, "ExternalIngestionService")
    return ingestion.ExternalIngestionService(
        event_store=event_store.FileEventStore(tmp_path),
        artifact_store=artifact_store.ArtifactStore(tmp_path),
    )


def _raw_provider_response() -> dict:
    return {
        "source_system": "example_provider",
        "captured_at": "2026-01-01T00:00:01Z",
        "callback_id": "callback_001",
        "body": {
            "run_id": "run_001",
            "claimed_run_status": "completed",
            "message": "provider says the run is done",
        },
    }


def test_external_ingestion_boundary_module_exists():
    ingestion = _ingestion_module()

    assert hasattr(ingestion, "ExternalIngestionService")
    assert hasattr(ingestion, "INGESTION_RESULT_STATUSES")
    assert set(ingestion.INGESTION_RESULT_STATUSES) == {
        "canonical_event",
        "imported_snapshot",
        "artifact_only",
        "rejected",
    }


def test_raw_external_input_cannot_directly_update_projected_state(tmp_path):
    store = event_store.FileEventStore(tmp_path)
    store.append(_run_created())
    before_state = projector.RunProjector().rebuild("run_001", store)

    result = _service(tmp_path).ingest_raw("run_001", _raw_provider_response())

    after_state = projector.RunProjector().rebuild("run_001", store)
    assert result["status"] in {"canonical_event", "imported_snapshot", "artifact_only", "rejected"}
    assert result["status"] != "state_updated"
    assert before_state.status == "running"
    assert after_state.status == "running"
    assert after_state.run_id == "run_001"


def test_raw_external_input_is_retained_only_through_artifact_or_rejected(tmp_path):
    store = event_store.FileEventStore(tmp_path)
    store.append(_run_created())

    result = _service(tmp_path).ingest_raw("run_001", _raw_provider_response())

    assert result["status"] in {"canonical_event", "imported_snapshot", "artifact_only", "rejected"}
    if result["status"] != "rejected":
        artifact_ref = result.get("artifact_ref") or result.get("raw_artifact_ref")
        assert isinstance(artifact_ref, dict)
        assert artifact_ref["ref_type"] == "artifact"
        assert artifact_ref["run_id"] == "run_001"


def test_malformed_external_input_is_rejected_or_artifact_only_without_state_event(tmp_path):
    store = event_store.FileEventStore(tmp_path)
    store.append(_run_created())

    result = _service(tmp_path).ingest_raw("run_001", {"source_system": "", "body": "not structured"})

    assert result["status"] in {"artifact_only", "rejected"}
    event_types = [event.event_type for event in store.list_events("run_001")]
    assert "run.completed" not in event_types
    assert "action.completed" not in event_types
    assert "snapshot.imported" not in event_types
    assert projector.RunProjector().rebuild("run_001", store).status == "running"


def test_raw_provider_callback_body_is_not_a_projector_input():
    events = [
        _run_created(),
        _event(
            "evt_002",
            "provider.callback.received",
            {
                "source_system": "example_provider",
                "body": {"claimed_run_status": "completed"},
            },
        ),
    ]

    with pytest.raises(ValueError) as exc_info:
        projector.RunProjector().project(events)

    message = str(exc_info.value)
    assert "unknown event_type" in message
    assert "provider.callback.received" in message


def test_external_ingestion_server_api_still_not_enabled_and_side_effect_free(tmp_path):
    api = server.InProcessServer(tmp_path)
    session_id = api.create_session()["session_id"]
    run_id = api.create_run(session_id, "external ingestion remains deferred")["run_id"]
    before_events = api.event_store.list_events(run_id)

    result = api.ingest_external_input(_raw_provider_response())

    assert result == {"status": "not_enabled", "capability": "external_ingestion"}
    assert api.event_store.list_events(run_id) == before_events


def test_external_ingestion_http_route_still_not_enabled_and_side_effect_free(tmp_path):
    app = http_api.create_http_app(tmp_path)
    session_id = app.request("POST", "/sessions").json()["session_id"]
    run_id = app.request("POST", f"/sessions/{session_id}/runs", json={"goal": "ingest"}).json()["run_id"]
    before_events = app.request("GET", f"/runs/{run_id}/events").json()

    response = app.request("POST", "/external-ingestion", json=_raw_provider_response())

    assert response.status_code == 501
    assert response.json()["status"] == "not_enabled"
    assert response.json()["error"]["capability"] == "external_ingestion"
    assert app.request("GET", f"/runs/{run_id}/events").json() == before_events


def test_ingestion_boundary_does_not_require_provider_adapter_or_network(monkeypatch, tmp_path):
    def fail_network(*args, **kwargs):
        raise AssertionError("external ingestion boundary must not open network connections")

    monkeypatch.setattr(socket, "create_connection", fail_network)

    result = _service(tmp_path).ingest_raw("run_001", _raw_provider_response())

    assert result["status"] in {"canonical_event", "imported_snapshot", "artifact_only", "rejected"}
