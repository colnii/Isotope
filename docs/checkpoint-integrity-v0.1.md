# Checkpoint Integrity v0.1

状态：draft

本文定义 checkpoint integrity/hash（检查点完整性校验 / 哈希）的 v0.1 边界。当前已实现最小 hash generation / validation，但它仍只是 checkpoint 可用性边界，不是事实来源。

## Purpose

Checkpoint integrity/hash 的目的，是验证 checkpoint blob 自身是否自洽、是否被意外篡改或损坏。

它不是新的事实来源，不用于证明 projected state 一定正确，也不能替代 canonical event log replay。

## Decision

v0.1 design decision：

- integrity/hash 不是 source of truth。
- integrity/hash 不能让 checkpoint 覆盖 canonical event log。
- integrity/hash 不能跳过 event validation、lifecycle validation、prefix consistency validation。
- hash mismatch 只能让 checkpoint 失效；恢复仍应回到 event log full rebuild。
- malformed checkpoint file 仍然 fail fast。
- v0.1 推荐使用 `sha256`。
- hash 字段可以由 `FileCheckpointStore` 保存，但 storage 不解释业务状态。
- 是否使用 checkpoint 仍由 `RunProjector` / checkpoint-assisted rebuild 决定。
- 当前实现只覆盖最小 `sha256` checkpoint hash，不包含 signature / MAC / key management，也不包含 event prefix digest。

当前实现状态：

- `RunProjector.create_checkpoint(...)` 会生成 `integrity`。
- `integrity` 包含 `algorithm: sha256` 和 `checkpoint_hash`。
- hash 输入使用 deterministic canonical JSON。
- hash 输入排除 `integrity` / `checkpoint_hash` 本身。
- 相同 checkpoint 内容 hash 稳定。
- checkpoint state 被改动会导致 integrity validation 失败。
- `rebuild_with_checkpoint(...)` 遇到 hash mismatch 不采用 checkpoint，回退 full rebuild。
- legacy checkpoint 无 hash 时仍走已有 validation path。
- hash match 后仍要走 state schema validation 和 prefix consistency validation。
- malformed checkpoint file 仍 fail-fast。
- `FileCheckpointStore` 仍是 opaque storage，只保存 hash 字段，不解释业务 state。
- hash mismatch 不能掩盖 lifecycle-invalid event log。

## Hard Boundaries

- hash 不能修正 checkpoint。
- hash 不能修正 event log。
- hash 不能把 checkpoint 提升为事实源。
- hash 不能让 projector 跳过 canonical event replay validation。
- hash 不能让 projector 跳过 checkpoint state schema validation。
- hash 不能让 projector 跳过 checkpoint prefix consistency validation。
- hash mismatch 不能产生新的 state，只能触发 checkpoint invalidation / full rebuild。
- 没有 hash 的 legacy checkpoint 不应被立即判为 malformed；v0 compatibility 可以允许它继续走现有 validation。
- 一旦 checkpoint 中存在 hash 字段，就必须校验。

## Hash Input

v0.1 推荐 hash 输入使用 canonical JSON：

- UTF-8 编码。
- sorted keys。
- deterministic separators。
- 排除 `integrity` / `checkpoint_hash` 自身字段。

hash 至少绑定以下 checkpoint 内容：

- `run_id`
- `projector_version`
- `basis_event_id`
- `state`
- `created_at`

如果后续加入 event prefix digest，应作为额外字段参与校验，但不能取代 replay validation。

## Validation Behavior

checkpoint-assisted rebuild 的 v0.1 行为应保持：

1. 读取 checkpoint。
2. 如果 checkpoint 没有 hash 字段，作为 legacy checkpoint 继续走现有 validation。
3. 如果 checkpoint 有 hash 字段，先用 canonical JSON 重新计算 hash。
4. 如果 hash mismatch，checkpoint 失效，fallback 到 event log full rebuild。
5. 如果 hash match，仍继续执行现有 validation：
   - event validation
   - lifecycle validation
   - checkpoint state schema validation
   - prefix consistency validation
6. 只有所有 validation 都通过，checkpoint 才能作为 replay basis。

hash mismatch 与 checkpoint version 不兼容类似：只能让 checkpoint 不被使用，不能阻止 event log full rebuild。

## Invalid Uses

以下用法明确无效：

- 用 hash 证明 checkpoint 比 event log 更可信。
- 用 hash 跳过 malformed event log fail-fast。
- 用 hash 跳过 lifecycle validation。
- 用 hash 跳过 prefix consistency validation。
- 用 hash 修复 checkpoint state。
- 用 hash 修复 event log。
- 把 hash 作为 external API 的长期协议承诺。
- 让 `FileCheckpointStore` 根据 hash 决定业务状态。

## Deferred

当前仍不实现：

- event prefix digest。
- signature / MAC。
- key management。
- migration / version negotiation。
- server API / HTTP exposure。
- automatic checkpoint scheduling。

## Future TDD Notes

已覆盖的最小测试：

- 无 hash 的 legacy checkpoint 继续走现有 validation。
- 有 hash 且 hash match 的 checkpoint 仍必须走 state schema / prefix consistency validation。
- hash mismatch fallback full rebuild。
- malformed checkpoint file 仍 fail fast。
- hash 输入排除 `integrity` / `checkpoint_hash` 自身字段。
- hash 输入使用 deterministic JSON。
- `FileCheckpointStore` 只保存 hash 字段，不解释业务状态。
- hash mismatch 不能隐藏 lifecycle-invalid event log。

后续实现必须先写 red tests，优先覆盖：

- event prefix digest 如加入，不能替代 replay validation。
- server-facing checkpoint boundary 如需暴露 checkpoint，只能调用 projector boundary，不能直接信任或解释 checkpoint。
