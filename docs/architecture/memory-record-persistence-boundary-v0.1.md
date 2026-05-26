# Memory Record Persistence Boundary v0.1

状态：draft

## 1. Purpose

本文定义 future memory record persistence 的最小边界。

当前 executor memory handler 已能在 authorized `write_memory` 下构造 `MemoryRecord` / record，并把 runtime execution provenance 与 `PolicyDecision.grants` 交给 memory service。当前 memory service 和 memory store 都仍是 not-enabled boundary；本文定义如果后续要持久化 memory record，应由谁负责、如何与 canonical event log 关联、哪些路径仍然不能实现。

本文不实现 memory storage、successful durable memory write、record index、query engine、ranking、controlled expand 或 public memory API。

## 2. Current State

当前状态：

- `MemoryRecord` v0 implementation shape 已存在。
- `MemoryRecord` 当前校验 structured `content`、list `source_refs`、包含 `run_id` / `execution_id` / `action_type` 的 `provenance`、`thread` / `run` / `session` scope，并拒绝 top-level `artifact_content`。
- executor memory handler not-enabled / provenance boundary 已存在。
- `Executor` 支持可选 `memory_service` 注入。
- configured `memory_service` 下，authorized `write_memory` 会进入 memory handler boundary。
- executor 会构造 `MemoryRecord` / record，并把 runtime execution provenance 与 grants 传给 memory service。
- `NotEnabledMemoryService.write_record(...)` 仍拒绝写入。
- `NotEnabledMemoryStore` 已作为 not-enabled persistence boundary 实现。
- `NotEnabledMemoryStore.save_record(...)` 支持 record / execution / grants / event_store 参数，但只做受控拒绝。
- `NotEnabledMemoryStore.list_records(...)` 返回空 list。
- `NotEnabledMemoryStore.record_path(...)` 返回 path-like locator，但不创建文件。
- `NotEnabledMemoryStore.save_record(...)` 会拒绝无 `ActionExecution`、无 `write_memory` grant、malformed record；valid record 也仍拒绝为 not-enabled。
- rejected persistence 不留下 partial record。
- rejected persistence 不 append `action.completed` 或 `memory.record_created`。
- `memory.record_created` canonical event read-model boundary 已实现。
- `RunState.memory_records` 只从 canonical `memory.record_created` event 投影 summary / refs / provenance-level metadata。
- `memory.record_created` 必须绑定 completed `write_memory` execution，且不能包含 full content / artifact content。
- `memory.record_superseded` canonical event read-model boundary 已实现。
- `memory.record_superseded` 只通过追加 canonical event 表达 supersession；旧 record 不被原地覆盖，只增加 supersession metadata 并指向已存在的新 record。
- `memory.record_superseded` 必须绑定 completed `write_memory` execution，且不能包含 full content / artifact content / raw content。
- projector 仍不读取 memory store 来推进 `RunState`。
- memory read-model checkpoint boundary 已实现。
- `RunProjector.create_checkpoint(...)` 会把 `memory_records` read model 写入 checkpoint state。
- `RunProjector.rebuild_with_checkpoint(...)` 可从 checkpoint + suffix events 恢复 `memory_records`。
- checkpoint memory records 只包含 summary / refs / provenance / supersession metadata，不包含 full content / artifact content / raw content。
- checkpoint state schema 会校验 memory record shape 和 supersession metadata。
- checkpoint prefix consistency 已覆盖 `memory_records`。
- checkpoint-assisted rebuild 仍不读取 memory store 或 query service。
- memory v0.1 scope 已按 `memory-v0.1-scope-freeze.md` frozen for demo planning：当前 persistence 线只证明 not-enabled store boundary、canonical event read model 和 checkpoint boundary，不证明 real storage 已可用。
- memory write failure 路径仍是 `action.started -> action.failed`。
- 当前没有 memory storage。
- 当前没有 successful memory record persistence implementation。
- 当前没有 successful durable memory write。
- `NotEnabledMemoryQueryService` 已实现 query-time authorization not-enabled boundary，但不实现 query engine。
- 当前没有 memory query implementation。
- 当前测试基线是 `539 passed`。

## 3. Hard Boundaries

memory store 不是 source of truth。canonical event log 仍是事实来源。

successful memory record persistence 必须可追溯到 authorized `ActionExecution`。memory record 不能绕过 `ActionProposal -> PolicyDecision -> ActionExecution -> canonical event` 链路。

