# LanceDB RAG Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `dense_retrieval={"backend":"lancedb"}` build and query a real optional LanceDB vector-store index through the existing generic RAG path.

**Architecture:** Keep `HybridRetriever` and RRF ranking unchanged. Extend `rag.index` config parsing to select either the existing in-memory local vector store or a LanceDB-backed vector store; `LanceDBVectorStore` owns optional dependency handling, table creation, upsert, and search row mapping. Memory and research callers continue to pass `dense_retrieval` through the same generic `build_rag_index` boundary.

**Tech Stack:** Python 3.13, pytest, optional `lancedb`, Isotope `RetrievalDocument`, deterministic embedding provider, `HybridRetriever`.

---

### Task 1: LanceDB Store Upsert Contract

**Files:**
- Modify: `tests/unit/rag/test_lancedb_optional_backend.py`
- Modify: `src/isotope/rag/vector_store.py`
- Modify: `src/isotope/rag/lancedb_store.py`

- [ ] **Step 1: Write failing upsert tests**

Add tests proving that missing LanceDB reports `dense_unavailable`, and a fake LanceDB module receives rows with `document_id`, `vector`, and metadata.

```python
def test_lancedb_store_upsert_reports_unavailable_when_dependency_is_missing(monkeypatch, tmp_path):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "lancedb":
            raise ModuleNotFoundError("No module named 'lancedb'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    store = LanceDBVectorStore(path=tmp_path / "vectors.lance", table_name="memory")
    result = store.upsert([("doc_1", [1.0, 0.0], {"kind": "memory"})])

    assert result.status == "dense_unavailable"
    assert result.reason_code == "lancedb_not_installed"
```

```python
def test_lancedb_store_upserts_rows_into_table(monkeypatch, tmp_path):
    fake_module = _FakeWritableLanceModule()
    monkeypatch.setattr(builtins, "__import__", _fake_import_for(fake_module))

    result = LanceDBVectorStore(path=tmp_path / "vectors.lance", table_name="memory").upsert(
        [("doc_1", [1.0, 0.0], {"kind": "memory"})]
    )

    assert result.status == "ok"
    assert fake_module.connections[0].tables["memory"].rows == [
        {"document_id": "doc_1", "vector": [1.0, 0.0], "kind": "memory"}
    ]
```

- [ ] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/rag/test_lancedb_optional_backend.py::test_lancedb_store_upsert_reports_unavailable_when_dependency_is_missing \
  tests/unit/rag/test_lancedb_optional_backend.py::test_lancedb_store_upserts_rows_into_table \
  -q
```

Expected: fail because `LanceDBVectorStore.upsert` does not exist yet.

- [ ] **Step 3: Implement minimal upsert**

Add `VectorUpsertResult`, extend `VectorStore` with `upsert(...)`, and implement `LanceDBVectorStore.upsert(...)` with optional dependency handling:

```python
@dataclass(frozen=True)
class VectorUpsertResult:
    status: str
    reason_code: str | None = None
```

`LanceDBVectorStore.upsert` connects to the configured path, creates or opens the configured table, writes normalized rows, and returns `ok`; missing dependency and write failures return `dense_unavailable`.

- [ ] **Step 4: Verify green**

Run the same two tests and expect them to pass.

### Task 2: `backend="lancedb"` Generic RAG Index

**Files:**
- Modify: `tests/unit/rag/test_index.py`
- Modify: `src/isotope/rag/index.py`
- Modify: `src/isotope/rag/__init__.py` only if a new public type must be exported

- [ ] **Step 1: Write failing config and index tests**

Add tests proving config parsing accepts LanceDB path/table name and `build_rag_index` upserts embedded documents into a LanceDB store.

```python
def test_rag_index_config_accepts_lancedb_backend():
    config = parse_rag_index_config(
        {
            "backend": "lancedb",
            "path": "/tmp/isotope-vectors",
            "table_name": "research",
            "dimensions": 8,
        }
    )

    assert config.backend == "lancedb"
    assert config.path == "/tmp/isotope-vectors"
    assert config.table_name == "research"
    assert config.dimensions == 8
