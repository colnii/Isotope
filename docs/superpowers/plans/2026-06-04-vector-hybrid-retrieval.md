# Vector Hybrid Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a general LanceDB-first hybrid retrieval layer that combines the existing BM25 scorer with optional dense vector search, then make `memory.query` consume it without changing public output or controlled-expand boundaries.

**Architecture:** Add generic `rag` contracts first, then layer sparse retrieval, dense vector protocols, RRF fusion, and a lazy optional LanceDB adapter. Domain callers adapt their records into low-sensitive retrieval documents; the first caller is memory query.

**Tech Stack:** Python 3.13, pytest, current in-tree BM25 scorer, optional LanceDB adapter via lazy import, deterministic test vector store for core tests.

---

## File Structure

- Create `src/isotope/rag/documents.py`: retrieval document and hit dataclasses shared by sparse, dense, and hybrid retrievers.
- Create `src/isotope/rag/sparse.py`: small wrapper around existing `rank_summary_documents(...)`.
- Create `src/isotope/rag/vector_store.py`: vector-store protocol, in-process deterministic vector store, and backend status shapes.
- Create `src/isotope/rag/embeddings.py`: embedding provider protocol and deterministic embedding provider used by tests and local fallback demos.
- Create `src/isotope/rag/hybrid.py`: RRF fusion and `HybridRetriever`.
- Create `src/isotope/rag/lancedb_store.py`: optional LanceDB adapter with lazy import and dense-unavailable failure conversion.
- Modify `src/isotope/rag/__init__.py`: re-export public retrieval types while keeping existing BM25 imports working.
- Create `src/isotope/memory/retrieval.py`: convert `MemoryRecord` previews into `RetrievalDocument` values and run hybrid retrieval.
- Modify `src/isotope/memory/views.py`: replace memory-specific term-overlap ranking with the new memory retrieval helper.
- Modify `src/isotope/memory/__init__.py`: preserve `LocalMemoryQueryService` output shape while reading ranking metadata from the helper.
- Add tests under `tests/unit/rag/`, `tests/unit/memory/`, and existing agent-loop memory tests.

## Task 1: LanceDB Optional Backend Spike

**Files:**
- Create: `tests/unit/rag/test_lancedb_optional_backend.py`
- Create: `src/isotope/rag/lancedb_store.py`
- Modify: `src/isotope/rag/__init__.py`

- [ ] **Step 1: Write the failing import/fallback test**

Create `tests/unit/rag/test_lancedb_optional_backend.py`:

```python
from __future__ import annotations

import builtins

from isotope.rag.lancedb_store import LanceDBVectorStore


def test_lancedb_store_reports_unavailable_when_dependency_is_missing(monkeypatch, tmp_path):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "lancedb":
            raise ModuleNotFoundError("No module named 'lancedb'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    store = LanceDBVectorStore(path=tmp_path / "vectors.lance", table_name="memory")
    result = store.search(query_vector=[1.0, 0.0, 0.0], limit=3)

    assert result.status == "dense_unavailable"
    assert result.reason_code == "lancedb_not_installed"
    assert result.hits == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python3.13 -m pytest tests/unit/rag/test_lancedb_optional_backend.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'isotope.rag.lancedb_store'`.

- [ ] **Step 3: Add the minimal LanceDB adapter shell**

Create `src/isotope/rag/lancedb_store.py`:

```python
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
```

Create `src/isotope/rag/vector_store.py` with the minimal result type needed by the test:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
python3.13 -m pytest tests/unit/rag/test_lancedb_optional_backend.py -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/rag/lancedb_store.py src/isotope/rag/vector_store.py tests/unit/rag/test_lancedb_optional_backend.py
git commit -m "feat(rag): add optional lancedb vector adapter shell"
```

## Task 2: Generic Retrieval Documents And Sparse Retriever

**Files:**
- Create: `src/isotope/rag/documents.py`
- Create: `src/isotope/rag/sparse.py`
- Modify: `src/isotope/rag/__init__.py`
- Test: `tests/unit/rag/test_sparse_retriever.py`

- [ ] **Step 1: Write the failing sparse retriever test**

Create `tests/unit/rag/test_sparse_retriever.py`:

```python
from __future__ import annotations

