# Server Checkpoint Boundary v0.1

状态：draft

本文定义未来 `InProcessServer` / Server API 如何使用 checkpoint（检查点），同时保持 canonical event log（规范事件日志）仍是唯一 source of truth。

## Purpose

Server-facing checkpoint boundary 的目的，是允许 server read path 在未来使用 checkpoint 加速 `RunState` rebuild，但不让 server 把 checkpoint 当成事实来源、状态修复工具或外部协议承诺。

本设计只收口边界，不实现代码。

## Current State

当前已实现：

- checkpoint storage boundary：`FileCheckpointStore` 保存 / 读取 run-scoped opaque checkpoint blob。
- projector-owned checkpoint creation：`RunProjector.create_checkpoint(...)` 从 canonical events 生成 checkpoint。
- projector-owned checkpoint save boundary：`RunProjector.save_checkpoint(...)` 从 event store 读取 events、生成 checkpoint、交给 checkpoint store 保存。
- checkpoint-assisted rebuild：`RunProjector.rebuild_with_checkpoint(...)` 可从 checkpoint basis state 继续 replay canonical events。
- checkpoint state schema validation。
- checkpoint prefix consistency validation。
- checkpoint integrity/hash validation。

当前未实现：

- `InProcessServer` 尚未接入 checkpoint。
- `get_run_state` 当前仍由 projector 从 event log rebuild。
- Server read model 仍来自 projector，不直接读取 checkpoint state。
- 没有 public checkpoint API。
- 没有 automatic checkpoint scheduling。
- 没有 `CheckpointService`。

## Decision

v0.1 decision：

- Server 不能把 checkpoint 当作 source of truth。
- Server 不能直接解释 checkpoint `state`。
- Server read path 如需使用 checkpoint，只能调用 projector-owned boundary，例如 `RunProjector.rebuild_with_checkpoint(...)`，或未来受控 wrapper。
- checkpoint missing / invalid / mismatch / incompatible 时，server-facing read 必须 fallback 到 canonical event log rebuild。
- checkpoint 只能加速 read/rebuild，不能改变 read 语义。
- 暂不暴露 public checkpoint endpoint。
- 暂不实现 automatic checkpoint scheduling。
- 暂不新增 `CheckpointService`，除非后续 TDD 证明 server / projector / storage 边界无法承载。

## Hard Boundaries

- Server 不能因为 checkpoint 存在而跳过 event log validation。
- Server 不能因为 checkpoint 存在而跳过 lifecycle validation。
- Server 不能因为 checkpoint 存在而跳过 checkpoint state schema validation。
- Server 不能因为 checkpoint 存在而跳过 prefix consistency validation。
- Server 不能直接读取 checkpoint `state` 并返回为 `RunState`。
- Server 不能修改 event log 来匹配 checkpoint。
- Server 不能修改 checkpoint state 来匹配 event log。
- Server 不能修改 projected state 来“修复”状态。
- Server 不能根据 checkpoint integrity/hash 判断业务状态正确。
- Server 不能让 checkpoint mismatch 阻止 full event log rebuild。
- Server 不能把 checkpoint schema 当作 public API protocol。

## v0 Candidate

未来 v0 可以考虑：

- `InProcessServer.get_run_state(run_id)` 使用 checkpoint-assisted rebuild。
- 该 read path 等价于 full event log rebuild；checkpoint 只影响性能，不影响结果。
- 提供 internal-only checkpoint save trigger，例如 `save_checkpoint_for_run(run_id)`。
- internal save trigger 只能调用 `RunProjector.save_checkpoint(...)`。
- Server constructor 可以接收 optional `checkpoint_store`，但没有 checkpoint store 时必须保持现有 full rebuild 行为。
- 如果 checkpoint-assisted rebuild 失败是 checkpoint 不可用类问题，可以回落 full rebuild；如果 event log 本身 malformed / lifecycle-invalid，必须 fail fast。

这些是 v0 candidate，不是永久协议。

## Invalid Uses

以下用法明确无效：

- Server 直接 `load_latest_checkpoint(...)` 后把 `checkpoint["state"]` 当作 `RunState` 返回。
- Server 发现 checkpoint missing 后创建空 completed state。
- Server 发现 checkpoint mismatch 后修改 checkpoint。
- Server 发现 event log invalid 后用 checkpoint 覆盖 event log。
- Server 将 checkpoint save / load 暴露为 public HTTP API。
- Server 将 checkpoint hash match 当作状态可信证明。
- Server 将 checkpoint schema 泄漏给外部 client 作为稳定契约。

## Deferred

当前仍 deferred：

- real HTTP checkpoint endpoint。
- SSE integration。
- automatic checkpoint scheduling。
- `CheckpointService`。
- event prefix digest。
- signature / MAC / key management。
- checkpoint migration / version negotiation。
- `SessionState` checkpoint。
- multi-run checkpoint coordination。
- public checkpoint inspection API。

## Future TDD Notes

下一轮建议先做一个最小 TDD slice：

- `InProcessServer.get_run_state(...)` 可选择 checkpoint-assisted rebuild。
- 无 checkpoint 时，结果等价于 full rebuild。
- checkpoint 可用时，结果等价于 full rebuild。
- checkpoint mismatch / invalid / incompatible 时，fallback full rebuild。
- lifecycle-invalid event log 不能被 checkpoint fallback 隐藏。
- server 不直接解释 checkpoint state。
- server 不修改 event log。
- server 不写 checkpoint，除非调用 future internal-only save boundary。
- `FileCheckpointStore` 仍保持 opaque。

暂不实现 public checkpoint API、automatic scheduling、`CheckpointService`、event prefix digest、signature / MAC / key management。
