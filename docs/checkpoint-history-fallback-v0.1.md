# Checkpoint History / Old-Checkpoint Fallback v0.1

状态：draft

本文定义 checkpoint history（检查点历史）和 old-checkpoint fallback（旧 checkpoint 回退）的 v0.1 边界。当前已经实现最小 projector-owned old-checkpoint fallback path，但 `save_checkpoint(...)` 仍是 latest-only checkpoint storage；本文说明候选 checkpoint 如何被读取和验证，以及为什么这不能改变 canonical event log 的 source-of-truth 边界。

## Purpose

checkpoint history / old-checkpoint fallback 的目的，是在 latest checkpoint 不可用时，允许 projector-owned read path 尝试更旧的 fully valid checkpoint 来缩短 replay 距离。

它不是事实恢复机制，不是 audit log，也不是 event log replacement。任何 checkpoint 候选都只能作为 derived replay basis，不能替代 canonical event log。

## Current State

当前实现状态：

- 当前已实现 `FileCheckpointStore.load_checkpoint_candidates(run_id)`。
- checkpoint candidates 按 checkpoint `created_at` newest-to-oldest 读取。
- candidate loading 仍保持 storage opaque，不解释 `projector_version`、checkpoint integrity、event prefix digest、event envelope version 或 projected state 语义。
- 当前 checkpoint path 是 `runs/{run_id}/checkpoints/latest.json`。
- 当前没有 checkpoint history index。
- 当前最小 old-checkpoint fallback path 已实现于 `RunProjector.rebuild_with_checkpoint(...)`。
- invalid latest checkpoint 后可以尝试 older checkpoint candidate。
- 每个 candidate 仍必须独立通过 projector-owned validation chain。
- invalid candidate 不能被部分读取或部分采用。
- 所有 candidates 都 invalid 时，会 fallback full event-log rebuild。
- lifecycle-invalid event log 不能被 older checkpoint fallback 隐藏。
- `FileCheckpointStore` 仍是 opaque storage，不解释 checkpoint state。
- latest-only replacement boundary 已实现：同一 run 第二次保存 checkpoint 会替换 `latest.json`，不创建 history 文件。
- invalid replacement 不会覆盖已有 valid latest checkpoint。
- replacement 不修改 event log，也不创建 / 删除 / 重写 `events.jsonl`。
- 当前 full regression：`360 passed`。

当前没有实现：

- checkpoint history index。
- checkpoint history persistence from `save_checkpoint(...)`。
- checkpoint GC。
- retention policy。
- public checkpoint inspection API。
- checkpoint migration / migrator registry。
- `CheckpointService`。

checkpoint history index / retention policy 的边界见 `docs/checkpoint-history-index-retention-v0.1.md`。

## Decision

v0.1 design decision：

- 当前不实现 checkpoint history index。
- 当前不实现 retention / GC。
- 当前继续 latest-only checkpoint save boundary。
- 当前已实现最小 projector-owned old-checkpoint fallback：candidate 必须 fully valid，才能作为 replay basis。
- 所有 checkpoint candidates 不可用时，fallback full canonical event-log rebuild。
- checkpoint history 如果未来实现，也不能把 checkpoint 变成第二事实源。
- old-checkpoint fallback 必须由 projector-owned boundary 执行，不能由 server 或 checkpoint store 直接解释 checkpoint state。

## Hard Boundaries

- checkpoint history 不能把 checkpoint 变成 source of truth。
- old-checkpoint fallback 不能跳过 canonical event log validation。
- old-checkpoint fallback 不能跳过 lifecycle validation。
- old-checkpoint fallback 不能跳过 projector validation。
- 每个候选 checkpoint 都必须独立通过 projector version validation。
- 每个候选 checkpoint 都必须独立通过 checkpoint integrity/hash validation。
- 每个候选 checkpoint 都必须独立通过 event prefix digest validation。
- 每个候选 checkpoint 都必须独立通过 event envelope version validation。
- 每个候选 checkpoint 都必须独立通过 checkpoint state schema validation。
- 每个候选 checkpoint 都必须独立通过 prefix consistency validation。
- invalid checkpoint 不能被部分读取。
- invalid checkpoint 不能被部分采用。
- old-checkpoint fallback 不能隐藏 malformed event log。
- old-checkpoint fallback 不能隐藏 lifecycle-invalid event log。
- server 不能直接选择、解释或信任 old checkpoint。
- server 如需使用 old-checkpoint fallback，只能调用 projector-owned boundary。
- fallback 不能重写 canonical events。
- fallback 不能删除 canonical events。
- fallback 不能压缩 canonical events。
- fallback 不能迁移 canonical events。
- `FileCheckpointStore` 仍保持 opaque，不解释 checkpoint business state。

