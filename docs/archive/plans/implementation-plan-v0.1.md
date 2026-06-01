# Isotope Implementation Plan v0.1

状态：`archived / historical plan`

归档原因：本文是早期 v0.1 最小 vertical slice（纵向切片）计划，证明当时的
kernel hard contracts（内核硬契约）能跑通；当前产品和实现已经转向
Supervisor、受控 worker 和应用层可用性路径。当前事实以
`../../current/status.md` 为准，当前架构边界以
`../../architecture/README.md` 和对应 boundary 文档为准。

本文件基于：

- `../../archive/architecture/kernel-v0.1/kernel-spec-v0.1.md`
- `../../archive/architecture/kernel-v0.1/kernel-architecture-v0.1.md`
- `../../architecture/commitment-levels.md`

它的目的不是新增架构概念，也不是最终代码任务拆解，而是把 v0.1 第一条最小 vertical slice（纵向切片）定清楚：先证明 kernel hard contracts 能跑通，再进入具体实现计划。

## 1. Purpose

v0.1 第一条 vertical slice 要验证一个最小但真实的执行闭环：

`user input -> Agent Runtime -> Action Compiler -> ActionProposal -> PolicyDecision.grants -> ActionExecution -> canonical events -> Projector -> RunState`

核心验证点不是“做复杂任务”，而是证明这些 hard contracts 能运行：

- 外部动作必须进入 canonical action chain。
- Executor 只能使用 `PolicyDecision.grants`。
- 所有状态变化来自 append-only canonical event log。
- Projector 只消费 canonical events。
- `RunState` 能从 event log 重建。
- Server API 只是入口和读面，不能绕过 kernel contracts。

## 2. Recommended Vertical Slice

推荐场景：一个 deterministic supervisor 执行内置 `write_artifact_tool`。

`write_artifact_tool` 是第一条 slice 的实现选择，不是最终 tool 协议。选择它是因为它能同时验证 execution、artifact provenance、`ResourceRef`、Artifact Store 和 Projector read model。纯 `echo_tool` 暂不作为第一条 slice 的主路径。

最小任务：

> 用户输入 “produce a hello artifact”，supervisor 提出 `call_tool` intent，policy 缩权批准，只授予 `write_artifact_tool` 和有限 budget，executor 执行，产出一个 artifact ref，Event Store 记录完整链路，Projector 投影 `RunState`，最终 run completed 并暴露 artifact summary。

这不是最终 tool 协议，也不是最终 domain pack。它只是验证 kernel 闭环的 implementation slice。

## 3. Hard Contracts Under Test

本 slice 必须证明：

- compact action / intent 不能直接执行，必须先生成 canonical `ActionProposal`。
- `PolicyDecision.modified` 能缩权批准，并且 executor 实际使用的是 `grants`。
- executor 不能访问未授权 tool、workspace mode 或 budget。
- execution lifecycle 必须通过 canonical events 记录。
- artifact 必须带 execution provenance。
- artifact identity 必须能生成结构化 `ResourceRef`。
- `RunState` 必须完全可由 canonical event log 重建。
- Server API 读到的 run status、action status、artifact summary 来自 Projector。

## 4. Included Runtime Modules

第一条 slice 必须包含：

- `Server API`
  - 提供最小 create session、create run、submit input、get run state、get events。
  - transport 可以按 v0 candidate 使用 HTTP JSON。
  - SSE streaming 先不进入 slice。
- `Agent Runtime`
  - 提供最小 supervisor loop。
  - 可以 deterministic，不需要真实 LLM。
  - 负责产生或接收模型侧 action intent，并交给 Action Compiler。
- `Action Compiler`
  - 将 compact intent 编译成 canonical `ActionProposal`。
  - 校验 action type、payload 和 runtime context。
- `Policy Engine`
  - 生成 `PolicyDecision`。
  - 至少支持 `approved`、`modified`、`denied`。
- `Executor`
  - 只基于 `PolicyDecision.grants` 执行。
  - 执行内置 `write_artifact_tool`。
- `Event Store`
  - append-only 保存 canonical events。
  - 支持按 run replay。
  - 第一条 slice 推荐使用 file event log；具体格式仍是 implementation detail。
- `Projector`
  - 从 canonical events 投影最小 `RunState`。
  - 支持删除 materialized state 后重建。
  - materialized state 可以先用 in-memory。
- `Artifact Store`
  - 保存一个最小 artifact。
  - 返回 artifact summary 和 artifact `ResourceRef`。

可以很薄但应保留边界：

- `Workspace Manager`
  - 返回 shared read-only 或 no-op workspace binding。
  - 证明 workspace 是 execution resource，不是 agent identity。
- `Retrieval Service`
  - 只支持按 artifact ref 读取 metadata / summary。
  - 不实现 ranking、budget 或 full selector。
- `Memory Service`
  - 不进入执行闭环。
  - 明确返回 not enabled 或 no-op。

## 5. Stubbed / Deferred Capabilities

第一条 slice 不负责实现：

- real LLM model loop。
- worker spawn / subagent 并发。
- durable session memory。
- memory query / controlled expand。
- external ingestion / `ImportedSnapshot`。
- checkpoint。
- SSE streaming。
- approval pause / resume。
- isolated workspace substrate。
- retry / cancel / supersede。
- full `ResourceRef` locator / selector 变体。
- retrieval ranking / budget / trimming。
- domain pack。
- auth / multi-user / quota。
- artifact type registry。
- full `ActionTypeRegistry`。

