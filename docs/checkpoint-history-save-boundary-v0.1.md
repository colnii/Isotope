# Checkpoint History Save Boundary v0.1

状态：draft

本文定义 checkpoint history save（检查点历史保存）的 v0.1 边界。当前只做设计说明，不实现 checkpoint history persistence，不修改 `save_checkpoint(...)` 的 latest-only 行为。

## Purpose

checkpoint history save 的目的，是在 future save path 需要保留历史 checkpoint candidates 时，明确谁能生成 checkpoint、如何保存 latest 与 history、失败时如何避免误导状态。

它不是事实来源，不是 public API，也不是 retention / GC 实现。

## Current State

当前实现状态：

- `RunProjector.save_checkpoint(...)` 仍是 latest-only replacement。
- `save_checkpoint(...)` 只写 `runs/{run_id}/checkpoints/latest.json`。
- `save_checkpoint(...)` 不创建 checkpoint history 文件。
- `FileCheckpointStore.load_checkpoint_candidates(run_id)` 已实现，可以读取 run-scoped candidates。
- candidate loading 能读取 candidates 不等于 save path 已经持久化 history。
- 最小 projector-owned old-checkpoint fallback 已实现的是 read path，不是 save/history policy。
- `InProcessServer.save_checkpoint_for_run(run_id)` 仍只调用 projector-owned `RunProjector.save_checkpoint(...)`。
- 当前没有 checkpoint history persistence from `save_checkpoint(...)`。
- 当前没有 checkpoint history index。
- 当前没有 retention policy。
- 当前没有 checkpoint GC。
- 当前没有 `CheckpointService`。
- 当前 full regression：`360 passed`。

## Decision

v0.1 design decision：

- checkpoint history save 不能修改 canonical event log。
- checkpoint history save 不能让 checkpoint 成为第二事实源。
- save path 不能跳过 `RunProjector.create_checkpoint(...)`。
- save path 不能保存未经过 projector-owned creation 的 checkpoint。
- invalid checkpoint 不能覆盖 latest。
- invalid checkpoint 不能进入 history。
- history save 不能让 server 直接解释 checkpoint state。
- history file / history index 失败不能破坏 event-log replay。
- latest write 与 history write 的失败顺序必须有明确策略，不能留下误导性状态。
- 本轮不修改当前 latest-only save behavior。

## Hard Boundaries

- history save 不能删除 canonical events。
- history save 不能重写 canonical events。
- history save 不能压缩 canonical events。
- history save 不能裁剪 canonical events。
- history save 不能修复坏 event log。
- history save 不能跳过 event validation。
- history save 不能跳过 lifecycle validation。
- history save 不能跳过 `RunProjector.create_checkpoint(...)`。
- history save 不能保存外部提交的 checkpoint state。
- invalid checkpoint 不能覆盖 `latest.json`。
- invalid checkpoint 不能写入 history candidates。
- history write failure 不能伪造 success。
- history index failure 不能阻止 full event-log replay。
- server 不能直接解释 history candidate 或 history index 来生成 `RunState`。
- public client 不能触发或上传 checkpoint history state。
- `FileCheckpointStore` 仍保持 opaque，不解释 checkpoint business state。

## v0 Candidate / Sketch

未来可以考虑以下保存策略：

- 先写 immutable candidate file，再更新 `latest.json`。
- 先写 `latest.json`，再 best-effort 写 history file。
- 引入 explicit `save_checkpoint_history(...)`，不改变当前 `save_checkpoint(...)`。

candidate filename 可以基于：

- `created_at`
- `basis_event_id`
- content hash

这些字段名和文件名策略只是 schema sketch，不是当前实现协议。

history persistence 应与 retention / GC 分开实现。

history index 更新如果失败，应有明确 fallback：

- directory scan
- full event replay
- fail fast with diagnostic

具体策略仍是 open question，但不能隐式猜测。

`save_checkpoint(...)` 是否继续 latest-only，还是新增参数 / 新方法，需要单独决策。当前推荐优先考虑新方法，避免 silently changing existing latest-only behavior。

## Invalid Uses

以下用法明确无效：

- 让 server 直接构造 history checkpoint state。
- 保存未经过 `RunProjector.create_checkpoint(...)` 的 checkpoint。
- history write 失败后返回 saved。
- history index 更新失败后假装 index 完整。
- 因为 history checkpoint 存在而删除 event log。
- 用 history save 修复 malformed event log。
- public client 上传 checkpoint history candidate。
- public client 指定 checkpoint history entry 作为事实来源。
- 将 checkpoint history save 暴露为 public HTTP API。

## Open Questions

以下问题当前不定为 Hard Contract：

- 是否改变 `save_checkpoint(...)` 语义，还是新增独立 method。
- latest write 和 history write 的原子性如何保证。
- history candidate 文件名如何生成。
- duplicate `created_at` 如何处理。
- duplicate `basis_event_id` 如何处理。
- history write 失败是否应该 fail whole save。
- history index 更新失败是否要保留 checkpoint blob。
- retention 是 save-time 执行，还是后台 / 手动执行。
- server manual save trigger 是否允许触发 history save。
- public checkpoint API 是否永远不暴露 history save。

## Deferred

当前仍不实现：

- checkpoint history persistence。
- checkpoint history save method。
- `save_checkpoint(...)` semantic change。
- checkpoint history index。
- retention policy。
- checkpoint GC。
- `CheckpointService`。
- public checkpoint API。
- public checkpoint inspection API。
- automatic checkpoint scheduling。
- save-time retention。
- checkpoint history write atomicity implementation。

当前也不修改 latest-only save behavior：`save_checkpoint(...)` 仍只替换 `latest.json`，不自动保存 history。

## Future TDD Notes

后续如继续实现，应先写 red tests，优先覆盖：

- current `save_checkpoint(...)` 是否保持 latest-only，或明确引入新 method。
- invalid checkpoint 不能覆盖 latest，也不能进入 history。
- latest write / history write failure ordering。
- history write 不修改 event log。
- history write 不读取 artifact content / executor state / server memory。
- history candidate 可被 `load_checkpoint_candidates(run_id)` 读取。
- retention / GC 不混入 history save slice。
- server manual save trigger 是否调用 history save 的明确边界。

不要在没有新 design patch 和 red tests 前实现 checkpoint history persistence、history index、retention policy、checkpoint GC、public checkpoint API 或 `CheckpointService`。