memory record 不能直接修改 `RunState`。projector 不能读取 memory store 来推进 native state，也不能把 persisted memory 当作 canonical event 替代品。

persisted record 必须有 structured content、source refs 和 provenance。memory 不能退化成 transcript dump、raw model context cache 或 artifact content mirror。

artifact content 不应默认内联进 memory record。memory record 可以引用 artifact / event / resource，但完整内容读取必须走 retrieval / controlled expand 边界。

memory persistence failure 不能伪造 success，不能创建 artifact，不能写 `action.completed`，不能写 `memory.record_created`。当前 `NotEnabledMemoryStore` 已锁住这一点：所有 save path 都拒绝，不写文件、不 append event、不留下 partial record。

## 4. Persistence Ownership

persistence 应由 `MemoryService` / future `MemoryStore` 负责。

executor 的职责是：

- 在 `PolicyDecision.grants` 允许时进入 memory handler boundary。
- 构造带 runtime execution provenance 的 record。
- 调用 memory service。
- 让 memory service failure 走 `action.failed`。

executor 不应直接写 file store、index、vector store 或 external memory backend。

server / agent runtime 不能直接写 durable memory，也不能接收 public client 上传的 memory state 后写入 store。

memory service 不能自行批准 action，不能扩大 grants，不能绕过 action chain。memory service 也不能自行 append unrelated canonical events 来修复或补写状态。

## 5. Event / State Relationship

future successful durable write path 应通过 canonical event 进入 read model。当前已实现的 v0 candidate event read-model boundary 是：

- `memory.record_created`
- `memory.record_superseded`

事件名只是 v0 candidate，不是永久协议。

当前 `RunProjector` 已支持并校验 `memory.record_created`：它只投影 record id、execution id、summary、source refs、provenance、basis event、quality 等 metadata，不投影 `content` / `full_content` / `artifact_content` / `raw_content`。当前 `RunProjector` 也已支持并校验 `memory.record_superseded`：它只增加 supersession metadata，保留旧 record 原始 summary / refs / provenance，要求 old/new record 都已存在且 supersession 绑定 completed `write_memory` execution。这个 boundary 只说明 canonical event 可以驱动 read model，不说明 memory store / successful persistence / successful update 已实现。

successful write 应先有 action execution context。最小顺序应保持：

- `action.started`
- memory service successful persistence
- candidate `memory.record_created`
- possible `action.completed`

失败路径仍应保持：

- `action.started`
- `action.failed`

memory record persistence 不允许补写、改写或删除旧 event。它只能在当前 authorized execution 下产生新的 derived record 和对应审计事件。memory update 语义必须通过 append-only supersession event 表达，不能原地覆盖旧 record。

query result 不能直接推进 `RunState`。memory store record presence 也不能让 projector 绕过 canonical event replay；只有 canonical `memory.record_created` / `memory.record_superseded` event 可以更新 `RunState.memory_records` read model。

checkpoint 也只是 canonical event replay 的派生优化。`RunState.memory_records` 可以进入 checkpoint 并通过 checkpoint-assisted rebuild 恢复，但 checkpoint 中只能保存 summary / refs / provenance / supersession metadata，不能保存 full content；如果 checkpoint state 与 event-log prefix projection 不一致，仍以 canonical event log replay 为准。

## 6. Store Shape Candidate

future successful store 可以是 file-backed v0 candidate，但本轮不实现。

candidate storage shape:

- per-scope or per-run directory。
- one record addressable by `memory_id`。
- JSON record blob using deterministic serialization。
- optional small index for lookup by scope / source ref / created_at。

一条 persisted record 至少应包含：

- `memory_id`
- `scope`
- `content`
- `summary`
- `source_refs`
- `provenance`
- `created_at`
- `supersedes`
- `quality`

`scope` 可以是 `thread` / `run` / `session`。字段名仍是 v0 candidate / sketch。

index、ranking、vector search、compaction、retention、GC、migration/versioning 继续 deferred。

## 7. Success / Failure Semantics

只有 success 才能产生 persisted record。

failure 不能留下 partial record。如果 store 写入无法保证原子性，future implementation 必须有明确 cleanup / temp-file / fail-fast 策略。

record persistence failure 不应创建 artifact，不应 append `action.completed`，不应 append `memory.record_created`。

duplicate / overwrite 仍暂不实现；supersession 当前只实现 canonical event read-model boundary，不实现 durable update / storage path。open questions:

