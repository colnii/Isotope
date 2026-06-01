# Memory Write / Query Boundary v0.1

状态：draft

## 1. Purpose

本文定义 Isotope v0.1 memory write / query 的最小边界，为后续 red tests 做准备。

目标不是实现 memory storage、durable memory write 或 memory query，而是先明确 memory 如何进入 action chain、如何被查询、如何保持 provenance，以及哪些路径仍然 deferred。

## 2. Current State

当前实现状态：

- `MemoryService` 仍是 not-enabled boundary。
- `NotEnabledMemoryService.write_record(...)` 已存在，但 direct durable write without authorized execution 会受控拒绝。
- `NotEnabledMemoryService.query(...)` 保持 legacy 调用兼容：`query("run_001", "anything")` 仍返回 `{"status": "not_enabled", "capability": "memory_query"}`。
- `NotEnabledMemoryService.query(...)` 已支持 caller_context / grants shape，但仍只返回受控 not-enabled boundary，不实现真实 query。
- `NotEnabledMemoryQueryService` 已作为 query-time authorization not-enabled boundary 实现。
- `NotEnabledMemoryQueryService.query(...)` 会显式校验 `grants` 和 `caller_context`。
- missing / malformed `grants` 或 `caller_context` 会受控 `ValueError` fail closed。
- `caller_context.run_id` 缺失或与 query `run_id` 不一致时，会在读取 memory store
  前返回 `reason_code: caller_context_run_mismatch`。
- `caller_context.caller` / `caller_context.purpose` 缺失、空白或不是字符串时，会在读取
  memory store 前返回 `reason_code: invalid_caller_context`。
- 无 memory query grant 时，不读取 memory store。
- `controlled_expand=True` 但没有 expand grant / positive integer budget 时，受控拒绝且不读取 full content。
- `controlled_expand=True` 且 budget 字段存在但不是正整数时，会在读取 memory store 前返回
  `reason_code: invalid_controlled_expand_budget`。
- `controlled_expand=True` 且授权/budget 有效时，当前仍只返回 summary / refs / provenance preview，
  并附带 `controlled_expand.status: deferred` metadata；不读取 full content。
- `NotEnabledMemoryQueryService` 在 valid controlled expand 请求下也会返回同样的 deferred metadata，
  同时保持 `reason_code: memory_query_not_enabled`。
- agent-loop `query_memory` 可透传 controlled expand 请求并在 action result 中显示 deferred metadata。
- Supervisor memory plain renderer 会显示已有 `controlled_expand.status` / budget / content policy metadata，
  但不会自己开启 full-content expand。
- memory query denial / not-enabled result 现在包含低敏 `reason_code` 和
  `content_policy`，便于 CLI / future API 解释拒绝原因而不暴露 raw content。
