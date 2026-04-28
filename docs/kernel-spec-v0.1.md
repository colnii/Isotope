# Isotope Kernel Spec v0.1（草案）

状态：`draft`

本文件不是最终实现 spec。它的目的，是把当前 `docs/isotope` 主线收口成一份可读的 v0.1 kernel 规格草案，并明确区分：

- `Hard Contract`：当前不应轻易回滚的架构边界。
- `v0 Candidate`：当前推荐推进方式，但允许后续调整。
- `Example / Schema Sketch`：解释性样例，不能当最终协议。
- `Open Question`：尚未收敛的问题，不能写入 decision log 当成结论。

## 1. Scope

### In Scope For v0.1

kernel v0.1 当前负责定义：

- session / run 边界。
- supervisor / worker 生命周期边界。
- policy-gated delegation。
- canonical action chain。
- canonical event log。
- state projection。
- structured memory。
- canonical resource references。
- external ingestion 边界。
- artifact / provenance 的基本语义。

### Hard Contract

`Isotope` 是一个 kernel-first、domain-agnostic agent runtime/platform。

它不是：

- `x-agent` recipe runtime 的延伸。
- grading-first runtime。
- 固定流程 workflow runner。
- 某个参考项目的复刻。

### v0 Candidate

v0 先按 `server-first`、`single-user local/server` 推进。

`HTTP JSON + SSE` 是 v0 server API 起点，但不是永久 transport contract。

### Open Question

- hosted multi-tenant 何时进入主线。
- 第一条最小 vertical slice 应覆盖哪些能力。
- domain pack 的正式接口形态。

## 2. Core Boundaries

### Hard Contract

`Session` 是 continuity boundary。

`Run` 是 execution boundary。

执行状态归 `Run`，而不是归 `Session`。`Session` 维持跨 run 的连续性，但不直接承载运行中的执行状态。

supervisor / worker 是 kernel 一等概念。delegation 可以由模型动态提出，但 runtime policy 是最终裁决者。

### v0 Candidate

当前对象模型建议包括：

- `Session`
- `Run`
- `AgentSpec`
- `AgentInstance`
- `Thread`
- `Workspace`
- `ActionProposal`
- `PolicyDecision`
- `ActionExecution`
- `Artifact`
- `MemoryRecord`
- `Event`
- `Checkpoint`
- `ImportedSnapshot`
- `ResourceRef`

supervisor 默认持久。worker 默认短命，但必要时可以 promotion 为更持久的 agent。

`AgentInstance` 默认只存在于某个 `Run` 内。跨 run 连续性来自 `Session Memory`、profile 和 artifacts，而不是复用运行态 agent object。

### Open Question

- `AgentSpec` / `AgentInstance` 的完整字段。
- worker promotion 的触发条件和持久化语义。
- `Thread` 是否需要独立生命周期状态机。

## 3. Action And Policy

### Hard Contract

所有外部动作必须进入 canonical action chain：

`ActionProposal -> PolicyDecision -> ActionExecution -> canonical event`

执行器只能使用 `PolicyDecision.grants`，不能使用未经裁决的 requested capabilities。

`PolicyDecision.modified` 是一等 outcome。runtime 可以缩权后批准，而不是只能批准或拒绝。

模型可以输出 compact action / intent，但 runtime 必须先编译并校验成 canonical `ActionProposal`，再进入 policy / execution。

### v0 Candidate

当前 action model 使用三类对象：

- `ActionProposal`：动作意图。
- `PolicyDecision`：runtime policy 的裁决。
- `ActionExecution`：一次实际执行尝试。

action-specific body 当前推荐命名为 `payload`，不用通用 `target`。具体 payload schema per action 仍未定稿。

当前推荐 outcome 集合：

- `approved`
- `modified`
- `denied`
- `pending_user_approval`
- `expired`

当前推荐 action event 集合：

- `action.proposed`
- `action.decided`
- `action.execution_created`
- `action.started`
- `action.completed`
- `action.failed`
- `action.cancelled`

approval 事件当前建议单独记录：

- `approval.requested`
- `approval.resolved`

### Example / Schema Sketch

任何 JSON 字段示例都只是 sketch。尤其是 `payload`、`requested_capabilities`、`grants`、`effective_grants_snapshot`、`result` 的具体结构，不能视为最终协议。

### Open Question

- `ActionTypeRegistry` 的 schema、版本化、注册生命周期；当前最小边界见 `docs/action-type-registry-v0.1.md`。
- `ActionExecution.result` 的统一形状。
- retry / cancel / supersede 语义。
- approval API 与 blocked/resume 的具体协议。
- model-facing compact protocol 的具体形式：JSON、tool calling、mini DSL，还是多模式。

