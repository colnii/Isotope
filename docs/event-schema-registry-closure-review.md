# Event Schema Registry / Compatibility Closure Review

状态：`first slice complete / closed for now`

本文记录 Event Schema Registry / Compatibility first slice 的 closure review。目标是确认当前实现足以作为 v0.2 kernel boundary，不把它扩大成 JSON Schema、migration framework、plugin registry 或 remote schema system。

## Closure Judgment

Event Schema Registry / Compatibility first slice 可以标为 `first slice complete / closed for now`。

当前 slice 已覆盖：

- `EventSchemaRegistry` 以 static in-process registry 登记 known canonical event types。
- 每个 registered event type 有 `event_schema_version`、required fields metadata 和 validation owner。
- `RunProjector` 在 local payload / lifecycle validation 之前先做 registry check。
- Unknown `event_type` fail-closed，抛 controlled `ValueError`，不会进入 `apply(...)`。
- Unsupported explicit payload `event_schema_version` fail-closed。
- Known legacy/current events 缺少 payload `event_schema_version` 时，只通过 registry known-event compatibility mapping 解释。
- Unknown missing-schema events 仍 fail-closed；没有放宽成 silently ignored。
- `event_envelope_version` 与 payload `event_schema_version` 保持分离。
- checkpoint `projector_version` / event prefix digest envelope version 仍独立于 event schema version。

## Evidence

Implementation evidence:

- `src/isotope_kernel/event_schema.py` defines `EventSchemaMetadata`, `EventSchemaRegistry`, `DEFAULT_EVENT_SCHEMA_VERSION`, and `DEFAULT_EVENT_SCHEMA_REGISTRY`.
- `src/isotope_kernel/projector.py` calls `DEFAULT_EVENT_SCHEMA_REGISTRY.validate_event(event)` before branch-specific payload validation and before `apply(...)`.
- `tests/isotope_kernel/test_event_schema_registry_boundary.py` covers registry existence, registered metadata, unknown event fail-closed, controlled diagnostics, and no JSON Schema / protobuf / Avro dependency.
- `tests/isotope_kernel/test_event_schema_version_compatibility.py` covers envelope/schema version separation, unsupported envelope version, unsupported payload schema version, missing schema metadata for new events, required field fail-fast, checkpoint separation, and no overreach modules.
- `tests/isotope_kernel/test_external_ingestion_boundary.py::test_raw_provider_callback_body_is_not_a_projector_input` now expects raw `provider.callback.received` to fail closed instead of being silently ignored.

Verification evidence from this closure path:

- Targeted event schema + stale Track F test sync: `13 passed`.
- Full regression: `986 passed`.
- `artifact-review --trace`: passed and kept HTTP full-content route `not_enabled`.
- `external-snapshot-review --trace`: passed and kept HTTP `/external-ingestion` `not_enabled`.
- Strict `x_agent.*` import check: no output.
- `/home/lumber/Github/x-agent` scoped status check: no output.

## Boundary Confirmations

No overreach was found:

- No JSON Schema dependency.
- No protobuf / Avro.
- No migration framework.
- No plugin event registry.
- No remote schema registry.
- No new dependency.
- No product event inspection API.
- No provider/webhook ingestion surface.

No kernel semantics were changed outside the intended boundary:

- Event store append-only semantics remain unchanged.
- Executor grants semantics remain unchanged.
- Checkpoint remains an acceleration / integrity boundary, not a schema repair source.
- Event envelope versioning remains separate from payload schema compatibility.

## Residual Notes

This slice is intentionally small. Remaining work is deferred unless explicitly requested:

- schema migration policy
- multi-version projector matrix
- reason-code taxonomy interaction with event schemas
- broader error taxonomy for schema validation errors
- public event inspection / debugging API

Test coverage nuance: `thread.created` is registered because `InProcessServer.create_run(...)` emits it and full regression exercises it. The explicit known-event unit test focuses on the main canonical event families and can be expanded later if desired, but this is not a blocker for closure.

## Next Suggested Path

Recommended next batch: `External Review Package Refresh`.

Reason: after app spikes, workspace lifecycle, policy / registry basis, RCS runtime helpers, and event schema compatibility first slices, the repo is at a coherent review point. A docs-only external review package can summarize what is proven, what remains deferred, and where not to overclaim.

If continuing kernel implementation instead, prefer `Tool Protocol Boundary` before `Worker Handoff App Spike Selection`, because worker handoff will quickly depend on clearer tool result / error / resource ownership semantics.
