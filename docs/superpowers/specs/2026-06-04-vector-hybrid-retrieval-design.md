# Vector Hybrid Retrieval Design

Date: 2026-06-04

## Goal

Add a general retrieval capability that combines the existing BM25 sparse
ranking with dense vector search through an external vector-store backend.

This is not a memory-only feature. `memory.query`, `supervisor.request_context`,
artifact summaries, research sources, and imported observations should all be
able to use the same retrieval contracts over time.

## Current Context

Isotope already has a reusable BM25 scorer in `src/isotope/rag/retrieval.py`:

- `SummarySearchDocument`
- `SummarySearchHit`
- `rank_summary_documents(...)`

The user-facing `SearchFlow` and Supervisor `request_project_context` path
already reuse this scorer for ranked public-summary and workspace-context
search. `memory.query` does not yet use it; it still uses a separate term
overlap scorer in `src/isotope/memory/views.py`.

The existing memory and Supervisor projection rules still apply:

- retrieval previews must stay low-sensitive by default;
- full memory content is only materialized through controlled expand grants;
- artifact full content must not be read through summary retrieval;
- view and LLM-facing payloads should keep using public contracts instead of
  private JSONL or raw file stitching.

## Design Decision

Use a mature external vector database or vector index backend. Do not implement
the vector database ourselves.

Isotope should own:

- retrieval document contracts;
- index lifecycle decisions;
- backend selection and configuration;
- sparse and dense score normalization;
- result fusion;
- content and permission boundaries;
- fallback behavior.

Isotope should not own:

- approximate nearest-neighbor internals;
- vector compression and storage engines;
- concurrent vector persistence;
- low-level durability and compaction;
- backend-specific query planning.

## Approaches Considered

### Recommended: LanceDB Adapter First

Add generic `rag` contracts and a backend adapter for one mature local-first
vector store. BM25 remains in-tree, dense search goes through the adapter, and
hybrid ranking is performed in Isotope.

LanceDB is the first adapter target because Isotope is not only indexing text
memory. Future artifacts include screenshots, UI state captures, screen
recordings, image/audio/video evidence, research sources, and generated
observations. LanceDB's table-oriented local storage, multimodal positioning,
vector search, full-text search, hybrid search, and schema evolution fit that
broader evidence-library direction better than a text-only vector-store slice.

### Alternative: In-Memory Dense Index First

Keep vectors in process and perform exact cosine similarity over a JSON or
SQLite sidecar.

This is simple for tests, but it does not satisfy the long-term requirement to
connect a vector database. It is acceptable only as a deterministic test backend,
not the production backend.

### Alternative: Backend-Native Hybrid Search

Use a vector database that supports hybrid search internally and delegate all
fusion to the backend.

This can be powerful, but it leaks backend-specific ranking semantics into the
product contract too early. Isotope should keep its own result contract and
fusion policy first, then optionally optimize per backend later.

## Scope

In scope for the first implementation slice:

- Add generic retrieval contracts under `src/isotope/rag/`.
- Reuse `rank_summary_documents(...)` as the sparse side.
- Add a vector-store protocol and at least one deterministic local/test backend.
- Add a LanceDB adapter shape without making Isotope depend on it for core tests.
- Add hybrid retrieval with deterministic rank fusion.
- Make `memory.query` use the generic hybrid retriever first, with BM25 fallback.
- Preserve `memory.query` output shape and controlled-expand behavior.
- Document the backend choice and fallback policy.

Out of scope for the first implementation slice:

- Building an ANN engine in Isotope.
- Indexing raw artifact full content.
- Replacing Supervisor workspace context search in the same commit.
- Web-scale research source indexing.
- UI controls for backend administration.
- Online background reindexing daemons.

## Architecture

The retrieval stack should be layered:

1. `RetrievalDocument`: a low-sensitive document shape with id, title, summary,
   optional body text, metadata, and sensitivity flags.
2. `SparseRetriever`: wraps the existing BM25 scorer.
3. `VectorStore`: protocol for indexing/querying dense vectors through a
   backend.
4. `EmbeddingProvider`: protocol for turning document/query text into dense
   vectors. Tests use deterministic embeddings.
5. `HybridRetriever`: runs sparse and dense retrieval, then fuses ranked lists.
6. Callers adapt their local domain records into `RetrievalDocument` values and
   map hits back to their existing public payloads.

