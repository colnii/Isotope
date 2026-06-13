"""Retrieval and ingestion helpers for RAG-style features."""

from .documents import RetrievalDocument, RetrievalHit, RetrievalResult
from .hybrid import HybridRetrievalResult, HybridRetriever
from .index import (
    RagIndex,
    RagIndexComponents,
    RagIndexConfig,
    build_rag_index,
    parse_rag_index_config,
)
from .retrieval import SummarySearchDocument, SummarySearchHit, rank_summary_documents
from .sparse import SparseRetriever
from .vector_store import VectorSearchHit, VectorSearchResult

__all__ = [
    "HybridRetrievalResult",
    "HybridRetriever",
    "RagIndex",
    "RagIndexComponents",
    "RagIndexConfig",
    "RetrievalDocument",
    "RetrievalHit",
    "RetrievalResult",
    "SparseRetriever",
    "SummarySearchDocument",
    "SummarySearchHit",
    "VectorSearchHit",
    "VectorSearchResult",
    "build_rag_index",
    "parse_rag_index_config",
    "rank_summary_documents",
]