from isotope.rag import RetrievalDocument, SparseRetriever


def test_sparse_retriever_uses_existing_bm25_ranking():
    documents = [
        RetrievalDocument(
            document_id="project_1",
            title="portfolio demo",
            summary="general workspace",
        ),
        RetrievalDocument(
            document_id="task_1",
            title="interview story",
            summary="portfolio hiring practice",
        ),
        RetrievalDocument(
            document_id="file_1",
            title="meal plan",
            summary="weekly groceries",
        ),
    ]

    result = SparseRetriever().search(query="portfolio interview", documents=documents, limit=2)

    assert result.status == "ok"
    assert [hit.document.document_id for hit in result.hits] == ["task_1", "project_1"]
    assert result.hits[0].score > result.hits[1].score > 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python3.13 -m pytest tests/unit/rag/test_sparse_retriever.py -q
```

Expected: FAIL with an import error for `RetrievalDocument` or `SparseRetriever`.

- [ ] **Step 3: Add retrieval document and sparse retriever**

Create `src/isotope/rag/documents.py`:

```python
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
```

Create `src/isotope/rag/sparse.py`:

```python
"""Sparse retrieval over low-sensitive retrieval documents."""

from __future__ import annotations

from .documents import RetrievalDocument, RetrievalHit, RetrievalResult
from .retrieval import SummarySearchDocument, rank_summary_documents


class SparseRetriever:
    backend = "bm25"

    def search(
        self,
        *,
        query: str,
        documents: list[RetrievalDocument],
        limit: int,
    ) -> RetrievalResult:
        summary_documents = [
            SummarySearchDocument(
                document_id=document.document_id,
                title=document.title,
                summary=" ".join(
                    part
                    for part in (document.summary, document.body)
                    if isinstance(part, str) and part
                ),
                metadata={"document": document},
            )
            for document in documents
        ]
        hits = rank_summary_documents(query, summary_documents)
        return RetrievalResult(
            status="ok",
            backend=self.backend,
            hits=[
                RetrievalHit(
                    document=hit.document.metadata["document"],
                    score=hit.score,
                    source=self.backend,
                )
                for hit in hits[:limit]
            ],
        )
```

Modify `src/isotope/rag/__init__.py`:

```python
"""Retrieval and ingestion helpers for RAG-style features."""

from .documents import RetrievalDocument, RetrievalHit, RetrievalResult
from .retrieval import SummarySearchDocument, SummarySearchHit, rank_summary_documents
from .sparse import SparseRetriever
from .vector_store import VectorSearchHit, VectorSearchResult

