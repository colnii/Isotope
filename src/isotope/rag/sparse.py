"""Sparse retrieval over public retrieval documents."""

from __future__ import annotations

from .documents import RetrievalDocument, RetrievalHit, RetrievalResult
from .retrieval import SummarySearchDocument, rank_summary_documents


class SparseRetriever:
    backend = "bm25"

    def search(
        self,
        *,
        query: str,
        documents: list[RetrievalDocument],
        limit: int,
    ) -> RetrievalResult:
        summary_documents = [
            SummarySearchDocument(
                document_id=document.document_id,
                title=document.title,
                summary=" ".join(
                    part
                    for part in (document.summary, document.body)
                    if isinstance(part, str) and part
                ),
                metadata={"document": document},
            )
            for document in documents
        ]
        hits = rank_summary_documents(query, summary_documents)
        return RetrievalResult(
            status="ok",
            backend=self.backend,
            hits=[
                RetrievalHit(
                    document=hit.document.metadata["document"],
                    score=hit.score,
                    source=self.backend,
                )
                for hit in hits[:limit]
            ],
        )
