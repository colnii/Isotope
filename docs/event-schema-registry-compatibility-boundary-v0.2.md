# Event Schema Registry / Compatibility Boundary v0.2

状态：boundary defined; red tests next

本文定义 canonical event schema registry（规范事件模式注册表）和 compatibility（兼容性）的最小 kernel contract。它是 docs-only boundary，不实现 registry、migration framework、JSON Schema dependency、protobuf、code generation 或 plugin event system。

## 1. Purpose

当前 Isotope 已有 canonical event envelope、严格的 known-event payload validation、checkpoint integrity、event prefix digest、registry / policy basis metadata，以及 replay / checkpoint-assisted rebuild。

事件类型继续增加后，kernel 需要固定以下问题：

- `event_type` 到 payload schema 的登记在哪里。
- `event_schema_version` 如何表示。
- 新 projector 遇到 unknown event 或 unsupported schema version 时如何处理。
- schema change 是 additive 还是 breaking。
- checkpoint schema version 和 event schema version 如何区分。

本文件只定义边界；下一步应先写 red tests 固定行为。

## 2. Definitions

| Term | Definition |
| --- | --- |
| `event_type` | Canonical event 的业务类型，例如 `action.proposed`、`workspace.released`、`snapshot.imported`。 |
| `event_envelope_version` | Event envelope representation version，当前由 `CanonicalEvent.event_envelope_version` 表示，已实现值为 `canonical_event_slice@v0`。它描述事件信封字段和序列化边界，不描述 payload 业务 schema。 |
| `event_schema_version` | 某个 `event_type` payload schema 的版本。当前尚未实现；未来应作为 payload metadata 或 registry-resolved metadata 出现。 |
| `EventSchemaRegistry` | 未来的 in-process static registry candidate，用于登记 `(event_type, event_schema_version)` 到 required fields、allowed fields、compatibility rules 和 validation owner。 |
| Compatibility policy | 对 old/new events、unknown versions、additive changes、breaking changes 的处理规则。 |
| Additive change | 不改变既有字段含义、不新增必填字段、旧 projector 可忽略或新 schema version 明确登记的 optional 扩展。 |
| Breaking change | 新增 required field、字段语义变化、字段删除、event rename、payload shape 不兼容，或旧 projector 无法确定解释的任何变更。 |
| Unsupported event | 当前 projector / registry 不支持的 `event_type` 或 `event_schema_version`。v0.2 目标 contract 是 fail closed。 |

## 3. Current State

已实现：

- `events.py` owns `EVENT_ENVELOPE_VERSION = "canonical_event_slice@v0"` and `CanonicalEvent` envelope validation。
- Unknown `event_envelope_version` fail-fast。
- Known event payload validation 主要由 `RunProjector._validate_event_payload(...)` 本地分支承担。
- Checkpoint integrity / event prefix digest 已绑定 event envelope representation。
- Registry / policy basis metadata 已进入 `action.proposed` / `action.decided` and projected action summaries。

尚未实现：

- 独立 `EventSchemaRegistry`。
- Per-event `event_schema_version`。
- `event_type` -> payload schema 的集中登记。
- Payload schema compatibility framework。
- Unknown event type fail-closed 的显式测试契约。

Implementation note: current projector validation 对 known events 很严格，但 unknown `event_type` handling 尚未作为独立 contract 固定；不能把它描述成已经完成的能力。下一批 red tests 应先锁住 unknown event fail-closed。

## 4. Hard Contracts

以下是下一实现 slice 必须满足的 kernel contract：

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

Recommended minimal shape if/when implementation starts:

- Keep `events.py` as owner of event type constants and `EVENT_ENVELOPE_VERSION`.
- Add a narrow `event_schema.py` or equivalent in-process static `EventSchemaRegistry`.
- Register each canonical event type with:
  - `event_type`
  - `event_schema_version`
  - required payload fields
  - forbidden payload fields where relevant
  - compatibility status
  - validation owner
- Keep projector lifecycle validation local where stateful ordering is required.
- Let registry handle stateless schema presence/version checks before projector lifecycle checks.
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

## 9. First Red Tests Recommendation

Suggested files:

- `tests/isotope_kernel/test_event_schema_registry_boundary.py`
- `tests/isotope_kernel/test_event_schema_version_compatibility.py`

Suggested coverage:

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

## 10. Relationship to Existing Docs

This document complements:

- `docs/event-envelope-versioning-v0.1.md`
- `docs/event-envelope-schema-registry-v0.1.md`
- `docs/event-prefix-digest-v0.1.md`
- `docs/checkpoint-schema-version-fields-v0.1.md`
- `docs/policy-profile-action-registry-versioning-boundary-v0.2.md`

Those docs cover envelope/checkpoint/registry-basis boundaries. This doc covers event payload schema compatibility and the next red-test target.
