"""Generic local RAG index wiring over retrieval documents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .documents import RetrievalDocument
from .embeddings import (
    DeterministicEmbeddingProvider,
    EmbeddingProvider,
    EmbeddingProviderUnavailable,
    FastEmbedEmbeddingProvider,
    UnavailableEmbeddingProvider,
)
from .lancedb_store import LanceDBVectorStore
from .vector_store import InMemoryVectorStore, VectorStore


@dataclass(frozen=True)
class RagIndexConfig:
    backend: str
    dimensions: int = 16
    path: str | None = None
    table_name: str | None = None
    embedding_provider: str = "deterministic"
    embedding_model: str | None = None


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
    if backend not in {"local", "lancedb"}:
        raise ValueError("dense_retrieval.backend must be local or lancedb")

    dimensions = value.get("dimensions", 16)
    if (
        isinstance(dimensions, bool)
        or not isinstance(dimensions, int)
        or dimensions <= 0
    ):
        raise ValueError("dense_retrieval.dimensions must be a positive integer")

    embedding_provider = value.get("embedding_provider", "deterministic")
    if embedding_provider not in {"deterministic", "fastembed"}:
        raise ValueError(
            "dense_retrieval.embedding_provider must be deterministic or fastembed"
        )
    embedding_model = _optional_config_text(value, "embedding_model")

    if backend == "lancedb":
        return RagIndexConfig(
            backend="lancedb",
            dimensions=dimensions,
            path=_required_config_text(value, "path"),
            table_name=_required_config_text(value, "table_name"),
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
        )

    return RagIndexConfig(
        backend="local",
        dimensions=dimensions,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
    )


def build_rag_index(
    documents: list[RetrievalDocument],
    config: RagIndexConfig | Mapping[str, Any] | None,
) -> RagIndex | None:
    normalized = (
        config if isinstance(config, RagIndexConfig) else parse_rag_index_config(config)
    )
    if normalized is None:
        return None

    embedding_provider = _build_embedding_provider(normalized)
    if normalized.backend == "lancedb":
        vector_store = LanceDBVectorStore(
            path=normalized.path or "",
            table_name=normalized.table_name or "",
        )
    else:
        vector_store = InMemoryVectorStore()
    try:
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
    except Exception:
        embedding_provider = UnavailableEmbeddingProvider(
            reason_code="embedding_provider_unavailable"
        )
        vector_store = InMemoryVectorStore()
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


def _required_config_text(value: Mapping[str, Any], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"dense_retrieval.{key} must be a non-empty string")
    return raw


def _optional_config_text(value: Mapping[str, Any], key: str) -> str | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"dense_retrieval.{key} must be a non-empty string")
    return raw


def _build_embedding_provider(config: RagIndexConfig) -> EmbeddingProvider:
    if config.embedding_provider == "fastembed":
        try:
            return FastEmbedEmbeddingProvider(model_name=config.embedding_model)
        except EmbeddingProviderUnavailable as exc:
            return UnavailableEmbeddingProvider(reason_code=exc.reason_code)
    return DeterministicEmbeddingProvider(dimensions=config.dimensions)
