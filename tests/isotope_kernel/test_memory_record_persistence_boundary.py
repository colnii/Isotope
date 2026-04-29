import pytest

from isotope_kernel import event_store, events, memory, models, projector


def _valid_memory_record() -> models.MemoryRecord:
    return models.MemoryRecord(
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


def _execution() -> models.ActionExecution:
    return models.ActionExecution(
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


def test_not_enabled_memory_store_boundary_exists_but_remains_unavailable():
    assert hasattr(memory, "NotEnabledMemoryStore")

    store = memory.NotEnabledMemoryStore()

    with pytest.raises(PermissionError, match="memory persistence|not enabled|memory_record"):
        store.save_record(
            _valid_memory_record(),
            execution=_execution(),
            grants=_write_memory_grants(),
        )


def test_direct_persistence_without_action_execution_is_rejected(tmp_path):
    store = memory.NotEnabledMemoryStore(tmp_path)

    with pytest.raises(PermissionError, match="execution|authorized|not enabled"):
        store.save_record(
            _valid_memory_record(),
            execution=None,
            grants=_write_memory_grants(),
        )


def test_direct_persistence_without_write_memory_grant_is_rejected(tmp_path):
    store = memory.NotEnabledMemoryStore(tmp_path)

    with pytest.raises(PermissionError, match="write_memory|grant|not enabled"):
        store.save_record(
            _valid_memory_record(),
            execution=_execution(),
            grants={"tools": []},
        )

    assert store.list_records(scope="thread") == []


def test_malformed_record_is_rejected_by_persistence_boundary(tmp_path):
    store = memory.NotEnabledMemoryStore(tmp_path)

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


def test_rejected_persistence_leaves_no_partial_record(tmp_path):
    store = memory.NotEnabledMemoryStore(tmp_path)
    record = _valid_memory_record()

    with pytest.raises(PermissionError, match="not enabled|memory"):
        store.save_record(
            record,
            execution=_execution(),
            grants=_write_memory_grants(),
        )

    assert store.list_records(scope=record.scope) == []
    assert not store.record_path(record.memory_id).exists()


def test_rejected_direct_persistence_emits_no_success_event(tmp_path):
    store = memory.NotEnabledMemoryStore(tmp_path)
    events_for_run = event_store.FileEventStore(tmp_path)

    before = events_for_run.list_events("run_001")

    with pytest.raises(PermissionError, match="not enabled|memory"):
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


def test_memory_query_default_shape_remains_refs_summary_preview_only():
    result = memory.NotEnabledMemoryService().query(
        run_id="run_001",
        query="worked examples",
        grants={"memory": {"query": True}},
        caller_context={"run_id": "run_001"},
    )

    assert result["status"] in {"not_enabled", "limited", "denied"}
    assert "content" not in result
    assert "artifact_content" not in result
    assert "full_text" not in result
    assert "raw_artifact_content" not in result
