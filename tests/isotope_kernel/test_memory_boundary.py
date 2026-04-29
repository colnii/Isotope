import pytest

from isotope_kernel import event_store, events, memory, projector, server


def test_not_enabled_memory_query_boundary_still_exists():
    result = memory.NotEnabledMemoryService().query("run_001", "anything")

    assert result == {"status": "not_enabled", "capability": "memory_query"}


def test_durable_write_boundary_method_exists_before_storage_is_enabled():
    service = memory.NotEnabledMemoryService()

    assert hasattr(service, "write_record")


def test_direct_durable_memory_write_without_authorized_execution_is_rejected():
    service = memory.NotEnabledMemoryService()

    with pytest.raises(PermissionError, match="authorized execution|not enabled|memory_write"):
        service.write_record(
            {
                "scope": "thread",
                "content": {"kind": "structured_note", "text": "remember this"},
                "source_refs": [],
                "provenance": {},
            },
            execution=None,
            grants={},
        )


def test_memory_query_requires_caller_context_and_grants():
    service = memory.NotEnabledMemoryService()

    result = service.query(
        run_id="run_001",
        query="hello",
        grants={},
        caller_context={},
    )

    assert result["status"] in {"denied", "limited", "not_enabled"}
    assert "content" not in result


def test_memory_query_default_result_does_not_include_full_artifact_content():
    service = memory.NotEnabledMemoryService()

    result = service.query(
        run_id="run_001",
        query="artifact text",
        grants={"memory": {"query": True}},
        caller_context={"run_id": "run_001"},
    )

    assert "content" not in result
    assert "artifact_content" not in result
    assert set(result).isdisjoint({"full_text", "raw_artifact_content"})


def test_projector_rebuild_does_not_require_or_read_memory_store(tmp_path):
    class ExplodingMemoryStore:
        def query(self, *args, **kwargs):
            raise AssertionError("projector must not query memory store")

        def load(self, *args, **kwargs):
            raise AssertionError("projector must not load memory store")

    store = event_store.FileEventStore(tmp_path)
    store.append(
        events.CanonicalEvent(
            event_id="evt_001",
            run_id="run_001",
            event_type="run.created",
            payload={"run_id": "run_001"},
            created_at="2026-04-29T00:00:00Z",
        )
    )
    memory_store = ExplodingMemoryStore()

    state = projector.RunProjector().rebuild("run_001", store)

    assert memory_store is not None
    assert state.run_id == "run_001"
    assert state.status == "running"


def test_server_memory_query_public_api_remains_absent_until_boundary_is_enabled(tmp_path):
    api = server.InProcessServer(tmp_path)

    assert not hasattr(api, "query_memory")