__all__ = [
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
```

- [ ] **Step 4: Run sparse and existing BM25 tests**

Run:

```bash
python3.13 -m pytest tests/unit/rag/test_sparse_retriever.py tests/integration/workspace/test_retrieval_authorization.py::test_summary_bm25_ranking_prefers_multi_term_overlap -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/rag/__init__.py src/isotope/rag/documents.py src/isotope/rag/sparse.py tests/unit/rag/test_sparse_retriever.py
git commit -m "feat(rag): wrap bm25 as sparse retriever"
```

## Task 3: Deterministic Dense Retrieval Contracts

**Files:**
- Modify: `src/isotope/rag/vector_store.py`
- Create: `src/isotope/rag/embeddings.py`
- Test: `tests/unit/rag/test_vector_store_contracts.py`

- [ ] **Step 1: Write failing deterministic dense tests**

Create `tests/unit/rag/test_vector_store_contracts.py`:

```python
from __future__ import annotations

from isotope.rag.embeddings import DeterministicEmbeddingProvider
from isotope.rag.vector_store import InMemoryVectorStore


def test_deterministic_embeddings_are_repeatable():
    provider = DeterministicEmbeddingProvider(dimensions=8)

    assert provider.embed("semantic search") == provider.embed("semantic search")
    assert provider.embed("semantic search") != provider.embed("meal planning")


def test_in_memory_vector_store_returns_dense_hits_by_cosine_similarity():
    provider = DeterministicEmbeddingProvider(dimensions=8)
    store = InMemoryVectorStore()
    store.upsert(
        [
            ("doc_search", provider.embed("semantic vector search"), {"kind": "memory"}),
            ("doc_meal", provider.embed("meal planning"), {"kind": "memory"}),
        ]
    )

    result = store.search(
        query_vector=provider.embed("semantic vector search"),
        limit=1,
    )

    assert result.status == "ok"
    assert [hit.document_id for hit in result.hits] == ["doc_search"]
    assert result.hits[0].score > 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
python3.13 -m pytest tests/unit/rag/test_vector_store_contracts.py -q
```

Expected: FAIL with missing `DeterministicEmbeddingProvider` or `InMemoryVectorStore`.

- [ ] **Step 3: Add deterministic embeddings and vector store**

Create `src/isotope/rag/embeddings.py`:

```python
"""Embedding provider contracts for dense retrieval."""

from __future__ import annotations

import hashlib
from typing import Protocol


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]:
        """Return a dense vector for text."""


class DeterministicEmbeddingProvider:
    """Small deterministic embedding provider for tests and local fallback demos."""

    def __init__(self, *, dimensions: int = 16) -> None:
        if isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions <= 0:
            raise ValueError("dimensions must be a positive integer")
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        if not isinstance(text, str):
            raise TypeError("embedding text must be a string")
        values: list[float] = []
        seed = text.encode("utf-8")
        counter = 0
        while len(values) < self.dimensions:
            digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            for byte in digest:
                values.append((byte / 127.5) - 1.0)
                if len(values) == self.dimensions:
                    break
            counter += 1
        return values
```

Extend `src/isotope/rag/vector_store.py`:

```python
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
    def search(self, *, query_vector: Sequence[float], limit: int) -> VectorSearchResult:
        """Search dense vectors."""


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._vectors: dict[str, tuple[list[float], dict | None]] = {}

    def upsert(self, rows: list[tuple[str, Sequence[float], dict | None]]) -> None:
        for document_id, vector, metadata in rows:
            self._vectors[document_id] = ([float(value) for value in vector], metadata)

    def search(self, *, query_vector: Sequence[float], limit: int) -> VectorSearchResult:
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
```

- [ ] **Step 4: Run the dense tests**

Run:

```bash
python3.13 -m pytest tests/unit/rag/test_vector_store_contracts.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/rag/embeddings.py src/isotope/rag/vector_store.py tests/unit/rag/test_vector_store_contracts.py
git commit -m "feat(rag): add dense vector store contracts"
```

## Task 4: Hybrid Retriever With RRF Fusion

**Files:**
- Create: `src/isotope/rag/hybrid.py`
- Modify: `src/isotope/rag/__init__.py`
- Test: `tests/unit/rag/test_hybrid_retriever.py`

- [ ] **Step 1: Write failing hybrid retrieval tests**

Create `tests/unit/rag/test_hybrid_retriever.py`:

```python
from __future__ import annotations

from isotope.rag import RetrievalDocument
from isotope.rag.embeddings import DeterministicEmbeddingProvider
from isotope.rag.hybrid import HybridRetriever
from isotope.rag.vector_store import InMemoryVectorStore


def test_hybrid_retriever_merges_sparse_and_dense_hits_without_duplicates():
    documents = [
        RetrievalDocument(document_id="sparse", title="exact keyword", summary="portfolio interview"),
        RetrievalDocument(document_id="dense", title="semantic", summary="career story"),
    ]
    embeddings = DeterministicEmbeddingProvider(dimensions=8)
    vector_store = InMemoryVectorStore()
    vector_store.upsert(
        [
            ("dense", embeddings.embed("portfolio interview"), {"source": "dense"}),
            ("sparse", embeddings.embed("unrelated"), {"source": "dense"}),
        ]
    )

    result = HybridRetriever(
        embedding_provider=embeddings,
        vector_store=vector_store,
    ).search(query="portfolio interview", documents=documents, limit=5)

    assert result.status == "ok"
    assert result.backend == "hybrid"
    assert sorted(hit.document.document_id for hit in result.hits) == ["dense", "sparse"]
    assert len({hit.document.document_id for hit in result.hits}) == len(result.hits)


