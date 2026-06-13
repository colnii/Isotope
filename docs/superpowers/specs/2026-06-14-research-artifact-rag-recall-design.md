# Research Artifact RAG Recall Design

## Goal

Make `research.report` artifacts a second caller of the generic `rag.index`
service so research report previews can be recalled without going through the
memory path.

## Scope

This slice adds preview-only recall over existing `research.report` artifact
metadata. It does not inspect report content, re-fetch web sources, create memory
records, add persistent vector storage, or automatically invoke recall from every
Supervisor turn.

## Current Problem

`research.search` writes durable `research.report` artifacts and
`research.promote` can build a memory write proposal from a report. Dense
retrieval is now generic under `isotope.rag`, but the only live caller is still
memory. A non-memory caller is needed to prove RAG is not bound to
`MemoryRecord` or memory expansion rules.

## Design

Add a research-specific preview adapter:

- enumerate artifacts under `runs/*/artifacts/*.json`;
- keep only `artifact_type == "research.report"`;
- read only top-level metadata fields such as `artifact_id`, `run_id`,
  `summary`, `ref`, `provenance`, `basis_refs`, and `source_refs`;
- convert each preview into a `RetrievalDocument`;
- call `build_rag_index(documents, dense_retrieval)`;
- query with `HybridRetriever`;
- return ranked artifact previews with a `content_policy` stating that report
  content is available only through explicit artifact inspect/expand paths.

The capability runner exposes this through `research.recall`. The model provides
`query` and optional filters; runtime injects `root`. The output remains
artifact-preview shaped, not report-body shaped.

## Data Flow

```text
research.report artifact JSON metadata
  -> ResearchArtifactPreview
  -> RetrievalDocument
  -> build_rag_index(...)
  -> HybridRetriever.search(...)
  -> public research_recall payload
```

## Safety

`research.recall` must not call `ArtifactStore.get_content(...)` or
`inspect_research_artifact(...)`, and must not return report content. Tests write
sensitive strings into artifact content and assert those strings never appear in
the recall payload.

## Testing

Add focused tests for:

- preview recall returns `research.report` metadata and hides report content;
- local dense config returns `retrieval.backend="hybrid"` and
  `dense_status="ok"`;
- default behavior remains `bm25/not_configured`;
- optional `run_id` filters the preview corpus;
- capability catalog/runner exposes `research.recall` with the preview-only
  safety boundary.
