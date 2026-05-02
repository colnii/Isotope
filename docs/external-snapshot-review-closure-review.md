# External Snapshot Review Closure Review

状态：`second app spike complete / closed for now`

## 1. Closure Judgment

`external-snapshot-review` 可以标为 second app spike complete / closed for now。

它已经证明一个 deterministic / in-process app-shaped flow 可以压力测试 Track F external observation boundary，而不需要 real provider adapter、webhook、network listener、real HTTP server、real LLM、filesystem mutation 或 memory query engine。

本轮未发现需要修改 `src/` 或 `tests/` 的 correctness bug。

## 2. Verified Flow

当前 `external-snapshot-review` flow:

- creates session / run through the in-process `HttpApiApp` facade。
- creates native action state before importing external observations。
- constructs deterministic `ImportedSnapshot` payloads。
- appends canonical `snapshot.imported` events。
- projects imported observations into `RunState.external_observations`。
- records conflict diagnostics when imported snapshots disagree with native state。
- preserves native `RunState.status` and action status。
- verifies replay restores the same external observation read model。
- verifies checkpoint-assisted rebuild restores the same external observation read model。
- verifies HTTP `/external-ingestion` remains `not_enabled`。
- keeps JSON / trace output summary-oriented and does not expose raw external content or artifact full content。

## 3. Coverage Compared With Artifact Review

`artifact-review` remains the first app spike and covers artifact / content-policy surfaces:

- artifact summary / structured `ResourceRef`。
- controlled full-content retrieval policy。
- review action chain。
- artifact provenance / review artifact handoff。
- replay and checkpoint。

`external-snapshot-review` covers a different kernel surface:

- `ImportedSnapshot` slice model。
- canonical `snapshot.imported` event projection。
- `RunState.external_observations` read model。
- conflict diagnostics。
- native state priority over imported observations。
- replay and checkpoint-assisted rebuild for external observations。
- fail-closed external ingestion surface.

Together, the first two app spikes now cover artifact / provenance and external observation boundaries without opening real integrations.

## 4. Non-Goals Still Intact

Still not implemented:

- real provider adapter。
- external callback / webhook。
- real HTTP server / network listener。
- public external ingestion product API。
- real LLM。
- memory query / storage engine。
- imported observation driving native state。
- reconciliation engine that converts observations into native facts。

HTTP `/external-ingestion` still returns `501 not_enabled` and remains a deferred boundary, not a product API.

## 5. Remaining Friction

No blocker-level friction remains for closing this spike.

Optional future friction:

- deterministic setup still appends canonical `snapshot.imported` events directly for the demo scenario; this is acceptable v0 setup glue while provider adapters and ingestion APIs remain deferred。
- there is no product-facing imported snapshot setup helper; adding one should wait for a dedicated boundary / red-test request。
- conflict diagnostics are intentionally read-model-only and do not attempt reconciliation。

These are future app / integration concerns, not blockers for closing the second app spike.

## 6. Recommended Next Batch

Recommended next batch depends on the next review goal:

- `App Spike Coverage Review` if the goal is to compare the two completed app spikes and identify remaining usability surfaces。
- `Kernel Gap Review Refresh` if the goal is to return from app pressure tests to kernel design backlog。

Do not directly enter real provider adapter, webhook, real HTTP server, real LLM, filesystem mutation, or memory query engine work without a new design boundary and red tests.
