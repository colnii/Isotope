"""Optional LanceDB vector-store adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .vector_store import VectorSearchResult


class LanceDBVectorStore:
    """Lazy optional LanceDB adapter.

    The base package must keep working without LanceDB installed.
    """

    def __init__(self, *, path: Path | str, table_name: str) -> None:
        self.path = Path(path)
        self.table_name = table_name

    def search(
        self,
        *,
        query_vector: Sequence[float],
        limit: int,
    ) -> VectorSearchResult:
        try:
            __import__("lancedb")
        except ModuleNotFoundError:
            return VectorSearchResult(
                status="dense_unavailable",
                reason_code="lancedb_not_installed",
                hits=[],
            )
        return VectorSearchResult(
            status="dense_unavailable",
            reason_code="lancedb_adapter_not_initialized",
            hits=[],
        )
