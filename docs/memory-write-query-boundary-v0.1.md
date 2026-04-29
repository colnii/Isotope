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
- projector 仍不读取 memory store 推进 `RunState`。
- server 仍没有 public `query_memory(...)` API。
- 当前没有 durable memory write implementation。
- 当前没有 memory storage。
- 当前没有 memory query implementation。
- 当前没有 vector index、ranking 或 controlled expand implementation。
- 当前测试基线是 `458 passed`。

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

## 4. Memory Write Boundary

第一阶段只实现 action-chain 和 not-enabled handler boundary，不实现 storage、successful durable write path 或 query engine。

`write_memory` action type 当前已可作为 registry-backed v0 candidate 进入 compiler / policy boundary，但名字仍是 v0 candidate，不是永久协议。

durable memory write 必须由 authorized execution 触发：

- compiler 只能生成 requested capabilities。
- compiler 必须按 registry `payload_requirements.required` 校验 payload；`write_memory` 不能只是 raw text。
- valid memory intent 必须保留 structured `content`、`source_refs`、`provenance`，可携带 `summary`。
- policy 决定是否授予 memory write grants。
- executor / memory service 只能基于 `PolicyDecision.grants` 写。
- successful memory write 未来必须 append canonical event，不能作为 side-channel state mutation。当前 not-enabled handler boundary 只允许失败路径写 `action.failed`。

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

当前仍不实现 memory record persistence、storage lookup、ref resolution 或 artifact content read。

## 7. Events / Action Chain

memory 相关事件名也只是 candidate，不是 hard protocol。

可能的 v0 event sketch：

- `memory.write_requested`
- `memory.record_created`
- `memory.query_requested`
- `memory.query_completed`

hard requirement 不是这些具体名字，而是：

- durable write 必须可追溯到 authorized execution。
- memory record creation 必须可通过 canonical event log 审计。
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

以下能力继续 deferred：

- real memory storage implementation。
- successful durable memory write implementation。
- memory query implementation。
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
- memory record persistence。
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

下一批 red tests / docs 可覆盖：

- memory record persistence boundary docs / tests。
- memory query authorization and controlled expand budget sketch。
- memory result cannot bypass artifact / `ResourceRef` authorization。
- external ingestion / `ImportedSnapshot` boundary docs。

这些 tests 的目标是锁住边界：memory 必须通过 action/policy/execution/event 进入 durable state，query 只能是受控 recall，不能成为第二事实源。
