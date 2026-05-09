from __future__ import annotations

import inspect

import pytest

from isotope_kernel import demo
from isotope_kernel.models import ImportedSnapshot
from isotope_kernel.refs import make_artifact_ref
from isotope_kernel.server import InProcessServer


def _snapshot(run_id: str, snapshot_id: str = "snapshot_001") -> ImportedSnapshot:
    ref = make_artifact_ref(run_id, f"artifact_{snapshot_id}")
    return ImportedSnapshot(
        snapshot_id=snapshot_id,
        source_system="example_provider",
        captured_at="2026-05-10T00:40:00Z",
        content_type="run_status",
        source_ref=ref,
        summary="provider claims run is completed",
        observation={
            "subject": {"type": "run", "id": run_id},
            "run_status": "completed",
        },
        quality={"confidence": 0.73, "coverage": "partial", "freshness": "fresh"},
        provenance={
            "provider": "example_provider",
            "capture_id": f"capture_{snapshot_id}",
            "raw_artifact_ref": ref.to_dict(),
        },
        basis_refs=[ref.to_dict()],
    )


def _server_with_run(tmp_path):
    server = InProcessServer(tmp_path)
    session = server.create_session()
    run = server.create_run(session["session_id"], goal="external snapshot helper")
    return server, run["run_id"]


def test_import_external_snapshot_appends_canonical_event_and_returns_observation(tmp_path):
    server, run_id = _server_with_run(tmp_path)

    result = server.import_external_snapshot(run_id, _snapshot(run_id))

    events = server.get_events(run_id)
    assert [event.event_type for event in events].count("snapshot.imported") == 1
    assert result["status"] in {"imported", "conflict"}
    assert result["snapshot_id"] == "snapshot_001"
    assert result["event_type"] == "snapshot.imported"
    assert result["basis_event_id"] == events[-1].event_id
    assert result["external_observation"]["snapshot_id"] == "snapshot_001"
    assert result["external_observation"]["source_ref"]["run_id"] == run_id
    assert "raw_external_content" not in result
    assert "provider_body" not in result


def test_import_external_snapshot_prevalidates_and_appends_no_partial_event_on_bad_ref(tmp_path):
    server, run_id = _server_with_run(tmp_path)
    snapshot = _snapshot("other_run", "snapshot_bad_ref")

    with pytest.raises(ValueError, match="run_id|source_ref|basis_refs|raw_artifact_ref"):
        server.import_external_snapshot(run_id, snapshot)

    assert "snapshot.imported" not in [event.event_type for event in server.get_events(run_id)]


def test_import_external_snapshot_rejects_mismatched_observation_subject_without_partial_event(tmp_path):
    server, run_id = _server_with_run(tmp_path)
    snapshot = _snapshot(run_id, "snapshot_bad_subject")
    snapshot = ImportedSnapshot(
        snapshot_id=snapshot.snapshot_id,
        source_system=snapshot.source_system,
        captured_at=snapshot.captured_at,
        content_type=snapshot.content_type,
        source_ref=snapshot.source_ref,
        summary=snapshot.summary,
        observation={"subject": {"type": "run", "id": "other_run"}, "run_status": "completed"},
        quality=snapshot.quality,
        provenance=snapshot.provenance,
        basis_refs=snapshot.basis_refs,
    )

    with pytest.raises(ValueError, match="observation.subject"):
        server.import_external_snapshot(run_id, snapshot)

    assert "snapshot.imported" not in [event.event_type for event in server.get_events(run_id)]


def test_external_snapshot_review_demo_uses_import_helper_not_private_append_glue():
    source = inspect.getsource(demo._run_external_snapshot_review_spike)

    assert "import_external_snapshot" in source
    assert "app.server._append(" not in source


def test_import_external_snapshot_does_not_open_raw_ingestion_api(tmp_path):
    server, _run_id = _server_with_run(tmp_path)

    assert server.ingest_external_input({"source_system": "example_provider"}) == {
        "status": "not_enabled",
        "capability": "external_ingestion",
    }