- query result 默认不返回 full content、artifact content、raw content 或 full text。
- `NotEnabledMemoryQueryService` 不是 query engine；controlled expand 仍未实现。
- query 默认不返回 full content / artifact content。
- memory action-chain boundary tests 已落地并通过。
- `ActionCompiler` 已支持 registry-backed non-`call_tool` action type，只要 `intent.action` 与 registry entry `action_type` 匹配。
- `ActionCompiler` 会检查 registry `payload_requirements.required`。
- valid `write_memory` intent 会保留 structured payload：`content`、`summary`、`source_refs`、`provenance`。
- `PolicyEngine` 不再硬编码只接受 `call_tool`；registry-backed `write_memory` proposal 可以进入 policy decision。
- `MemoryRecord` v0 implementation shape 已新增并通过测试；它只是 slice-only implementation shape，不是最终 protocol。
- `MemoryRecord` 当前校验 structured dict `content`、list `source_refs`、包含 `run_id` / `execution_id` / `action_type` 的 `provenance`、`thread` / `run` / `session` scope，并拒绝 top-level `artifact_content`。
- executor memory handler not-enabled / provenance boundary 已落地并通过测试。
- `Executor` 现在支持可选 `memory_service` 注入。
- 如果传入 `memory_service`，authorized `write_memory` 会进入 memory handler boundary。
- executor 会从 structured payload 构造 `MemoryRecord` / record，并把 runtime execution provenance 和 `PolicyDecision.grants` 传给 memory service。
- 当前 `NotEnabledMemoryService.write_record(...)` 仍会受控拒绝，因此 memory write failure 路径是 `action.started -> action.failed`。
- memory write failure 不创建 artifact、不写 `action.completed`、不写 `memory.record_created`。
- grants 缺少 `write_memory` 时，executor 不调用 memory service。
- 没有传 `memory_service` 时，`write_memory` 仍是 unsupported handler。
- memory record persistence not-enabled boundary 已落地并通过测试。
- `NotEnabledMemoryStore` 支持 `save_record(...)`、`list_records(...)`、`record_path(...)`，但 `save_record(...)` 只做受控拒绝。
- `NotEnabledMemoryStore.save_record(...)` 会拒绝无 `ActionExecution`、无 `write_memory` grant、malformed record；valid record 也仍拒绝为 not-enabled。
- rejected persistence 不留下 partial record，不 append `action.completed` / `memory.record_created`。
- `memory.record_created` canonical event read-model boundary 已落地并通过测试。
- `RunState.memory_records` 已作为最小 read model 实现。
- `RunProjector` 已支持并校验 `memory.record_created`。
- `memory.record_created` 只投影 summary / refs / provenance-level metadata，不投影 full content。
- `memory.record_created` payload 拒绝 `content` / `full_content` / `artifact_content` / `raw_content`。
- `memory.record_created` 必须绑定 completed `write_memory` execution；failed / denied / pending / non-`write_memory` execution 都会被拒绝。
- `memory.record_superseded` canonical event read-model boundary 已落地并通过测试。
- `RunProjector` 已支持并校验 `memory.record_superseded`。
- supersession 只通过追加 canonical event 表达；旧 memory record 不被原地覆盖，只增加 supersession metadata 并指向已存在的新 record。
- `memory.record_superseded` payload 拒绝 full content / artifact content / raw content，并要求绑定 completed `write_memory` execution。
- failed / denied / pending / non-`write_memory` execution 不能 supersede memory record。
- 这是 canonical event projection boundary，不是 durable memory storage 或 successful memory update implementation。
- memory read-model checkpoint boundary 已落地并通过测试。
- `RunProjector.create_checkpoint(...)` 会把 `memory_records` read model 写入 checkpoint state。
- `RunProjector.rebuild_with_checkpoint(...)` 可从 checkpoint + suffix events 恢复 `memory_records`。
- checkpoint memory records 只包含 summary / refs / provenance / supersession metadata。
- checkpoint memory records 拒绝 `content` / `full_content` / `artifact_content` / `raw_content`。
- checkpoint state schema 会校验 memory record shape 与 supersession metadata。
- checkpoint prefix consistency 已覆盖 `memory_records`。
- event-log replay 与 checkpoint-assisted replay 都不读取 memory store 或 query service。
- memory v0.1 scope 已按 `memory-v0.1-scope-freeze.md` frozen for demo planning：当前可展示 boundary / read-model / checkpoint contract，不应展示为 completed durable memory storage 或 query engine。
- projector 仍不读取 memory store 推进 `RunState`。
- projector 仍不读取 memory query service 推进 `RunState`。
- server 仍没有 public direct memory write / update 或 `query_memory(...)` API。
- 当前没有 durable memory write implementation。
- 当前已有本地 `FileMemoryStore` 和 agent-loop record/query first slice；它仍不是
  public memory API 或完整 product memory。
- 当前没有 successful memory record persistence implementation。
- 当前已有本地低敏 query read model：`memory/views.py` 和 Supervisor
  `memory --query` 返回 summary / refs / provenance preview，不返回 full content。
- 当前没有 vector index、ranking 或 controlled expand implementation。
- 当前测试基线是 `539 passed`。

当前已有相关基础：

- action chain：`ActionProposal -> PolicyDecision -> ActionExecution -> canonical event`。
- `PolicyDecision.grants` enforcement。
- artifact provenance。
- structured `ResourceRef`。
- retrieval summary-only authorization boundary。
- `ActionTypeRegistry` 已接入 compiler / policy / executor / server。
- projector 仍只从 canonical event log rebuild `RunState`。

## 3. Hard Boundaries

memory 不是 transcript dump。

MemoryRecord 必须有 structured content 和 provenance。memory 不能只是未经结构化的聊天记录、日志片段或模型上下文缓存。

durable memory write 必须走 canonical action chain：