## v0 Candidate / Sketch

当前实现可以读取 per-run checkpoint candidates，但没有 checkpoint history index。

当前 v0 implementation choice：

- 保留 latest checkpoint 语义。
- `FileCheckpointStore.load_checkpoint_candidates(run_id)` 从 run-scoped checkpoint directory 读取 candidate blobs。
- fallback order 使用 checkpoint `created_at` newest-to-oldest scan。
- 每个候选 checkpoint 先完整执行现有 checkpoint validation chain。
- 找到第一个 fully valid checkpoint 后，从该 checkpoint 的 `basis_event_id` 之后继续 replay suffix events。
- 如果所有 checkpoint 都 invalid，则 fallback full event-log rebuild。

未来可以考虑：

- 增加 checkpoint history index。
- 让 `save_checkpoint(...)` 保留最近 N 个 checkpoint。
- checkpoint history index 自身需要 integrity / ordering / retention 边界。
- retention / GC 和 fallback 选择逻辑分开设计，不能在 fallback slice 中顺手实现。

更完整的 history index / retention policy sketch 见 `docs/checkpoint-history-index-retention-v0.1.md`。

这些只是 v0 candidate / schema sketch，不是当前实现协议。

## History Index Sketch

如果未来引入 history index，index 可能包含：

- `checkpoint_id`
- `run_id`
- `created_at`
- `basis_event_id`
- `event_count`
- `projector_version`
- checkpoint blob location

这些字段只是解释用 sketch。当前不实现 history index，也不承诺字段名。

## Invalid Uses

以下用法明确无效：

- 用 checkpoint history 替代 event log。
- 用 old checkpoint 修复坏 event log。
- 用 old checkpoint 隐藏 lifecycle-invalid event。
- latest checkpoint invalid 时跳过 event validation 直接信任 older checkpoint。
- checkpoint store 解释 checkpoint validity 后只返回看起来 valid 的 candidates。
- server 直接从 checkpoint history 选择 checkpoint 并返回 checkpoint state。
- checkpoint store 根据 checkpoint state 判断业务状态。
- public client 指定某个 checkpoint 作为事实来源。
- public client 上传 checkpoint state。
- 把 checkpoint history 当 public audit log。
- 因 checkpoint history 存在而删除 event log。

## Open Questions

以下问题当前不定为 Hard Contract：

- history index 是单独文件、目录 listing，还是 event-store 附属 metadata。
- checkpoint history 是否 append-only。
- fallback 到旧 checkpoint 是否需要 diagnostic / audit event。
- invalid checkpoint 是否保留、隔离、还是标记。
- old checkpoint fallback 和 future migration / migrator registry 如何协作。
- event prefix digest 变化后是否允许旧 checkpoint fallback。
- checkpoint history 是否需要独立 integrity/hash。
- checkpoint history 如何和 retention / GC 协作。
- public inspection API 能否暴露 checkpoint history metadata。

## Deferred

当前仍不实现：

- checkpoint history index。
- checkpoint history persistence from `save_checkpoint(...)`。
- checkpoint GC。
- retention policy。
- checkpoint inspection API。
- checkpoint migration implementation。
- checkpoint migrator registry。
- `CheckpointService`。
- public checkpoint API。
- event log compaction。
- event log migration。
- automatic checkpoint scheduling。
- checkpoint retention / compaction beyond latest-only replacement。

## Future TDD Notes

已覆盖的最小测试：

- `FileCheckpointStore.load_checkpoint_candidates(run_id)` 存在。
- checkpoint candidates newest-to-oldest 读取。
- candidate loading 保持 storage opaque。
- invalid latest checkpoint 后尝试 older candidate。
- 每个 candidate checkpoint 必须独立通过完整 validation chain。
- invalid candidate 不能部分读取或部分采用。
- all invalid candidates fallback full event-log rebuild。
- lifecycle-invalid event log 不能被 older checkpoint fallback 隐藏。
- `save_checkpoint(...)` 仍是 latest-only replacement，不创建 history 文件。

后续如继续扩展，应先写 red tests，至少覆盖：

- checkpoint history index。
- checkpoint history persistence from `save_checkpoint(...)`。
- retention / GC。
- corrupt / missing history index 不能跳过 full event-log replay。
- server 不能直接解释 checkpoint history 或 checkpoint state。
- `FileCheckpointStore` 继续保持 opaque。

不要在没有新 design patch 和 red tests 前实现 checkpoint history index、GC、retention policy、public checkpoint API 或 `CheckpointService`。