The initial production backend should be a LanceDB adapter, not a hard
dependency in the default install. The LanceDB optional dependency can be added
after the adapter is validated in code. If no dense backend is configured,
hybrid retrieval reports `dense_status="not_configured"` and returns BM25
results.

LanceDB is the first target because the long-term retrieval surface is broader
than text RAG:

- local-first embedded storage fits a desktop/supervisor workbench;
- table schema evolution fits new metadata, embedding columns, OCR, captions,
  and labels;
- multimodal tables can represent screenshots, images, audio/video refs,
  transcripts, and generated evidence side by side;
- vector, full-text, SQL, and hybrid retrieval can grow under one table model;
- indexes remain derived and rebuildable from Isotope's source artifacts,
  memory records, and observation stores.

## Data Flow

Memory query:

`FileMemoryStore.list_records()` -> `MemoryRecord` previews ->
`RetrievalDocument` values -> `HybridRetriever` -> ranked memory ids ->
existing `memory.query` preview payload -> optional controlled expand.

Supervisor workspace context, later:

workspace candidate lines -> `RetrievalDocument` values -> `HybridRetriever` ->
existing `ContextItem` payloads and `context_results.jsonl`.

Artifacts and research sources, later:

summary/provenance/source metadata -> `RetrievalDocument` values ->
`HybridRetriever` -> public summary refs. Full content remains behind explicit
retrieval grants.

## Fusion Policy

Use Reciprocal Rank Fusion (RRF) for the first slice:

```text
score(document) = sum(weight(source) / (k + rank(source, document)))
```

Recommended defaults:

- `sparse_weight = 1.0`
- `dense_weight = 1.0`
- `rrf_k = 60`

RRF is stable because it combines rankings rather than comparing raw BM25 and
cosine scores directly. Raw backend scores can still be included in diagnostic
metadata but should not become the public ranking contract.

## Backend Policy

Backend behavior should be explicit:

- `bm25`: sparse-only fallback, always available.
- `hybrid`: sparse plus dense when the vector backend is configured and healthy.
- `dense_unavailable`: dense path failed or is not configured; results come from
  BM25 and include fallback metadata.

Milvus Lite and Qdrant remain valuable later adapters:

- Milvus Lite is strong when Isotope wants database-native dense, sparse, and
  hybrid search with a path to Standalone/Distributed Milvus.
- Qdrant is strong when Isotope wants a direct local-to-service vector-search
  path with mature payload filtering and server deployment.

Neither should be the first backend unless the LanceDB spike fails on Python
3.13 installation, local persistence, hybrid query behavior, or optional
dependency isolation.

## Error Handling

- Invalid queries still raise the existing validation errors.
- Missing vector backend does not fail product queries.
- Embedding failures do not read full content and fall back to BM25.
- Vector index misses return sparse results when available.
- LanceDB import, schema, or query failures are converted to dense-unavailable
  metadata before falling back.
- Malformed memory records keep the current store behavior.
- Backend-specific exceptions are converted into low-sensitive retrieval status
  metadata.

## Security And Privacy

Index documents must be built from the same low-sensitive fields that the caller
is already allowed to expose. For the first memory slice, the dense index text is
limited to summary, source refs, provenance preview fields, scope, and quality.
`MemoryRecord.content` is not embedded by default.

For artifacts, dense indexing must start from summaries and provenance. Full
artifact content indexing requires a separate design because it changes the
content exposure boundary.

## Testing

Tests should prove:

- BM25 ranking stays available through the generic sparse retriever.
- Deterministic dense backend can rank a document absent from sparse results.
- Hybrid RRF merges sparse and dense hits without duplicate results.
- Dense backend failure falls back to BM25 with status metadata.
- `memory.query` preserves its public output shape.
- `memory.query` does not read or embed `MemoryRecord.content` without controlled
  expand.
- Controlled expand still materializes only authorized matched records.

Run targeted `rag`, `memory`, and agent-loop memory tests before broader
Supervisor context tests.

## Implementation Notes

Suggested modules:

- `src/isotope/rag/documents.py`
- `src/isotope/rag/sparse.py`
- `src/isotope/rag/vector_store.py`
- `src/isotope/rag/embeddings.py`
- `src/isotope/rag/hybrid.py`
- `src/isotope/rag/lancedb_store.py`
- `src/isotope/memory/retrieval.py`

Keep existing imports from `isotope.rag` working by re-exporting the current
BM25 symbols.

The implementation should avoid forcing a new dependency into the base package
while the LanceDB adapter is validated as an optional backend.
