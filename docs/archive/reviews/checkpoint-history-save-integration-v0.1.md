# Checkpoint History Save Integration v0.1

状态：draft

本文定义 checkpoint history save integration（检查点历史保存集成）的 v0.1 边界：在 `FileCheckpointStore.save_checkpoint_history(...)`、`RunProjector.save_checkpoint_history(...)` 和 `InProcessServer.save_checkpoint_history_for_run(...)` 已存在后，server 如何保持显式内部调用边界。

本文不实现 history index、retention policy、GC、public checkpoint API 或 automatic scheduling。

## Purpose

checkpoint history save integration 的目的，是明确底层 storage method 和上层 projector/server caller 之间的责任边界。

它回答的是调用边界问题：现在可以保存 history candidate，但谁有资格调用、调用后算不算成功、是否改变 latest save 语义，都必须先被明确。

## Current State

当前实现状态：

- `FileCheckpointStore.save_checkpoint_history(run_id, checkpoint)` 已实现。
- `save_checkpoint_history(...)` 是 explicit history candidate save method。
- history candidate 写入 `runs/{run_id}/checkpoints/` 下非 `latest.json` 文件。
- history save 不覆盖 `latest.json`。
- history save 不修改 canonical event log。
- history save 复用 storage-level run_id 和 checkpoint 基础校验。
- `FileCheckpointStore` 仍保持 opaque storage，不解释 checkpoint state / integrity / projector version。
- `FileCheckpointStore.load_checkpoint_candidates(run_id)` 可读取 history candidates，并按 newest-to-oldest 返回。
- `save_checkpoint(...)` 仍是 latest-only replacement，不自动创建 history files。
- `RunProjector.save_checkpoint(...)` 当前仍只调用 `checkpoint_store.save_checkpoint(...)`。
- `RunProjector.save_checkpoint_history(...)` 已实现为显式 projector-owned history save method。
- `RunProjector.save_checkpoint_history(...)` 从 `event_store.list_events(run_id)` 读取 canonical events。
- `RunProjector.save_checkpoint_history(...)` 通过 `RunProjector.create_checkpoint(...)` 生成 checkpoint。
- `RunProjector.save_checkpoint_history(...)` 调用 `checkpoint_store.save_checkpoint_history(run_id, checkpoint)` 保存 history candidate。
- `RunProjector.save_checkpoint_history(...)` 不调用 `checkpoint_store.save_checkpoint(...)`。
- `RunProjector.save_checkpoint_history(...)` 不写 `latest.json`。
- `RunProjector.save_checkpoint_history(...)` 不修改 event log。
- empty / malformed / lifecycle-invalid event stream 会 fail-fast，不写 history candidate。
- `InProcessServer.save_checkpoint_for_run(...)` 当前仍只走 projector-owned latest save。
- `InProcessServer.save_checkpoint_history_for_run(run_id)` 已实现为 internal-only explicit history save trigger。
- 未配置 `checkpoint_store` 时，`save_checkpoint_history_for_run(...)` 返回 `{"status": "not_enabled", "capability": "checkpoint_history"}`。
- 配置 `checkpoint_store` 时，`save_checkpoint_history_for_run(...)` 只调用 projector-owned `RunProjector().save_checkpoint_history(run_id, self.event_store, self.checkpoint_store)`。
- server 不直接调用 `checkpoint_store.save_checkpoint_history(...)`。
- server 不接收、不构造、不解释 checkpoint state。
- server history save 成功后只返回最小 metadata：`status`、`run_id`、`basis_event_id`、`checkpoint_kind`。
- server history save 不返回 checkpoint state。
- server history save 不修改 event log。
- server history save 不写 `latest.json`。
- server 不能直接构造、解释或选择 checkpoint history state。
- 当前 full regression：`391 passed`。
- 最新 implementation commit：`067d48c4d6e693ed305d5794fd18d0d71eddd90f`。

## Decision

v0.1 design decision：

- 当前不改变 `RunProjector.save_checkpoint(...)` 默认语义。
- 当前不改变 `InProcessServer.save_checkpoint_for_run(...)` 默认语义。
- 当前不让 latest save path 自动写 history candidate。
- projector-owned history save integration 已通过显式 method 实现。
- server history save integration 已通过 explicit internal method 实现，并且必须继续显式调用 projector-owned method。
- 不建议偷偷让 existing latest save 也写 history。
- server 如未来触发 history save，只能调用 projector-owned boundary，不能直接调用 storage 保存外部 checkpoint state。
- history save integration 不能修改 event log。
- history save integration 不能让 checkpoint 成为第二事实源。

