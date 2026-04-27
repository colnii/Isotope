# Checkpoint Ownership v0.1

状态：draft

本文定义 checkpoint ownership（检查点归属）和边界。当前实现只覆盖 opaque checkpoint storage、最小 checkpoint-assisted projector rebuild、projector-owned checkpoint creation、checkpoint state schema validation、projector-owned checkpoint save boundary 和 checkpoint prefix consistency hardening；checkpoint schema 仍是 v0 candidate。

## Purpose

Checkpoint 的目的，是在不改变事实来源的前提下，加速 replay / recovery / inspection。

本设计要防止一个长期风险：checkpoint 被误用成第二事实源，绕过 canonical event log、event validation 或 projector validation。

## Decision

v0.1 决定：

- canonical event log 仍然是唯一 source of truth。
- checkpoint 只是 derived object（派生对象），只能从 canonical events 和 projector 输出得到。
- checkpoint 可以丢弃、重建、迁移；checkpoint 丢失不能影响事实正确性。
- v0.1 采用 `Projector-owned checkpoint`。
- Projector 负责产出 checkpoint。
- `FileCheckpointStore` 或后续 storage layer 只负责保存/读取 checkpoint blob。
- checkpoint storage 不解释 checkpoint 语义。
- v0.1 暂不新增独立 Checkpoint Service。
- checkpoint schema 是 v0 candidate，不是永久协议。

## Hard Boundaries

- checkpoint 不能取代 canonical event log。
- checkpoint 不能修正 event log。
- checkpoint 不能让 projector 跳过 canonical event validation。
- checkpoint 不能包含 external raw input。
- checkpoint 不参与 external ingestion。
- checkpoint 不接收 `ImportedSnapshot`。
- checkpoint 不能改变 `RunState` / `SessionState` 的事实来源边界。
- 如果 checkpoint 与 event log 冲突，以 event log replay 为准。

## v0.1 Ownership Model

v0.1 ownership 分工：

- `RunProjector`：解释 canonical events，产出 projected state，执行 checkpoint-assisted rebuild，并负责生成 projector-owned checkpoint blob。
- `FileCheckpointStore` / future storage layer：只保存和读取 opaque checkpoint blob，不解释 checkpoint 字段含义。
- `InProcessServer` / future server API：当前未接入 checkpoint；未来可以请求 projector rebuild 或 server-facing checkpoint-assisted rebuild，但不能直接把 checkpoint 当成 state source。
- future checkpoint storage：只是一种 storage concern，不是新的 truth layer。

不新增独立 `CheckpointService`，除非后续 TDD 证明 projector/storage 边界无法承载最小实现。

## Checkpoint Contents

v0.1 checkpoint 至少应绑定：

- `run_id`
- `projector_version`
- `basis_event_id` 或等价的 last applied event cursor
- projected state snapshot
- `created_at`

这些字段是当前推荐 shape，用于 future TDD 的测试方向，不是永久协议。

checkpoint 不应包含：

- external raw input
- provider raw response
- tool raw stderr/stdout 全量内容
- 未经 event log 或 artifact/provenance 边界管理的大内容
- 用于修正 event log 的 patch

## Recovery Flow

checkpoint-assisted rebuild 的 v0.1 流程应是：

1. 读取 checkpoint。
2. 校验 checkpoint 的 `run_id`、`projector_version` 和 basis cursor。
3. 如果 checkpoint version 不兼容，丢弃 checkpoint，从 canonical event log 重新投影。
4. 如果 checkpoint 可用，从 checkpoint 的 basis cursor 之后继续 replay canonical event log。
5. replay 过程中仍执行 canonical event validation 和 projector lifecycle validation。
6. 输出 materialized `RunState` / `SessionState`。

checkpoint 只缩短 replay 距离，不改变 replay 语义。

## Invalid Uses

以下用法明确无效：