## 4. Workspace

### Hard Contract

workspace 是 execution resource，不是 agent 身份的一部分。

workspace 访问与升级必须受 runtime policy 控制。

### v0 Candidate

当前推荐 hybrid workspace model：

- 默认共享、偏只读。
- 写操作、长任务或高风险工具升级到 isolated workspace。
- workspace binding / lease metadata 由 run 管理。
- worker 可以绑定共享或隔离 workspace，具体取决于 `PolicyDecision.grants`。

### Open Question

第一版 workspace substrate 尚未确定：

- process
- git worktree
- container
- remote executor

workspace path safety、文件变更追踪、回滚、artifact capture 仍需单独设计。

## 5. Event Log, Checkpoint, State Projection

### Hard Contract

canonical event log 是 `RunState` / `SessionState` 的唯一 source of truth。

canonical event log 必须是 append-only。

外部 raw log、provider response、callback 原文、workspace 文件或数据库快照，不能直接驱动 state projector。

projector 只能消费 canonical events。

checkpoints 和 materialized views 都是 canonical events 的派生读模型，不是新的事实源。

durable objects 只有在被 canonical event 引入、注册、钉住，或作为 canonical event 携带的规范化事实时，才能影响状态。

### v0 Candidate

当前推荐保留：

- checkpoints 用于 recovery / inspection / faster reads。
- `RunState` / `SessionState` 作为 API/UI 读模型。

### Open Question

- `RunState` 的具体字段 schema。
- `SessionState` 的具体字段 schema。
- checkpoint 的格式、频率、压缩和恢复策略。
- materialized view 的重建与迁移策略。

## 6. External Ingestion

### Hard Contract

外部输入必须先经过 ingestion，不能直接更新 `RunState` / `SessionState`。

ingestion 只有三种结果：

- 变成本地 canonical event。
- 变成被 canonical event 接纳的 external observation。
- 只作为 artifact / provenance 保存，不参与状态推进。

外部观察不是第二事实源，不能覆盖 native state。

状态精度取决于 adapter 质量。kernel 不能假装比外部源更懂。

imported / derived observation 一旦影响展示或派生状态，必须保留足够的质量、来源和新鲜度信息，不能伪装成 native state。

### v0 Candidate

`ImportedSnapshot` 是当前推荐的 external observation 建模方式。

`snapshot.imported` 是当前推荐事件名。

当前推荐 projection 分类：

- `native_only`
- `imported_eligible`
- `derived`

### Example / Schema Sketch

`ImportedSnapshot` 的 JSON 示例、quality enum、observation metadata 字段都只是 sketch。

`confidence`、`coverage`、`freshness`、`basis_refs` 是当前字段示例，不是最终 schema。

### Open Question

- external observation 的最终对象名。
- adapter 准入、版本、schema migration 规则。
- conflict resolution 的具体读模型。
- 哪些状态字段可以进入 `imported_eligible`。

## 7. ResourceRef And Retrieval

### Hard Contract

正式协议使用结构化 `ResourceRef`。

URI-like 写法只用于 display/debug，不能作为 formal API 协议。

policy、retrieval、tool input 都先对 refs 生效。runtime 解引用后，再决定调用方能拿到 summary、full content、structured slice 或 denial。

### v0 Candidate

当前 `ResourceRef` 顶层 shape 建议包括：

- `ref_type`
- `scope`
- `locator`
- `selector`
- `version`

完整 `ref_type`、`locator`、`selector` 变体尚未定稿。

### Example / Schema Sketch

```json
{
  "ref_type": "artifact",
  "scope": "run",
  "locator": {
    "run_id": "run_001",
    "artifact_id": "artifact_123"
  },
  "selector": null,
  "version": null
}
```

该 JSON 只是 illustrative sketch，不是最终协议。

### Open Question

- `ResourceRef` 的完整变体集合。
- selector 类型。
- version pinning / content addressing 的具体规则。
- retrieval policy 的 ranking、裁剪、budget、expand 降级策略。

## 8. Memory

### Hard Contract

memory 不是 transcript dump。

`MemoryRecord` 不能只是索引卡片。它需要结构化 `content` 和 provenance。

durable memory 写入必须可审计、可追溯，并进入 canonical action/event 路径。

memory 默认不内联大块 artifact 内容。

### v0 Candidate

当前 memory layers：

- `Thread Working Memory`
- `Run Memory`
- `Session Memory`
- `Artifact Index`

`Artifact Index` 是 retrieval surface，不是 memory 本体。

