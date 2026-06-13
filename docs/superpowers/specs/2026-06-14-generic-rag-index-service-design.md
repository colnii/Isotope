# Generic RAG Index Service Design

## Goal

Move dense retrieval wiring out of the memory-specific path so `memory.query`,
`memory.recall`, future research artifacts, workspace summaries, and web source
previews can all use the same RAG index/query contract over
`RetrievalDocument`.

## Scope

This slice builds a generic in-process RAG service under `src/isotope/rag/` and
migrates memory dense retrieval to it. It does not add persistent LanceDB,
pgvector, background reindexing, artifact full-content indexing, or default
desktop auto-enable behavior.

## Current Problem

`HybridRetriever` is generic, but the dense setup currently lives in
`src/isotope/memory/dense.py`. That module validates dense config, creates a
deterministic embedding provider, builds an in-memory vector store, and indexes
documents. As a result, any non-memory caller would need to duplicate or import
memory-specific code to get dense retrieval.

## Design

Add `src/isotope/rag/index.py` with:

- `RagIndexConfig`: validates opt-in dense backend config.
- `RagIndex`: owns `EmbeddingProvider` and `VectorStore` for a set of
  `RetrievalDocument` values.
- `build_rag_index(documents, config)`: returns `None` when dense retrieval is
  not configured, or a ready index when `backend="local"`.
- `RagIndex.components()`: exposes the provider/store pair needed by
  `HybridRetriever` without exposing backend internals to callers.

The local backend keeps using `DeterministicEmbeddingProvider` and
`InMemoryVectorStore`. Embedding text is built from `RetrievalDocument.title`,
`summary`, and `body`; domain callers decide what text is safe to place in those
fields.

Memory keeps only memory-specific responsibilities:

- validate `dense_retrieval` through the generic parser;
- convert `MemoryRecord` into `RetrievalDocument`;
- call the generic RAG index builder;
- map retrieval hits back to memory preview output.

## Data Flow

```text
MemoryRecord / future artifact preview / future workspace summary
  -> caller-specific RetrievalDocument adapter
  -> build_rag_index(documents, dense_retrieval)
  -> HybridRetriever.search(query, documents, provider/store)
  -> caller maps RetrievalHit back to public payload
```

## Error Handling

Unknown dense backend names and invalid dimensions fail validation with field
names that match capability input keys. Missing config returns `None` and keeps
the current `bm25/not_configured` behavior. Backend runtime failures remain
handled by `HybridRetriever`, which reports `dense_unavailable` and falls back to
BM25.

## Testing

Add `tests/unit/rag/test_index.py` for:

- absent config returns no index;
- local config builds an index and produces dense search hits;
- invalid backend/dimensions fail with actionable messages.

Update memory dense tests to prove `memory.query` still returns
`hybrid/ok` when local dense is enabled and still does not expose
`MemoryRecord.content`.

Run targeted `rag`, `memory`, capability memory tests, CLI smoke, and the
Supervisor dev-eval gate when `changed_surface` requires it.
