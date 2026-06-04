from __future__ import annotations

from isotope.memory.retrieval import query_memory_records_hybrid
from isotope.platform.schemas.memory import MemoryRecord
from isotope.rag.embeddings import DeterministicEmbeddingProvider
from isotope.rag.vector_store import InMemoryVectorStore


def _record(
    memory_id: str, summary: str, content: dict | None = None
) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        scope="run",
        content=content or {"secret": "SECRET_CONTENT_SHOULD_NOT_BE_INDEXED"},
        summary=summary,
        source_refs=[{"kind": "artifact", "id": memory_id}],
        provenance={
            "run_id": "run_1",
            "execution_id": "exec_1",
            "action_type": "write_memory",
        },
        created_at="2026-06-04T00:00:00+00:00",
        supersedes=[],
        quality="candidate",
    )


def test_memory_hybrid_retrieval_indexes_low_sensitive_preview_fields_only():
    records = [
        _record("mem_public", "summary-only planner context"),
        _record("mem_secret", "unrelated", {"secret": "summary-only planner context"}),
    ]

    result = query_memory_records_hybrid(
        records, query="summary-only planner context", limit=5
    )

    assert [record.memory_id for record in result.visible] == ["mem_public"]
    assert result.backend == "bm25"
    assert result.dense_status == "not_configured"


def test_memory_hybrid_retrieval_can_include_dense_only_hits():
    records = [
        _record("mem_sparse", "exact portfolio interview"),
        _record("mem_dense", "career story"),
    ]
    embeddings = DeterministicEmbeddingProvider(dimensions=8)
    vector_store = InMemoryVectorStore()
    vector_store.upsert(
        [
            ("mem_dense", embeddings.embed("portfolio interview"), {}),
        ]
    )

    result = query_memory_records_hybrid(
        records,
        query="portfolio interview",
        limit=5,
        embedding_provider=embeddings,
        vector_store=vector_store,
    )

    assert sorted(record.memory_id for record in result.visible) == [
        "mem_dense",
        "mem_sparse",
    ]
    assert result.backend == "hybrid"
    assert result.dense_status == "ok"
