# Deferred Boundary Review v0.1

状态：draft

## 1. Purpose

本文用于在 checkpoint v0.1 和 `ActionTypeRegistry` 主线完成后，评审下一阶段 deferred surface 的默认进入顺序。

目标不是实现新能力，而是先决定下一份 design note 和 red tests 应该落在哪条边界上，避免直接跳进 real LLM、real HTTP、plugin system、memory implementation 或 external provider integration。

## 2. Current Completed Surface

当前 kernel slice 已完成：

- action chain：`ActionProposal -> PolicyDecision -> ActionExecution -> canonical events`。
- canonical event log / projector：event log 仍是唯一 source of truth，projector 只从 canonical events rebuild `RunState`。
- checkpoint v0.1：latest/history checkpoint save、assisted rebuild、candidate fallback、integrity/hash、event prefix digest、server read path 和 internal save triggers 已足够支撑当前 kernel slice，并已 frozen。
- `ActionTypeRegistry`：minimal registry module 已实现，并已接入 `ActionCompiler` registry lookup、`PolicyEngine` requirement lookup、`Executor` handler lookup 和 `InProcessServer` shared registry wiring。
- memory v0.1：not-enabled write/query/persistence boundaries、`MemoryRecord` shape、`write_memory` compiler/policy/executor boundary、canonical memory read model、append-only supersession、event-log replay 和 checkpoint-assisted rebuild 已足够支撑 v0.1 demo planning，并已 frozen 到 boundary / read-model / checkpoint 范围。
- v0.1 demo entrypoint 已实现：`python -m isotope_kernel.demo` 输出 plain text summary，`--json` 输出 JSON summary，真实验证 event replay 和 checkpoint-assisted rebuild。
- packaging / install smoke coverage 已落地：当前 `pyproject.toml` metadata、src-layout discovery、editable install、installed import、installed demo plain / JSON 和 repo-root side-effect boundary 已通过测试。
- 当前测试基线：`557 passed`。

当前 hard boundary 仍不变：

- checkpoint 不是第二事实源。
- registry 不能绕过 action chain。
- registry 不能自动 approve action。
- registry 不能扩大 `PolicyDecision.grants`。
- server / storage 不能直接解释 checkpoint state。

## 3. Frozen / Do Not Reopen By Default

默认不要继续打开以下方向：

- checkpoint history index / retention / GC 深挖。
- dynamic plugin system。
- real LLM。
- real HTTP。
- external provider integration。
- memory write implementation。
- memory storage / query engine 深挖。
- public extension API。
- public checkpoint API。
- automatic checkpoint scheduling。

这些方向只有在先落 design/doc patch 和 red tests 后，才可进入实现。

## 4. Candidate A: Memory Write / Query Boundary

Memory Write / Query Boundary 更贴近 kernel 内部能力，已作为上一阶段默认候选完成到 v0.1 frozen 范围。当前不要继续默认推进 storage/query implementation；后续只有在 demo 或 operational need 明确 reopened scope 后再扩展。

优点：

- 能复用现有 action chain、policy grants、executor event ownership 和 canonical event log。
- 能复用 artifact provenance、structured `ResourceRef` 和 retrieval 边界。
- 能先定义 durable memory 与 projected state 的关系，避免后续 memory 变成隐式状态源。
- 能为后续学习型 / 长程任务提供明确的 write/query contract。

风险：

- 如果边界不清，memory 容易退化成 transcript dump。
- 如果 server 或 agent runtime 可直接写 memory，会绕过 action/policy/execution/event。
- 如果 memory 被 projector 当作输入源，可能污染 `RunState` source-of-truth 边界。

必须守住：

- durable memory write 必须走 action / policy / execution / event。
- memory 不能直接修改 `RunState`。
- memory write 必须有 provenance。
- memory query 只能作为 retrieval-like recall，不是 mandatory loop stage。
- memory result 不能绕过 policy grants 或 artifact/resource authorization。
- memory schema 是 v0 candidate，不是永久协议。

## 5. Candidate B: External Ingestion / ImportedSnapshot Boundary

External Ingestion / `ImportedSnapshot` Boundary 是第二优先级候选。

优点：

- 能验证外部观察不能直接推进 state 的 hard contract。
- 能定义 raw external input、artifact、derived observation 和 projector 的边界。
- 能把 provider freshness / source / quality 等信息纳入可审计结构。

风险：

- 比 memory 更容易引入 provider-specific 假设。
- 容易把 external input 当成 canonical event truth。
- 如果 `ImportedSnapshot` 被 projector 当作修正 state 的事实，可能制造第二事实源。

必须守住：

- raw external input 只能先成为 artifact。
- `ImportedSnapshot` 不是第二事实源。
- imported / derived observation 必须带 quality、source、freshness。
- external ingestion 不能直接修正 event log。
- external ingestion 不能跳过 action chain、policy、executor 或 artifact provenance。
- provider-specific parsing 不应进入 kernel core。

## 6. Candidate C: Real LLM / HTTP / Plugin System

Real LLM、real HTTP 和 plugin system 继续 deferred。

原因：

