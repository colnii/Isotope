# Checkpoint Retention / Compaction v0.1

状态：draft

本文定义 checkpoint retention / compaction（检查点保留 / 压缩清理）的 v0.1 边界：checkpoint blob 如何保留、替换、清理，以及这些操作为什么绝不能影响 canonical event log。

当前已实现 latest-only checkpoint storage boundary hardening、checkpoint candidate loading、最小 projector-owned old-checkpoint fallback path 和 explicit history candidate save method。`save_checkpoint(...)` 仍是 latest-only replacement，不自动保留 history；broader retention policy、checkpoint history index、GC、automatic scheduling 和 event log compaction 仍不实现。

## Purpose

checkpoint retention / compaction 的目的，是控制 checkpoint blob 的存储增长，并明确未来如果出现 checkpoint history，应如何选择、替换和清理 checkpoint。

它不是 event log compaction，不产生新事实，不改变 `RunState` 语义，也不能让 checkpoint 成为第二事实源。

## Current State

当前实现状态：

- `FileCheckpointStore` 是 run-scoped opaque storage。
- 当前路径是 latest checkpoint 风格，例如 `runs/{run_id}/checkpoints/latest.json`。
- `RunProjector.save_checkpoint(...)` 已存在。
- `InProcessServer.save_checkpoint_for_run(...)` 已是 internal-only manual trigger。
- checkpoint 已有 checkpoint hash。
- checkpoint 已有 event prefix digest。
- latest-only checkpoint storage boundary hardening 已实现。
- checkpoint path 仍是 `runs/{run_id}/checkpoints/latest.json`。
- 同一 run 第二次保存 checkpoint 会替换 `latest.json`。
- invalid replacement 不会覆盖已有 valid latest checkpoint。
- replacement 不修改 event log，也不创建 / 删除 / 重写 `events.jsonl`。
- `checkpoint_path` / `save_checkpoint` / `load_latest_checkpoint` 都校验 run_id path segment。
- `FileCheckpointStore` 仍保持 opaque，不解释 checkpoint business state。
- `FileCheckpointStore.load_checkpoint_candidates(run_id)` 已实现，可按 checkpoint `created_at` newest-to-oldest 读取 run-scoped candidates。
- candidate loading 仍保持 storage opaque，不解释 `projector_version`、checkpoint integrity、event prefix digest、event envelope version 或 projected state 语义。
- `RunProjector.rebuild_with_checkpoint(...)` 可使用 candidate chain。
- invalid latest checkpoint 后可以尝试 older fully valid checkpoint candidate。
- 每个 candidate 仍必须独立通过 projector-owned validation chain。
- invalid candidate 不能被部分读取或部分采用。
- 所有 candidates 都 invalid 时，会 fallback full event-log rebuild。
- lifecycle-invalid event log 不能被 older checkpoint fallback 隐藏。
- `save_checkpoint(...)` 仍是 latest-only replacement，不创建 checkpoint history 文件。
- `FileCheckpointStore.save_checkpoint_history(run_id, checkpoint)` 已实现为 explicit history candidate save method。
- history candidate 写入 run-scoped `checkpoints/` 目录下非 `latest.json` 文件。
- history save 不覆盖 `latest.json`，不修改 event log。
- invalid history checkpoint 在写入前被拒绝。
- `FileCheckpointStore` 仍保持 opaque，不解释 checkpoint state / integrity / projector version。
- checkpoint history / old-checkpoint fallback 边界见 `docs/checkpoint-history-fallback-v0.1.md`。
- checkpoint history index / retention policy 边界见 `docs/checkpoint-history-index-retention-v0.1.md`。
- checkpoint history save 边界见 `docs/checkpoint-history-save-boundary-v0.1.md`。
- checkpoint history save integration 边界见 `docs/checkpoint-history-save-integration-v0.1.md`。
- `RunProjector.save_checkpoint_history(...)` 已实现为显式 projector-owned history save method。
- server 当前还没有 automatic history save integration，latest save path 仍不自动写 history。
- checkpoint migration / version negotiation design note 已落文档。
- 当前 full regression：`379 passed`。

当前没有实现：

- retention policy。
- checkpoint history index。
- `save_checkpoint(...)` semantic change / automatic history persistence。
- broader checkpoint compaction。
- automatic checkpoint scheduling。
- checkpoint GC。
- event log compaction。
- checkpoint migration / version negotiation implementation。

## Decision

v0.1 design decision：

- checkpoint retention / compaction 只能处理 checkpoint blobs。
- retention / compaction 不能处理 canonical event log。
- 当前继续使用 latest-only checkpoint，不急着保留 history。
- latest-only checkpoint storage boundary 已加固。
- 当前已实现最小 projector-owned old-checkpoint fallback：candidate 必须 fully valid，才能作为 replay basis。
- 所有 checkpoint candidates 都不可用时，fallback full canonical event-log rebuild。
- compaction 在本文中只表示清理旧 checkpoint blobs，不表示 event log compaction。
- checkpoint 删除后，系统必须仍能从 canonical event log full rebuild。
- `FileCheckpointStore` 仍保持 opaque，不解释业务 state。
- public client 不能通过 retention / compaction 能力提交、选择或读取 checkpoint state。
- history index 不是 source of truth，不能证明 checkpoint 有效。
- retention / GC 只能作用于 checkpoint blobs 或 future index metadata。
- corrupt / missing history index 不能让系统跳过 full event-log replay。

## Hard Boundaries

