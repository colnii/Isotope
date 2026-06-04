"""Hybrid sparse+dense retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .documents import RetrievalDocument, RetrievalHit, RetrievalResult
from .embeddings import EmbeddingProvider
from .sparse import SparseRetriever
from .vector_store import VectorStore


@dataclass(frozen=True)
class HybridRetrievalResult(RetrievalResult):
    metadata: dict[str, Any] | None = None


class HybridRetriever:
    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
        sparse_weight: float = 1.0,
        dense_weight: float = 1.0,
        rrf_k: int = 60,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.sparse = SparseRetriever()
        self.sparse_weight = sparse_weight
        self.dense_weight = dense_weight
        self.rrf_k = rrf_k

    def search(
        self,
        *,
        query: str,
        documents: list[RetrievalDocument],
        limit: int,
    ) -> HybridRetrievalResult:
        sparse_result = self.sparse.search(
            query=query, documents=documents, limit=max(limit, 20)
        )
        dense_status = "not_configured"
        dense_hits_by_id: dict[str, int] = {}
        if self.embedding_provider is not None and self.vector_store is not None:
            try:
                dense_result = self.vector_store.search(
                    query_vector=self.embedding_provider.embed(query),
                    limit=max(limit, 20),
                )
                dense_status = dense_result.status
                dense_hits_by_id = {
                    hit.document_id: rank
                    for rank, hit in enumerate(dense_result.hits, start=1)
                }
            except Exception:
                dense_status = "dense_unavailable"

        documents_by_id = {document.document_id: document for document in documents}
        sparse_hits_by_id = {
            hit.document.document_id: rank
            for rank, hit in enumerate(sparse_result.hits, start=1)
        }
        candidate_ids = set(sparse_hits_by_id) | set(dense_hits_by_id)
        fused = [
            RetrievalHit(
                document=documents_by_id[document_id],
                score=_rrf_score(
                    document_id,
                    sparse_hits_by_id=sparse_hits_by_id,
                    dense_hits_by_id=dense_hits_by_id,
                    sparse_weight=self.sparse_weight,
                    dense_weight=self.dense_weight,
                    rrf_k=self.rrf_k,
                ),
                source="hybrid",
                metadata={
                    "sparse_rank": sparse_hits_by_id.get(document_id),
                    "dense_rank": dense_hits_by_id.get(document_id),
                },
            )
            for document_id in candidate_ids
            if document_id in documents_by_id
        ]
        ranked = sorted(
            fused, key=lambda hit: (-hit.score, hit.document.document_id)
        )[:limit]
        backend = "hybrid" if dense_status == "ok" else "bm25"
        return HybridRetrievalResult(
            status="ok",
            backend=backend,
            hits=ranked,
            metadata={"dense_status": dense_status},
        )


def _rrf_score(
    document_id: str,
    *,
    sparse_hits_by_id: dict[str, int],
    dense_hits_by_id: dict[str, int],
    sparse_weight: float,
    dense_weight: float,
    rrf_k: int,
) -> float:
    score = 0.0
    if document_id in sparse_hits_by_id:
        score += sparse_weight / (rrf_k + sparse_hits_by_id[document_id])
    if document_id in dense_hits_by_id:
        score += dense_weight / (rrf_k + dense_hits_by_id[document_id])
    return score