- `ActionProposal`
- `PolicyDecision`
- `ActionExecution`
- canonical event

memory 不能直接修改 `RunState`。projector 不能直接读取 memory store 来推进 native state。

memory 不能成为 canonical event log 之外的 source of truth。canonical event log 仍是事实来源；memory 是由授权 execution 产生的可检索 derived / durable record。

memory query 是 retrieval-like recall，不是 run loop mandatory stage。run loop 不能假设每次都必须查询 memory。

memory query / controlled expand 不能绕过 retrieval policy、`ResourceRef` authorization 或 grants。

memory 默认不内联大块 artifact content。完整内容读取必须通过明确授权的 controlled expand / retrieval path。

server / agent runtime 不能直接写 durable memory，也不能用 memory query 结果绕过 policy 或 event log。

### 3.1 Capability Invocation Boundary

memory query / retrieval 是 capability，但 capability 的调用方不一定是模型本身。这里要区分两个入口：

- **runtime-invoked capability**：由 app shell / agent runtime 在构造上下文、控制 token budget、处理上下文不足或准备代码修改前自动触发。RAG / retrieval 更常见地属于这个入口：runtime 先检索相关 refs / summaries / previews，再把被授权的结果放入模型可见上下文。
- **model-invoked tool capability**：由模型在推理过程中显式选择调用，例如未来的 `search_code`、`read_file`、`run_tests` 或其他 tool。

两种入口都必须遵守同一组 kernel 边界：不能绕过 `ResourceRef`、grants、retrieval policy、canonical event log 或 artifact full-content 读取规则。区别只在“谁决定触发”：前者是 runtime / app shell 的上下文编排决策，后者是模型可见的 tool-use 决策。

因此，RAG / retrieval 不应被理解为“必须暴露给模型主动调用的 tool”。在代码修改类 app 中，它可以是自动备课式的 runtime capability：先找相关文件、定义、调用点和测试，再把受控上下文交给模型；模型随后再决定是否使用显式 tool 执行读取、修改或验证。

## 4. Memory Write Boundary

第一阶段只实现 action-chain、canonical event read-model、checkpoint read-model 和 not-enabled handler boundary，不实现 storage、successful durable write path 或 query engine。

`write_memory` action type 当前已可作为 registry-backed v0 candidate 进入 compiler / policy boundary，但名字仍是 v0 candidate，不是永久协议。

durable memory write 必须由 authorized execution 触发：

- compiler 只能生成 requested capabilities。
- compiler 必须按 registry `payload_requirements.required` 校验 payload；`write_memory` 不能只是 raw text。
- valid memory intent 必须保留 structured `content`、`source_refs`、`provenance`，可携带 `summary`。
- policy 决定是否授予 memory write grants。
- executor / memory service 只能基于 `PolicyDecision.grants` 写。
- successful memory write / update 未来必须 append canonical event，不能作为 side-channel state mutation。当前 projector 已支持 `memory.record_created` 与 `memory.record_superseded` canonical event read-model boundary，但 not-enabled handler boundary 仍只允许失败路径写 `action.failed`。

MemoryRecord 必须带 source refs / execution provenance。当前 executor memory handler boundary 已在调用 memory service 前补齐 runtime provenance：

- source refs 应指向 artifacts、events、resources 或 other memory refs。
- provenance 至少应能追溯 run / thread / execution / action。
- created_at 必须由受控 runtime path 生成。
- executor 传给 memory service 的 record provenance 会包含 runtime `run_id`、`execution_id`、`action_type`。

server / agent runtime 不能直接写 durable memory。public client 也不能直接提交 MemoryRecord。

failed memory write 必须走 action failed path，不得伪造成功 record。

memory write 不能补写、改写或修复过去 event。它只能产生新的 derived memory record 和对应 canonical event。

## 5. Memory Query Boundary

memory query 是 read-side recall。

当前最小实现只锁 not-enabled / fail-closed boundary：

- `NotEnabledMemoryQueryService.query(...)` 必须显式接收 `grants` 和 `caller_context`。
- missing / malformed `grants` 或 `caller_context` 受控拒绝，不能泄漏原生 `AttributeError` / `TypeError`。
- `caller_context.run_id` 必须和 query `run_id` 对齐；`caller_context.caller` /
  `caller_context.purpose` 必须是非空字符串，供后续 audit / policy 解释调用来源和目的。
