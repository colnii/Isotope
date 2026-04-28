# Isotope Current Status

本文是当前仓库的状态入口。后续 agent 开始新任务前应先读这里，再决定是否需要查阅更细的 spec / architecture / implementation plan。

## Repo Status

- `isotope` 是独立的 kernel-first agent runtime 项目。
- 当前代码已经从 `x-agent` staging snapshot 迁移到 `/home/lumber/Github/isotope`。
- `x-agent` 不是 Isotope 的 canonical repo；后续 Isotope 实现不应回到 `x-agent` 扩展。
- 最新 implementation commit：`067d48c4d6e693ed305d5794fd18d0d71eddd90f`。

## Implemented Slice

当前已实现并由 tests 覆盖的最小 slice：

- file event log
- action chain
- `PolicyDecision.grants` enforcement
- artifact provenance
- structured `ResourceRef`
- projector replay
- `RunState` rebuild
- in-process server facade
- denied / failed / pending boundary
- event envelope validation
- `ResourceRef` validation
- event ordering preservation
- duplicate event protection
- malformed event log fail-fast
- approval requested event boundary
- pending approval projection
- action lifecycle ordering validation
- illegal lifecycle transition fail-fast
- file-backed artifact persistence
- fresh `ArtifactStore` metadata/content read
- malformed artifact file fail-fast
- retrieval authorization validation
- summary-only retrieval boundary
- retrieval content-read prevention
- workspace grants validation
- shared_ro-only workspace binding
- executor uses decision workspace grants only
- policy proposal validation
- policy decision outcome validation
- denied decision no-effective-grants validation
- required grants shape validation
- action compiler input validation
- runtime identity validation from runtime context
- valid minimal intent to canonical `ActionProposal`
- server facade input validation
- malformed client input controlled `ValueError`
- invalid server request no action lifecycle event side effects
- invalid server request no artifact side effects
- fresh `RunState` rebuild remains event-log based
- success path executor event ownership
- `Executor.execute(...)` appends `action.started` before artifact side effect
- `Executor.execute(...)` appends `artifact.created` and `action.completed`
- server facade does not duplicate executor-owned success events
- server facade remains responsible for run-level completion such as `run.completed`
- failure path executor event ownership
- `Executor.execute(...)` appends `action.failed` with the same execution id after started execution fails
- failed execution does not append `artifact.created` / `action.completed` / `run.completed`
- server facade does not duplicate executor-owned failure events
- checkpoint ownership design note 已落文档
- projector / run completion invariant hardening
- `run.completed` requires a completed execution
- `run.completed` cannot override running / failed / pending approval state
- `run.completed` closes later action/artifact lifecycle events
- projector remains canonical-event-only for run completion state
- checkpoint storage boundary
- `FileCheckpointStore` run-scoped opaque blob save/load
- checkpoint required fields: `run_id`, `projector_version`, `basis_event_id`, `state`, `created_at`
- checkpoint `run_id` must match target run
- checkpoint rejects external raw input / provider response / imported snapshot
- missing checkpoint returns `None`
- malformed checkpoint file fail-fast
- checkpoint store does not modify event log
- projector event payload validation hardening
- `PolicyDecision.modified` enters execution lifecycle like `approved`
- malformed projector event payload fail-fast with controlled `ValueError`
- projector validates action decided/started/completed/failed payloads
- projector validates artifact created payload and rejects projected content
- projector validates approval requested payload
- projector remains canonical-event-only and does not read artifact store / executor state / server memory / checkpoint
- minimal checkpoint-assisted projector rebuild
- `RunProjector.rebuild_with_checkpoint(...)`
- no checkpoint falls back to full event log rebuild
- incompatible checkpoint version falls back to full event log rebuild
- compatible checkpoint replays canonical events after `basis_event_id`
- missing checkpoint basis event fail-fast
- checkpoint run_id mismatch fail-fast
- checkpoint cannot hide malformed / lifecycle-invalid event log
- checkpoint-assisted rebuild still runs canonical event validation / lifecycle validation
- checkpoint-assisted rebuild has no public checkpoint API integration
- no CheckpointService
- projector-owned checkpoint creation
- `RunProjector.create_checkpoint(...)`
- checkpoint creation uses canonical events through `project(...)` and cannot bypass validation
- checkpoint contains `run_id`, `projector_version`, `basis_event_id`, `state`, `created_at`
- checkpoint `basis_event_id` equals the last replayed canonical event id
- checkpoint state contains `run_id`, `status`, `current_agent`, `actions`, `artifacts`, `last_event_id`
- checkpoint state excludes artifact content
- checkpoint excludes external raw input / provider response / imported snapshot
- malformed or lifecycle-invalid event stream cannot produce checkpoint
- empty events cannot produce checkpoint
- checkpoint creation returns a derived blob and does not write checkpoint store
- created checkpoint can be saved by `FileCheckpointStore` and used by `rebuild_with_checkpoint(...)`
- checkpoint state schema validation hardening
- `RunProjector.rebuild_with_checkpoint(...)` validates checkpoint state schema only for compatible projector version
- incompatible projector version still falls back to full rebuild even with malformed checkpoint state
- checkpoint `state` must be a dict
- checkpoint `state` must contain `run_id`, `status`, `current_agent`, `actions`, `artifacts`, `last_event_id`
- checkpoint `state.run_id` must match rebuild target run_id
- checkpoint `state.last_event_id` must equal checkpoint `basis_event_id`
- checkpoint `state.status` must be a known run status
- checkpoint `state.actions` must be a dict
- checkpoint `state.artifacts` must be a list
- checkpoint artifact entry cannot contain `content`
- checkpoint artifact entry must contain `ref`, `artifact_type`, `summary`, `provenance`
- malformed checkpoint state fail-fast with controlled `ValueError`
- `FileCheckpointStore` remains opaque blob storage and does not interpret projected state
- projector-owned checkpoint save boundary
- `RunProjector.save_checkpoint(...)`
- save boundary reads canonical events from `event_store.list_events(run_id)`
- save boundary generates checkpoint through projector-owned `create_checkpoint(...)`
- save boundary calls `checkpoint_store.save_checkpoint(run_id, checkpoint)`
- saved checkpoint can be read by `load_latest_checkpoint(...)`
- saved checkpoint can be used by `rebuild_with_checkpoint(...)` and remains equivalent to full rebuild
- empty event log fail-fast without writing checkpoint
- malformed or lifecycle-invalid event stream fail-fast without writing checkpoint
- save checkpoint does not modify event log
- save checkpoint does not read artifact store / executor state / server memory
- checkpoint `basis_event_id` is the last event id in the event log
- saved checkpoint still excludes artifact content / external raw input
- checkpoint prefix consistency hardening
- `RunProjector.rebuild_with_checkpoint(...)` compares checkpoint state with event-log prefix projection at `basis_event_id`
- checkpoint is used for replay only when checkpoint state matches prefix projection
- checkpoint state `status` / `current_agent` / `actions` / `artifacts` mismatch falls back to full rebuild
- checkpoint state with extra action or missing artifact falls back to full rebuild
- fallback full rebuild still runs full event validation
- lifecycle-invalid event log cannot be hidden by checkpoint mismatch fallback
- `FileCheckpointStore` remains opaque and does not perform consistency checks
- checkpoint integrity/hash design note 已落文档
- checkpoint integrity/hash validation
- `RunProjector.create_checkpoint(...)` generates `integrity`
- checkpoint integrity uses `algorithm: sha256` and `checkpoint_hash`
- checkpoint hash input uses deterministic canonical JSON
- checkpoint hash input excludes `integrity` / `checkpoint_hash`
- identical checkpoint content produces stable hash
- modified checkpoint state causes integrity validation failure
- hash mismatch invalidates checkpoint and falls back to full rebuild
- legacy checkpoint without hash still uses existing validation path
- hash match still runs checkpoint state schema validation and prefix consistency validation
- malformed checkpoint file remains fail-fast
- `FileCheckpointStore` remains opaque and only stores hash fields
- hash mismatch cannot hide lifecycle-invalid event log
- server-facing checkpoint boundary design note 已落文档
- `InProcessServer` read path checkpoint-assisted rebuild
- `InProcessServer` constructor supports optional `checkpoint_store`
- `get_run_state` uses full event log rebuild when no `checkpoint_store` is configured
- `get_run_state` calls projector-owned `RunProjector.rebuild_with_checkpoint(...)` when `checkpoint_store` is configured
- server does not directly read or interpret checkpoint `state`
- server does not create checkpoints or write checkpoint store from `get_run_state`
- `create_checkpoint(...)` remains `not_enabled`
- checkpoint missing / invalid / mismatch / incompatible falls back to full rebuild
- lifecycle-invalid event log still fail-fast and cannot be hidden by checkpoint fallback
- checkpoint save trigger boundary design note 已落文档
- internal-only checkpoint save trigger
- `InProcessServer.save_checkpoint_for_run(run_id)`
- `save_checkpoint_for_run(...)` returns `not_enabled` without configured `checkpoint_store`
- `save_checkpoint_for_run(...)` only calls projector-owned `RunProjector.save_checkpoint(...)` when `checkpoint_store` is configured
- saved checkpoint trigger returns minimal metadata: `status`, `run_id`, `basis_event_id`
- saved checkpoint trigger does not return full checkpoint state
- saved checkpoint trigger does not modify event log
- saved checkpoint trigger does not read artifact content / executor state / server memory
- empty / malformed / lifecycle-invalid event stream fail-fast without writing checkpoint
- saved checkpoint can be loaded by `FileCheckpointStore.load_latest_checkpoint(...)`
- saved checkpoint can power `get_run_state(...)` checkpoint-assisted rebuild
- `create_checkpoint(...)` remains `not_enabled`
- event prefix digest design note 已落文档
- event prefix digest minimal validation
- `RunProjector.create_checkpoint(...)` writes event prefix digest metadata into checkpoint `integrity`
- event prefix digest fields: `event_digest_algorithm`, `event_prefix_digest`, `event_digest_basis_event_id`, `event_digest_event_count`, `event_digest_event_envelope_version`
- event prefix digest uses deterministic JSON / UTF-8
- event prefix digest covers canonical events from the first event through `basis_event_id`
- event prefix digest input includes canonical event representation fields: `event_id`, `run_id`, `event_type`, `payload`, `created_at`, `event_envelope_version`
- event append order affects event prefix digest
- prefix event payload changes alter event prefix digest
- event prefix digest mismatch invalidates checkpoint and falls back to full rebuild
- event prefix digest mismatch cannot hide lifecycle-invalid event log
- event prefix digest match still runs checkpoint state schema validation
- event prefix digest match still runs prefix projection consistency validation
- legacy checkpoint without event prefix digest still uses compatibility path
- suffix events still replay after digest-matched checkpoint
- `FileCheckpointStore` remains opaque and does not interpret digest
- `InProcessServer` has no digest-specific behavior
- checkpoint retention / compaction design note 已落文档
- current checkpoint storage remains latest-only
- latest-only checkpoint storage boundary hardening
- checkpoint path remains `runs/{run_id}/checkpoints/latest.json`
- saving a second checkpoint for the same run replaces `latest.json`
- latest-only replacement does not create checkpoint history files
- invalid replacement does not overwrite the existing valid latest checkpoint
- latest-only replacement does not modify event log
- latest-only replacement does not create / delete / rewrite `events.jsonl`
- `checkpoint_path` / `save_checkpoint` / `load_latest_checkpoint` validate run_id path segment
- invalid run_id path segments fail fast with controlled `ValueError`
- `FileCheckpointStore` remains opaque and does not interpret checkpoint business state
- broader retention / compaction remains deferred
- retention / compaction cannot delete, rewrite, compress, or trim canonical event log
- checkpoint deletion must still allow full rebuild from canonical event log
- checkpoint history / old-checkpoint fallback design note 已落文档
- checkpoint candidate loading
- `FileCheckpointStore.load_checkpoint_candidates(run_id)`
- run-scoped checkpoint candidates load newest-to-oldest by checkpoint `created_at`
- checkpoint candidate loading remains storage-opaque and does not interpret projector version / integrity / digest / state semantics
- minimal projector-owned old-checkpoint fallback path
- `RunProjector.rebuild_with_checkpoint(...)` can use checkpoint candidate chain when available
- invalid latest checkpoint can fall back to an older fully valid candidate
- every candidate must independently pass projector-owned validation chain before use
- invalid candidate is not partially read as state
- all invalid candidates fall back to full event-log rebuild
- lifecycle-invalid event log cannot be hidden by older checkpoint fallback
- `save_checkpoint(...)` remains latest-only replacement and does not create history files
- no checkpoint history index is implemented
- server cannot directly select, interpret, or trust old checkpoints outside projector-owned boundaries
- checkpoint history index / retention policy design note 已落文档
- history index is not source of truth and cannot prove checkpoint validity
- retention / GC can only apply to checkpoint blobs or future index metadata, never canonical event log
- corrupt / missing history index cannot let the system skip full event-log replay
- current latest-only save behavior remains unchanged
- checkpoint history save boundary design note 已落文档
- explicit checkpoint history candidate save method
- `FileCheckpointStore.save_checkpoint_history(run_id, checkpoint)`
- history candidate files are written under `runs/{run_id}/checkpoints/` without using `latest.json`
- `save_checkpoint_history(...)` does not overwrite `latest.json`
- invalid history checkpoint is rejected before writing candidate files
- history save does not modify event log
- history candidates can be read by `load_checkpoint_candidates(run_id)` newest-to-oldest
- `FileCheckpointStore` remains opaque and does not interpret checkpoint state / integrity / projector version
- `save_checkpoint(...)` remains latest-only replacement and does not automatically save history
- checkpoint history save integration boundary design note 已落文档
- projector-owned checkpoint history save method
- `RunProjector.save_checkpoint_history(...)`
- history save method reads canonical events from `event_store.list_events(run_id)`
- history save method creates checkpoint through `RunProjector.create_checkpoint(...)`
- history save method calls `checkpoint_store.save_checkpoint_history(run_id, checkpoint)`
- history save method does not call `checkpoint_store.save_checkpoint(...)`
- history save method does not write `latest.json`
- history save method does not modify event log
- empty / malformed / lifecycle-invalid event stream fail-fast without writing history candidate
- `RunProjector.save_checkpoint(...)` remains latest-only
- `InProcessServer.save_checkpoint_for_run(...)` still uses projector-owned latest save by default
- internal-only explicit server checkpoint history save trigger
- `InProcessServer.save_checkpoint_history_for_run(run_id)`
- `save_checkpoint_history_for_run(...)` returns `not_enabled` with capability `checkpoint_history` when no `checkpoint_store` is configured
- `save_checkpoint_history_for_run(...)` delegates only to projector-owned `RunProjector.save_checkpoint_history(run_id, self.event_store, self.checkpoint_store)`
- server does not directly call `checkpoint_store.save_checkpoint_history(...)`
- server does not receive, construct, or interpret checkpoint state for history save
- successful server history save returns minimal metadata: `status`, `run_id`, `basis_event_id`, `checkpoint_kind`
- server history save does not return checkpoint state
- server history save does not modify event log
- server history save does not write `latest.json`
- `InProcessServer.save_checkpoint_for_run(...)` remains latest-only
- `InProcessServer.create_checkpoint(...)` remains `not_enabled`
- checkpoint v0.1 scope freeze 已落文档
- checkpoint v0.1 is functionally sufficient for the current kernel slice
- checkpoint line is frozen unless explicitly reopened by storage growth / performance / operational need
- checkpoint history index / retention / GC remain deferred but are not the next implementation target
- `ActionTypeRegistry` minimal boundary design note 已落文档
- `ActionTypeRegistry` implementation remains deferred until red tests
- registry must not replace `ActionCompiler` / `PolicyEngine` / `Executor`
- registry must not expand `PolicyDecision.grants` or bypass action chain
- checkpoint migration / version negotiation design note 已落文档
- current checkpoint uses `projector_version`; current projector version is `run_projector@v1`
- incompatible checkpoint projector version invalidates checkpoint and falls back to full rebuild
- checkpoint schema remains v0 candidate
- checkpoint schema version fields design note 已落文档
- `projector_version` remains the only implemented checkpoint compatibility version boundary
- `checkpoint_schema_version` / `state_schema_version` / `integrity_schema_version` are not implemented fields
- checkpoint schema version fields cannot override `projector_version` or make checkpoint a source of truth
- `FileCheckpointStore` remains opaque and does not interpret checkpoint schema fields
- event envelope remains slice-only shape, not final protocol
- migration / version negotiation cannot modify canonical event log or skip checkpoint validation chain
- checkpoint projector version boundary hardening
- malformed `projector_version` is not used as compatible checkpoint version
- non-string / empty `projector_version` invalidates checkpoint and falls back to full rebuild
- incompatible or malformed version fallback does not read checkpoint state
- incompatible or malformed version fallback cannot hide lifecycle-invalid event log
- `projector_version` override still controls compatibility when valid
- malformed `projector_version` cannot be accepted by passing the same malformed override
- future sketch fields such as `checkpoint_schema_version` and `state_schema_version` cannot override `projector_version`; event envelope version metadata also cannot override `projector_version`
- compatible checkpoint with future sketch fields still follows the current validation chain
- `FileCheckpointStore` remains opaque and does not interpret version fields
- event envelope versioning design note 已落文档
- minimal event envelope version boundary
- `CanonicalEvent` has `event_envelope_version`
- default event envelope version is `canonical_event_slice@v0`
- legacy event JSON without `event_envelope_version` is read as current slice legacy representation
- empty / non-string / unknown event envelope version is rejected with controlled `ValueError`
- current `CanonicalEvent` envelope remains slice-only implementation shape, not final protocol
- current event envelope contains `event_id`, `run_id`, `event_type`, `payload`, `created_at`, `event_envelope_version`
- event prefix digest input includes `event_envelope_version`
- checkpoint integrity metadata records the digest-bound event envelope version
- checkpoint event envelope version mismatch invalidates checkpoint and falls back to full rebuild without reading checkpoint state
- legacy checkpoint without event envelope version metadata still uses compatibility path
- event envelope version mismatch cannot rewrite event log or make malformed events valid
- event envelope schema registry design note 已落文档
- current only event envelope version is `canonical_event_slice@v0`
- no event envelope schema registry or registry lookup is implemented
- future registry cannot rewrite event log, make malformed events valid, or generate state outside projector-owned boundary