```

```python
def test_lancedb_rag_index_builds_dense_components_for_documents(monkeypatch, tmp_path):
    fake_module = _FakeWritableLanceModule()
    monkeypatch.setattr(builtins, "__import__", _fake_import_for(fake_module))

    index = build_rag_index(
        [RetrievalDocument(document_id="doc_1", title="semantic vector search")],
        {"backend": "lancedb", "path": str(tmp_path / "vectors"), "table_name": "rag", "dimensions": 8},
    )

    assert index is not None
    result = index.components().vector_store.search(
        query_vector=index.components().embedding_provider.embed("semantic vector search"),
        limit=5,
    )
    assert result.status == "ok"
    assert [hit.document_id for hit in result.hits] == ["doc_1"]
```

- [ ] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/rag/test_index.py::test_rag_index_config_accepts_lancedb_backend \
  tests/unit/rag/test_index.py::test_lancedb_rag_index_builds_dense_components_for_documents \
  -q
```

Expected: fail because only `backend="local"` is accepted.

- [ ] **Step 3: Implement index selection**

Extend `RagIndexConfig` with optional `path` and `table_name`; validate `backend` as `local` or `lancedb`; for LanceDB require non-empty string `path` and `table_name`. `build_rag_index` should instantiate `LanceDBVectorStore`, call `upsert(...)`, and still return components so `HybridRetriever` can call `search`.

- [ ] **Step 4: Verify green**

Run the two index tests and expect pass.

### Task 3: Capability Contracts And Caller Tests

**Files:**
- Modify: `src/isotope/capabilities/catalog.py`
- Modify: `tests/unit/capabilities/research/test_recall.py`
- Modify: `tests/unit/capabilities/memory/test_dense_retrieval.py`
- Modify: `docs/current/agent-task-queue.md`
- Modify: `docs/current/supervisor-command-reference.md`
- Modify: `docs/current/terminology.md`

- [ ] **Step 1: Write failing contract tests**

Update existing research and memory dense tests to assert `dense_retrieval.backend` enum includes both `local` and `lancedb`, and that `path/table_name` are exposed for LanceDB.

```python
assert properties["dense_retrieval"]["properties"]["backend"]["enum"] == ["local", "lancedb"]
assert "path" in properties["dense_retrieval"]["properties"]
assert "table_name" in properties["dense_retrieval"]["properties"]
```

- [ ] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/capabilities/research/test_recall.py::test_runner_discovers_research_recall_from_default_catalog \
  tests/unit/capabilities/memory/test_dense_retrieval.py -q
```

Expected: fail because catalog enum still only exposes `local`.

- [ ] **Step 3: Update catalog and docs**

Update `dense_retrieval` schema descriptions for `memory.query`, `memory.recall`, and `research.recall` to include `backend="lancedb"`, `path`, and `table_name`; update current docs to say LanceDB is now an optional vector-store backend and still falls back when unavailable.

- [ ] **Step 4: Verify green**

Run the same tests and expect pass.

### Task 4: Final Verification And Commit

**Files:**
- All changed files

- [ ] **Step 1: Run targeted unit tests**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/rag/test_lancedb_optional_backend.py \
  tests/unit/rag/test_index.py \
  tests/unit/rag/test_hybrid_retriever.py \
  tests/unit/capabilities/research/test_recall.py \
  tests/unit/capabilities/memory/test_dense_retrieval.py \
  tests/unit/features/research/test_research_recall.py \
  tests/unit/memory/test_memory_dense_retrieval.py \
  -q
```

- [ ] **Step 2: Run changed-surface gate**

```bash
scripts/dev-eval changed_surface --base origin/main --json
```

If it requires Supervisor capacity eval, run the recommended command and read generated reviewer prompts.

- [ ] **Step 3: Commit and push**

```bash
git add docs/superpowers/plans/2026-06-14-lancedb-rag-index.md \
  src/isotope/rag/vector_store.py src/isotope/rag/lancedb_store.py src/isotope/rag/index.py \
  src/isotope/capabilities/catalog.py \
  tests/unit/rag/test_lancedb_optional_backend.py tests/unit/rag/test_index.py \
  tests/unit/capabilities/research/test_recall.py tests/unit/capabilities/memory/test_dense_retrieval.py \
  docs/current/agent-task-queue.md docs/current/supervisor-command-reference.md docs/current/terminology.md
git commit -m "feat(rag): add lancedb dense retrieval backend"
git push
```
