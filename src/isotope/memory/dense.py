"""Memory-specific adapter for generic dense retrieval wiring."""

from __future__ import annotations

from typing import Any, Mapping

from isotope.platform.schemas.memory import MemoryRecord
from isotope.rag.index import (
    RagIndexComponents,
    RagIndexConfig,
    build_rag_index,
    parse_rag_index_config,
)

from .retrieval import memory_record_retrieval_document


def parse_memory_dense_retrieval_config(
    value: Mapping[str, Any] | None,
) -> RagIndexConfig | None:
    return parse_rag_index_config(value)


def build_memory_dense_retrieval(
    records: list[MemoryRecord],
    config: RagIndexConfig | Mapping[str, Any] | None,
) -> RagIndexComponents | None:
    index = build_rag_index(
        [memory_record_retrieval_document(record) for record in records],
        config,
    )
    return index.components() if index is not None else None
