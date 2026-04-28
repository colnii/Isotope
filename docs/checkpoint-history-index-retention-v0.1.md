# Checkpoint History Index / Retention Policy v0.1

状态：draft

本文定义 checkpoint history index（检查点历史索引）和 retention policy（保留策略）的 v0.1 边界。当前只落设计说明，不实现 history index、retention policy、GC 或 `CheckpointService`。

## Purpose

checkpoint history index 的目的，是在 future checkpoint history 存在时，为 run-scoped checkpoint candidates 提供可验证、可排序、可维护的候选元数据。

retention policy 的目的，是在不影响 canonical event log 的前提下，控制 checkpoint blobs 和 future index metadata 的存储增长。

二者都不是事实来源，不证明 checkpoint 有效，也不能改变 `RunState` 语义。

## Current State

当前实现状态：

- `FileCheckpointStore.load_checkpoint_candidates(run_id)` 已实现。
- checkpoint candidates 可按 checkpoint `created_at` newest-to-oldest 读取。
- candidate loading 仍保持 storage opaque，不解释 projector version、checkpoint integrity、event prefix digest、event envelope version 或 projected state 语义。
- 最小 projector-owned old-checkpoint fallback path 已实现于 `RunProjector.rebuild_with_checkpoint(...)`。
- invalid latest checkpoint 后可尝试 older fully valid candidate。
- 每个 candidate 仍必须通过 projector-owned validation chain 后才能作为 replay basis。
- `save_checkpoint(...)` 仍只写 `runs/{run_id}/checkpoints/latest.json`。
- `save_checkpoint(...)` 不创建 checkpoint history 文件。
- `FileCheckpointStore.save_checkpoint_history(run_id, checkpoint)` 已实现为 explicit history candidate save method。
- `save_checkpoint_history(...)` 可写入非 `latest.json` history candidate。
- history save 不覆盖 latest，不修改 event log。
- `FileCheckpointStore` 仍保持 opaque，不解释 checkpoint state / integrity / projector version。
- checkpoint history save boundary design note 已落文档，见 `docs/checkpoint-history-save-boundary-v0.1.md`。
- checkpoint history save integration boundary design note 已落文档，见 `docs/checkpoint-history-save-integration-v0.1.md`。
- `RunProjector.save_checkpoint_history(...)` 已实现为显式 projector-owned history save method。
- `InProcessServer.save_checkpoint_history_for_run(...)` 已实现为 internal-only explicit history save trigger。
- latest/default save path 仍不自动写 history。
- 当前没有 persisted history index。
- 当前没有 retention policy。
- 当前没有 checkpoint GC。
- 当前没有 `CheckpointService`。
- 当前 full regression：`391 passed`。

## Decision

v0.1 design decision：

- history index 不是 source of truth。
- history index 不能证明 checkpoint 有效。
- checkpoint 是否可用仍只能由 projector-owned validation chain 判断。
- retention policy 不能删除、重写、压缩或裁剪 canonical event log。
- retention / GC 只能作用于 checkpoint blobs 或 future index metadata。
- corrupt / missing history index 不能让系统跳过 full event-log replay。
- server 不能直接解释 history index 或 checkpoint state 来生成 `RunState`。
- old-checkpoint fallback 不能隐藏 malformed / lifecycle-invalid event log。
- 本轮不实现 history index、retention policy、GC 或 `CheckpointService`。

## Hard Boundaries

- history index 不能取代 canonical event log。
- history index 不能让 checkpoint 成为第二事实源。
- history index 不能让 malformed checkpoint 合法。
- history index 不能让 projector 跳过 checkpoint validation chain。
- history index 不能让 server / checkpoint store 直接生成 projected state。
- retention policy 不能删除 canonical events。
- retention policy 不能重写 canonical events。
- retention policy 不能压缩 canonical events。
- retention policy 不能裁剪 canonical events。
- retention / GC 不能修复坏 event log。
- retention / GC 不能隐藏 malformed event log。
- retention / GC 不能隐藏 lifecycle-invalid event log。
- retention / GC 不能删除唯一可用于 event replay 的 source-of-truth data。
- corrupt history index 必须导致 fail fast、fallback directory scan 或 full event-log replay；不能隐式猜测。
- missing history index 不能阻止 full event-log replay。
- `FileCheckpointStore` 仍保持 opaque，不解释 checkpoint business state。
- `RunProjector` 仍是判断 checkpoint candidate 是否可用的 owner。