当前推荐 memory shape：

- structured `content`
- preview / summary
- refs
- provenance
- append + supersession 更新语义

当前推荐 recall 路径是 `Memory Query + controlled expand`。controlled expand 不能绕过 retrieval policy。

`write_memory` / `promote_memory` 是推荐 action type 名，不是硬协议。

### Open Question

- `MemoryRecord` 的最终 schema。
- memory ranking / exposure 策略。
- session memory promotion policy。
- controlled expand 的预算、裁剪、降级和审计事件。
- memory 与 artifact graph 的索引关系。

## 9. Model-Facing Protocol Boundary

### Hard Contract

canonical schema 面向 runtime、storage、audit 和 replay。

模型不必直接输出完整 canonical schema。

policy、execution 和 event log 只消费 canonical objects。

如果模型输出 compact action / intent，runtime 必须先编译、校验并规范化成 canonical object。

### v0 Candidate

当前建议继续设计：

- model-facing compact protocol
- action compiler
- ref handles
- rendered context views
- validator / repair layer

这些名字和协议形态仍未定稿。

### Open Question

- compact protocol 应该优先使用 JSON、tool calling、mini DSL，还是多模式。
- 低级模型输出失败时如何 repair / reprompt / escalate。
- rendered context view 与 canonical `ResourceRef` 的映射格式。

## 10. Server Model

### v0 Candidate

当前推荐：

- server-first
- single-user local/server first
- HTTP JSON + SSE
- run 可以在没有在线 client 附着的情况下继续运行或恢复
- UI、CLI 和 API client 消费同一套 event stream，避免各自维护不可回放的内部 orchestration state
- API surface 覆盖 sessions、runs、event stream、artifacts、approvals、memory query

### Example / Schema Sketch

当前 endpoint list 只是 sketch，不是最终 public API：

- `POST /v0/sessions`
- `GET /v0/sessions/{session_id}`
- `POST /v0/sessions/{session_id}/runs`
- `GET /v0/runs/{run_id}`
- `GET /v0/runs/{run_id}/events`
- `GET /v0/runs/{run_id}/stream`
- `POST /v0/approvals/{approval_id}/resolve`
- `POST /v0/runs/{run_id}/memory/query`

### Open Question

- API auth / identity。
- approval API 细节。
- streaming event envelope。
- pagination / replay cursor。
- long-running run 的 resume contract。

## 11. Relationship To x-agent And Reference Projects

### Hard Contract

`x-agent` 是设计证据和未来 domain/tool pack 材料，不定义 `Isotope` kernel 架构。

`GenericAgent`、`PetGPT`、study companion 等参考方向只作为 pressure test，不作为 kernel 模板照搬。

application-level orientation、persona、pedagogy、grading policy 和学习路线不属于 kernel。

### v0 Candidate

从参考项目中保留的压力测试点包括：

- active context density。
- provenance-backed durable memory。
- workspace-backed state。
- path-safe primitives。
- tool/session guardrails。
- subagent lifecycle control。
- trace/export discipline。
- artifact-centric state。
- provenance-aware retrieval。

## 12. Current Open Questions

当前 v0.1 不解决以下问题：

- `ActionTypeRegistry` 的 schema、版本化、注册生命周期；当前最小边界见 `docs/action-type-registry-v0.1.md`。
- `ActionExecution.result` 的统一形状。
- retry / cancel / supersede 语义。
- `RunState` / `SessionState` 的具体字段 schema。
- `ResourceRef` 的完整 locator / selector 变体。
- retrieval policy 的 ranking、裁剪、budget、expand 降级策略。
- model-facing compact protocol 的具体形式。
- approval API、approval event 与 blocked/resume 细节。
- workspace substrate 第一版实现。
- domain pack 接口。
- 第一条最小可运行 vertical slice。

## 13. Conflict Check

当前 v0.1 与 `docs/isotope` 主线没有根本冲突。

需要持续避免的误读：

- `HTTP JSON + SSE` 是 v0 candidate，不是永久 transport contract。
- `write_memory` / `promote_memory` 是推荐 action type 名，不是硬协议。
- `ResourceRef` 是 hard contract，但当前 JSON shape 是 v0 candidate。
- 所有 JSON、endpoint list、enum 和字段名示例都只是 Example / Schema Sketch，除非明确进入 hard contract 或 v0 candidate。
- 模型侧 compact protocol 不削弱 action chain；它必须先编译成 canonical `ActionProposal`。
- `ImportedSnapshot` 是推荐建模方式，但核心硬约束是外部输入不能直接驱动 state projector。
