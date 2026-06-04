"""Retrieval and ingestion helpers for RAG-style features."""

from .documents import RetrievalDocument, RetrievalHit, RetrievalResult
from .hybrid import HybridRetrievalResult, HybridRetriever
from .retrieval import SummarySearchDocument, SummarySearchHit, rank_summary_documents
from .sparse import SparseRetriever
from .vector_store import VectorSearchHit, VectorSearchResult

__all__ = [
    "HybridRetrievalResult",
    "HybridRetriever",
    "RetrievalDocument",
    "RetrievalHit",
    "RetrievalResult",
    "SparseRetriever",
    "SummarySearchDocument",
    "SummarySearchHit",
    "VectorSearchHit",
    "VectorSearchResult",
    "rank_summary_documents",
]
