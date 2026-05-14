# Event Schema Registry / Compatibility Boundary v0.2

状态：first slice complete / closed for now

本文定义 canonical event schema registry（规范事件模式注册表）和 compatibility（兼容性）的最小 kernel contract。该 boundary 的 first green slice 已实现：static in-process `EventSchemaRegistry`、known canonical event metadata、unknown event fail-closed 和 unsupported payload schema version fail-closed。它仍不实现 migration framework、JSON Schema dependency、protobuf、code generation、remote registry 或 plugin event system。

## 1. Purpose

当前 Isotope 已有 canonical event envelope、严格的 known-event payload validation、checkpoint integrity、event prefix digest、registry / policy basis metadata，以及 replay / checkpoint-assisted rebuild。

事件类型继续增加后，kernel 需要固定以下问题：

- `event_type` 到 payload schema 的登记在哪里。
- `event_schema_version` 如何表示。
- 新 projector 遇到 unknown event 或 unsupported schema version 时如何处理。
- schema change 是 additive 还是 breaking。
- checkpoint schema version 和 event schema version 如何区分。

本文件先定义边界；当前 red / green slice 和 closure review 已固定最小行为。Closure review 见 `event-schema-registry-closure-review.md`。

## 2. Definitions

| Term | Definition |
| --- | --- |
| `event_type` | Canonical event 的业务类型，例如 `action.proposed`、`workspace.released`、`snapshot.imported`。 |
| `event_envelope_version` | Event envelope representation version，当前由 `CanonicalEvent.event_envelope_version` 表示，已实现值为 `canonical_event_slice@v0`。它描述事件信封字段和序列化边界，不描述 payload 业务 schema。 |
| `event_schema_version` | 某个 `event_type` payload schema 的版本。当前 first slice 支持 explicit payload metadata；legacy/current known events 缺失该字段时通过 registry compatibility mapping 解释。 |
| `EventSchemaRegistry` | 当前的 in-process static registry，用于登记 `event_type`、`event_schema_version`、required fields 和 validation owner；它不是 JSON Schema / migration framework。 |
| Compatibility policy | 对 old/new events、unknown versions、additive changes、breaking changes 的处理规则。 |
| Additive change | 不改变既有字段含义、不新增必填字段、旧 projector 可忽略或新 schema version 明确登记的 optional 扩展。 |
| Breaking change | 新增 required field、字段语义变化、字段删除、event rename、payload shape 不兼容，或旧 projector 无法确定解释的任何变更。 |
| Unsupported event | 当前 projector / registry 不支持的 `event_type` 或 `event_schema_version`。v0.2 目标 contract 是 fail closed。 |

## 3. Current State

已实现：

- `events.py` owns `EVENT_ENVELOPE_VERSION = "canonical_event_slice@v0"` and `CanonicalEvent` envelope validation。
- Unknown `event_envelope_version` fail-fast。
- Known event payload validation 主要由 `RunProjector._validate_event_payload(...)` 本地分支承担。
- `event_schema.py` provides static `EventSchemaRegistry` metadata for known canonical event types。
- `RunProjector` calls the registry before local payload / lifecycle validation。
- Unknown `event_type` fail-closed with controlled `ValueError` and does not advance projector state。
- Unsupported explicit payload `event_schema_version` fail-closed。
- Legacy/current known events without explicit `event_schema_version` are accepted only through registry compatibility mapping。
- Checkpoint integrity / event prefix digest 已绑定 event envelope representation。
- Registry / policy basis metadata 已进入 `action.proposed` / `action.decided` and projected action summaries。

尚未实现：

- JSON Schema / protobuf / Avro validation backend。
- Full schema migration framework。
- Remote / plugin schema registry。
- Multi-version projector matrix。
- Product event inspection API。

Implementation note: Track F stale test sync 已把 raw `provider.callback.received` 从 silently ignored 改为 fail-closed。该 event 不应注册成 canonical event；provider adapters / webhooks / HTTP ingestion remain deferred。

## 4. Hard Contracts

以下是当前 first slice 已锁住、后续仍必须保持的 kernel contract：

- Every canonical `event_type` should have a registered payload schema/version.
- Projector must fail closed on unknown `event_type`, unless an event type is explicitly registered as ignored/deferred with a documented reason.
- Projector must fail closed on unsupported `event_schema_version`.
- `event_envelope_version` and `event_schema_version` are separate metadata.
- Old event logs must remain replayable by projector versions that declare support for their event schema versions.
- Schema changes must be append/new-version, not silent mutation of old event meaning.
- Event replay must not depend on mutable current defaults, plugin loading, or network registry lookup.
- Checkpoint schema/version is separate from event schema/version.
- Checkpoints may accelerate rebuild, but cannot supply, override, or repair event schema metadata.
- Validation errors should be controlled and diagnosable, preferably `ValueError` at the current slice boundary.
- Event store append-only semantics remain unchanged.

