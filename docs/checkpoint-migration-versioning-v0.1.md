# Checkpoint Migration / Versioning v0.1

状态：draft

本文定义 checkpoint migration / version negotiation（检查点迁移 / 版本协商）的 v0.1 边界：当 checkpoint schema、projector version 或 event envelope version 变化时，系统如何处理旧 checkpoint，并防止 migration 被误用成第二事实源。

本设计只收口边界，不实现 migrator、registry 或 version negotiation 机制。

## Purpose

checkpoint migration / versioning 的目的，是在 checkpoint shape 或 projector 行为变化时，明确哪些 checkpoint 可以继续作为 replay basis，哪些 checkpoint 必须失效并回到 canonical event log full rebuild。

它不是 state 修复机制，不生成新事实，也不能改变 canonical event log 的权威地位。

## Current State

当前实现状态：

- checkpoint 当前包含 `projector_version`。
- `RunProjector.PROJECTOR_VERSION` 当前是 `run_projector@v1`。
- `RunProjector.rebuild_with_checkpoint(...)` 遇到 projector version 不兼容时，会丢弃 checkpoint 并 fallback full rebuild。
- checkpoint schema 仍是 v0 candidate，不是永久协议。
- checkpoint schema version fields design note 已落文档，边界见 `docs/checkpoint-schema-version-fields-v0.1.md`。
- event envelope 仍是 slice-only shape，不是最终协议。
- event envelope versioning design note 已落文档，最小 event envelope version boundary 已实现；边界见 `docs/event-envelope-versioning-v0.1.md`。
- `CanonicalEvent` 当前有 `event_envelope_version`，默认值是 `canonical_event_slice@v0`。
- checkpoint integrity metadata 已记录 event prefix digest 绑定的 event envelope version。
- checkpoint integrity/hash validation 已实现。
- event prefix digest validation 已实现。
- checkpoint state schema validation 和 prefix consistency validation 已实现。
- checkpoint projector version boundary hardening 已实现。
- 当前实现仍以 `projector_version` 作为 checkpoint compatibility 的唯一已实现版本边界。
- `checkpoint_schema_version` / `state_schema_version` / `integrity_schema_version` 目前还没有实现字段。
- 当前 full regression：`352 passed`。

当前没有实现：

- checkpoint migrator。
- version negotiation。
- schema registry。
- migrator registry。
- checkpoint schema version 字段。
- state schema version 字段。
- integrity schema version 字段。
- event envelope schema registry。

## Implementation Status

当前已实现的 projector version boundary：

- malformed `projector_version` 不会被使用。
- non-string / empty `projector_version` 会让 checkpoint invalid，并 fallback full rebuild。
- incompatible `projector_version` fallback 不读取 checkpoint state。
- malformed / incompatible version fallback 不能隐藏 lifecycle-invalid event log。
- `projector_version` override 参数仍控制兼容性，但 malformed version 不能因为 caller 传同样 malformed 值而被接受。
- future sketch fields 如 `checkpoint_schema_version` / `state_schema_version` 不能 override `projector_version`；已实现的 event envelope version boundary 也不能 override `projector_version`。
- checkpoint schema version fields 如果未来实现，也不能让 malformed checkpoint 合法，不能让 checkpoint state 被直接读取。
- compatible checkpoint 带 future sketch fields 时，仍按当前 validation chain 处理。
- `FileCheckpointStore` 仍保持 opaque，不解释 version 字段。

## Decision

v0.1 design decision：

- 不兼容 checkpoint 不能被强行使用。
- 当前没有 migrator 时，`projector_version` mismatch 只能让 checkpoint 失效，并 fallback full rebuild。
- malformed `projector_version` 与 mismatch 一样，只能让 checkpoint 失效，并 fallback full rebuild。
- migration / version negotiation 不能修改 canonical event log。
- migration 不能伪造 projected state。
- migrator 如果未来存在，也只能从 canonical events 和旧 derived checkpoint 生成新的 derived checkpoint。
- migrator 输出应是新的 checkpoint blob，不应原地修改旧 checkpoint，除非后续另有明确设计。
- event replay 仍是最终恢复路径。
- checkpoint hash、event prefix digest、state schema validation、prefix consistency validation 和 lifecycle validation 不能被 migration 跳过。
- checkpoint schema 和 projector version 的字段名仍是 v0 candidate / schema sketch，不是永久协议。
- checkpoint schema version fields 的详细边界见 `docs/checkpoint-schema-version-fields-v0.1.md`。
- 当前 `event_envelope_version` 是 v0 slice implementation shape，不是最终 protocol；它不能只藏在 checkpoint 里，必须影响 event serialization、digest、replay 和 projector validation 的明确边界。

## Hard Boundaries

- version mismatch 不能被忽略。
- version mismatch 不能通过 server、storage 或 caller 直接覆盖。
- checkpoint schema version mismatch 不能覆盖或绕过 `projector_version`。
- 不兼容 checkpoint 不能作为 `RunState` source。
- migration / version negotiation 不能删除、重写、压缩或裁剪 canonical events。
- migration / version negotiation 不能把 checkpoint 写回 event log。
- migration / version negotiation 不能跳过 canonical event replay validation。
- migration / version negotiation 不能跳过 action lifecycle validation。
- migration / version negotiation 不能跳过 checkpoint state schema validation。
- migration / version negotiation 不能跳过 prefix projection consistency validation。
- migration / version negotiation 不能跳过 checkpoint integrity/hash validation。
- migration / version negotiation 不能跳过 event prefix digest validation。
- event envelope version mismatch 不能让 malformed event 变合法。
- checkpoint 中的 event envelope version metadata 不能覆盖 event log 的真实 representation。
- migration 失败时必须 fallback full rebuild 或 fail fast；不能返回半迁移 state。
- public client 不能提交 checkpoint state、migration adapter 或 version override。
- `FileCheckpointStore` 仍保持 opaque，不解释 schema version 或业务 state。