## Hard Boundaries

- history integration 不能绕过 `RunProjector.create_checkpoint(...)`。
- server 不能直接调用 storage 写外部传入的 checkpoint state。
- public client 不能触发 checkpoint history save。
- public client 不能上传 checkpoint history state。
- history save integration 不能修改 canonical event log。
- history save integration 不能删除、重写、压缩或裁剪 canonical events。
- history save integration 不能让 checkpoint 成为 source of truth。
- history candidate 存在不能跳过 projector-owned validation chain。
- `save_checkpoint(...)` latest-only 语义不能被静默改变。
- `InProcessServer.save_checkpoint_for_run(...)` 默认 latest-only 语义不能被静默改变。
- 如果未来同时写 latest 和 history，失败顺序必须显式定义。
- history candidate 写入失败不能伪造 success。
- history candidate 写入成功不能证明 checkpoint 可用于 rebuild；可用性仍由 projector-owned validation chain 判断。
- `FileCheckpointStore` 仍不能解释 checkpoint business state。
- server 不能直接从 history candidate 构造 `RunState`。

## v0 Candidate

当前已实现方向一：新增 projector-owned method。

- `RunProjector.save_checkpoint_history(...)`。
- method 仍从 canonical event log 读取 events。
- method 仍通过 `RunProjector.create_checkpoint(...)` 生成 checkpoint。
- method 再调用 `checkpoint_store.save_checkpoint_history(run_id, checkpoint)`。
- method 不修改 `RunProjector.save_checkpoint(...)` latest-only 语义。

当前已实现方向二：新增 explicit internal-only server trigger。

- `InProcessServer.save_checkpoint_history_for_run(run_id)`。
- internal caller 显式要求 history save。
- 默认仍 latest-only。
- 不能通过 public HTTP / public API 暴露。
- server 不能接收外部 checkpoint state。
- server 只能委托 projector-owned method。
- 返回值只包含 minimal metadata，不包含 checkpoint state。

当前推荐：

- 不改变 `RunProjector.save_checkpoint(...)` 默认语义。
- 不改变 `InProcessServer.save_checkpoint_for_run(...)` 默认语义。
- 后续如果实现，优先新增显式 projector-owned method，而不是偷偷让 latest save 也写 history。

这些名称和返回值都是 v0 candidate / sketch，不是永久 protocol。

## Invalid Uses

以下用法明确无效：

- 让 `RunProjector.save_checkpoint(...)` 静默开始写 history candidates。
- 让 `InProcessServer.save_checkpoint_for_run(...)` 静默开始写 history candidates。
- 让 `InProcessServer.save_checkpoint_history_for_run(...)` 变成 public API。
- 让 public client 上传 checkpoint history candidate。
- 让 public client 选择 checkpoint history entry 作为事实来源。
- server 直接调用 `FileCheckpointStore.save_checkpoint_history(...)` 保存外部 checkpoint state。
- server 根据 history save success 直接返回 projected state。
- history candidate 写入失败后返回 saved。
- history candidate 存在后跳过 event replay validation。
- history candidate 存在后跳过 lifecycle validation。
- history candidate 存在后跳过 checkpoint integrity / event prefix digest / prefix consistency validation。

## Deferred

当前仍 deferred：

- automatic history persistence from `save_checkpoint(...)`。
- public checkpoint API。
- public checkpoint HTTP endpoint。
- checkpoint history index。
- retention policy。
- checkpoint GC。
- `CheckpointService`。
- automatic checkpoint scheduling。
- history save retention / compaction interaction。
- history write atomicity implementation。

## Future TDD Notes

后续如继续实现，应先写 red tests，优先覆盖：

- `RunProjector.save_checkpoint(...)` 仍保持 latest-only。
- `InProcessServer.save_checkpoint_for_run(...)` 仍默认 latest-only。
- `RunProjector.save_checkpoint_history(...)` 继续通过 `create_checkpoint(...)` 生成 checkpoint。
- history save method 继续只调用 `checkpoint_store.save_checkpoint_history(...)`，不修改 event log。
- empty / malformed / lifecycle-invalid event stream fail-fast，不写 history candidate。
- history save failure 不伪造 success。
- `InProcessServer.save_checkpoint_history_for_run(...)` 必须只调用 projector-owned method。
- `InProcessServer.save_checkpoint_history_for_run(...)` 不能返回 checkpoint state。
- public checkpoint API 仍不暴露。

不要在没有新 design patch 和 red tests 前实现 automatic history persistence、history index、retention policy、checkpoint GC、public checkpoint API 或 `CheckpointService`。