- 没有 query grant 时不能读取 memory store。
- 请求 `controlled_expand=True` 时，缺少 expand grant / positive integer budget 不能读取 full content；
  invalid budget shape 必须在读取 memory store 前 fail closed。
- 请求 `controlled_expand=True` 且授权有效时，当前 implementation 仍是 preview-only：返回
  `controlled_expand.status: deferred` / budget metadata，但不调用 full-content expand。
- not-enabled fallback 也返回 deferred metadata，明确表达授权形状有效但 query engine 仍未开启。
- agent-loop query result 和 Supervisor plain renderer 可以展示 deferred metadata，帮助用户区分
  “已请求 expand” 与 “full-content expand 尚未实现”。
- 返回结果不得包含 full content、artifact content、raw content 或 full text。

这不是 memory query engine，也不是 controlled expand implementation。

query result 应返回：

- memory refs
- summary / preview
- source refs
- provenance hints
- optional controlled expand token / handle

query result 不能直接变成 `RunState` native fact。它只能作为 recall result 进入后续 action / reasoning context。

full content expand 必须受 retrieval policy / grants 控制。没有 grant 时，应返回 denial / limited view，不应读取完整内容。

memory query 不能绕过 `ResourceRef` authorization。memory refs 应使用 structured `ResourceRef` 或等价 v0 handle。

memory query 不是每个 run 必跑的一步。runtime 可以按需要查询，也可以不查询。

memory query 不应默认内联大块 artifact content。默认返回 summary / preview / refs。

## 6. MemoryRecord v0 Implementation Shape

当前已有 slice-only `MemoryRecord` implementation shape。以下字段仍不是最终协议：

```python
{
    "memory_id": "mem_001",
    "scope": "thread",  # thread | run | session
    "content": {
        "kind": "structured_note",
        "text": "..."
    },
    "summary": "...",
    "source_refs": [
        {"ref_type": "artifact", "run_id": "run_001", "artifact_id": "artifact_001"}
    ],
    "provenance": {
        "run_id": "run_001",
        "thread_id": "thread_001",
        "execution_id": "exec_001",
        "action_type": "write_memory"
    },
    "created_at": "...",
    "supersedes": [],
    "quality": "candidate"
}
```

字段说明：

- `memory_id`：memory record identity。
- `scope`：record visibility boundary，例如 thread / run / session。
- `content`：structured content，不是 raw transcript dump。
- `summary`：默认 retrieval / preview surface。
- `source_refs`：可追溯来源。
- `provenance`：execution / action provenance。
- `created_at`：record creation time。
- `supersedes`：可选 supersession relation。
- `quality`：candidate quality / confidence / review marker。

当前最小 validation：

- `content` 必须是 structured dict，不能是 raw string transcript。
- `source_refs` 必须是 list，不能退回 raw string handle。
- `provenance` 必须是 dict，并包含 `run_id`、`execution_id`、`action_type`。
- `scope` 只能是 `thread` / `run` / `session`。
- top-level `artifact_content` 不被接受；memory 默认不内联 artifact content。

当前只实现 memory record persistence not-enabled boundary 和 checkpoint read-model boundary；仍不实现 successful persistence、storage lookup、record index、ref resolution 或 artifact content read。

## 7. Events / Action Chain

memory 相关事件名也只是 v0 candidate，不是永久 protocol。

当前已实现的 canonical event read-model boundary：

- `memory.record_created`
- `memory.record_superseded`

`memory.record_created` 当前只表示 projector 可从 canonical event log 投影 memory summary / refs / provenance metadata。`memory.record_superseded` 当前只表示 projector 可从 canonical event log 投影 append-only supersession metadata：旧 record 不被覆盖，只被标记 superseded 并指向已存在的新 record。`RunProjector` 当前也能把 `RunState.memory_records` 写入 checkpoint，并从 checkpoint + suffix events 恢复该 read model；checkpoint 中仍只能保存 summary / refs / provenance / supersession metadata，不能夹带 full content。它们不表示 durable memory storage / successful memory update 已实现，也不允许 memory store 直接推进 `RunState`。

可能的 future v0 event sketch：

- `memory.write_requested`
- `memory.query_requested`
- `memory.query_completed`

hard requirement 不是这些具体名字，而是：