- 直接从 checkpoint 写回或覆盖 event log。
- 用 checkpoint 接收 external ingestion 或 `ImportedSnapshot`。
- 在 event log 缺失时，用 checkpoint 假装事实完整。
- 因 checkpoint 存在而跳过 malformed event log fail-fast。
- 在 checkpoint version 不兼容时继续恢复。
- 让 EventStore 根据 checkpoint 内容决定业务状态。
- 把 checkpoint schema 当成长期 protocol 扩散到外部 API。

## Deferred

当前仍不实现：

- automatic checkpoint scheduling
- checkpoint compaction
- checkpoint migration
- checkpoint version negotiation
- checkpoint integrity hash
- partial checkpoint
- SessionState checkpoint
- server API / HTTP exposure
- external ingestion integration

## Implementation Notes For Future TDD

已覆盖的最小行为：

- checkpoint 丢失时仍可从 event log 完整 rebuild。
- checkpoint version 不兼容时被丢弃，并从 event log 重新投影。
- checkpoint basis cursor 之后的 events 会继续 replay。
- malformed event log 不会因为 checkpoint 存在而被静默跳过。
- `FileCheckpointStore` 只存取 checkpoint blob，不解释 projector state。
- checkpoint 不包含 external raw input。
- `RunProjector.create_checkpoint(...)` 只通过 canonical events 和 `project(...)` 生成 checkpoint。
- checkpoint creation 不写 checkpoint store。
- checkpoint creation 拒绝 empty events、malformed events 和 lifecycle-invalid events。
- 创建出的 checkpoint 可由 `FileCheckpointStore` 保存，并可用于 `rebuild_with_checkpoint(...)`。
- `RunProjector.rebuild_with_checkpoint(...)` 只在 checkpoint projector version 兼容时校验 checkpoint state schema。
- checkpoint version 不兼容时仍 fallback full rebuild，不因 malformed checkpoint state 失败。
- checkpoint state 必须是 dict，并包含 `run_id`、`status`、`current_agent`、`actions`、`artifacts`、`last_event_id`。
- checkpoint state 的 `run_id`、`last_event_id`、run status、actions/artifacts shape 会在 projector 使用前校验。
- checkpoint artifact entry 不得包含 `content`，且必须包含 `ref`、`artifact_type`、`summary`、`provenance`。
- malformed checkpoint state fail-fast，抛受控 `ValueError`。
- `RunProjector.save_checkpoint(...)` 只组合 `event_store.list_events(run_id)`、`create_checkpoint(...)` 和 `checkpoint_store.save_checkpoint(run_id, checkpoint)`。
- save checkpoint 读取 canonical events，生成 projector-owned checkpoint，并交给 checkpoint store 保存。
- save checkpoint 不修改 event log，不读取 artifact store / executor state / server memory。
- empty event log 或 invalid event stream 会 fail-fast，且不写 checkpoint。
- 保存后的 checkpoint 可读回，并可用于 `rebuild_with_checkpoint(...)`，结果与 full rebuild 等价。
- `RunProjector.rebuild_with_checkpoint(...)` 会比较 checkpoint state 与 `basis_event_id` 对应的 event-log prefix projection。
- 只有 checkpoint state 与 prefix projection 一致时，才从 checkpoint 继续 replay basis 之后的 events。
- checkpoint state 的 `status` / `current_agent` / `actions` / `artifacts` 不一致时，fallback full rebuild。
- checkpoint state 多出不存在的 action 或少了已有 artifact 时，fallback full rebuild。
- fallback full rebuild 仍执行完整 event validation，lifecycle-invalid event log 不能被 checkpoint mismatch 隐藏。
- `FileCheckpointStore` 保持 opaque，不负责 consistency check。
- checkpoint schema 仍被标记为 v0 candidate。

后续实现必须先写 red tests，优先覆盖：

- checkpoint integrity/hash design note。
- server-facing checkpoint boundary design note。
- server API 如需使用 checkpoint，只能调用 projector rebuild boundary，不能直接读取 checkpoint 当作 state source。
