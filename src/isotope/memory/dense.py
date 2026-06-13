"""Dense retrieval wiring for local memory records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from isotope.platform.schemas.memory import MemoryRecord
from isotope.rag.documents import RetrievalDocument
from isotope.rag.embeddings import DeterministicEmbeddingProvider, EmbeddingProvider
from isotope.rag.vector_store import InMemoryVectorStore, VectorStore

from .retrieval import memory_record_retrieval_document


@dataclass(frozen=True)
class MemoryDenseRetrievalConfig:
    backend: str
    dimensions: int = 16


@dataclass(frozen=True)
class MemoryDenseRetrieval:
    embedding_provider: EmbeddingProvider
    vector_store: VectorStore


def parse_memory_dense_retrieval_config(
    value: Mapping[str, Any] | None,
) -> MemoryDenseRetrievalConfig | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("dense_retrieval must be an object")

    backend = value.get("backend")
    if backend != "local":
        raise ValueError("dense_retrieval.backend must be local")

    dimensions = value.get("dimensions", 16)
    if (
        isinstance(dimensions, bool)
        or not isinstance(dimensions, int)
        or dimensions <= 0
    ):
        raise ValueError("dense_retrieval.dimensions must be a positive integer")

    return MemoryDenseRetrievalConfig(backend="local", dimensions=dimensions)


def build_memory_dense_retrieval(
    records: list[MemoryRecord],
    config: MemoryDenseRetrievalConfig | Mapping[str, Any] | None,
) -> MemoryDenseRetrieval | None:
    normalized = (
        config
        if isinstance(config, MemoryDenseRetrievalConfig)
        else parse_memory_dense_retrieval_config(config)
    )
    if normalized is None:
        return None

    embedding_provider = DeterministicEmbeddingProvider(
        dimensions=normalized.dimensions
    )
    vector_store = InMemoryVectorStore()
    vector_store.upsert(
        [
            (
                document.document_id,
                embedding_provider.embed(_document_embedding_text(document)),
                dict(document.metadata or {}),
            )
            for document in (
                memory_record_retrieval_document(record) for record in records
            )
        ]
    )
    return MemoryDenseRetrieval(
        embedding_provider=embedding_provider,
        vector_store=vector_store,
    )


def _document_embedding_text(document: RetrievalDocument) -> str:
    return " ".join(
        part
        for part in (document.title, document.summary, document.body)
        if isinstance(part, str) and part
    )