- durable write 必须可追溯到 authorized execution。
- memory record creation 必须可通过 canonical event log 审计。
- `memory.record_created` 必须绑定 completed `write_memory` execution。
- `memory.record_created` 不能包含 full content / artifact content。
- `memory.record_superseded` 必须绑定 completed `write_memory` execution。
- `memory.record_superseded` 不能包含 full content / artifact content / raw content。
- memory update 语义必须是 append-only supersession，不是原地修改。
- query event 是否需要进入 canonical log 仍是 open question。
- query result 不能直接推进 `RunState`。

## 8. Retrieval / ResourceRef Boundary

memory query 应和 retrieval boundary 对齐：

- 默认返回 refs / summary / preview。
- controlled expand 受 grants / policy 控制。
- full content read 不能隐式发生。
- memory ref 必须能携带 enough locator / provenance，不应退回 raw string handle。
- memory result 不应直接复制 artifact content。

`ResourceRef` 可以覆盖 memory ref，但具体字段仍是 v0 candidate。memory ref 不应绕过 artifact / event / workspace authorization。

## 9. Deferred

Memory record persistence boundary design note 已落在 `memory-record-persistence-boundary-v0.1.md`。`NotEnabledMemoryStore` 已实现为 unavailable persistence boundary，但只做受控拒绝，不实现 successful storage。

以下能力继续 deferred：

- real memory storage implementation。
- successful durable memory write implementation。
- successful memory update / supersession write implementation。
- memory query implementation。
- successful memory record persistence implementation。
- memory record index。
- ranking / exposure strategy。
- session memory promotion policy。
- vector index。
- embedding provider。
- controlled expand budget implementation。
- memory compaction。
- memory GC。
- public memory HTTP API。
- real LLM recall loop。
- memory migration / version negotiation。
- memory inspection API。
- server memory API。

## 10. First Red Tests

第一批 memory boundary tests 已落地并通过，但只覆盖 not-enabled / rejection boundary，不实现 memory storage / write / query。

已覆盖：

- `NotEnabledMemoryService` exists and legacy query remains not-enabled。
- direct durable memory write without authorized execution is rejected。
- memory query accepts explicit grants / caller context shape but remains controlled not-enabled。
- memory query result does not include full content / artifact content by default。
- projector does not read memory store to advance `RunState`。
- server still has no public `query_memory(...)` API.

第二批 memory action-chain boundary tests 已落地并通过，但只覆盖 compiler / policy boundary 和 executor unsupported-handler boundary，不实现 storage / query。

已覆盖：

- `write_memory` intent 不能只是 raw text。
- valid memory intent 会保留 structured payload：`content`、`summary`、`source_refs`、`provenance`。
- registry-backed `write_memory` proposal 可以进入 `PolicyEngine` decision。
- executor 没有 `memory_service` 时，authorized `write_memory` 会受控失败并写 `action.started -> action.failed`，不创建 artifact、不写 memory record。
- server 仍没有 direct memory write API。

第三批 MemoryRecord shape tests 已落地并通过，但只覆盖 implementation shape / validation，不实现 persistence / storage / write / query。

已覆盖：

- `MemoryRecord` v0 shape exists。
- valid `MemoryRecord` requires structured `content` and `provenance`。
- raw transcript string content is rejected。
- missing `run_id` / `execution_id` / `action_type` provenance is rejected。
- `source_refs` must be list。
- `scope` is limited to `thread` / `run` / `session`。
- top-level `artifact_content` is not accepted。

第四批 executor memory handler not-enabled / provenance boundary tests 已落地并通过，但只覆盖 handler boundary 和 failure behavior，不实现 successful durable write / persistence / storage / query。

已覆盖：

- `Executor` accepts optional `memory_service`。
- authorized `write_memory` with configured `memory_service` enters memory handler boundary。
- executor constructs `MemoryRecord` / record from structured payload。
- runtime execution provenance is passed to memory service。
- `PolicyDecision.grants` is passed to memory service。
- `NotEnabledMemoryService.write_record(...)` rejection writes `action.started -> action.failed`。
- memory write failure does not create artifact, append `action.completed`, or append `memory.record_created`。
- missing `write_memory` grant does not call memory service。
- without `memory_service`, `write_memory` remains unsupported handler。

