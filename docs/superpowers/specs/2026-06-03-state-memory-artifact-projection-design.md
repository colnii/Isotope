# State Memory Artifact Projection Design

## Goal

Unify new state and memory-facing views around the existing public projection
contracts. New views must consume `SupervisorStateSnapshot`, `MemoryRecord`
previews, and artifact summaries instead of stitching together private JSONL
ledgers or raw artifact files.

## Current Context

The repository already has the contracts needed for this boundary:

- `build_supervisor_state_snapshot(...)` returns the low-sensitive
  `SupervisorStateSnapshot` payload used by dashboard and desktop snapshot.
- `MemoryRecord`, `FileMemoryStore`, and `isotope.memory.views` expose structured
  memory records and low-sensitive memory previews.
- `RetrievalService.get_artifact_summary(...)` exposes artifact summary,
  reference, and provenance without returning full content.

Existing dashboard and desktop snapshot code already read the Supervisor state
snapshot. The current weaker area is auxiliary status views such as multi-worker
and current-batch, where view adapters can still be built from separately
collected inputs. This change brings those views under the same projection rule.

## Scope

In scope:

- Add tests that make the projection boundary explicit for dashboard,
  desktop/current-batch, multi-worker, memory, and artifact summary inputs.
- Extend `SupervisorStateSnapshot` with low-sensitive memory and artifact
  summary sections that are safe for view adapters.
- Keep multi-worker state derived from `MemoryRecord` values, not private
  worker JSONL files.
- Keep current-batch derived from the already projected active goals and
  managed-worker summaries.
- Keep artifact views summary-only through the retrieval contract.

Out of scope:

- Full artifact content projection.
- Memory controlled-expand changes.
- New storage format or migration.
- Replacing low-level ledger/store/projector code. Those layers may still read
  files because they are the public projection sources.

## Architecture

The boundary is layered:

1. Store/projector/retrieval layer reads durable files and validates schema.
2. Projection layer converts data into low-sensitive public payloads.
3. View adapters consume projection payloads and render JSON/plain UI output.

The important rule is not "no file reads anywhere"; it is "no private file
stitching in new view adapters." File access stays inside `FileMemoryStore`,
`RunProjector`, Supervisor ledgers, worker event channel, and artifact retrieval.

## Data Flow

Supervisor state:

`supervisor/*.jsonl` ledgers -> projection helpers ->
`SupervisorStateSnapshot.to_dict()` -> dashboard, desktop snapshot, current-batch.

Memory:

`memory/*.json` -> `FileMemoryStore.list_records()` -> `MemoryRecord` values ->
memory previews and multi-worker summaries.

Artifacts:

`runs/*/artifacts/*.json` -> `ArtifactStore` -> `RetrievalService` ->
artifact summary payloads. View adapters must not read artifact content unless a
future explicit full-content grant path is added.

## Implementation Shape

- Add memory summary fields to `SupervisorStateSnapshot`:
  `memory_records_total`, `memory_records_by_scope`, and `recent_memory_records`.
- Add artifact summary fields to `SupervisorStateSnapshot`:
  `artifact_summaries_total` and `recent_artifact_summaries`.
- Add small projection helpers in `features/supervisor/state/projection.py` that
  use existing `FileMemoryStore`, `ArtifactStore`, and `RetrievalService`.
- Add an optional `state_snapshot` input to current-batch/dashboard helpers where
  the helper can consume already projected active goals instead of reassembling
  them.
- Keep `platform.state.multi_worker` record-oriented: the reusable core operates
  on `MemoryRecord` lists; the root-reading wrapper remains the store boundary.

## Error Handling

Malformed memory records are already skipped or rejected by the memory store
depending on storage mode. Malformed artifacts should be skipped by the
Supervisor state projection when building a low-sensitive dashboard snapshot,
because a single bad artifact file should not break the whole Supervisor view.
Direct retrieval of a specific artifact summary should keep raising the existing
typed validation errors.

## Testing

Tests should prove:

- `SupervisorStateSnapshot` includes low-sensitive memory and artifact summary
  sections without raw memory content or artifact content.
- Multi-worker summaries can be built from supplied `MemoryRecord` values.
- Dashboard/current-batch can consume the projected snapshot active goals.
- Artifact summary retrieval remains summary-only.

Run the targeted tests first, then the existing supervisor state, desktop
snapshot, memory view, and multi-worker tests.
