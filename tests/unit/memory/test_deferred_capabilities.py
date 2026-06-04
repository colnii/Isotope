import isotope.memory as memory
import isotope.runtime.in_process as server


def test_memory_query_service_returns_ok_results(tmp_path):
    store = memory.FileMemoryStore(tmp_path)
    service = memory.LocalMemoryQueryService(store)

    result = service.query(
        "run_001",
        "anything",
        grants={"memory": {"query": True}},
        caller_context={"run_id": "run_001", "caller": "pytest", "purpose": "query"},
    )

    assert result["status"] == "ok"
    assert result["capability"] == "memory_query"
    assert result["results"] == []


def test_external_ingestion_captures_structured_input(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], "ingest external input")

    result = api.ingest_external_input(
        {
            "run_id": run["run_id"],
            "source_system": "pytest",
            "captured_at": "2026-06-04T00:00:00Z",
            "body": {"message": "input"},
        }
    )

    assert result["status"] == "artifact_only"
    assert result["artifact_ref"]["ref_type"] == "artifact"


def test_checkpoint_saves_current_run_state(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], "save checkpoint")

    result = api.create_checkpoint(run["run_id"])

    assert result["status"] == "saved"
    assert result["run_id"] == run["run_id"]
    assert result["basis_event_id"].startswith("evt_")
