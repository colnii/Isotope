# Checkpoint History Save Boundary v0.1

状态：draft

本文定义 checkpoint history save（检查点历史保存）的 v0.1 边界。当前已实现 explicit history candidate save method，但不修改 `save_checkpoint(...)` 的 latest-only 行为，也不引入 checkpoint history index、retention policy、GC 或 public API。

## Purpose

checkpoint history save 的目的，是在 future save path 需要保留历史 checkpoint candidates 时，明确谁能生成 checkpoint、如何保存 latest 与 history、失败时如何避免误导状态。

它不是事实来源，不是 public API，也不是 retention / GC 实现。

## Current State

当前实现状态：

- `RunProjector.save_checkpoint(...)` 仍调用 latest-only replacement path。
- `save_checkpoint(...)` 只写 `runs/{run_id}/checkpoints/latest.json`。
- `save_checkpoint(...)` 不创建 checkpoint history 文件。
- `FileCheckpointStore.save_checkpoint_history(run_id, checkpoint)` 已实现为 explicit history candidate save method。
- `save_checkpoint_history(...)` 将 candidate 写入 `runs/{run_id}/checkpoints/` 下非 `latest.json` 文件。
- `save_checkpoint_history(...)` 不覆盖或修改 `latest.json`。
- `save_checkpoint_history(...)` 复用 run_id 和 checkpoint 基础 storage validation。
- invalid checkpoint 在写入前被拒绝，不会产生 history candidate。
- history save 不修改 canonical event log，也不创建 / 删除 / 重写 `events.jsonl`。
- history save 后的 candidate 可由 `load_checkpoint_candidates(run_id)` 读取，并按 newest-to-oldest 返回。
- `FileCheckpointStore` 仍保持 opaque，不解释 checkpoint state / integrity / projector version。
- `FileCheckpointStore.load_checkpoint_candidates(run_id)` 已实现，可以读取 run-scoped candidates。
- candidate loading 能读取 candidates，也能读取 explicit history save 写入的 candidates；这不改变 `save_checkpoint(...)` latest-only 语义。
- checkpoint history save integration boundary 已落文档，见 `../reviews/checkpoint-history-save-integration-v0.1.md`。
- 最小 projector-owned old-checkpoint fallback 已实现的是 read path，不是 save/history policy。
- `InProcessServer.save_checkpoint_for_run(run_id)` 仍只调用 projector-owned `RunProjector.save_checkpoint(...)`。
- `RunProjector.save_checkpoint_history(...)` 已实现为显式 projector-owned history save method。
- `InProcessServer.save_checkpoint_history_for_run(run_id)` 已实现为 internal-only explicit history save trigger。
- server history save trigger 只委托 projector-owned `RunProjector.save_checkpoint_history(...)`，不直接调用 storage、不接收或解释 checkpoint state、不写 `latest.json`。
- automatic history persistence from latest/default save path 仍未实现。
- 当前没有 checkpoint history index。
- 当前没有 retention policy。
- 当前没有 checkpoint GC。
- 当前没有 `CheckpointService`。
- 当前 full regression：`391 passed`。

## Decision

v0.1 design decision：

- checkpoint history save 不能修改 canonical event log。
- checkpoint history save 不能让 checkpoint 成为第二事实源。
- save path 不能跳过 `RunProjector.create_checkpoint(...)`。
- save path 不能保存未经过 projector-owned creation 的 checkpoint。
- invalid checkpoint 不能覆盖 latest。
- invalid checkpoint 不能进入 history candidate files。
- history save 不能让 server 直接解释 checkpoint state。
- history file / history index 失败不能破坏 event-log replay。
- `save_checkpoint_history(...)` 是 storage boundary，不是 projector-owned checkpoint creation boundary；caller 仍必须维护 projector-owned creation 规则。
- `save_checkpoint(...)` 与 `save_checkpoint_history(...)` 的组合、原子性和自动触发策略仍未实现。
- 当前不修改 latest-only save behavior。

## Hard Boundaries

- history save 不能删除 canonical events。
- history save 不能重写 canonical events。
- history save 不能压缩 canonical events。
- history save 不能裁剪 canonical events。
- history save 不能修复坏 event log。
- history save 不能跳过 event validation。
- history save 不能跳过 lifecycle validation。
- history save integration 不能跳过 `RunProjector.create_checkpoint(...)`。
- history save 不能保存外部提交的 checkpoint state。
- invalid checkpoint 不能覆盖 `latest.json`。
- invalid checkpoint 不能写入 history candidates。
- history candidate file 不能命名为 `latest.json`。
- history write failure 不能伪造 success。
- history index failure 不能阻止 full event-log replay。
- server 不能直接解释 history candidate 或 history index 来生成 `RunState`。
- public client 不能触发或上传 checkpoint history state。
- `FileCheckpointStore` 仍保持 opaque，不解释 checkpoint business state。

## v0 Candidate / Sketch

当前已实现的 storage-level history save：

- explicit method：`FileCheckpointStore.save_checkpoint_history(run_id, checkpoint)`。
- candidate file 写入 run-scoped `checkpoints/` 目录。
- candidate file 不使用 `latest.json`。
- candidate file 可被 `load_checkpoint_candidates(run_id)` 读取。
- store 层只做 storage boundary validation，不解释 checkpoint business state。

未来可以考虑以下更高层保存策略：

- 先写 immutable candidate file，再更新 `latest.json`。
- 先写 `latest.json`，再 best-effort 写 history file。
- 组合 `save_checkpoint(...)` 和 `save_checkpoint_history(...)`，但必须明确失败顺序。

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

`save_checkpoint(...)` 当前继续 latest-only。是否让 projector/server save trigger 额外调用 `save_checkpoint_history(...)`，需要遵守 `../reviews/checkpoint-history-save-integration-v0.1.md` 并单独决策，避免 silently changing existing latest-only behavior。

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
- latest/default save trigger 是否允许自动触发 history save。
- public checkpoint API 是否永远不暴露 history save。

## Deferred

当前仍不实现：

- `save_checkpoint(...)` semantic change。
- automatic history persistence from `save_checkpoint(...)`。
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

- current `save_checkpoint(...)` 是否继续保持 latest-only。
- projector/server caller 对 `save_checkpoint_history(...)` 的显式调用边界。
- 显式 projector-owned history save method 的调用边界。
- invalid checkpoint 不能覆盖 latest，也不能进入 history。
- latest write / history write failure ordering。
- history write 不修改 event log。
- history write 不读取 artifact content / executor state / server memory。
- history candidate 可被 `load_checkpoint_candidates(run_id)` 读取。
- retention / GC 不混入 history save slice。
- latest/default save trigger 是否调用 history save 的明确边界。

不要在没有新 design patch 和 red tests 前实现 automatic history persistence from `save_checkpoint(...)`、history index、retention policy、checkpoint GC、public checkpoint API 或 `CheckpointService`。