- 当前 kernel 还需要先稳定 memory / ingestion 的 data boundary。
- real provider integration 会引入 auth、timeouts、rate limits、payload drift 和 provider-specific behavior。
- plugin system 会放大 action registry 的 surface，容易过早变成 public extension API。
- HTTP / SSE 会引入 API lifecycle、auth 和 streaming semantics，还不是当前最小 kernel 的瓶颈。

当前不应实现：

- dynamic action registration。
- third-party tools。
- remote tool discovery。
- real LLM tool calling integration。
- public extension API。
- real HTTP checkpoint / memory / ingestion endpoint。

## 7. Recommendation

Memory Write / Query Boundary docs、第一批 memory boundary tests、memory action-chain compiler/policy boundary tests、`MemoryRecord` v0 shape tests、executor memory handler not-enabled / provenance boundary tests、memory record persistence not-enabled boundary tests、memory query authorization boundary tests、`memory.record_created` canonical event boundary tests、`memory.record_superseded` canonical event boundary tests 和 memory read-model checkpoint boundary tests 已落地；当前只 harden not-enabled / rejection boundary、compiler/policy action-chain boundary、MemoryRecord shape validation、executor failure/provenance boundary、unavailable persistence store boundary、query-time authorization boundary、canonical event read-model boundary 与 checkpoint read-model boundary。

推荐顺序：

1. `docs/memory-write-query-boundary-v0.1.md` 已落文档。
2. 第一批 not-enabled / rejection boundary tests 已通过。
3. memory action-chain boundary tests 已通过：compiler 支持 registry-backed `write_memory` payload requirements，policy 可处理 registry-backed `write_memory` proposal。
4. `MemoryRecord` v0 implementation shape 已通过测试：structured `content`、list `source_refs`、required provenance、limited scope、no top-level `artifact_content`。
5. executor memory handler not-enabled / provenance boundary 已通过测试：`Executor` 可选注入 `memory_service`，authorized `write_memory` 会构造 record 并把 runtime execution provenance / grants 传给 memory service；not-enabled rejection 只写 `action.started -> action.failed`，不创建 artifact、不写 `action.completed` / `memory.record_created`。
6. memory record persistence not-enabled boundary 已通过测试：`NotEnabledMemoryStore.save_record(...)` 拒绝 missing execution、missing `write_memory` grant、malformed record 和 valid record；不写文件、不 append success events、不留下 partial record。
7. memory query authorization not-enabled boundary 已通过测试：`NotEnabledMemoryQueryService.query(...)` 校验 explicit grants / caller_context；无 query grant 或无 controlled expand grant / budget 时 fail closed，不读取 memory store / full content。
8. `memory.record_created` canonical event read-model boundary 已通过测试：`RunState.memory_records` 只由 canonical event 投影 summary / refs / provenance metadata，要求 completed `write_memory` execution，拒绝 full content 字段；executor + not-enabled memory service 仍不会产生 successful memory write。
9. `memory.record_superseded` canonical event read-model boundary 已通过测试：memory update 语义是 append-only supersession，不是原地修改；旧 record 只增加 supersession metadata 并指向已存在的新 record，且 event 必须绑定 completed `write_memory` execution；executor + not-enabled memory service 仍不会产生 successful memory update。
10. memory read-model checkpoint boundary 已通过测试：`RunProjector.create_checkpoint(...)` 包含 `memory_records`，`RunProjector.rebuild_with_checkpoint(...)` 可从 checkpoint + suffix events 恢复 `memory_records`，schema / prefix consistency 会拒绝 full content 和 malformed memory read model。
11. memory v0.1 scope 已 frozen for demo planning：当前可展示 boundary / read-model / checkpoint contract，但不展示 durable storage/query product capability。
12. `docs/demo-entrypoint-v0.1.md` 已定义并实现 demo scope：一个本地 module entrypoint 展示 deterministic kernel 闭环，不展示完整产品。
13. 下一步可选择 external ingestion boundary docs、memory result cannot bypass artifact / `ResourceRef` authorization red tests、public-open-source cleanup plan，或停在当前稳定点。
14. 不直接做完整 memory implementation。
15. External Ingestion / `ImportedSnapshot` 排在 demo entrypoint scope 之后。
16. real LLM / HTTP / plugin system 继续 deferred。

理由：

- memory 是 kernel 内部 surface，能直接检验 action chain、policy grants、artifact/resource provenance 和 retrieval 的组合边界。
- memory 的错误实现会快速破坏 source-of-truth 约束，因此应先写清 hard boundary。
- external ingestion 更容易牵涉 provider-specific details，应在 memory boundary 明确后再进入。

## 8. Next TDD Entry Point

demo entrypoint TDD 已完成。下一轮建议选择以下 red tests / docs 之一：

- memory result cannot bypass artifact / ResourceRef authorization。
- external ingestion / `ImportedSnapshot` boundary docs。
- public-open-source cleanup plan。
- 或停在当前稳定点。

不要直接进入 memory storage implementation、memory query engine、controlled expand implementation、real LLM、external ingestion implementation、HTTP、SSE、plugin system 或 dynamic tool loading。
