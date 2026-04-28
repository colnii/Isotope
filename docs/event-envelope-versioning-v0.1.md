# Event Envelope Versioning v0.1

状态：draft

本文定义 event envelope versioning（事件信封版本化）的 v0.1 边界：当前 slice-only `CanonicalEvent` envelope 未来如何版本化，以及 event prefix digest（事件前缀摘要）如何绑定到明确的 event representation（事件表示）。

当前已实现最小 event envelope version boundary：`CanonicalEvent` 带有当前 slice representation 的 `event_envelope_version`，checkpoint event prefix digest 也记录它绑定的 event representation version。本文件仍不是最终 protocol spec，schema registry 和 migration 仍 deferred。

## Purpose

event envelope versioning 的目的，是在不改变 canonical event log source of truth（唯一事实来源）的前提下，让未来 event serialization、event prefix digest、replay 和 projector validation 能够明确知道自己处理的是哪一种 event representation。

它不是 event migration 实现，不是 event log compaction，也不是绕过 malformed event validation 的机制。

## Current State

当前实现状态：

- 当前 `CanonicalEvent` 仍是 slice-only implementation shape，不是最终协议。
- 当前 envelope 包含 `event_id`、`run_id`、`event_type`、`payload`、`created_at`、`event_envelope_version`。
- 当前 `event_envelope_version` 默认值是 `canonical_event_slice@v0`，用于标记当前 slice event representation boundary。
- legacy event JSON 缺少 `event_envelope_version` 时，按当前 slice legacy representation 读取并填入 `canonical_event_slice@v0`。
- empty / non-string / unknown event envelope version 会被拒绝，抛受控 `ValueError`。
- 当前 event prefix digest 已存在。
- 当前 event prefix digest input 包含 `event_envelope_version`。
- checkpoint integrity metadata 已记录 digest 绑定的 event envelope version：`event_digest_event_envelope_version`。
- checkpoint event envelope version mismatch 会让 checkpoint invalid，并 fallback full rebuild，且不会读取 checkpoint state。
- legacy checkpoint 缺少 event envelope version metadata 时，仍按兼容路径处理。
- 当前 full regression：`352 passed`。

## Decision

v0.1 design decision：

- append-only canonical event log 仍是唯一 source of truth。
- event envelope versioning 不能重写 canonical event log。
- event envelope versioning 不能让 malformed event 变合法。
- event prefix digest 必须明确绑定到当前 event representation version。
- 老事件如果没有 version，只能按当前明确的 legacy slice representation 处理，不能由 caller 隐式猜测。
- envelope version 不能只藏在 checkpoint 里；它必须出现在 event representation boundary 中，并影响 event serialization、digest、replay 和 projector validation。
- 当前 `event_envelope_version` 是 v0 slice implementation shape，不是最终协议。
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

当前 slice event representation 是：

- `canonical_event_slice@v0`

这个 version string 已作为当前 slice 的 `EVENT_ENVELOPE_VERSION` 使用，但它仍不是最终 protocol。

当前最小 envelope shape：

```json
{
  "event_id": "evt_001",
  "run_id": "run_001",
  "event_type": "run.created",
  "payload": {},
  "created_at": "2026-04-28T00:00:00Z",
  "event_envelope_version": "canonical_event_slice@v0"
}
```

字段名和 version string 是当前 v0 slice implementation shape，不是永久协议。

当前 checkpoint integrity / event prefix digest metadata 包含 event representation version：

```json
{
  "integrity": {
    "event_digest_algorithm": "sha256",
    "event_prefix_digest": "...",
    "event_digest_basis_event_id": "evt_123",
    "event_digest_event_count": 42,
    "event_digest_event_envelope_version": "canonical_event_slice@v0"
  }
}
```

这仍是当前 v0 slice implementation shape。event prefix digest 即使绑定 version，也不能替代 replay validation。

## Digest Binding

当前 event prefix digest 输入使用当前 slice 的 canonical event representation：

- `event_id`
- `run_id`
- `event_type`
- `payload`
- `created_at`
- `event_envelope_version`

digest input 必须明确包含 event representation version。

最低要求：

- digest 必须保留 event append order。
- digest 必须说明自己使用的 event representation version。
- digest mismatch 只能让 checkpoint invalid，并 fallback full rebuild。
- digest match 不能证明业务状态正确。
- digest match 后仍必须执行 event validation、lifecycle validation、checkpoint state schema validation 和 prefix consistency validation。

## Open Questions

以下问题当前不定为 Hard Contract：

- version 是 per-event、per-run log，还是两者都有。
- legacy no-version events 长期是否继续支持，以及支持多久。
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

- event envelope schema registry 是否需要，以及如何和当前 `canonical_event_slice@v0` 兼容。
- event payload schema per `event_type` 如何版本化。
- version mismatch 不能隐藏 malformed / lifecycle-invalid event log。
- event envelope version 不得只由 checkpoint 决定。
- `FileCheckpointStore` 仍不解释 event envelope version。

不要直接实现 event migration、schema registry、content-addressed event ids 或 event log compaction。
