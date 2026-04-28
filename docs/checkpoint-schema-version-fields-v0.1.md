# Checkpoint Schema Version Fields v0.1

状态：draft

本文定义 checkpoint schema version fields（检查点 schema 版本字段）的 v0.1 边界：未来如果给 checkpoint blob、projected state snapshot 或 integrity metadata 增加独立 schema version，系统应如何处理，而不把 checkpoint schema 误当成稳定 protocol 或第二事实源。

本轮只做设计说明，不实现任何 schema version 字段、registry 或 migrator。

## Purpose

Checkpoint schema version fields 的目的，是在 checkpoint shape 演进时，让 projector 能明确判断 checkpoint 是否仍可作为 replay basis。

这些字段只影响 checkpoint availability validation（可用性校验）。它们不能产生 `RunState`，不能修复 checkpoint，也不能替代 canonical event log replay。

## Current State

当前实现状态：

- 当前 checkpoint 已有 `projector_version`。
- 当前实现仍以 `projector_version` 作为 checkpoint compatibility 的唯一已实现版本边界。
- `RunProjector.PROJECTOR_VERSION` 当前是 `run_projector@v1`。
- checkpoint projector version boundary 已实现：malformed / incompatible `projector_version` 会让 checkpoint invalid，并 fallback full rebuild。
- 当前 event envelope version boundary 已实现，`CanonicalEvent.event_envelope_version` 默认是 `canonical_event_slice@v0`。
- 当前 checkpoint schema 仍是 v0 candidate，不是最终 protocol。
- `checkpoint_schema_version` / `state_schema_version` / `integrity_schema_version` 目前还没有实现字段。
- `FileCheckpointStore` 仍是 opaque storage，只保存/读取 checkpoint blob，不解释 checkpoint 内容。
- 当前 full regression：`352 passed`。

## Decision

v0.1 design decision：

- `projector_version` 仍是当前唯一已实现 checkpoint compatibility version boundary。
- checkpoint schema version fields 如果未来出现，也不能覆盖或绕过 `projector_version`。
- checkpoint schema version fields 不能让 checkpoint state 被直接信任。
- checkpoint schema version fields 不能把 checkpoint 变成 source of truth。
- schema version mismatch 只能让 checkpoint invalid 并 fallback full rebuild，除非未来有明确 migrator。
- migrator 如果未来存在，也只能生成新的 derived checkpoint blob，不能修改 canonical event log。
- 当前不实现 checkpoint schema version fields，不实现 schema registry，不实现 migrator registry。

## Hard Boundaries

- checkpoint schema version 不能覆盖或绕过 `projector_version`。
- checkpoint schema version mismatch 不能让 checkpoint state 被读取。
- checkpoint schema version 不能让 malformed checkpoint 合法。
- checkpoint schema version 不能修改 canonical event log。
- checkpoint schema version 不能修复 canonical event log。
- checkpoint schema version 不能把 checkpoint 变成第二事实源。
- checkpoint schema version 不能跳过 checkpoint integrity/hash validation。
- checkpoint schema version 不能跳过 event prefix digest validation。
- checkpoint schema version 不能跳过 checkpoint state schema validation。
- checkpoint schema version 不能跳过 prefix consistency validation。
- checkpoint schema version 不能跳过 lifecycle validation。
- server 不能直接解释 checkpoint schema version 来生成 state，仍必须走 projector-owned boundary。
- `FileCheckpointStore` 不能根据 schema version 判断业务状态，仍保持 opaque。

## v0 Candidate / Sketch

未来可以考虑增加这些字段：

- `checkpoint_schema_version`
- `state_schema_version`
- `integrity_schema_version`

Schema sketch：

```json
{
  "run_id": "run_001",
  "projector_version": "run_projector@v1",
  "checkpoint_schema_version": "checkpoint@v1",
  "state_schema_version": "run_state@v1",
  "integrity": {
    "integrity_schema_version": "checkpoint_integrity@v1",
    "algorithm": "sha256",
    "checkpoint_hash": "..."
  }
}
```

这些字段名只是 sketch，不是当前实现契约。

未来如果实现，版本检查顺序应至少保持：

1. 校验 checkpoint 文件基础 shape。
2. 校验 `projector_version` compatibility。
3. 如果 `projector_version` compatible，再检查 checkpoint / state / integrity schema compatibility。
4. 如果 schema mismatch 且没有明确 migrator，checkpoint invalid 并 fallback full rebuild。
5. 如果 schema compatible，继续执行 checkpoint integrity/hash validation。
6. 继续执行 event prefix digest validation。
7. 继续执行 checkpoint state schema validation。
8. 继续执行 prefix consistency validation。
9. replay suffix canonical events。

legacy checkpoint 缺少这些 schema version fields 时，必须有明确兼容策略或 fallback 策略，不能由 caller、server 或 storage 隐式猜测。

## Open Questions

以下问题当前不定为 Hard Contract：

- checkpoint schema version 是否独立于 projector version。
- state schema version 是否应该绑定到 `RunState` projector version。
- integrity metadata 是否需要单独 version。
- schema mismatch 是 fallback full rebuild，还是通过 migrator 转换。
- migrator 是否必须产生 audit event。
- checkpoint schema version 是否应该进入 checkpoint hash input。
- integrity schema version 是否应该进入 checkpoint hash input，或者只作为 integrity metadata。
- public inspection API 是否能暴露这些字段。
- legacy checkpoint 缺少 schema version fields 时应兼容多久。
- schema version fields 是否需要和 event envelope version / event prefix digest metadata 联动。

## Invalid Uses

以下用法明确无效：

- 用 checkpoint schema version 覆盖 `projector_version`。
- 用 checkpoint schema version 修复 malformed checkpoint。
- 用 checkpoint schema version 跳过 event log replay。
- 用 checkpoint schema version 跳过 checkpoint state schema validation。
- 用 checkpoint schema version 跳过 prefix consistency validation。
- 让 `FileCheckpointStore` 解释 checkpoint schema version 并返回业务状态。
- 让 server 根据 checkpoint schema version 直接组装 `RunState`。
- 让 public client 上传 checkpoint schema version override。
- 把 checkpoint schema version fields 当成当前稳定 public protocol。

## Deferred

当前仍不实现：

- `checkpoint_schema_version` 字段。
- `state_schema_version` 字段。
- `integrity_schema_version` 字段。
- checkpoint schema registry。
- state schema registry。
- integrity schema registry。
- migrator registry。
- checkpoint migration implementation。
- version negotiation implementation。
- audit event for checkpoint migration。
- public checkpoint inspection API。
- public checkpoint API / HTTP endpoint。

## Future TDD Notes

后续如继续推进，应先写 red tests，优先覆盖：

- legacy checkpoint 缺少 schema version fields 的兼容或 fallback 行为。
- malformed `checkpoint_schema_version` / `state_schema_version` / `integrity_schema_version` 不能被使用。
- schema mismatch 不读取 checkpoint state，并 fallback full rebuild。
- schema mismatch fallback 不能隐藏 lifecycle-invalid event log。
- schema version fields 不能 override `projector_version`。
- `FileCheckpointStore` 仍不解释 schema version fields。

不要直接实现 schema registry、migrator registry、checkpoint migration、public checkpoint inspection API 或 event log migration。
