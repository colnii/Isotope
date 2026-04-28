# Server Checkpoint Boundary v0.1

状态：draft

本文定义 `InProcessServer` / Server API 如何使用 checkpoint（检查点），同时保持 canonical event log（规范事件日志）仍是唯一 source of truth。

## Purpose

Server-facing checkpoint boundary 的目的，是允许 server read path 使用 checkpoint 加速 `RunState` rebuild，但不让 server 把 checkpoint 当成事实来源、状态修复工具或外部协议承诺。

本文收口 server-facing checkpoint 边界；当前 in-process read path 和 internal-only save trigger 已有最小实现，public API / scheduling / retention implementation 仍 deferred。

## Current State

当前已实现：

- checkpoint storage boundary：`FileCheckpointStore` 保存 / 读取 run-scoped opaque checkpoint blob。
- projector-owned checkpoint creation：`RunProjector.create_checkpoint(...)` 从 canonical events 生成 checkpoint。
- projector-owned checkpoint save boundary：`RunProjector.save_checkpoint(...)` 从 event store 读取 events、生成 checkpoint、交给 checkpoint store 保存。
- checkpoint-assisted rebuild：`RunProjector.rebuild_with_checkpoint(...)` 可从 checkpoint basis state 继续 replay canonical events。
- checkpoint state schema validation。
- checkpoint prefix consistency validation。
- checkpoint integrity/hash validation。
- event prefix digest validation。
- checkpoint candidate loading。
- minimal projector-owned old-checkpoint fallback path。
- checkpoint save trigger boundary design note。
- checkpoint retention / compaction boundary design note。
- checkpoint history / old-checkpoint fallback boundary。
- checkpoint history index / retention policy boundary design note。
- checkpoint history save boundary design note。

相关 retention / compaction 边界见 `docs/checkpoint-retention-compaction-v0.1.md`。
checkpoint history / old-checkpoint fallback 边界见 `docs/checkpoint-history-fallback-v0.1.md`。
checkpoint history index / retention policy 边界见 `docs/checkpoint-history-index-retention-v0.1.md`。
checkpoint history save 边界见 `docs/checkpoint-history-save-boundary-v0.1.md`。

当前 server read path：

- `InProcessServer` constructor 支持 optional `checkpoint_store`。
- `get_run_state` 没有 `checkpoint_store` 时仍由 projector 从 event log full rebuild。
- `get_run_state` 有 `checkpoint_store` 时调用 projector-owned `RunProjector.rebuild_with_checkpoint(...)`。
- Server read model 仍来自 projector，不直接读取或解释 checkpoint state。
- `get_run_state` 不创建 checkpoint，不写 checkpoint store。
- `create_checkpoint(...)` 仍返回 `not_enabled`。
- `save_checkpoint_for_run(...)` 已作为 internal-only manual save trigger 实现。
- `save_checkpoint_for_run(...)` 只调用 projector-owned `RunProjector.save_checkpoint(...)`，不读取或解释 checkpoint state。
- checkpoint missing 或所有 candidates invalid 时 fallback full rebuild。
- projector-owned read path 可在 invalid latest checkpoint 后尝试 older fully valid checkpoint candidate。
- server 不直接选择、解释或信任 old checkpoint，仍只调用 projector-owned boundary。
- lifecycle-invalid event log 仍 fail-fast，不能被 checkpoint fallback 掩盖。

当前仍未实现：

- 没有 public checkpoint API。
- 没有 automatic checkpoint scheduling。
- 没有 `CheckpointService`。
- 没有 broader checkpoint retention / compaction implementation。
- 没有 checkpoint history index。
- 没有 checkpoint history persistence from `save_checkpoint(...)`。
- 没有 checkpoint history save method。
- 没有 checkpoint GC / retention policy。

## Decision

v0.1 decision：