## v0 Candidate Shape

当前先不实现 migrator。

当前 v0 candidate 行为：

- `projector_version` 不匹配继续 fallback full rebuild。
- non-string / empty `projector_version` 继续 fallback full rebuild。
- 无兼容 migrator 时，不尝试使用旧 checkpoint。
- 不兼容 checkpoint 的存在不影响 canonical event log rebuild。
- future schema sketch fields 不能覆盖 `projector_version` 兼容性判断；event envelope version mismatch 只能让 checkpoint invalid 并 fallback full rebuild。
- `checkpoint_schema_version` / `state_schema_version` / `integrity_schema_version` 目前只是 sketch，不是当前实现契约。

未来可以考虑在 checkpoint 中增加：

- `checkpoint_schema_version`
- `state_schema_version`
- `integrity_schema_version`
- `event_envelope_schema_version`
- `migration_from`
- `migration_adapter`

Schema sketch：

```json
{
  "run_id": "run_001",
  "projector_version": "run_projector@v2",
  "checkpoint_schema_version": "checkpoint@v1",
  "state_schema_version": "run_state@v1",
  "event_envelope_schema_version": "event_envelope@v1",
  "integrity": {
    "integrity_schema_version": "checkpoint_integrity@v1"
  },
  "migration_from": {
    "projector_version": "run_projector@v1"
  }
}
```

这些字段名只是 v0 candidate / schema sketch，不是当前实现协议。

`event_envelope_version` 的更完整边界见 `docs/event-envelope-versioning-v0.1.md`。当前 event representation version 是 `canonical_event_slice@v0`，但这仍只是当前 slice implementation shape，不是最终 protocol。

## Version Negotiation Flow

当前无 migrator 时的流程：

1. 读取 checkpoint blob。
2. 校验 checkpoint 文件和基础字段。
3. 比较 checkpoint `projector_version` 与当前 projector version。
4. 如果不兼容，丢弃 checkpoint，fallback full event-log rebuild。
5. 如果兼容，继续执行 checkpoint integrity/hash validation。
6. 继续执行 event prefix digest validation。
7. 继续执行 checkpoint state schema validation。
8. 继续执行 prefix projection consistency validation。
9. replay suffix canonical events。

未来如果引入 migrator，也必须保持：

- migrator 输入不能替代 canonical event log。
- migrator 输出必须重新走 checkpoint integrity/hash、event prefix digest、state schema 和 prefix consistency validation。
- migrator 不能改变 event log。
- migrator 不能让 server 或 storage 直接解释 checkpoint state。

## Open Questions

以下问题当前不定为 Hard Contract：

- checkpoint schema version 是否独立于 projector version。
- future event envelope schema version 变化后，event prefix digest 如何迁移或比较；当前边界见 `docs/event-envelope-versioning-v0.1.md`。
- event migration 后 digest 如何处理。
- migration 是否保留 old checkpoint。
- migration 失败是否 fallback full rebuild。
- migration 是否需要 audit event。
- 是否需要 checkpoint migrator registry。
- 是否允许跨 projector major version 使用 checkpoint。
- schema version 字段是否应进入 checkpoint hash 输入。
- event envelope version 是否需要长期保留在每个 `CanonicalEvent` 上，还是未来升级为 per-run/per-log version。

## Invalid Uses

以下用法明确无效：

- 把 version mismatch 当成 warning，然后继续使用 checkpoint。
- 用 migration 修复坏 event log。
- 用 migration 绕过 malformed event log fail-fast。
- 用 migration 绕过 lifecycle validation。
- 用 migration 绕过 checkpoint integrity/hash 或 event prefix digest。
- 在 storage 层根据 version 字段决定业务状态。
- 让 public client 指定目标 version 或上传 migrated checkpoint state。
- 把 checkpoint migration 当成 event log migration。
- 把旧 checkpoint 覆盖成新 checkpoint，而没有保留 provenance 或明确迁移边界。

## Deferred

当前仍不实现：

- checkpoint migrator implementation。
- version negotiation implementation。
- checkpoint schema registry。
- state schema registry。
- integrity schema registry。
- event envelope schema registry。
- event schema registry。
- payload schema registry。
- migrator registry。
- audit event for checkpoint migration。
- public checkpoint inspection API。
- event log migration。
- event log compaction。
- `CheckpointService`。

## Future TDD Notes

下一轮如继续推进，应先写 red tests，优先覆盖：

- checkpoint schema version fields boundary red tests。
- event envelope schema registry design note。
- malformed future `checkpoint_schema_version` / `event_envelope_schema_version` 字段的边界。
- 不兼容 version fallback full rebuild 继续执行完整 event validation。
- `FileCheckpointStore` 仍不解释 version 字段。

不要直接实现 migrator、registry、event log migration 或 public checkpoint inspection API。