def test_hybrid_retriever_falls_back_to_sparse_when_dense_is_unavailable():
    documents = [
        RetrievalDocument(document_id="sparse", title="exact keyword", summary="portfolio interview"),
    ]

    result = HybridRetriever().search(
        query="portfolio interview",
        documents=documents,
        limit=5,
    )

    assert result.status == "ok"
    assert result.backend == "bm25"
    assert result.metadata["dense_status"] == "not_configured"
    assert [hit.document.document_id for hit in result.hits] == ["sparse"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3.13 -m pytest tests/unit/rag/test_hybrid_retriever.py -q
```

Expected: FAIL with missing `isotope.rag.hybrid`.

- [ ] **Step 3: Add hybrid retriever**

Create `src/isotope/rag/hybrid.py`:

```python
"""Hybrid sparse+dense retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .documents import RetrievalDocument, RetrievalHit, RetrievalResult
from .embeddings import EmbeddingProvider
from .sparse import SparseRetriever
from .vector_store import VectorStore


@dataclass(frozen=True)
class HybridRetrievalResult(RetrievalResult):
    metadata: dict[str, Any] | None = None


class HybridRetriever:
    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
        sparse_weight: float = 1.0,
        dense_weight: float = 1.0,
        rrf_k: int = 60,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.sparse = SparseRetriever()
        self.sparse_weight = sparse_weight
        self.dense_weight = dense_weight
        self.rrf_k = rrf_k

    def search(
        self,
        *,
        query: str,
        documents: list[RetrievalDocument],
        limit: int,
    ) -> HybridRetrievalResult:
        sparse_result = self.sparse.search(query=query, documents=documents, limit=max(limit, 20))
        dense_status = "not_configured"
        dense_hits_by_id: dict[str, int] = {}
        if self.embedding_provider is not None and self.vector_store is not None:
            try:
                dense_result = self.vector_store.search(
                    query_vector=self.embedding_provider.embed(query),
                    limit=max(limit, 20),
                )
                dense_status = dense_result.status
                dense_hits_by_id = {
                    hit.document_id: rank
                    for rank, hit in enumerate(dense_result.hits, start=1)
                }
            except Exception:
                dense_status = "dense_unavailable"

        documents_by_id = {document.document_id: document for document in documents}
        sparse_hits_by_id = {
            hit.document.document_id: rank
            for rank, hit in enumerate(sparse_result.hits, start=1)
        }
        candidate_ids = set(sparse_hits_by_id) | set(dense_hits_by_id)
        fused = [
            RetrievalHit(
                document=documents_by_id[document_id],
                score=_rrf_score(
                    document_id,
                    sparse_hits_by_id=sparse_hits_by_id,
                    dense_hits_by_id=dense_hits_by_id,
                    sparse_weight=self.sparse_weight,
                    dense_weight=self.dense_weight,
                    rrf_k=self.rrf_k,
                ),
                source="hybrid",
                metadata={
                    "sparse_rank": sparse_hits_by_id.get(document_id),
                    "dense_rank": dense_hits_by_id.get(document_id),
                },
            )
            for document_id in candidate_ids
            if document_id in documents_by_id
        ]
        ranked = sorted(fused, key=lambda hit: (-hit.score, hit.document.document_id))[:limit]
        backend = "hybrid" if dense_status == "ok" else "bm25"
        if not ranked:
            return HybridRetrievalResult(
                status="ok",
                backend=backend,
                hits=[],
                metadata={"dense_status": dense_status},
            )
        return HybridRetrievalResult(
            status="ok",
            backend=backend,
            hits=ranked,
            metadata={"dense_status": dense_status},
        )


def _rrf_score(
    document_id: str,
    *,
    sparse_hits_by_id: dict[str, int],
    dense_hits_by_id: dict[str, int],
    sparse_weight: float,
    dense_weight: float,
    rrf_k: int,
) -> float:
    score = 0.0
    if document_id in sparse_hits_by_id:
        score += sparse_weight / (rrf_k + sparse_hits_by_id[document_id])
    if document_id in dense_hits_by_id:
        score += dense_weight / (rrf_k + dense_hits_by_id[document_id])
    return score
```

Modify `src/isotope/rag/__init__.py` so the complete file is:

```python
"""Retrieval and ingestion helpers for RAG-style features."""

from .documents import RetrievalDocument, RetrievalHit, RetrievalResult
from .hybrid import HybridRetriever, HybridRetrievalResult
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
```

This preserves the existing `SummarySearchDocument`, `SummarySearchHit`, and
`rank_summary_documents` imports while exposing the new retrieval contracts.

The key new import is:

```python
from .hybrid import HybridRetriever, HybridRetrievalResult
```

- [ ] **Step 4: Run hybrid and rag tests**

Run:

```bash
python3.13 -m pytest tests/unit/rag -q
```

Expected: all `tests/unit/rag` tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/rag/__init__.py src/isotope/rag/hybrid.py tests/unit/rag/test_hybrid_retriever.py
git commit -m "feat(rag): add hybrid retrieval fusion"
```

## Task 5: Memory Retrieval Adapter

**Files:**
- Create: `src/isotope/memory/retrieval.py`
- Test: `tests/unit/memory/test_memory_hybrid_retrieval.py`

- [ ] **Step 1: Write failing memory adapter tests**

Create `tests/unit/memory/test_memory_hybrid_retrieval.py`:

```python
from __future__ import annotations

from isotope.memory.retrieval import query_memory_records_hybrid
from isotope.platform.schemas.memory import MemoryRecord
from isotope.rag.embeddings import DeterministicEmbeddingProvider
from isotope.rag.vector_store import InMemoryVectorStore


def _record(memory_id: str, summary: str, content: dict | None = None) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        scope="run",
        content=content or {"secret": "SECRET_CONTENT_SHOULD_NOT_BE_INDEXED"},
        summary=summary,
        source_refs=[{"kind": "artifact", "id": memory_id}],
        provenance={"run_id": "run_1", "execution_id": "exec_1", "action_type": "write_memory"},
        created_at="2026-06-04T00:00:00+00:00",
        supersedes=[],
        quality="candidate",
    )


def test_memory_hybrid_retrieval_indexes_low_sensitive_preview_fields_only():
    records = [
        _record("mem_public", "summary-only planner context"),
        _record("mem_secret", "unrelated", {"secret": "summary-only planner context"}),
    ]

    result = query_memory_records_hybrid(records, query="summary-only planner context", limit=5)

    assert [record.memory_id for record in result.visible] == ["mem_public"]
    assert result.backend == "bm25"
    assert result.dense_status == "not_configured"


def test_memory_hybrid_retrieval_can_include_dense_only_hits():
    records = [
        _record("mem_sparse", "exact portfolio interview"),
        _record("mem_dense", "career story"),
    ]
    embeddings = DeterministicEmbeddingProvider(dimensions=8)
    vector_store = InMemoryVectorStore()
    vector_store.upsert(
        [
            ("mem_dense", embeddings.embed("portfolio interview"), {}),
        ]
    )

    result = query_memory_records_hybrid(
        records,
        query="portfolio interview",
        limit=5,
        embedding_provider=embeddings,
        vector_store=vector_store,
    )

    assert sorted(record.memory_id for record in result.visible) == ["mem_dense", "mem_sparse"]
    assert result.backend == "hybrid"
    assert result.dense_status == "ok"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
python3.13 -m pytest tests/unit/memory/test_memory_hybrid_retrieval.py -q
```

Expected: FAIL with missing `isotope.memory.retrieval`.

- [ ] **Step 3: Implement memory retrieval adapter**

Create `src/isotope/memory/retrieval.py`:

```python
"""Memory-specific adapters for generic retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from isotope.platform.schemas.memory import MemoryRecord
from isotope.rag.documents import RetrievalDocument
from isotope.rag.embeddings import EmbeddingProvider
from isotope.rag.hybrid import HybridRetriever
from isotope.rag.vector_store import VectorStore


@dataclass(frozen=True)
class MemoryQueryMatches:
    all_matches: list[MemoryRecord]
    visible: list[MemoryRecord]
    backend: str
    dense_status: str
    ranking: dict[str, dict[str, Any]]


def query_memory_records_hybrid(
    records: list[MemoryRecord],
    *,
    query: str,
    limit: int,
    run_id: str | None = None,
    session_id: str | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    vector_store: VectorStore | None = None,
) -> MemoryQueryMatches:
    filtered = [
        record
        for record in records
        if _record_allowed(record, run_id=run_id, session_id=session_id)
    ]
    documents = [_memory_record_document(record) for record in filtered]
    result = HybridRetriever(
        embedding_provider=embedding_provider,
        vector_store=vector_store,
    ).search(query=query, documents=documents, limit=max(limit, len(documents)))
    records_by_id = {record.memory_id: record for record in filtered}
    ranked_records = [
        records_by_id[hit.document.document_id]
        for hit in result.hits
        if hit.document.document_id in records_by_id
    ]
    return MemoryQueryMatches(
        all_matches=ranked_records,
        visible=ranked_records[:limit],
        backend=result.backend,
        dense_status=(result.metadata or {}).get("dense_status", "unknown"),
        ranking={
            hit.document.document_id: {
                "score": hit.score,
                "source": hit.source,
                "metadata": dict(hit.metadata or {}),
            }
            for hit in result.hits
        },
    )


def _record_allowed(
    record: MemoryRecord,
    *,
    run_id: str | None,
    session_id: str | None,
) -> bool:
    if run_id is not None and record.provenance.get("run_id") != run_id:
        return False
    if session_id is not None and record.provenance.get("session_id") != session_id:
        return False
    return True


def _memory_record_document(record: MemoryRecord) -> RetrievalDocument:
    source_text = " ".join(str(value) for ref in record.source_refs for value in ref.values())
    provenance_text = " ".join(str(value) for value in record.provenance.values())
    return RetrievalDocument(
        document_id=record.memory_id,
        title=record.summary,
        summary=" ".join(
            part
            for part in (
                record.summary,
                source_text,
                provenance_text,
                record.scope,
                record.quality,
            )
            if part
        ),
        metadata={
            "scope": record.scope,
            "quality": record.quality,
            "source_refs": [dict(ref) for ref in record.source_refs],
            "provenance": dict(record.provenance),
        },
        sensitivity="low",
    )
```

- [ ] **Step 4: Run memory adapter tests**

Run:

```bash
python3.13 -m pytest tests/unit/memory/test_memory_hybrid_retrieval.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/memory/retrieval.py tests/unit/memory/test_memory_hybrid_retrieval.py
git commit -m "feat(memory): adapt records to hybrid retrieval"
```

## Task 6: Wire Memory Query To Hybrid Retrieval

**Files:**
- Modify: `src/isotope/memory/views.py`
- Modify: `src/isotope/memory/__init__.py`
- Test: `tests/integration/memory/test_memory_query_authorization_boundary.py`
- Test: `tests/unit/agents/loop/test_agent_loop_memory_integration.py`

- [ ] **Step 1: Add failing public-shape regression test**

Append to `tests/integration/memory/test_memory_query_authorization_boundary.py`:

```python
def test_memory_query_reports_retrieval_backend_without_full_content_read():
    store = MemoryRecordStore()
    service = memory.LocalMemoryQueryService(memory_store=store)

    result = service.query(
        run_id="run_001",
        query="controlled expand",
        grants={"memory": {"query": True}},
        caller_context={
            "run_id": "run_001",
            "caller": "test",
            "purpose": "backend_metadata",
        },
        limit=2,
    )

    assert result["status"] == "ok"
    assert result["retrieval"]["backend"] == "bm25"
    assert result["retrieval"]["dense_status"] == "not_configured"
    assert "SECRET" not in str(result)
```

- [ ] **Step 2: Run the new regression test to verify it fails**

Run:

```bash
python3.13 -m pytest tests/integration/memory/test_memory_query_authorization_boundary.py::test_memory_query_reports_retrieval_backend_without_full_content_read -q
```

Expected: FAIL with missing `retrieval` key.

- [ ] **Step 3: Replace memory query ranking**

In `src/isotope/memory/views.py`, make `query_memory_records(...)` delegate to the new helper:

```python
from .retrieval import MemoryQueryMatches as _HybridMemoryQueryMatches
from .retrieval import query_memory_records_hybrid
```

Replace the body of `query_memory_records(...)` with:

```python
def query_memory_records(
    records: list[MemoryRecord],
    *,
    query: str,
    run_id: str | None = None,
    session_id: str | None = None,
    limit: int = 20,
) -> _HybridMemoryQueryMatches:
    if limit <= 0:
        raise ValueError("limit must be positive")
    clean_query = _required_query(query)
    return query_memory_records_hybrid(
        records,
        query=clean_query,
        run_id=run_id,
        session_id=session_id,
        limit=limit,
    )
```

In `src/isotope/memory/__init__.py`, add retrieval metadata to `LocalMemoryQueryService.query(...)` result:

```python
        result: dict[str, Any] = {
            "status": "ok",
            "capability": "memory_query",
            "content_policy": "memory_record_refs_expandable",
            "retrieval": {
                "backend": matches.backend,
                "dense_status": matches.dense_status,
            },
            "results": results,
        }
```

- [ ] **Step 4: Run targeted memory tests**

Run:

```bash
python3.13 -m pytest tests/integration/memory/test_memory_query_authorization_boundary.py tests/unit/memory/test_memory_views.py tests/unit/agents/loop/test_agent_loop_memory_integration.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/memory/views.py src/isotope/memory/__init__.py tests/integration/memory/test_memory_query_authorization_boundary.py
git commit -m "feat(memory): route query through hybrid retrieval"
```

## Task 7: LanceDB Adapter Behavior With Fake Module

**Files:**
- Modify: `src/isotope/rag/lancedb_store.py`
- Test: `tests/unit/rag/test_lancedb_optional_backend.py`

- [ ] **Step 1: Add a fake-module adapter test**

Append to `tests/unit/rag/test_lancedb_optional_backend.py`:

```python
from isotope.rag.vector_store import VectorSearchHit


class _FakeLanceTable:
    def search(self, query_vector):
        self.query_vector = query_vector
        return self

    def limit(self, limit):
        self.query_limit = limit
        return self

    def to_list(self):
        return [
            {"document_id": "doc_1", "_distance": 0.1, "kind": "memory"},
            {"document_id": "doc_2", "_distance": 0.4, "kind": "memory"},
        ]


class _FakeLanceConnection:
    def open_table(self, table_name):
        assert table_name == "memory"
        return _FakeLanceTable()


class _FakeLanceModule:
    @staticmethod
    def connect(path):
        return _FakeLanceConnection()


def test_lancedb_store_maps_rows_to_vector_hits(monkeypatch, tmp_path):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "lancedb":
            return _FakeLanceModule
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = LanceDBVectorStore(path=tmp_path / "vectors.lance", table_name="memory").search(
        query_vector=[1.0, 0.0],
        limit=2,
    )

    assert result.status == "ok"
    assert result.hits == [
        VectorSearchHit(document_id="doc_1", score=0.9, metadata={"kind": "memory"}),
        VectorSearchHit(document_id="doc_2", score=0.6, metadata={"kind": "memory"}),
    ]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python3.13 -m pytest tests/unit/rag/test_lancedb_optional_backend.py::test_lancedb_store_maps_rows_to_vector_hits -q
```

Expected: FAIL with `dense_unavailable` because the adapter shell does not query the fake table yet.

- [ ] **Step 3: Implement LanceDB query mapping**

Replace `LanceDBVectorStore.search(...)` in `src/isotope/rag/lancedb_store.py`:

```python
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
```

- [ ] **Step 4: Run LanceDB adapter tests**

Run:

```bash
python3.13 -m pytest tests/unit/rag/test_lancedb_optional_backend.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/rag/lancedb_store.py tests/unit/rag/test_lancedb_optional_backend.py
git commit -m "feat(rag): map lancedb search results"
```

## Task 8: Documentation And Final Verification

**Files:**
- Modify: `docs/current/agent-task-queue.md`
- Modify: `docs/current/terminology.md`
- Test: targeted command set below

- [ ] **Step 1: Update current docs**

In `docs/current/terminology.md`, add or update a row for hybrid retrieval:

```markdown
| hybrid retrieval | 通用 RAG 检索基建，先用 BM25 稀疏检索，配置 dense backend 时再融合向量检索；第一外部后端目标是 LanceDB，失败时降级 BM25 | RAG/检索 | `src/isotope/rag/hybrid.py`, `src/isotope/rag/lancedb_store.py` |
```

In `docs/current/agent-task-queue.md`, update the memory/default-context note to say:

```markdown
`default_context.memory` 现在通过通用 hybrid retrieval helper 查询低敏
`MemoryRecord` preview 字段；未配置 LanceDB 或 dense 查询失败时继续走 BM25。
`controlled_expand` 仍然是唯一读取 `MemoryRecord.content` 的授权路径。
```

- [ ] **Step 2: Run targeted verification**

Run:

```bash
python3.13 -m pytest tests/unit/rag tests/unit/memory/test_memory_hybrid_retrieval.py tests/unit/memory/test_memory_views.py tests/integration/memory/test_memory_query_authorization_boundary.py tests/unit/agents/loop/test_agent_loop_memory_integration.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run import compatibility check**

Run:

```bash
PYTHONPATH=src python3.13 - <<'PY'
from isotope.rag import SummarySearchDocument, rank_summary_documents
from isotope.rag import RetrievalDocument, SparseRetriever
print(SummarySearchDocument.__name__)
print(rank_summary_documents("x", []))
print(RetrievalDocument(document_id="d", title="t"))
print(SparseRetriever().backend)
PY
```

Expected output includes:

```text
SummarySearchDocument
[]
RetrievalDocument(document_id='d', title='t'
bm25
```

- [ ] **Step 4: Inspect changed files and commit**

Run:

```bash
git status --short
git diff --check
```

Expected: only retrieval, memory, tests, and docs files are changed; `git diff --check` exits 0.

Commit:

```bash
git add docs/current/agent-task-queue.md docs/current/terminology.md
git commit -m "docs(rag): document hybrid retrieval backend"
```

## Self-Review

- Spec coverage: Tasks 1 and 7 cover optional LanceDB adapter and fallback; Tasks 2-4 cover generic BM25, vector, and hybrid contracts; Tasks 5-6 cover `memory.query`; Task 8 covers docs and verification.
- Scope control: Supervisor workspace context, artifact full-content indexing, web-scale research indexing, and UI administration are not implemented in this slice.
- Boundary control: The memory adapter indexes summary, refs, provenance, scope, and quality only. `MemoryRecord.content` remains behind controlled expand.
- Type consistency: `RetrievalDocument.document_id`, `VectorSearchHit.document_id`, and `MemoryRecord.memory_id` are mapped explicitly by `src/isotope/memory/retrieval.py`.
- Placeholder scan: This plan uses concrete files, tests, commands, expected failures, and commit messages for each task.
