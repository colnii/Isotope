"""Generic retrieval document contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RetrievalDocument:
    document_id: str
    title: str
    summary: str | None = None
    body: str | None = None
    metadata: dict[str, Any] | None = None
    sensitivity: str = "low"


@dataclass(frozen=True)
class RetrievalHit:
    document: RetrievalDocument
    score: float
    source: str
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class RetrievalResult:
    status: str
    hits: list[RetrievalHit]
    backend: str
    reason_code: str | None = None
