from __future__ import annotations

import isotope.memory as memory
from isotope.platform.schemas.memory import MemoryRecord


def test_memory_query_service_keeps_bm25_when_dense_retrieval_is_absent(tmp_path):
    store = memory.FileMemoryStore(tmp_path)
    store.append_record(_record("mem_sparse", "exact portfolio interview"))
    service = memory.LocalMemoryQueryService(store)

    result = service.query(
        "run_1",
        "portfolio interview",
        grants={"memory": {"query": True}},
        caller_context={"run_id": "run_1", "caller": "pytest", "purpose": "query"},
    )

    assert result["retrieval"] == {
        "backend": "bm25",
        "dense_status": "not_configured",
    }
    assert [item["record_id"] for item in result["results"]] == ["mem_sparse"]


def test_memory_query_service_can_enable_local_dense_retrieval(tmp_path):
    store = memory.FileMemoryStore(tmp_path)
    store.append_record(_record("mem_sparse", "exact portfolio interview"))
    service = memory.LocalMemoryQueryService(
        store,
        dense_retrieval={"backend": "local", "dimensions": 8},
    )

    result = service.query(
        "run_1",
        "portfolio interview",
        grants={"memory": {"query": True}},
        caller_context={"run_id": "run_1", "caller": "pytest", "purpose": "query"},
    )

    assert result["retrieval"] == {"backend": "hybrid", "dense_status": "ok"}
    assert [item["record_id"] for item in result["results"]] == ["mem_sparse"]


def test_memory_query_service_rejects_unknown_dense_backend(tmp_path):
    store = memory.FileMemoryStore(tmp_path)

    try:
        memory.LocalMemoryQueryService(
            store,
            dense_retrieval={"backend": "unknown"},
        )
    except ValueError as exc:
        assert "dense_retrieval.backend" in str(exc)
    else:
        raise AssertionError("unknown dense backend should fail validation")


def _record(memory_id: str, summary: str) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        scope="run",
        content={"secret": "raw content must not be indexed"},
        summary=summary,
        source_refs=[{"kind": "artifact", "id": memory_id}],
        provenance={
            "run_id": "run_1",
            "execution_id": "exec_1",
            "action_type": "write_memory",
        },
        created_at="2026-06-14T00:00:00+00:00",
        supersedes=[],
        quality="candidate",
    )
