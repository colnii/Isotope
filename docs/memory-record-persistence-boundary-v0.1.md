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
- memory write failure 路径仍是 `action.started -> action.failed`。
- 当前没有 memory storage。
- 当前没有 successful memory record persistence implementation。
- 当前没有 successful durable memory write。
- 当前没有 memory query implementation。
- 当前测试基线是 `466 passed`。

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

future success path 可以考虑 candidate event：

- `memory.record_created`

事件名只是 v0 candidate，不是永久协议。

successful write 应先有 action execution context。最小顺序应保持：

- `action.started`
- memory service successful persistence
- candidate `memory.record_created`
- possible `action.completed`

失败路径仍应保持：

- `action.started`
- `action.failed`

memory record persistence 不允许补写、改写或删除旧 event。它只能在当前 authorized execution 下产生新的 derived record 和对应审计事件。

query result 不能直接推进 `RunState`。memory record presence 也不能让 projector 绕过 canonical event replay。

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

duplicate / overwrite / supersession 暂不实现。open questions:

- duplicate `memory_id` 是 fail-fast、idempotent success，还是 create new revision。
- `supersedes` 是否需要验证 target record exists。
- overwrite 是否永远禁止。
- partial write cleanup 是否需要 diagnostic event。

## 8. Query Relationship

future memory query 可以读取 persisted records，但 query 是 read-side recall，不是 run loop mandatory stage。

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

下一批 red tests 可考虑：

- memory query authorization / controlled expand。
- memory result cannot bypass artifact / `ResourceRef` authorization。
- external ingestion / `ImportedSnapshot` boundary docs。
- public-open-source cleanup plan。
- 或停在当前稳定点。

successful persistence path remains explicitly deferred until storage design is intentionally reopened.
