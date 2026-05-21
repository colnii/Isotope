import json

import pytest

from isotope.platform.schemas.memory import MemoryRecord
import isotope.platform.state as platform_state
import isotope.platform.state.memory_store as memory_store


def _memory_record(memory_id: str = "mem_001", scope: str = "thread") -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        scope=scope,
        content={
            "kind": "structured_note",
            "text": f"{memory_id} prefers worked examples.",
        },
        summary=f"{memory_id} prefers worked examples.",
        source_refs=[
            {
                "ref_type": "artifact",
                "run_id": "run_001",
                "artifact_id": f"artifact_{memory_id}",
            }
        ],
        provenance={
            "run_id": "run_001",
            "execution_id": f"exec_{memory_id}",
            "action_type": "write_memory",
        },
        created_at="2026-04-29T00:00:00Z",
        supersedes=[],
        quality="candidate",
    )


def test_jsonl_memory_store_appends_records(tmp_path):
    assert hasattr(memory_store, "MemoryStore")
    assert hasattr(memory_store, "JsonlMemoryStore")
    assert platform_state.JsonlMemoryStore is memory_store.JsonlMemoryStore

    store = memory_store.JsonlMemoryStore(tmp_path)
    record = _memory_record()

    assert store.append_record(record) == record

    lines = store.records_path().read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["memory_id"] for line in lines] == ["mem_001"]


def test_jsonl_memory_store_lists_records_by_scope(tmp_path):
    store = memory_store.JsonlMemoryStore(tmp_path)
    thread_record = _memory_record("mem_thread", scope="thread")
    run_record = _memory_record("mem_run", scope="run")
    store.append_record(thread_record)
    store.append_record(run_record)

    assert store.list_records() == [thread_record, run_record]
    assert store.list_records(scope="thread") == [thread_record]
    assert store.list_records(scope="run") == [run_record]


def test_jsonl_memory_store_loads_record_by_id(tmp_path):
    store = memory_store.JsonlMemoryStore(tmp_path)
    record = _memory_record("mem_target")
    store.append_record(_memory_record("mem_other"))
    store.append_record(record)

    assert store.load_record("mem_target") == record
    assert store.load_record("mem_missing") is None


def test_jsonl_memory_store_rejects_duplicate_memory_id(tmp_path):
    store = memory_store.JsonlMemoryStore(tmp_path)
    store.append_record(_memory_record("mem_001"))

    with pytest.raises(ValueError, match="duplicate memory_id"):
        store.append_record(_memory_record("mem_001"))
