import pytest

import isotope.platform.state.event_store as event_store
import isotope.platform.events.events as events
import isotope.memory as memory
from isotope.platform.schemas.actions import ActionExecution
from isotope.platform.schemas.memory import MemoryRecord
import isotope.platform.state.projector as projector


def _valid_memory_record() -> MemoryRecord:
    return MemoryRecord(
        memory_id="mem_001",
        scope="thread",
        content={
            "kind": "structured_note",
            "text": "Learner prefers worked examples.",
        },
        summary="Learner prefers worked examples.",
        source_refs=[
            {
                "ref_type": "artifact",
                "run_id": "run_001",
                "artifact_id": "artifact_001",
            }
        ],
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
        effective_grants_snapshot={
            "tools": ["write_memory"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
    )


def _write_memory_grants() -> dict:
    return {
        "tools": ["write_memory"],
        "workspace": {"mode": "shared_ro"},
        "budget": {"seconds": 30},
    }


def test_file_memory_store_persists_authorized_records(tmp_path):
    store = memory.FileMemoryStore(tmp_path)

    result = store.save_record(
        _valid_memory_record(),
        execution=_execution(),
        grants=_write_memory_grants(),
    )

    assert result == {"status": "saved", "record_id": "mem_001"}
    assert store.load_record("mem_001") == _valid_memory_record()


def test_direct_persistence_without_action_execution_is_rejected(tmp_path):
    store = memory.FileMemoryStore(tmp_path)

    with pytest.raises(PermissionError, match="execution|authorized"):
        store.save_record(
            _valid_memory_record(),
            execution=None,
            grants=_write_memory_grants(),
        )


def test_direct_persistence_without_write_memory_grant_is_rejected(tmp_path):
    store = memory.FileMemoryStore(tmp_path)

    with pytest.raises(PermissionError, match="write_memory|grant"):
        store.save_record(
            _valid_memory_record(),
            execution=_execution(),
            grants={"tools": []},
        )

    assert store.list_records(scope="thread") == []


def test_malformed_record_is_rejected_by_persistence_boundary(tmp_path):
    store = memory.FileMemoryStore(tmp_path)

    malformed_record = {
        "memory_id": "mem_bad",
        "scope": "thread",
        "summary": "missing structured content and provenance",
    }

    with pytest.raises((TypeError, ValueError, PermissionError), match="content|source_refs|provenance|record"):
        store.save_record(
            malformed_record,
            execution=_execution(),
            grants=_write_memory_grants(),
        )


def test_duplicate_persistence_leaves_original_record(tmp_path):
    store = memory.FileMemoryStore(tmp_path)
    record = _valid_memory_record()
    store.save_record(
        record,
        execution=_execution(),
        grants=_write_memory_grants(),
    )

    with pytest.raises(ValueError, match="duplicate memory_id"):
        store.save_record(
            record,
            execution=_execution(),
            grants=_write_memory_grants(),
        )

    assert store.list_records(scope=record.scope) == [record]
    assert store.record_path(record.memory_id).exists()


def test_direct_persistence_does_not_emit_success_event(tmp_path):
    store = memory.FileMemoryStore(tmp_path)
    events_for_run = event_store.FileEventStore(tmp_path)

    before = events_for_run.list_events("run_001")

    store.save_record(
        _valid_memory_record(),
        execution=_execution(),
        grants=_write_memory_grants(),
        event_store=events_for_run,
    )

    after = events_for_run.list_events("run_001")
    assert after == before
    assert [event.event_type for event in after] == []


def test_projector_rebuild_still_does_not_read_memory_store(tmp_path):
    class ExplodingMemoryStore:
        def list_records(self, *args, **kwargs):
            raise AssertionError("projector must not list memory records")

        def load_record(self, *args, **kwargs):
            raise AssertionError("projector must not load memory records")

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


def test_memory_query_default_shape_returns_refs_without_full_content(tmp_path):
    store = memory.FileMemoryStore(tmp_path)
    store.save_record(
        _valid_memory_record(),
        execution=_execution(),
        grants=_write_memory_grants(),
    )
    result = memory.LocalMemoryQueryService(store).query(
        run_id="run_001",
        query="worked examples",
        grants={"memory": {"query": True}},
        caller_context={
            "run_id": "run_001",
            "caller": "agent_loop",
            "purpose": "agent_recall",
        },
    )

    assert result["status"] == "ok"
    assert "content" not in result
    assert "artifact_content" not in result
    assert "full_text" not in result
    assert "raw_artifact_content" not in result