## 5. Minimal Implementation Shape Candidate

Current minimal shape:

- Keep `events.py` as owner of event type constants and `EVENT_ENVELOPE_VERSION`.
- `event_schema.py` owns a narrow in-process static `EventSchemaRegistry`.
- Register each canonical event type with:
  - `event_type`
  - `event_schema_version`
  - required payload fields
  - validation owner
- Keep projector lifecycle validation local where stateful ordering is required.
- Registry handles stateless known-type and schema-version checks before projector lifecycle checks.
- Prefer explicit `event_schema_version` in event payload metadata for new events.

Why prefer explicit `event_schema_version`: replay should not depend on the current default registry. This mirrors registry/policy basis metadata already added to action proposals and policy decisions.

Legacy/current events that lack `event_schema_version` may be interpreted only through an explicit compatibility rule, for example:

- `(event_type, missing event_schema_version)` maps to `slice_v0` only for current known events.
- This compatibility rule must live in code/tests, not in caller assumptions.
- Unknown event type with missing schema version remains fail-closed.

## 6. Compatibility Rules

| Change | Rule |
| --- | --- |
| Add optional field | Allowed only if old projector can ignore it safely, or a new schema version is declared. |
| Add required field | Breaking unless a new schema version is declared and old events remain supported. |
| Change field meaning | Breaking; require new schema version or new event type. |
| Rename event type | Breaking; prefer new event type while keeping old event replay support. |
| Remove field | Breaking unless field was optional and absent behavior is already specified. |
| Tighten forbidden content fields | Allowed as fail-closed hardening if old valid events did not contain those fields. |
| Unknown future event | Fail closed in v0.2. Do not silently ignore. |
| Unsupported schema version | Fail closed in v0.2. Do not guess. |

## 7. Event / Checkpoint Interaction

- `event_envelope_version` remains part of the event representation and event prefix digest input.
- Future `event_schema_version` should be part of event payload metadata or otherwise deterministically resolved from event data.
- Checkpoint `projector_version`, checkpoint state schema, and event schema version are separate concepts.
- A checkpoint can record which event prefix it covers; it cannot rewrite event schema versions.
- If a checkpoint was produced before an event schema compatibility change, it must either validate under the declared checkpoint/projector rules or be ignored with full replay fallback.

## 8. Deferred

Do not implement these in the first slice:

- Full schema migration engine.
- Remote schema registry.
- JSON Schema dependency.
- Code generation.
- protobuf / Avro.
- Multi-version projector matrix.
- External plugin event types.
- Marketplace / remote event bundles.
- Public event-inspection product API.

## 9. First Slice Tests

Implemented files:

- `tests/isotope_kernel/test_event_schema_registry_boundary.py`
- `tests/isotope_kernel/test_event_schema_version_compatibility.py`

Coverage:

- `EventSchemaRegistry` or equivalent boundary exists and lists known canonical event types.
- Every known canonical event type has a schema id/version.
- Unknown event type fail-closed.
- Unsupported `event_schema_version` fail-closed.
- Missing `event_schema_version` for current legacy events is accepted only through explicit compatibility mapping.
- `event_envelope_version` and `event_schema_version` are distinct.
- Checkpoint schema/version cannot override event schema version.
- Additive optional field behavior is explicit.
- Required field addition / field meaning change / event rename require new schema version or new event type.
- Validation errors are controlled.
- No JSON Schema / protobuf / migration framework / plugin marketplace / remote registry / new dependency.

## 10. Closure Review

Closure review: `event-schema-registry-closure-review.md`。

Current closure decision:

- first slice complete / closed for now
- unknown event fail-closed
- unsupported `event_schema_version` fail-closed
- legacy/current missing schema compatibility only for known events
- no JSON Schema / protobuf / Avro / migration framework / plugin registry / remote registry

## 11. Relationship to Existing Docs

This document complements:

- `event-envelope-versioning-v0.1.md`
- `event-envelope-schema-registry-v0.1.md`
- `event-prefix-digest-v0.1.md`
- `checkpoint-schema-version-fields-v0.1.md`
- `policy-profile-action-registry-versioning-boundary-v0.2.md`

Those docs cover envelope/checkpoint/registry-basis boundaries. This doc covers event payload schema compatibility and links to the closed first-slice review.