- duplicate `memory_id` 是 fail-fast、idempotent success，还是 create new revision。
- future persistence store 的 `supersedes` 字段如何与 canonical `memory.record_superseded` event 对齐。
- overwrite 是否永远禁止。
- partial write cleanup 是否需要 diagnostic event。

## 8. Query Relationship

future memory query 可以读取 persisted records，但 query 是 read-side recall，不是 run loop mandatory stage。

当前 `NotEnabledMemoryQueryService` 只锁 query-time authorization boundary：它校验 explicit `grants` / `caller_context`，`caller_context.run_id` 必须存在且和 query `run_id` 对齐；无 query grant、missing/mismatched caller run、或无 controlled expand grant / budget 时 fail closed，不读取 memory store / full content，并返回低敏 `reason_code` / `content_policy` 供上层解释。它不是 query engine，也不是 controlled expand implementation。

默认 query result 应返回：

- memory refs
- summary / preview
- source refs
- provenance hints

默认不返回 full content，不返回 artifact content。

full content / controlled expand 仍受 grants、retrieval policy、`ResourceRef` authorization 和 budget 控制。

query result 不能变成 `RunState` native fact。若 query result 要影响 state，必须通过后续 action / policy / execution / canonical event。

## 9. Deferred

以下能力继续 deferred：

- memory storage implementation。
- successful durable memory write。
- successful memory update / supersession write implementation。
- successful memory record persistence implementation。
- record indexing。
- vector embeddings。
- ranking / exposure。
- session memory promotion。
- memory compaction。
- memory GC。
- memory migration / versioning。
- controlled expand implementation。
- public memory API。
- public memory HTTP endpoint。
- memory inspection API。
- real LLM recall loop。

## 10. First Red Tests

第一批 persistence boundary tests 已落地并通过，但只覆盖 not-enabled store / rejection boundary，不实现 successful durable storage。

已覆盖：

- `NotEnabledMemoryStore` boundary exists，但 implementation 仍 unavailable / not-enabled。
- direct persistence without `ActionExecution` is rejected。
- direct persistence without `PolicyDecision.grants["tools"]` containing `write_memory` is rejected。
- record missing structured `content` / `source_refs` / execution provenance is rejected。
- persistence failure does not leave partial record。
- persistence failure does not append `action.completed` or `memory.record_created`。
- projector rebuild does not read memory store to advance `RunState`。
- query defaults to refs / summary / preview and does not expose full content by default.

第二批 `memory.record_created` canonical event boundary tests 已落地并通过，但只覆盖 event/read-model boundary，不实现 successful durable storage。

已覆盖：

- `RunState.memory_records` minimal read model exists。
- valid `memory.record_created` projects summary / refs / provenance metadata only。
- `memory.record_created` rejects full content fields。
- `memory.record_created` requires required payload fields and completed `write_memory` execution。
- failed / denied / pending / non-`write_memory` execution is rejected。
- executor + not-enabled memory service still cannot produce successful memory write。
- server still has no public direct memory write API。

第三批 `memory.record_superseded` canonical event boundary tests 已落地并通过，但只覆盖 event/read-model boundary，不实现 successful durable update / storage。

已覆盖：

- valid `memory.record_superseded` marks old record superseded and points to an existing new record。
- old record summary / refs / provenance are not overwritten。
- `memory.record_superseded` requires old / new record ids, execution id, reason, provenance, and basis event。
- missing old / new record, self-supersession, full content fields, and non-completed / non-`write_memory` execution are rejected。

第四批 memory read-model checkpoint boundary tests 已落地并通过，但只覆盖 checkpoint/read-model boundary，不实现 durable memory storage 或 query engine。

已覆盖：

- `RunState.memory_records` can rebuild from event log replay and checkpoint-assisted replay。
- checkpoint state includes `memory_records` read model。
- checkpoint memory records exclude full content / artifact content / raw content。
- checkpoint schema validates memory record shape and supersession metadata。
- checkpoint prefix consistency covers memory read model mismatch。
- projector does not read memory store / query service to fill checkpoint state。
- executor + not-enabled memory service still cannot produce successful memory write or supersession。
- server still has no public direct memory update / supersede API。

下一阶段默认转向 v0.1 demo entrypoint planning。若 memory scope 被明确 reopened，后续 red tests 可考虑：

- memory result cannot bypass artifact / `ResourceRef` authorization。
- external ingestion / `ImportedSnapshot` boundary docs。
- public-open-source cleanup plan。
- 或停在当前稳定点。

successful persistence path remains explicitly deferred until storage design is intentionally reopened.