## v0 Candidate / Sketch

未来 history index 可以是 per-run metadata。

index metadata 可以记录：

- checkpoint locator
- `created_at`
- `basis_event_id`
- `projector_version`
- digest metadata summary

index ordering 应 deterministic，优先 newest-to-oldest。

如果 index corrupt，future behavior 可以考虑：

- fail fast 并要求人工处理
- fallback directory scan
- fallback full event-log replay

具体选择仍是 open question，但不能静默猜测 index 内容。

retention policy 可以考虑：

- latest-only
- keep last N
- keep by age
- keep by basis spacing

retention / GC 应和 save path、fallback path 分开实现，不能顺手混进同一个 TDD slice。

history save path 如果保留 checkpoint history，必须先遵守 `docs/checkpoint-history-save-boundary-v0.1.md`，不能静默改变 current latest-only save behavior。

以上字段和策略只是 v0 candidate / schema sketch，不是当前实现协议。

## Invalid Uses

以下用法明确无效：

- 用 history index 替代 event log。
- 用 history index 证明 checkpoint 有效。
- 用 history index 跳过 checkpoint integrity/hash validation。
- 用 history index 跳过 event prefix digest validation。
- 用 history index 跳过 checkpoint state schema validation。
- 用 retention policy 删除 canonical event log。
- 用 GC 修复坏 checkpoint 或坏 event log。
- server 直接读取 index 后选择 checkpoint 并返回 checkpoint state。
- public client 指定 checkpoint history entry 作为事实来源。
- public client 上传 history index 或 checkpoint state。
- 把 checkpoint history index 当 public audit log。

## Open Questions

以下问题当前不定为 Hard Contract：

- history index 是单独 JSON 文件、JSONL、目录 listing，还是 event-store metadata。
- history index 是否 append-only。
- history index 是否需要自己的 integrity/hash。
- index 与 checkpoint blob 写入的原子性如何保证。
- duplicate `created_at` 如何排序。
- duplicate `basis_event_id` 如何排序。
- retention 删除 checkpoint 后是否需要 tombstone。
- GC 是否需要 audit / diagnostic event。
- public inspection API 能否暴露 history index metadata。
- future checkpoint migration 与 retention 谁先执行。
- corrupt index 是 fail fast、fallback directory scan，还是 fallback full rebuild。

## Deferred

当前仍不实现：

- checkpoint history index。
- retention policy。
- checkpoint GC。
- `save_checkpoint(...)` semantic change / automatic history persistence。
- `CheckpointService`。
- public checkpoint inspection API。
- automatic checkpoint scheduling。
- checkpoint retention scheduler。
- checkpoint history index integrity/hash。
- checkpoint history index migration。
- event log compaction。

当前也不修改 latest-only save behavior：`save_checkpoint(...)` 仍只替换 `latest.json`，不自动保存 history。

## Future TDD Notes

后续如继续实现，应先写 red tests，优先覆盖：

- history index corrupt / missing 行为。
- deterministic newest-to-oldest candidate ordering through index。
- index 与 checkpoint blob 写入的原子性。
- retention policy 只删除 checkpoint blobs / index metadata，不触碰 canonical event log。
- deleted checkpoint 后仍可 full event-log rebuild。
- server 不能直接解释 history index 或 checkpoint state。
- `FileCheckpointStore` 继续保持 opaque。

不要在没有新 design patch 和 red tests 前实现 checkpoint history index、retention policy、checkpoint GC、public checkpoint inspection API 或 `CheckpointService`。
