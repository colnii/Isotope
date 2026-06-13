# RAG Dense Memory Close Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `memory.query` and `memory.recall` accept an explicit dense retrieval configuration so local memory recall can run BM25+dense hybrid retrieval instead of always reporting `dense_status=not_configured`.

**Architecture:** Keep the generic retriever in `src/isotope/rag/` and adapt memory records through a small `src/isotope/memory/dense.py` wiring module. The local dense backend is explicit opt-in, builds embeddings from preview-safe `MemoryRecord` fields, and injects the existing `DeterministicEmbeddingProvider` plus `InMemoryVectorStore` into the current hybrid retriever. Default behavior remains BM25-only.

**Tech Stack:** Python 3.13, pytest, existing deterministic embedding provider, existing in-memory vector store, existing capability runner.

---

### Task 1: Capability Input Contract

**Files:**
- Modify: `tests/unit/memory/test_deferred_capabilities.py`
- Modify: `tests/unit/capabilities/test_memory.py`
- Modify: `src/isotope/capabilities/memory.py`
- Modify: `src/isotope/capabilities/catalog.py`

- [ ] **Step 1: Write failing capability tests**

Add tests proving `memory.query` and `memory.recall` accept `dense_retrieval={"backend":"local","dimensions":8}` and return `retrieval.backend="hybrid"` plus `dense_status="ok"` without exposing memory content.

- [ ] **Step 2: Run tests to verify failure**

Run: `PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/memory/test_deferred_capabilities.py::test_memory_query_capability_can_enable_local_dense_retrieval tests/unit/capabilities/test_memory.py::test_memory_query_capability_runner_accepts_local_dense_retrieval -q`

Expected: FAIL because `dense_retrieval` is ignored or not declared by the capability contract.

- [ ] **Step 3: Implement input validation and catalog contract**

Accept `dense_retrieval={"backend": "local", "dimensions": <positive int>}`; reject unknown backend names and invalid dimensions; declare `dense_retrieval` in both `memory.query` and `memory.recall` input contracts.

- [ ] **Step 4: Run focused tests**

Run: `PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/capabilities/test_memory.py tests/unit/memory/test_deferred_capabilities.py -q`

Expected: PASS.

### Task 2: Memory Dense Adapter

**Files:**
- Create: `src/isotope/memory/dense.py`
- Modify: `src/isotope/memory/__init__.py`
- Modify: `src/isotope/memory/retrieval.py`
- Modify: `src/isotope/memory/views.py`
- Test: `tests/unit/memory/test_memory_dense_retrieval.py`

- [ ] **Step 1: Write failing service tests**

Add coverage that `LocalMemoryQueryService(..., dense_retrieval=...)` returns `backend=hybrid`, the default service still returns `bm25/not_configured`, and unknown dense backends are rejected.

- [ ] **Step 2: Run tests to verify failure**

Run: `PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/memory/test_memory_dense_retrieval.py -q`

Expected: FAIL because `LocalMemoryQueryService` has no dense retrieval argument.

- [ ] **Step 3: Implement adapter**

Create a small adapter that validates config, builds `DeterministicEmbeddingProvider`, indexes only preview-safe `MemoryRecord` fields already used by `query_memory_records_hybrid(...)`, and returns the provider/store pair for query injection.

- [ ] **Step 4: Run focused tests**

Run: `PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/rag tests/unit/memory tests/unit/capabilities/test_memory.py -q`

Expected: PASS.

### Task 3: CLI Smoke, Docs, Eval

**Files:**
- Modify: `docs/current/supervisor-command-reference.md`
- Modify: `docs/current/terminology.md`
- Modify: `docs/current/agent-task-queue.md`

- [ ] **Step 1: Run CLI smoke**

Run `isotope-capability run memory.query` against a temp memory store with `dense_retrieval.backend=local`.

Expected: JSON contains `retrieval.backend="hybrid"` and `retrieval.dense_status="ok"`.

- [ ] **Step 2: Update docs**

Document that dense retrieval is opt-in for now; default remains `bm25/not_configured`; the local backend is deterministic smoke wiring, not the external LanceDB backend.

- [ ] **Step 3: Run verification**

Run targeted memory/RAG tests, CLI smoke, `git diff --check`, `scripts/dev-eval changed_surface --base origin/main --json`, and the recommended dev-eval command when required.

Expected: targeted tests pass; dev-eval hard gates pass.
