"""Optional LanceDB vector-store adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from .vector_store import VectorSearchHit, VectorSearchResult, VectorUpsertResult


class LanceDBVectorStore:
    """Lazy optional LanceDB adapter.

    The base package must keep working without LanceDB installed.
    """

    def __init__(self, *, path: Path | str, table_name: str) -> None:
        self.path = Path(path)
        self.table_name = table_name

    def upsert(
        self,
        rows: list[tuple[str, Sequence[float], dict[str, Any] | None]],
    ) -> VectorUpsertResult:
        try:
            lancedb = __import__("lancedb")
        except ModuleNotFoundError:
            return VectorUpsertResult(
                status="dense_unavailable",
                reason_code="lancedb_not_installed",
            )
        try:
            normalized = _lancedb_rows(rows)
            connection = lancedb.connect(str(self.path))
            try:
                table = connection.open_table(self.table_name)
            except Exception:
                _create_table(connection, self.table_name, normalized)
            else:
                _add_rows(table, normalized)
        except Exception:
            return VectorUpsertResult(
                status="dense_unavailable",
                reason_code="lancedb_upsert_failed",
            )
        return VectorUpsertResult(status="ok")

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


def _lancedb_rows(
    rows: list[tuple[str, Sequence[float], dict[str, Any] | None]],
) -> list[dict[str, Any]]:
    return [
        {
            "document_id": document_id,
            "vector": [float(value) for value in vector],
            **{
                str(key): value
                for key, value in (metadata or {}).items()
                if key not in {"document_id", "vector"}
            },
        }
        for document_id, vector, metadata in rows
    ]


def _create_table(connection: Any, table_name: str, rows: list[dict[str, Any]]) -> Any:
    try:
        return connection.create_table(table_name, data=rows, mode="overwrite")
    except TypeError:
        return connection.create_table(table_name, rows)


def _add_rows(table: Any, rows: list[dict[str, Any]]) -> Any:
    try:
        return table.add(rows, mode="overwrite")
    except TypeError:
        return table.add(rows)
