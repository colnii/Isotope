# External Ingestion Boundary v0.2

状态：`effectively complete / closed for now`

## 1. Purpose

Track F defines the minimum boundary for external ingestion / `ImportedSnapshot`.

The goal is not to integrate a real provider. The goal is to prevent external raw input from becoming a second source of truth or directly mutating `RunState` / `SessionState`.

Closure decision: Track F is closed for now at boundary / read-model / checkpoint support. It is not a provider integration, webhook, network listener, external ingestion HTTP API, or production ingestion system.

## 2. Why This Track Now

Track D, Track A, Track C, and Track E are closed for now. The v0.2 developer demo has a tag and demonstrates the in-process HTTP facade, approval pause / resume, controlled artifact content policy, checkpoint rebuild, and memory `boundary_only` status.

External ingestion is the next useful kernel boundary because it tests how Isotope accepts observations from outside the canonical event log without letting those observations override native state.

## 3. Current State

Current completed surfaces relevant to this track:

- Artifact store exists.
- Artifact summary / structured `ResourceRef` / provenance boundaries exist.
- Controlled artifact content retrieval requires structured `ResourceRef`, grants, caller context, and purpose.
- HTTP external ingestion routes are still deferred / `not_enabled`.
- Projector rebuilds `RunState` from canonical events and validated checkpoints, not from external raw input.
- Memory remains `boundary_only`; there is no durable memory storage or query engine.
- `src/isotope_kernel/ingestion.py` exists as the first not-enabled / artifact-only boundary.
- `ImportedSnapshot` exists as a slice-only model.
- `snapshot.imported` canonical events can project imported observations into `RunState.external_observations`.
- `RunState.external_observations` now has a stable read-model shape for snapshot id, type, source, freshness, quality, provenance, basis refs, and observation status.
- `external_observations` is included in checkpoint state and restored by checkpoint-assisted rebuild.
- Imported observations do not overwrite native `RunState.status` or action status.
- Projector does not read raw artifact content when projecting imported snapshots.
- Native canonical state takes priority over imported observations.
- Conflicting snapshots are marked as conflict instead of merged into fake certainty.
- Duplicate snapshot identity is controlled and cannot create inconsistent duplicate observations.
- `server.ingest_external_input(...)` remains fail-closed / `not_enabled`.
- Current baseline after the read-model invariants slice is `765 passed`.

## 4. Hard Boundaries

- External raw input must not directly update `RunState` or `SessionState`.
- External raw input must first land as artifact / provenance if it is retained.
- Ingestion can produce only one of these outcomes:
  - canonical event
  - accepted external observation / `ImportedSnapshot`
  - artifact-only provenance
- `ImportedSnapshot` is not a second source of truth. It is an external observation accepted by canonical event.
- Projector only consumes canonical events.
- Imported / derived observation that affects a read model must carry quality / provenance / freshness / basis refs.
- Native state from canonical kernel events has priority over imported observation.
- Conflicting imported snapshots must not be merged into fake certainty.
- Snapshot refs must be structured `ResourceRef`; URI string shortcuts are rejected.
- v0.2 does not implement real provider adapters, OpenAI / Responses integration, GitHub webhooks, hosted ingestion, or network listeners.

## 5. Ingestion Result Semantics

### Artifact-only provenance

Malformed, unsupported, or unauthorised external raw input may be retained only as artifact provenance or rejected. It must not create a native read-model fact.

### Accepted ImportedSnapshot

An accepted `ImportedSnapshot` must be introduced by a canonical event such as `snapshot.imported`.

The event name is a v0.2 candidate, not a permanent protocol commitment.

### Canonical event

If external input is later promoted into a native fact, that promotion must happen through an explicit canonical event with basis refs. It must not happen by letting projector read raw artifact content.

## 6. ImportedSnapshot Shape Candidate

A minimal `ImportedSnapshot` candidate should include:

- `snapshot_id`
- `source_ref`: structured `ResourceRef`
- `scope`: run / session / thread candidate
- `observation_type`
- `observed_at` or equivalent freshness marker
- `summary`
- `basis_refs`
- `quality`
- `provenance`

Quality metadata should include at least:

- `confidence`
- `coverage`
- `freshness`
- optional `conflict_status`

This shape is only a boundary candidate. It should not be treated as a durable external-ingestion protocol.

## 7. Projection Relationship

Imported observations can enter only an observation / diagnostics read-model area unless a later native canonical event explicitly accepts them as native state.

Projector must not:

- read raw artifact content during rebuild
- call provider adapters
- let imported observation overwrite native run / action status
- infer certainty from multiple conflicting snapshots

Native state wins when native canonical events and imported observations disagree.

## 8. Conflict Semantics

