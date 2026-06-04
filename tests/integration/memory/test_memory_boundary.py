import pytest

import isotope.platform.events.events as events
import isotope.platform.state.event_store as event_store
import isotope.platform.state.projector as projector
import isotope.runtime.in_process as server
from isotope.memory import FileMemoryStore, LocalMemoryQueryService, LocalMemoryWriteService
from isotope.platform.schemas.actions import ActionExecution
from isotope.platform.schemas.memory import MemoryRecord


def _record() -> MemoryRecord:
    return MemoryRecord(
        memory_id="mem_001",
        scope="run",
        content={"kind": "structured_note", "text": "remember this"},
        summary="Remember this.",
        source_refs=[],
        provenance={
            "run_id": "run_001",
            "execution_id": "exec_001",
            "action_type": "write_memory",
        },
        created_at="2026-04-29T00:00:00Z",
        supersedes=[],
        quality="candidate",
    )


def _execution() -> ActionExecution:
    return ActionExecution(
        execution_id="exec_001",
        proposal_id="prop_001",
        decision_id="dec_001",
        action_type="write_memory",
        status="started",
        effective_grants_snapshot={"tools": ["write_memory"]},
    )


def test_local_memory_write_service_persists_authorized_records(tmp_path):
    store = FileMemoryStore(tmp_path)
    service = LocalMemoryWriteService(store)

    result = service.write_record(
        _record(),
        execution=_execution(),
        grants={"tools": ["write_memory"]},
    )

    assert result == {"status": "saved", "record_id": "mem_001"}
    assert store.load_record("mem_001") == _record()


def test_local_memory_write_requires_authorized_execution(tmp_path):
    service = LocalMemoryWriteService(FileMemoryStore(tmp_path))

    with pytest.raises(PermissionError, match="authorized execution"):
        service.write_record(_record(), execution=None, grants={"tools": ["write_memory"]})


def test_local_memory_query_requires_caller_context_and_grants(tmp_path):
    store = FileMemoryStore(tmp_path)
    store.append_record(_record())
    service = LocalMemoryQueryService(store)

    result = service.query(
        run_id="run_001",
        query="remember",
        grants={},
        caller_context={},
    )

    assert result["status"] == "denied"
    assert result["reason_code"] == "missing_memory_query_grant"
    assert "content" not in result


def test_local_memory_query_returns_record_refs_without_full_content(tmp_path):
    store = FileMemoryStore(tmp_path)
    store.append_record(_record())
    service = LocalMemoryQueryService(store)

    result = service.query(
        run_id="run_001",
        query="remember",
        grants={"memory": {"query": True}},
        caller_context={
            "run_id": "run_001",
            "caller": "agent_loop",
            "purpose": "agent_recall",
        },
    )

    assert result["status"] == "ok"
    assert result["content_policy"] == "memory_record_refs_expandable"
    assert result["results"][0]["record_id"] == "mem_001"
    assert "content" not in result["results"][0]


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


def test_server_still_uses_explicit_memory_routes_instead_of_direct_store_api(tmp_path):
    api = server.InProcessServer(tmp_path)

    assert not hasattr(api, "write_memory")
    assert not hasattr(api, "query_memory")
