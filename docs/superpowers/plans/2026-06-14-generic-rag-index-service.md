# Generic RAG Index Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move local dense index wiring from `memory` into a reusable `rag` service over `RetrievalDocument`.

**Architecture:** Add `src/isotope/rag/index.py` as the generic config/index builder. Memory keeps only `MemoryRecord` projection and output mapping, then calls the generic builder. The first backend remains explicit local deterministic dense retrieval; default behavior remains BM25-only.

**Tech Stack:** Python 3.13, pytest, existing `RetrievalDocument`, `HybridRetriever`, `DeterministicEmbeddingProvider`, and `InMemoryVectorStore`.

---

### Task 1: Generic RAG Index Module

**Files:**
- Create: `tests/unit/rag/test_index.py`
- Create: `src/isotope/rag/index.py`
- Modify: `src/isotope/rag/__init__.py`

- [ ] **Step 1: Write failing tests**

```python
from isotope.rag import RetrievalDocument
from isotope.rag.index import build_rag_index, parse_rag_index_config


def test_build_rag_index_returns_none_without_dense_config():
    assert build_rag_index([], None) is None


def test_local_rag_index_builds_dense_components_for_documents():
    documents = [
        RetrievalDocument(document_id="doc_1", title="semantic vector search"),
    ]

    index = build_rag_index(
        documents,
        {"backend": "local", "dimensions": 8},
    )

    components = index.components()
    result = components.vector_store.search(
        query_vector=components.embedding_provider.embed("semantic vector search"),
        limit=5,
    )
    assert result.status == "ok"
    assert [hit.document_id for hit in result.hits] == ["doc_1"]


def test_rag_index_config_rejects_unknown_backend():
    try:
        parse_rag_index_config({"backend": "unknown"})
    except ValueError as exc:
        assert "dense_retrieval.backend" in str(exc)
    else:
        raise AssertionError("unknown backend should fail")
```

- [ ] **Step 2: Run tests to verify failure**

Run: `PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/rag/test_index.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'isotope.rag.index'`.

- [ ] **Step 3: Implement minimal module**

Create dataclasses `RagIndexConfig`, `RagIndexComponents`, `RagIndex`; implement `parse_rag_index_config(...)`, `build_rag_index(...)`, and document text extraction from `RetrievalDocument.title/summary/body`.

- [ ] **Step 4: Run focused tests**

Run: `PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/rag/test_index.py tests/unit/rag/test_hybrid_retriever.py -q`

Expected: PASS.

### Task 2: Memory Migration

**Files:**
- Modify: `src/isotope/memory/dense.py`
- Modify: `tests/unit/memory/test_memory_dense_retrieval.py`
- Modify: `tests/unit/capabilities/memory/test_dense_retrieval.py`

- [ ] **Step 1: Update tests to keep behavior fixed**

Existing tests already require `memory.query` and `memory.recall` to return `hybrid/ok` and keep `MemoryRecord.content` hidden.

- [ ] **Step 2: Replace memory-local dense construction**

Make `memory.dense` delegate config parsing and index construction to `isotope.rag.index`, keeping `build_memory_dense_retrieval(...)` as a compatibility wrapper for memory callers.

- [ ] **Step 3: Run focused tests**

Run: `PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/memory/test_memory_dense_retrieval.py tests/unit/capabilities/memory/test_dense_retrieval.py -q`

Expected: PASS.

### Task 3: Verification and Commit

**Files:**
- Modify: `docs/current/terminology.md`
- Modify: `docs/current/agent-task-queue.md`

- [ ] **Step 1: Update docs**

Document `src/isotope/rag/index.py` as the generic local dense index boundary, with memory as the first caller.

- [ ] **Step 2: Run verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/rag tests/unit/memory tests/unit/capabilities/test_memory.py tests/unit/capabilities/memory/test_dense_retrieval.py -q
git diff --check
scripts/dev-eval changed_surface --base origin/main --json
```

If `changed_surface` requires an eval, run its `recommended_command`.

- [ ] **Step 3: Commit and push**

Run:

```bash
git add docs/current/terminology.md docs/current/agent-task-queue.md docs/superpowers/specs/2026-06-14-generic-rag-index-service-design.md docs/superpowers/plans/2026-06-14-generic-rag-index-service.md src/isotope/rag/__init__.py src/isotope/rag/index.py src/isotope/memory/dense.py tests/unit/rag/test_index.py
git commit -m "feat(rag): add generic local index service"
git push
```