Conflicting snapshots must be visible as conflict, ambiguity, or diagnostics. They must not be merged into a deterministic native status without a separate canonical decision event.

Examples:

- An imported observation claims a run completed, but native events show it failed.
- Two imported snapshots disagree on external completion time.
- A snapshot lacks coverage for fields it appears to summarize.

In all cases, the read model must preserve uncertainty instead of manufacturing certainty.

## 9. Read Model / Checkpoint Invariants

`RunState.external_observations` is a projected diagnostics/read-model area, not native state. Each observation must retain:

- `snapshot_id`
- `snapshot_type`
- `source_system`
- `captured_at`
- `quality` with confidence / coverage / freshness-level metadata
- `provenance` with structured raw artifact `ResourceRef`
- `basis_refs`
- observation status / conflict status

The checkpoint state includes `external_observations` because it is part of the `RunState` read model. Checkpoint-assisted rebuild must restore the same observation read model as event-log replay, while still validating shape, rejecting raw content fields, and falling back / failing consistently on malformed state.

External observations must never:

- overwrite native `RunState.status`
- overwrite native action status
- read raw artifact content during projection
- merge conflicting imported snapshots into a deterministic native fact
- become a second source of truth

Conflict metadata must preserve the basis refs that caused the conflict so replay and checkpoint-assisted rebuild remain auditable.

## 10. HTTP / API Relationship

Track F does not open a public ingestion API in this boundary document.

Current HTTP external ingestion routes remain deferred / `not_enabled`. If a future HTTP facade route is added, it must still:

- accept raw input only through explicit ingestion boundary
- store retained raw input as artifact / provenance
- introduce accepted snapshots through canonical events
- reject URI string shortcuts when structured `ResourceRef` is required
- return stable error shape for malformed or unsupported input

## 11. Deferred

- real provider adapter
- OpenAI / Responses ingestion
- GitHub webhook ingestion
- hosted network listener
- automatic reconciliation
- external source as truth
- semantic merge / ranking
- durable external observation index
- UI for conflicts
- memory ingestion or memory query integration

## 12. Tests

Completed first test files:

- `tests/isotope_kernel/test_external_ingestion_boundary.py`
- `tests/isotope_kernel/test_imported_snapshot_projection_boundary.py`

Covered goals:

- raw external input can only be saved as artifact, not directly advance `RunState`.
- malformed external input is artifact-only or rejected, and cannot produce state.
- accepted `ImportedSnapshot` must be introduced by canonical `snapshot.imported` event.
- projector does not read raw artifact content.
- imported observation can enter only observation / diagnostics area, not overwrite native run / action status.
- imported observation must carry confidence / coverage / freshness / basis_refs or equivalent quality metadata.
- conflicting snapshots are marked as conflict and not merged into deterministic state.
- native canonical event wins over imported snapshot.
- snapshot ref must be structured `ResourceRef`, not a URI string.
- external ingestion routes / APIs remain deferred or `not_enabled`.

These first tests define only the initial boundary slice. They do not implement a real provider adapter, external webhook, OpenAI / Responses / GitHub integration, external ingestion HTTP API, or imported-observation-driven native state.

Completed read-model invariant test files:

- `tests/isotope_kernel/test_external_observation_read_model.py`
- `tests/isotope_kernel/test_external_observation_conflicts.py`

Covered goals:

- `RunState.external_observations` has a stable shape with source, freshness, quality, provenance, basis refs, and status.
- observations do not include raw artifact full content.
- observations do not change native run status or action status.
- event-log replay restores the same observation read model.
- checkpoint-assisted rebuild restores the same observation read model.
- malformed observation payloads fail fast and do not create partial observations.
- duplicate snapshot identity is controlled.
- conflicting observations are marked conflict and preserve basis refs.
- native canonical state has priority over imported observations.

These tests extend the Track F boundary without implementing provider adapters, network callbacks, HTTP ingestion, or imported-observation-driven native state.

## 13. Closure Criteria

Track F can be treated as effectively complete for the current v0.2 cycle because:

- raw external input cannot directly update `RunState` / `SessionState`
- `ingestion.py` remains a fail-closed / not-enabled boundary
- `ImportedSnapshot` exists only as a slice model, not a final protocol
- accepted imported snapshots enter through canonical `snapshot.imported`
- projector only projects into `RunState.external_observations`
- imported observations do not override native run/action status
- external observations can be restored by event replay and checkpoint-assisted rebuild
- conflicts are explicit in the read model instead of merged into deterministic native facts
- projector does not read raw artifact content
- HTTP `/external-ingestion` remains `501 not_enabled`
- no provider adapter, webhook, network listener, or new dependency exists

Any future Track F work should start with a new design note / red tests and should not directly implement real provider adapters or public ingestion APIs.
