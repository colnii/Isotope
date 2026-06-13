# FastEmbed RAG Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in local FastEmbed embedding provider to the generic RAG index path.

**Architecture:** Keep `dense_retrieval.backend` as the vector-store selector (`local` or `lancedb`). Add `dense_retrieval.embedding_provider` and `dense_retrieval.embedding_model` as the embedding-model selector. Memory and research callers keep passing the same `dense_retrieval` object through `rag.index`.

**Tech Stack:** Python 3.13, pytest, optional `fastembed`, existing `lancedb`, existing `HybridRetriever`.

---

### Task 1: Config And Contract

**Files:**
- Modify: `src/isotope/rag/index.py`
- Modify: `src/isotope/capabilities/catalog.py`
- Test: `tests/unit/rag/test_index.py`
- Test: `tests/unit/capabilities/test_memory.py`
- Test: `tests/unit/capabilities/research/test_recall.py`

- [x] **Step 1: Write failing tests**

Add tests that `parse_rag_index_config(...)` accepts `embedding_provider="fastembed"` and `embedding_model`, rejects unknown providers, and exposes the new fields in the shared dense retrieval input contract.

- [x] **Step 2: Verify red**

Run: `PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/rag/test_index.py::test_rag_index_config_accepts_fastembed_provider tests/unit/rag/test_index.py::test_rag_index_config_rejects_unknown_embedding_provider tests/unit/capabilities/test_memory.py::test_memory_recall_capability_is_registered_as_inspection_product_candidate tests/unit/capabilities/research/test_recall.py::test_runner_discovers_research_recall_from_default_catalog -q`

Expected: fail because config and catalog do not expose FastEmbed yet.

- [x] **Step 3: Implement minimal config**

Extend `RagIndexConfig` with `embedding_provider` and `embedding_model`; validate providers as `deterministic` or `fastembed`; update `_dense_retrieval_input_contract()`.

- [x] **Step 4: Verify green**

Run the same command from Step 2. Expected: pass.

### Task 2: FastEmbed Provider

**Files:**
- Modify: `src/isotope/rag/embeddings.py`
- Modify: `src/isotope/rag/index.py`
- Test: `tests/unit/rag/test_index.py`

- [x] **Step 1: Write failing tests**

Add fake-import tests proving `build_rag_index(...)` instantiates `fastembed.TextEmbedding` with the configured model and degrades to BM25 when the optional package is missing.

- [x] **Step 2: Verify red**

Run: `PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/rag/test_index.py::test_fastembed_rag_index_uses_configured_model tests/unit/rag/test_index.py::test_fastembed_rag_index_degrades_when_dependency_is_missing -q`

Expected: fail because no FastEmbed provider exists.

- [x] **Step 3: Implement minimal provider**

Add `FastEmbedEmbeddingProvider`, lazy-import `fastembed.TextEmbedding`, and add an unavailable provider used when the optional dependency cannot load.

- [x] **Step 4: Verify green**

Run the same command from Step 2. Expected: pass.

### Task 3: Real Smoke

**Files:**
- Modify: `pyproject.toml`
- Modify: `tests/integration/rag/test_lancedb_real_backend.py`
- Modify: `docs/current/supervisor-command-reference.md`
- Modify: `docs/current/agent-task-queue.md`

- [x] **Step 1: Add integration smoke**

Add a real `fastembed` + `lancedb` round trip using a small default model and assertions that semantic retrieval returns the expected document.

- [x] **Step 2: Install dependency**

Run: `/home/lumber/Github/isotope/.venv/bin/python -m pip install -e ".[test]"`

Expected: `fastembed` installs without dependency conflicts.

- [x] **Step 3: Verify targeted tests**

Run: `PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/rag/test_index.py tests/unit/capabilities/test_memory.py tests/unit/capabilities/research/test_recall.py tests/integration/rag/test_lancedb_real_backend.py -q`

Expected: pass.

- [x] **Step 4: Run dev eval gate**

Run: `scripts/dev-eval changed_surface --base origin/main --json`

If `eval_required=true`, run the recommended smoke command and report the hard gates.