- retention / compaction 不能删除 canonical events。
- retention / compaction 不能重写 canonical events。
- retention / compaction 不能压缩 canonical events。
- retention / compaction 不能裁剪 canonical events。
- checkpoint compaction 不能产生新的事实。
- checkpoint compaction 不能修改 `RunState` 语义。
- checkpoint compaction 不能跳过 event validation。
- checkpoint compaction 不能跳过 lifecycle validation。
- checkpoint compaction 不能跳过 checkpoint state schema validation。
- checkpoint compaction 不能跳过 prefix consistency validation。
- checkpoint compaction 不能跳过 checkpoint integrity hash validation。
- checkpoint compaction 不能跳过 event prefix digest validation。
- checkpoint retention 不能暴露 public checkpoint API。
- checkpoint retention 不能把 checkpoint history 当成 public audit log。
- old-checkpoint fallback 不能绕过 canonical event log validation。
- old-checkpoint fallback 不能隐藏 malformed 或 lifecycle-invalid event log。
- 每个候选 checkpoint 都必须独立通过 projector version、integrity/hash、event prefix digest、event envelope version、checkpoint state schema 和 prefix consistency validation。
- server 不能直接选择、解释或信任 old checkpoint。
- `FileCheckpointStore` 仍保持 opaque，不解释 checkpoint business state。

## v0 Candidate

当前 v0 candidate：

- 保持 latest-only checkpoint。
- `save_checkpoint(...)` 继续替换 latest checkpoint blob。
- latest-only replacement 不触碰 event log。
- latest-only replacement 不创建 checkpoint history 文件。
- invalid replacement 不覆盖已有 valid latest checkpoint。
- `save_checkpoint_history(...)` 可显式保存 history candidate，但不改变 latest-only replacement 语义。
- `save_checkpoint_history(...)` 不触碰 event log。
- `run_id` 作为受控 path segment 校验。
- `FileCheckpointStore.load_checkpoint_candidates(run_id)` 可读取 run-scoped checkpoint candidates。
- candidate loading 按 `created_at` newest-to-oldest 读取，但 storage 不解释 checkpoint 业务语义。
- `RunProjector.rebuild_with_checkpoint(...)` 可在 invalid latest checkpoint 后尝试 older fully valid candidate。
- 所有 candidates invalid 时，fallback full event-log rebuild。

未来可以考虑：

- 保留最近 N 个 checkpoint。
- 按 `created_at` / `basis_event_id` / `event_count` 选择 checkpoint。
- retention metadata 包含 `checkpoint_id`、`created_at`、`basis_event_id`、`event_count`、`projector_version`。
- checkpoint history index 自身也需要 integrity / ordering / retention 边界。
- retention / GC 应和 candidate fallback 设计分开，不在同一个实现 slice 中顺手完成。
- history save 应和 retention / GC 分开实现，不能在 save slice 中顺手做清理策略。

更完整的 history index / retention policy sketch 见 `docs/checkpoint-history-index-retention-v0.1.md`。

这些字段名和策略只是 v0 candidate / schema sketch，不是永久协议。

## Invalid Uses

以下用法明确无效：

- 用 checkpoint 替代 event log。
- 因为 checkpoint 已经存在而删除 event log。
- 用 checkpoint compaction 修复坏 event log。
- 用 retention policy 隐藏 lifecycle-invalid event。
- 把 checkpoint history 当 public audit log。
- 让 client 指定 checkpoint state。
- 让 client 上传 checkpoint state。
- 让 client 指定某个 checkpoint 作为事实来源。
- 把 checkpoint compaction 当成 event log compaction。

## Deferred / Open Questions

当前仍 deferred / open：

- 是否保持 latest-only，还是保留最近 N 个 checkpoint。
- checkpoint 文件命名与 `checkpoint_id`。
- checkpoint history index 的完整性、顺序和错误处理。
- `save_checkpoint(...)` semantic change / automatic history persistence。
- server automatic history save integration。
- retention 触发时机。
- automatic checkpoint scheduling。
- checkpoint GC。
- checkpoint retention policy。
- checkpoint migration / version negotiation implementation。
- checkpoint migrator registry。
- schema registry。
- event log compaction；注意这不是 checkpoint compaction。
- public checkpoint inspection API。
- `CheckpointService`。

## Future TDD Notes

已覆盖的最小测试：

- latest checkpoint replacement 不修改 event log。
- latest checkpoint replacement 不创建 / 删除 / 重写 `events.jsonl`。
- same-run second save replaces `latest.json` without history files。
- invalid replacement does not overwrite existing valid latest checkpoint。
- `checkpoint_path` / `save_checkpoint` / `load_latest_checkpoint` reject invalid run_id path segments。
- latest checkpoint replacement 后 full rebuild 仍可用。
- malformed latest checkpoint 不阻止 event log full rebuild。
- retention / compaction 不读取 artifact content、executor state 或 server memory。
- `FileCheckpointStore.load_checkpoint_candidates(run_id)` 可读取 run-scoped candidates。
- checkpoint candidates newest-to-oldest 读取。
- candidate loading 保持 storage opaque。
- invalid latest checkpoint 后可以尝试 older fully valid candidate。
- 每个 candidate 都独立通过 projector-owned validation chain。
- invalid candidate 不能被部分读取或部分采用。
- all invalid candidates fallback full event-log rebuild。
- lifecycle-invalid event log 不能被 older checkpoint fallback 隐藏。
- explicit history candidate save method。
- history save 不覆盖 latest checkpoint。
- history save 不修改 event log。
- invalid history checkpoint 不会写入 candidate file。

后续如继续扩展，应先写 red tests，优先覆盖：

- checkpoint history index integrity / ordering boundary。
- automatic history persistence from `save_checkpoint(...)`。
- projector/server history save integration boundary。
- checkpoint retention / GC。
- corrupt / missing history index 不能跳过 full event-log replay。
- server 不能直接解释 checkpoint history 或 checkpoint state。

不要直接实现 checkpoint history index、GC、retention policy、automatic scheduling 或 event log compaction。
