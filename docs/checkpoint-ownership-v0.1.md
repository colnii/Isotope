# Checkpoint Ownership v0.1

状态：draft

本文只定义 checkpoint ownership（检查点归属）和边界，不定义最终 checkpoint schema，也不授权直接实现 checkpoint。

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
- EventStore 或后续 storage layer 只负责保存/读取 checkpoint blob。
- EventStore 不解释 checkpoint 语义。
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

- `RunProjector`：解释 canonical events，产出 projected state，并在未来负责生成 checkpoint。
- `FileEventStore` / future storage layer：只保存和读取 opaque checkpoint blob，不解释 checkpoint 字段含义。
- `InProcessServer` / future server API：可以请求 projector rebuild 或未来 checkpoint-assisted rebuild，但不能直接把 checkpoint 当成 state source。
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

checkpoint-assisted recovery 的 v0.1 流程应是：

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

本轮不实现：

- checkpoint write/read API
- checkpoint storage format
- checkpoint compaction
- checkpoint migration
- checkpoint version negotiation
- checkpoint integrity hash
- partial checkpoint
- SessionState checkpoint
- server API / HTTP exposure
- external ingestion integration

## Implementation Notes For Future TDD

后续实现必须先写 red tests，至少覆盖：

- checkpoint 丢失时仍可从 event log 完整 rebuild。
- checkpoint version 不兼容时被丢弃，并从 event log 重新投影。
- checkpoint basis cursor 之后的 events 会继续 replay。
- malformed event log 不会因为 checkpoint 存在而被静默跳过。
- EventStore 只存取 checkpoint blob，不解释 projector state。
- checkpoint 不包含 external raw input。
- checkpoint schema 仍被标记为 v0 candidate。