## Tests

当前验证命令：

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel -q
```

当前预期结果：

```text
391 passed
```

Import boundary check:

```bash
rg -n '(^|\s)(from|import) x_agent\b' src/isotope_kernel tests/isotope_kernel || true
```

当前预期：无输出。

## Deferred

以下能力明确 deferred，不能在没有 design/doc patch 和 red tests 前直接实现：

- real LLM
- `ActionTypeRegistry`
- memory write
- external ingestion / `ImportedSnapshot`
- public checkpoint API / HTTP endpoint
- automatic checkpoint scheduling
- CheckpointService
- `save_checkpoint(...)` semantic change / automatic history persistence
- checkpoint history index
- checkpoint GC
- checkpoint retention policy
- checkpoint inspection API
- signature / MAC / key management
- checkpoint migration / version negotiation implementation
- checkpoint migrator registry
- `checkpoint_schema_version` field
- `state_schema_version` field
- `integrity_schema_version` field
- schema registry
- checkpoint schema registry
- state schema registry
- integrity schema registry
- event schema registry
- payload schema registry
- event envelope schema registry
- event envelope registry lookup
- event migration
- audit event for checkpoint migration
- content-addressed event ids
- event log compaction
- SSE
- auth
- multi-agent concurrency
- real HTTP API

## Forbidden

当前禁止：

- import `x_agent.*`
- 复制 `x-agent` assessment pipeline
- 把 v0 implementation shape 当成永久 protocol

## Suggested Next Step

下一步建议优先做：

- `ActionTypeRegistry` minimal boundary red tests
- first registry red tests should cover `call_tool` + `write_artifact_tool`, unknown tool fail-closed, malformed registry entry fail-fast
- memory write/query boundary docs only if `ActionTypeRegistry` is not the immediate next slice
- external ingestion / `ImportedSnapshot` boundary docs only after the next kernel surface is explicitly selected

checkpoint v0.1 当前 frozen unless explicitly reopened；不要继续默认深挖 checkpoint history index / retention / GC。不要直接进入 real LLM / memory implementation / ingestion implementation。
