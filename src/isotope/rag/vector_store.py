"""Vector-store contracts for dense retrieval."""

from __future__ import annotations

from dataclasses import dataclass


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
