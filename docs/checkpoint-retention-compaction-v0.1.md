# Checkpoint Retention / Compaction v0.1

状态：draft

本文定义 checkpoint retention / compaction（检查点保留 / 压缩清理）的 v0.1 边界：checkpoint blob 如何保留、替换、清理，以及这些操作为什么绝不能影响 canonical event log。

本轮只落设计说明，不实现 retention policy、checkpoint history、GC、automatic scheduling 或 event log compaction。

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
- 当前 full regression：`311 passed`。

当前没有实现：

- retention policy。
- checkpoint history。
- checkpoint compaction。
- automatic checkpoint scheduling。
- checkpoint GC。
- event log compaction。

## Decision

v0.1 design decision：

- checkpoint retention / compaction 只能处理 checkpoint blobs。
- retention / compaction 不能处理 canonical event log。
- 当前可以继续使用 latest-only checkpoint，不急着保留 history。
- compaction 在本文中只表示清理旧 checkpoint blobs，不表示 event log compaction。
- checkpoint 删除后，系统必须仍能从 canonical event log full rebuild。
- `FileCheckpointStore` 仍保持 opaque，不解释业务 state。
- public client 不能通过 retention / compaction 能力提交、选择或读取 checkpoint state。

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
- `FileCheckpointStore` 仍保持 opaque，不解释 checkpoint business state。

## v0 Candidate

当前 v0 candidate：

- 保持 latest-only checkpoint。
- `save_checkpoint(...)` 可以继续替换 latest checkpoint blob。
- latest-only replacement 不应触碰 event log。
- latest-only replacement 后，missing / invalid latest checkpoint 仍 fallback full rebuild。

未来可以考虑：

- 保留最近 N 个 checkpoint。
- 按 `created_at` / `basis_event_id` / `event_count` 选择 checkpoint。
- retention metadata 包含 `checkpoint_id`、`created_at`、`basis_event_id`、`event_count`、`projector_version`。
- 如果多个 checkpoint 可用，优先选择最新 compatible + valid checkpoint。
- 如果最新 checkpoint invalid，fallback 更旧 checkpoint 或 full rebuild。

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
- old checkpoint fallback 策略。
- retention 触发时机。
- automatic checkpoint scheduling。
- checkpoint GC。
- checkpoint migration / version negotiation。
- event log compaction；注意这不是 checkpoint compaction。
- public checkpoint inspection API。
- `CheckpointService`。

## Future TDD Notes

下一轮如进入 implementation，应先写 red tests，优先覆盖：

- `FileCheckpointStore` latest-only replacement boundary hardening。
- latest checkpoint replacement 不修改 event log。
- latest checkpoint replacement 后 full rebuild 仍可用。
- malformed latest checkpoint 不阻止 event log full rebuild。
- retention / compaction 不读取 artifact content、executor state 或 server memory。

不要直接实现 checkpoint history、GC、automatic scheduling 或 event log compaction。
