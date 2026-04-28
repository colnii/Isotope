# Event Envelope Versioning v0.1

状态：draft

本文定义 event envelope versioning（事件信封版本化）的 v0.1 边界：当前 slice-only `CanonicalEvent` envelope 未来如何版本化，以及 event prefix digest（事件前缀摘要）如何绑定到明确的 event representation（事件表示）。

本轮只做设计说明，不实现 event envelope version 字段、schema registry 或 migration。

## Purpose

event envelope versioning 的目的，是在不改变 canonical event log source of truth（唯一事实来源）的前提下，让未来 event serialization、event prefix digest、replay 和 projector validation 能够明确知道自己处理的是哪一种 event representation。

它不是 event migration 实现，不是 event log compaction，也不是绕过 malformed event validation 的机制。

## Current State

当前实现状态：

- 当前 `CanonicalEvent` 仍是 slice-only implementation shape，不是最终协议。
- 当前 envelope 大致包含 `event_id`、`run_id`、`event_type`、`payload`、`created_at`。
- 当前没有显式 event envelope version 字段。
- 当前 event prefix digest 已存在。
- 当前 event prefix digest 绑定的是当前 slice 的 canonical event representation。
- 当前可以把这个隐式表示在文档中称为 `canonical_event_slice@v0`，但这只是文档称呼，不是实现字段。
- 当前 full regression：`341 passed`。

## Decision

v0.1 design decision：

- append-only canonical event log 仍是唯一 source of truth。
- event envelope versioning 不能重写 canonical event log。
- event envelope versioning 不能让 malformed event 变合法。
- 一旦引入显式 event envelope version，event prefix digest 必须明确绑定到某个 event representation version。
- 老事件如果没有 version，只能按明确的 legacy slice representation 处理，不能隐式猜测。
- envelope version 不能只藏在 checkpoint 里；它影响 event serialization、digest、replay 和 projector validation。
- 本轮不实现 version 字段。
- 本轮不实现 event schema registry 或 payload schema registry。

## Hard Boundaries

- event envelope versioning 不能删除 canonical events。
- event envelope versioning 不能重写 canonical events。
- event envelope versioning 不能压缩或裁剪 canonical event log。
- version mismatch 不能让 malformed event 变合法。
- version mismatch 不能跳过 event validation。
- version mismatch 不能跳过 lifecycle validation。
- version mismatch 不能跳过 checkpoint integrity/hash validation。
- version mismatch 不能跳过 event prefix digest validation。
- version mismatch 不能跳过 prefix consistency validation。
- version mismatch 不能跳过 full event log replay fallback。
- legacy no-version events 必须有明确的 interpretation boundary；不能由 caller、server 或 checkpoint 随意选择解释方式。
- checkpoint 中的 version metadata 不能覆盖 event log 中的真实 event representation。
- `FileCheckpointStore` 仍保持 opaque，不解释 event envelope version 或 payload schema。
- `InProcessServer` 不能直接解释 event envelope version 来生成 state；仍必须通过 projector-owned boundary。

## v0 Candidate Shape

当前隐式 event representation 可在文档中称为：

- `canonical_event_slice@v0`

这个名字只用于设计讨论，不是当前实现字段。

未来显式字段可以考虑：

```json
{
  "event_id": "evt_001",
  "run_id": "run_001",
  "event_envelope_version": "canonical_event@v1",
  "event_type": "run.created",
  "payload": {},
  "created_at": "2026-04-28T00:00:00Z"
}
```

字段名和 version string 都只是 v0 candidate / schema sketch，不是永久协议。

未来 checkpoint integrity / event prefix digest metadata 可以考虑包含 event representation version，例如：

```json
{
  "integrity": {
    "event_digest_algorithm": "sha256",
    "event_prefix_digest": "...",
    "event_digest_basis_event_id": "evt_123",
    "event_digest_event_count": 42,
    "event_representation_version": "canonical_event@v1"
  }
}
```

这同样只是 schema sketch。event prefix digest 即使绑定 version，也不能替代 replay validation。

## Digest Binding

当前 event prefix digest 输入使用当前 slice 的 canonical event representation：

- `event_id`
- `run_id`
- `event_type`
- `payload`
- `created_at`

未来一旦引入 event envelope version，digest input 必须明确包含或绑定 event representation version。

最低要求：

- digest 必须保留 event append order。
- digest 必须说明自己使用的 event representation version。
- digest mismatch 只能让 checkpoint invalid，并 fallback full rebuild。
- digest match 不能证明业务状态正确。
- digest match 后仍必须执行 event validation、lifecycle validation、checkpoint state schema validation 和 prefix consistency validation。

## Open Questions

以下问题当前不定为 Hard Contract：

- version 是 per-event、per-run log，还是两者都有。
- legacy no-version events 如何处理。
- event envelope version 是否参与 event id。
- event envelope version 是否参与 content hash。
- event payload schema per `event_type` 如何版本化。
- event migration 是追加新事件、生成 derived view，还是只影响 checkpoint。
- event ordering / idempotency 如何和 version 交互。
- event prefix digest 跨 envelope version 是否可比较。
- 是否需要 event envelope schema registry。
- 是否需要 payload schema registry。

## Invalid Uses

以下用法明确无效：

- 用 envelope version 修复坏 event。
- 用 checkpoint 中的 version metadata 覆盖 event log 中的真实 event representation。
- 在没有明确 legacy rule 时猜测 no-version event 的含义。
- 用 event envelope migration 重写 canonical event log。
- 用 event envelope version 绕过 event validation 或 lifecycle validation。
- 用 event prefix digest 的 version metadata 替代 replay。
- 让 public client 上传 event envelope version override。

## Deferred

当前仍不实现：

- event envelope version field。
- event schema registry。
- payload schema registry。
- event migration。
- event log compaction。
- content-addressed event ids。
- checkpoint migrator。
- public checkpoint inspection API。
- public event inspection API。
- event prefix digest version migration。

## Future TDD Notes

后续如继续推进，应先写 red tests，优先覆盖：

- legacy no-version event 按 `canonical_event_slice@v0` 处理的边界。
- event prefix digest metadata 绑定 event representation version。
- version mismatch 不能隐藏 malformed / lifecycle-invalid event log。
- event envelope version 不得只由 checkpoint 决定。
- `FileCheckpointStore` 仍不解释 event envelope version。

不要直接实现 event migration、schema registry、content-addressed event ids 或 event log compaction。
