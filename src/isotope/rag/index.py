"""Generic local RAG index wiring over retrieval documents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .documents import RetrievalDocument
from .embeddings import DeterministicEmbeddingProvider, EmbeddingProvider
from .vector_store import InMemoryVectorStore, VectorStore


@dataclass(frozen=True)
class RagIndexConfig:
    backend: str
    dimensions: int = 16


@dataclass(frozen=True)
class RagIndexComponents:
    embedding_provider: EmbeddingProvider
    vector_store: VectorStore


@dataclass(frozen=True)
class RagIndex:
    embedding_provider: EmbeddingProvider
    vector_store: VectorStore

    def components(self) -> RagIndexComponents:
        return RagIndexComponents(
            embedding_provider=self.embedding_provider,
            vector_store=self.vector_store,
        )


def parse_rag_index_config(value: Mapping[str, Any] | None) -> RagIndexConfig | None:
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

    return RagIndexConfig(backend="local", dimensions=dimensions)


def build_rag_index(
    documents: list[RetrievalDocument],
    config: RagIndexConfig | Mapping[str, Any] | None,
) -> RagIndex | None:
    normalized = (
        config if isinstance(config, RagIndexConfig) else parse_rag_index_config(config)
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
                embedding_provider.embed(document_embedding_text(document)),
                dict(document.metadata or {}),
            )
            for document in documents
        ]
    )
    return RagIndex(
        embedding_provider=embedding_provider,
        vector_store=vector_store,
    )


def document_embedding_text(document: RetrievalDocument) -> str:
    return " ".join(
        part
        for part in (document.title, document.summary, document.body)
        if isinstance(part, str) and part
    )
