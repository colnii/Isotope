"""Memory-specific adapters for generic retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from isotope.platform.schemas.memory import MemoryRecord
from isotope.rag.documents import RetrievalDocument
from isotope.rag.embeddings import EmbeddingProvider
from isotope.rag.hybrid import HybridRetriever
from isotope.rag.vector_store import VectorStore


@dataclass(frozen=True)
class MemoryQueryMatches:
    all_matches: list[MemoryRecord]
    visible: list[MemoryRecord]
    backend: str
    dense_status: str
    ranking: dict[str, dict[str, Any]]


def query_memory_records_hybrid(
    records: list[MemoryRecord],
    *,
    query: str,
    limit: int,
    run_id: str | None = None,
    session_id: str | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    vector_store: VectorStore | None = None,
) -> MemoryQueryMatches:
    filtered = [
        record
        for record in records
        if _record_allowed(record, run_id=run_id, session_id=session_id)
    ]
    documents = [_memory_record_document(record) for record in filtered]
    result = HybridRetriever(
        embedding_provider=embedding_provider,
        vector_store=vector_store,
    ).search(query=query, documents=documents, limit=max(limit, len(documents)))
    records_by_id = {record.memory_id: record for record in filtered}
    ranked_records = [
        records_by_id[hit.document.document_id]
        for hit in result.hits
        if hit.document.document_id in records_by_id
    ]
    return MemoryQueryMatches(
        all_matches=ranked_records,
        visible=ranked_records[:limit],
        backend=result.backend,
        dense_status=(result.metadata or {}).get("dense_status", "unknown"),
        ranking={
            hit.document.document_id: {
                "score": hit.score,
                "source": hit.source,
                "metadata": dict(hit.metadata or {}),
            }
            for hit in result.hits
        },
    )


def _record_allowed(
    record: MemoryRecord,
    *,
    run_id: str | None,
    session_id: str | None,
) -> bool:
    if run_id is not None and record.provenance.get("run_id") != run_id:
        return False
    if session_id is not None and record.provenance.get("session_id") != session_id:
        return False
    return True


def _memory_record_document(record: MemoryRecord) -> RetrievalDocument:
    source_text = " ".join(
        str(value) for ref in record.source_refs for value in ref.values()
    )
    provenance_text = " ".join(str(value) for value in record.provenance.values())
    return RetrievalDocument(
        document_id=record.memory_id,
        title=record.summary,
        summary=" ".join(
            part
            for part in (
                record.summary,
                source_text,
                provenance_text,
                record.scope,
                record.quality,
            )
            if part
        ),
        metadata={
            "scope": record.scope,
            "quality": record.quality,
            "source_refs": [dict(ref) for ref in record.source_refs],
            "provenance": dict(record.provenance),
        },
        sensitivity="low",
    )
