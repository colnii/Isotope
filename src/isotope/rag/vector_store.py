"""Vector-store contracts for dense retrieval."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol, Sequence


@dataclass(frozen=True)
class VectorSearchHit:
    document_id: str
    score: float
    metadata: dict | None = None


@dataclass(frozen=True)
class VectorSearchResult:
    status: str
    hits: list[VectorSearchHit]
    reason_code: str | None = None


class VectorStore(Protocol):
    def search(
        self, *, query_vector: Sequence[float], limit: int
    ) -> VectorSearchResult:
        """Search dense vectors."""


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._vectors: dict[str, tuple[list[float], dict | None]] = {}

    def upsert(self, rows: list[tuple[str, Sequence[float], dict | None]]) -> None:
        for document_id, vector, metadata in rows:
            self._vectors[document_id] = ([float(value) for value in vector], metadata)

    def search(
        self, *, query_vector: Sequence[float], limit: int
    ) -> VectorSearchResult:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        query = [float(value) for value in query_vector]
        hits = [
            VectorSearchHit(
                document_id=document_id,
                score=_cosine_similarity(query, vector),
                metadata=metadata,
            )
            for document_id, (vector, metadata) in self._vectors.items()
        ]
        ranked = sorted(
            (hit for hit in hits if hit.score > 0),
            key=lambda hit: (-hit.score, hit.document_id),
        )
        return VectorSearchResult(status="ok", hits=ranked[:limit])


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
