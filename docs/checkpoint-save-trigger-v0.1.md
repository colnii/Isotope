# Checkpoint Save Trigger v0.1

状态：draft

本文定义 checkpoint save trigger（检查点保存触发器）的 v0.1 边界：未来谁可以触发保存 checkpoint、何时保存、以及哪些能力仍然 deferred。

本轮只定设计，不实现代码。

## Purpose

Checkpoint save trigger 的目标，是给已有 projector-owned checkpoint save boundary 一个受控调用入口，用于维护、测试和 recovery acceleration（恢复加速）。

它不能把 checkpoint 变成第二事实源，也不能让 server 或 public client 直接提交 checkpoint state。

## Current State

当前已实现：

- `RunProjector.save_checkpoint(...)` 已存在。
- `FileCheckpointStore` 已存在。
- `InProcessServer.get_run_state(...)` 已可选使用 checkpoint-assisted rebuild。

当前仍未实现：

- `InProcessServer.create_checkpoint(...)` 仍返回 `{"status": "not_enabled", "capability": "checkpoint"}`。
- 没有 server save trigger。
- 没有 automatic checkpoint scheduling。
- 没有 public checkpoint API。
- 没有 `CheckpointService`。

## Decision

v0.1 decision：

- checkpoint save trigger 只能调用 projector-owned `RunProjector.save_checkpoint(...)`。
- checkpoint save trigger 不能自行生成 projected state。
- checkpoint save trigger 不能接收 public client 提交的 checkpoint state。
- checkpoint save trigger 只能产生 derived checkpoint object，不改变 `RunState` 语义。
- save 失败不能伪造 checkpoint。
- empty / malformed / lifecycle-invalid event stream 必须 fail-fast，不写 checkpoint。
- `create_checkpoint(...)` 仍应保持 `not_enabled`，避免被误读为 public checkpoint API。
- 后续 internal-only trigger 推荐命名为 `save_checkpoint_for_run(...)`。

## Hard Boundaries

- save trigger 不能修改 event log。
- save trigger 不能读取 artifact content 来生成 projected state。
- save trigger 不能读取 executor state 来生成 projected state。
- save trigger 不能读取 server memory 来生成 projected state。
- save trigger 不能绕过 `RunProjector.save_checkpoint(...)`。
- save trigger 不能在 event stream invalid 时写 checkpoint。
- save trigger 不能在 empty event log 上写 checkpoint。
- save trigger 不能把 checkpoint state 暴露给 public client。
- save trigger 不能把 checkpoint hash match 当作事实正确性证明。
- public client 不能直接提交 checkpoint state。

## v0 Candidate

未来 v0 可以考虑：

- 新增 internal-only `save_checkpoint_for_run(run_id)`。
- 该 trigger 只用于维护、测试、recovery acceleration，不是 public API。
- 可以由 `InProcessServer` facade 暴露为内部方法，但不能走 HTTP public endpoint。
- 方法内部只组合：
  - `RunProjector.save_checkpoint(run_id, event_store, checkpoint_store)`
  - optional minimal response shaping
- 返回值可以是 schema sketch，例如：
  - `{ "status": "saved", "run_id": "...", "basis_event_id": "...", "checkpoint_ref": "..." }`
- 字段名仍是 example / schema sketch，不是永久协议。

当前不实现 automatic scheduling；本设计只允许 manual/internal trigger。

## Invalid Uses

以下用法明确无效：

- 复用 public-looking `create_checkpoint(...)` 作为 save trigger。
- 通过 public HTTP endpoint 让 client 保存 checkpoint。
- 让 client 上传 checkpoint state。
- server 自行读取 artifacts / executor state / memory 拼 checkpoint。
- save trigger 在 event log invalid 时写入 checkpoint。
- save trigger 失败后返回伪造的 saved 状态。
- save trigger 修改 event log 来匹配 checkpoint。
- save trigger 修改 checkpoint state 来匹配 event log。

## Deferred

当前仍 deferred：

- internal-only server save trigger implementation。
- automatic checkpoint scheduling。
- checkpoint retention / compaction。
- `CheckpointService`。
- public checkpoint API / HTTP endpoint。
- checkpoint inspection API。
- event prefix digest。
- signature / MAC / key management。
- checkpoint migration / version negotiation。
- `SessionState` checkpoint。

## Future TDD Notes

下一轮建议只实现 internal-only server save trigger：

- 优先新增 `InProcessServer.save_checkpoint_for_run(run_id)`，不要复用 `create_checkpoint(...)`。
- `create_checkpoint(...)` 继续返回 `not_enabled`，除非先有明确 rename/deprecation 设计。
- trigger 必须调用 `RunProjector.save_checkpoint(...)`。
- trigger 不修改 event log。
- trigger 不读取 artifact content、executor state 或 server memory。
- empty event log fail-fast，不写 checkpoint。
- malformed / lifecycle-invalid event stream fail-fast，不写 checkpoint。
- saved checkpoint 可由 `FileCheckpointStore.load_latest_checkpoint(...)` 读回。
- saved checkpoint 可用于 `get_run_state(...)` 的 checkpoint-assisted rebuild。
- public checkpoint API / HTTP endpoint 仍不实现。