第五批 memory record persistence not-enabled boundary tests 已落地并通过，但只覆盖 unavailable store / rejection boundary，不实现 successful persistence / storage / query。

已覆盖：

- `NotEnabledMemoryStore` exists。
- direct persistence without `ActionExecution` is rejected。
- direct persistence without `write_memory` grant is rejected。
- malformed record is rejected。
- valid record is still rejected as not-enabled。
- rejected persistence leaves no partial record。
- rejected persistence does not append `action.completed` or `memory.record_created`。
- projector still does not read memory store to advance `RunState`。
- query default shape still excludes full content / artifact content。

第六批 memory query authorization not-enabled boundary tests 已落地并通过，但只覆盖 query-time auth / fail-closed，不实现 query engine 或 controlled expand。

已覆盖：

- `NotEnabledMemoryQueryService` exists。
- missing / malformed `grants` 或 `caller_context` is controlled rejected。
- missing or mismatched caller context run returns `reason_code: caller_context_run_mismatch`
  before reading memory store。
- missing / empty / non-string caller audit context returns
  `reason_code: invalid_caller_context` before reading memory store。
- missing query grant returns `reason_code: missing_memory_query_grant` and does not read memory store。
- controlled expand without expand grant / positive integer budget returns
  `reason_code: missing_controlled_expand_grant` and does not read full content。
- controlled expand with invalid budget shape returns
  `reason_code: invalid_controlled_expand_budget` before reading memory store。
- valid controlled expand grant still returns summary / refs / provenance preview only,
  includes `controlled_expand.status: deferred`, and does not read full content。
- not-enabled query with valid controlled expand grant returns
  `reason_code: memory_query_not_enabled` plus deferred controlled expand metadata。
- agent-loop query memory surfaces deferred controlled expand metadata without leaking content。
- Supervisor memory plain renderer prints deferred controlled expand metadata when present in the payload。
- not-enabled query returns `reason_code: memory_query_not_enabled` while preserving
  summary / refs / provenance-only content policy。
- default query result excludes full content / artifact content / raw content。
- projector still does not read memory query service or memory store to advance `RunState`。
- server still has no public `query_memory(...)` API。

第七批 `memory.record_created` canonical event boundary tests 已落地并通过，但只覆盖 projector/event read-model boundary，不实现 successful durable memory write 或 storage。

已覆盖：

- `RunState.memory_records` exists as a minimal read model。
- `memory.record_created` is a canonical event projection boundary, not memory-store-driven state。
- projector projects only summary / refs / provenance metadata。
- projector rejects `memory.record_created` full content fields: `content`、`full_content`、`artifact_content`、`raw_content`。
- projector fail-fast validates required fields including `record_id`、`execution_id`、`summary`、`source_refs`、`provenance`、`basis_event_id`。
- `memory.record_created` must bind to a completed `write_memory` execution。
- failed / denied / pending / non-`write_memory` execution is rejected。
- executor + not-enabled memory service still cannot create `memory.record_created`。
- server still has no public direct memory write API。

第八批 memory read-model checkpoint boundary tests 已落地并通过，但只覆盖 checkpoint/read-model boundary，不实现 durable memory storage 或 query engine。

已覆盖：

- event-log replay reconstructs `RunState.memory_records`。
- `RunProjector.create_checkpoint(...)` includes `memory_records` in checkpoint state。
- `RunProjector.rebuild_with_checkpoint(...)` restores `memory_records` from checkpoint + suffix events。
- checkpoint memory records exclude `content`、`full_content`、`artifact_content`、`raw_content`。
- checkpoint state schema validates memory record shape and supersession metadata。
- checkpoint prefix consistency covers memory read model mismatch。
- projector does not read memory store or query service for checkpoint-assisted rebuild。

下一阶段默认转向 v0.1 demo entrypoint planning。若 scope 被明确 reopened，后续 red tests / docs 可覆盖：

- memory result cannot bypass artifact / `ResourceRef` authorization。
- external ingestion / `ImportedSnapshot` boundary docs。
- public-open-source cleanup plan。
- 或停在当前稳定点。

这些 tests 的目标仍是锁住边界：memory 必须通过 action/policy/execution/event 进入 durable state，query 只能是受控 recall，不能成为第二事实源。不要在 v0.1 demo 前默认继续实现 memory storage、successful write、query engine 或 controlled expand。