这些能力不是取消，只是不由第一条 slice 证明。

## 6. Minimal Objects

最小对象集合：

- `Session`
  - `session_id`
  - `status`
  - `current_run_id`
- `Run`
  - `run_id`
  - `session_id`
  - `status`
  - `goal`
- `AgentInstance`
  - 一个 supervisor instance。
- `Thread`
  - 一个 main thread。
- `ActionProposal`
  - `proposal_id`
  - `run_id`
  - `agent_id`
  - `thread_id`
  - `action_type`
  - `payload`
  - `requested_capabilities`
- `PolicyDecision`
  - `decision_id`
  - `proposal_id`
  - `outcome`
  - `grants`
  - `reason_codes`
- `ActionExecution`
  - `execution_id`
  - `proposal_id`
  - `decision_id`
  - `action_type`
  - `status`
  - `effective_grants_snapshot`
- `Artifact`
  - `artifact_id`
  - `artifact_type`
  - `summary`
  - `content` 或 content handle
  - `provenance.execution_id`
- `ResourceRef`
  - v0 slice 只使用 artifact ref。
- `RunState`
  - `run_id`
  - `status`
  - `current_agent`
  - action summary
  - artifact summary
  - `last_event_id`

这些字段是 v0 slice 的 implementation shape，不是最终 protocol。

## 7. Minimal Events

最小 happy path 事件：

- `session.created`
- `run.created`
- `agent.created`
- `thread.created`
- `action.proposed`
- `action.decided`
- `action.execution_created`
- `action.started`
- `artifact.created`
- `action.completed`
- `run.completed`

最小 failure / denied path 可以补：

- `action.failed`
- `run.failed`

这些 event names 是 v0 candidate，不是永久协议。

## 8. Runtime Flow

典型 happy path：

1. Server API 创建 session。
2. Server API 创建 run。
3. Agent Runtime 创建 deterministic supervisor instance 和 main thread。
4. Server API 接收用户输入或 client request。
5. Agent Runtime 推进 supervisor loop，产生 `call_tool` compact intent。
6. Action Compiler 将 compact intent 编译为 `ActionProposal`。
7. Event Store append `action.proposed`。
8. Policy Engine 生成 `PolicyDecision`，可用 `modified` 缩减 tool / workspace / budget。
9. Event Store append `action.decided`。
10. Executor 基于 decision grants 创建 `ActionExecution`。
11. Event Store append `action.execution_created` 和 `action.started`。
12. Executor 调用内置 test tool。
13. Artifact Store 保存 artifact，并返回 artifact `ResourceRef`。
14. Event Store append `artifact.created` 和 `action.completed`。
15. Agent Runtime 根据 projected state 判断 run 完成。
16. Event Store append `run.completed`。
17. Projector 从 canonical events 投影 `RunState`。
18. Server API 读取 Projector 输出，返回 run state、events 和 artifact summary。

## 9. Acceptance Criteria

第一条 slice 的验收标准：

- 创建 session 和 run 后，Event Store 里只有 canonical events 能推进状态。
- canonical events 只能 append，不能原地修改或删除；修正必须通过追加新 event 表达。
- compact action 不能直接执行，必须先生成 `ActionProposal`。
- `PolicyDecision.outcome = modified` 时，Executor 实际使用 `grants`，不能使用 requested capabilities。
- Executor 无法访问未授权 tool 或 workspace mode。
- Artifact 必须带 execution provenance，并能生成结构化 `ResourceRef`。
- `RunState` 必须完全可由 event log 重建，不能读 executor 内存状态。
- 删除 materialized `RunState` 后重放 events，得到等价状态。
- 使用 fresh projector / fresh process 从 file event log 重建，得到等价 `RunState`。
- Server API 读到的 run status、action status、artifact summary 来自 Projector。
- 至少有一个测试证明 Projector 只使用 canonical event 中的 artifact ref / summary 推进 read model，不读取 artifact content 来推进 native state。
- happy path 通过。
- 至少一个 `modified` case 通过。
- 至少一个 `denied` 或 unsupported case 通过。
- 所有非实现范围能力明确返回 unsupported / not_enabled，而不是静默绕过。

## 10. Non-Goals

本计划不解决：

- 最终 public API。
- 最终 event envelope schema。
- full `ResourceRef` schema。
- real LLM integration。
- multi-agent scheduling。
- durable memory。
- external ingestion。
- checkpoint ownership。
- hosted multi-tenant。
- domain pack interface。

## 11. Open Questions Before Coding

进入编码前至少要明确：

- 第一条 slice 固定使用 `write_artifact_tool`；未来是否保留 `echo_tool` 作为更小测试工具仍开放。
- retrieval 是否进入 v0 Server API endpoint，还是只作为 internal service。
- approval 在 v0 是否只保留 pending / denied 语义，不做完整审批 API。
- checkpoint 在 v0 slice 中是否完全 deferred。
- minimal storage 采用 file event log + in-memory materialized state；SQLite 是否作为后续 storage backend 仍开放。
- implementation 是否仍放在 `x-agent` staging repo，还是迁移到独立 Isotope repo 后再开始。
