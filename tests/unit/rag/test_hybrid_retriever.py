from __future__ import annotations

from isotope.rag import RetrievalDocument
from isotope.rag.embeddings import DeterministicEmbeddingProvider
from isotope.rag.hybrid import HybridRetriever
from isotope.rag.vector_store import InMemoryVectorStore


def test_hybrid_retriever_merges_sparse_and_dense_hits_without_duplicates():
    documents = [
        RetrievalDocument(
            document_id="sparse", title="exact keyword", summary="portfolio interview"
        ),
        RetrievalDocument(
            document_id="dense", title="semantic", summary="career story"
        ),
    ]
    embeddings = DeterministicEmbeddingProvider(dimensions=8)
    vector_store = InMemoryVectorStore()
    vector_store.upsert(
        [
            ("dense", embeddings.embed("portfolio interview"), {"source": "dense"}),
            ("sparse", embeddings.embed("unrelated"), {"source": "dense"}),
        ]
    )

    result = HybridRetriever(
        embedding_provider=embeddings,
        vector_store=vector_store,
    ).search(query="portfolio interview", documents=documents, limit=5)

    assert result.status == "ok"
    assert result.backend == "hybrid"
    assert sorted(hit.document.document_id for hit in result.hits) == [
        "dense",
        "sparse",
    ]
    assert len({hit.document.document_id for hit in result.hits}) == len(result.hits)


def test_hybrid_retriever_falls_back_to_sparse_when_dense_is_unavailable():
    documents = [
        RetrievalDocument(
            document_id="sparse", title="exact keyword", summary="portfolio interview"
        ),
    ]

    result = HybridRetriever().search(
        query="portfolio interview",
        documents=documents,
        limit=5,
    )

    assert result.status == "ok"
    assert result.backend == "bm25"
    assert result.metadata["dense_status"] == "not_configured"
    assert [hit.document.document_id for hit in result.hits] == ["sparse"]