- Server 不能把 checkpoint 当作 source of truth。
- Server 不能直接解释 checkpoint `state`。
- Server read path 使用 checkpoint 时，只能调用 projector-owned boundary，例如 `RunProjector.rebuild_with_checkpoint(...)`，或未来受控 wrapper。
- checkpoint missing / invalid / mismatch / incompatible 时，server-facing read 必须通过 projector-owned boundary 尝试可用 candidate，或 fallback 到 canonical event log rebuild。
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
- Server 不能因为 checkpoint retention / compaction 存在而删除、重写、压缩或裁剪 canonical event log。
- Server 不能直接选择、解释或信任 old checkpoint。
- Server 如需使用 old-checkpoint fallback，仍只能调用 projector-owned boundary。
- Server 不能直接解释 history index 或 checkpoint state 来生成 `RunState`。
- Server 不能直接解释 history candidate 或 history save result 来生成 `RunState`。
- Server 不能让 checkpoint mismatch 阻止 full event log rebuild。
- Server 不能让 corrupt / missing history index 阻止 full event log rebuild。
- Server 不能把 checkpoint schema 当作 public API protocol。

## v0 Candidate

当前 v0 implementation choice：

- `InProcessServer.get_run_state(run_id)` 使用 checkpoint-assisted rebuild。
- 该 read path 等价于 full event log rebuild；checkpoint 只影响性能，不影响结果。
- Server constructor 接收 optional `checkpoint_store`；没有 checkpoint store 时保持现有 full rebuild 行为。
- checkpoint missing 或所有 candidates invalid 时 fallback full rebuild。
- projector-owned `rebuild_with_checkpoint(...)` 可使用 candidate chain；如果 invalid latest checkpoint 后存在 older fully valid candidate，可以从该 candidate 继续 replay suffix events。
- 所有 candidates invalid 时 fallback full rebuild。
- event log 本身 malformed / lifecycle-invalid 时必须 fail fast。

当前 v0 implementation choice 还包括：

- 提供 internal-only checkpoint save trigger：`save_checkpoint_for_run(run_id)`。
- internal save trigger 只能调用 `RunProjector.save_checkpoint(...)`。
- 不复用 public-looking `create_checkpoint(...)`；它当前仍应保持 `not_enabled`。

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
- signature / MAC / key management。
- broader checkpoint retention / compaction implementation。
- checkpoint history index。
- checkpoint history persistence from `save_checkpoint(...)`。
- checkpoint history save method。
- checkpoint GC / retention policy。
- checkpoint migration / version negotiation。
- `SessionState` checkpoint。
- multi-run checkpoint coordination。
- public checkpoint inspection API。

## Future TDD Notes

下一轮建议先做一个最小 TDD slice：

已覆盖的最小测试：

- `InProcessServer(root)` 默认仍使用 full event log rebuild。
- `InProcessServer(root, checkpoint_store=...)` 的 `get_run_state(...)` 通过 projector-owned checkpoint-assisted rebuild，结果等价于 full rebuild。
- server 不返回被污染的 checkpoint state。
- `get_run_state(...)` 不创建 checkpoint。
- lifecycle-invalid event log 不能被 checkpoint fallback 隐藏。
- `create_checkpoint(...)` 仍返回 `not_enabled`。

后续如继续扩展，应先写 red tests，优先覆盖：

- internal-only checkpoint save trigger 已实现，后续扩展仍需 red tests。
- checkpoint save trigger 只能调用 `RunProjector.save_checkpoint(...)`。
- trigger 不读取 artifact content、executor state 或 server memory。
- empty / malformed / lifecycle-invalid event stream fail-fast，不写 checkpoint。
- public API 仍不得暴露 checkpoint state。
- checkpoint retention / compaction 如接入 server-facing flow，不能让 server 直接解释 checkpoint state，也不能影响 event log。
- checkpoint history index / retention 如接入 server-facing flow，server 仍不能直接选择或解释 checkpoint，只能调用 projector-owned boundary。
- checkpoint history save 如接入 server-facing flow，server 仍不能接收或解释 checkpoint state，只能调用 projector-owned save boundary。
- corrupt / missing history index 如出现在 server-facing read path，不能让 server 跳过 full event-log replay。

暂不实现 public checkpoint API、automatic scheduling、`CheckpointService`、broader checkpoint retention / compaction implementation、checkpoint history index、checkpoint history persistence from `save_checkpoint(...)`、checkpoint history save method、signature / MAC / key management。
