from __future__ import annotations

from isotope.rag.embeddings import DeterministicEmbeddingProvider
from isotope.rag.vector_store import InMemoryVectorStore


def test_deterministic_embeddings_are_repeatable():
    provider = DeterministicEmbeddingProvider(dimensions=8)

    assert provider.embed("semantic search") == provider.embed("semantic search")
    assert provider.embed("semantic search") != provider.embed("meal planning")


def test_in_memory_vector_store_returns_dense_hits_by_cosine_similarity():
    provider = DeterministicEmbeddingProvider(dimensions=8)
    store = InMemoryVectorStore()
    store.upsert(
        [
            ("doc_search", provider.embed("semantic vector search"), {"kind": "memory"}),
            ("doc_meal", provider.embed("meal planning"), {"kind": "memory"}),
        ]
    )

    result = store.search(
        query_vector=provider.embed("semantic vector search"),
        limit=1,
    )

    assert result.status == "ok"
    assert [hit.document_id for hit in result.hits] == ["doc_search"]
    assert result.hits[0].score > 0
