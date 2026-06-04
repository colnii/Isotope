"""Optional LanceDB vector-store adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .vector_store import VectorSearchHit, VectorSearchResult


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
            lancedb = __import__("lancedb")
        except ModuleNotFoundError:
            return VectorSearchResult(
                status="dense_unavailable",
                reason_code="lancedb_not_installed",
                hits=[],
            )
        try:
            table = lancedb.connect(str(self.path)).open_table(self.table_name)
            rows = table.search(list(query_vector)).limit(limit).to_list()
        except Exception:
            return VectorSearchResult(
                status="dense_unavailable",
                reason_code="lancedb_query_failed",
                hits=[],
            )
        hits = []
        for row in rows:
            document_id = row.get("document_id")
            if not isinstance(document_id, str) or not document_id:
                continue
            distance = row.get("_distance", 1.0)
            score = 1.0 - float(distance)
            metadata = {
                str(key): value
                for key, value in row.items()
                if key not in {"document_id", "_distance", "vector"}
            }
            hits.append(
                VectorSearchHit(
                    document_id=document_id,
                    score=score,
                    metadata=metadata,
                )
            )
        return VectorSearchResult(status="ok", hits=hits)
