# Isotope Kernel One-Pager（一页说明）

## 这个 Kernel 想解决什么问题

`Isotope` 不是想再做一个固定流程的 workflow runner（工作流执行器）。当前设想里的 kernel（内核）想提供的是一个通用 agent runtime/platform（智能体运行时 / 平台），它至少要能：

- 运行一个持久的 supervisor（监督者）以及它委派出去的 workers（执行子 agent）
- 允许模型提出动作，但最终由 runtime（运行时）负责裁决和执行
- 在需要的时候切换到隔离的 execution environment（执行环境）
- 持久化 event trace（事件轨迹）、checkpoint（检查点）、artifact（产物）和 memory（记忆）
- 把外部系统返回先规范化，再投影成可审计的状态
- 支持长任务的恢复、检查、回放和审计

当前目标是一个 `server-first`、`single-user local/server` 的平台内核，不是只服务批改场景的单用途产品，也不是一开始就面向 hosted multi-tenant（托管多租户）部署。

## 标准说法

`Isotope v0` 目前可以用一句话概括：

**它是一个 supervisor-kernel-first（监督者内核优先）的 agent runtime。**

这句话展开以后，核心意思是：

- 顶层有一个持久的 supervisor
- 普通 worker 默认短命，但在必要时可以提升为更持久的 agent
- delegation（委派）可以由模型动态提出
- 但 execution（执行）始终受 runtime policy（运行时策略）裁决
- workspace isolation（工作空间隔离）采用混合模型
- 底层持久化采用 append-only event log（只追加事件日志）加 snapshots（快照）
- `RunState` / `SessionState` 只由 canonical event log（规范事件日志）投影出来

这个 kernel 目标上是 domain-agnostic（领域无关）的。`grading` 只是未来可能挂在上面的一个 domain pack（领域包），不是整个架构的中心。

## 核心对象

- `Session`
  跨多个 `Run` 保持连续性的会话上下文。
- `Run`
  一次顶层执行实例，拥有自己的事件日志、产物、记忆和 agents。
- `AgentSpec`
  agent 的静态定义，比如默认提示词、工具边界、策略默认值。
- `AgentInstance`
  某个 `Run` 里的运行态 agent 实例。
- `Thread`
  上下文容器，承载消息、局部计划和 working memory（工作记忆）。
- `Workspace`
  执行环境资源，可以是共享的，也可以是隔离的。
- `ActionProposal`
  模型或 runtime 提出的一个外部动作提案。
- `PolicyDecision`
  runtime 对提案做出的裁决结果，包含真正授权的 grants（授予能力）。
- `ActionExecution`
  基于某个决策创建出来的一次实际执行尝试。
- `Artifact`
  工具、worker 或 runtime 产出的耐久化结果。
- `MemoryRecord`
  带结构化 `content`、preview/summary 和 provenance（来源溯源）的记忆条目。
- `Event`
  事件日志里的只追加事实记录。
- `Checkpoint`
  从事件流派生出来的快照。
- `ImportedSnapshot`
  被 canonical event 接纳过的外部观察，不是第二个事实源。
- `ResourceRef`
  指向 artifact、memory、event 等资源的结构化规范引用。

## Hard Contracts（硬约束）

这些是当前不应轻易回滚的架构边界：

- `Isotope` 是 kernel-first、domain-agnostic runtime，不是 `x-agent` recipe runtime 的延伸。
- `Supervisor-Kernel First` 是当前主方向；supervisor / worker 是 kernel 一等概念。
- `Session` 是 continuity boundary；`Run` 是 execution boundary，执行状态归 `Run`。
- delegation 可以由模型动态提出，但 runtime policy 是最终裁决者。
- 外部动作必须进入 canonical action chain：`ActionProposal -> PolicyDecision -> ActionExecution -> canonical event`。
- 真正执行时只能使用 `PolicyDecision.grants`，不能使用未经裁决的 requested capabilities。
- `PolicyDecision.modified` 是一等 outcome。
- 正式协议统一使用结构化 `ResourceRef`；URI-like 字符串只用于 display/debug。
- `RunState` / `SessionState` 的唯一 source of truth 是 canonical event log。
- 外部 raw log、provider response、callback 原文不能直接更新 state projector。
- 外部输入必须先经过 ingestion；`ImportedSnapshot` 不是第二事实源。
- `MemoryRecord` 需要结构化 `content` 和 provenance；memory 不是 transcript dump。
- `GenericAgent` / `PetGPT` / study companion 只作为 pressure test，不作为 kernel 模板照搬。

## v0 Candidates（v0 候选方案）

这些是当前推荐推进方式，可以先写入 living spec，但不应被当成最终协议：

- `server-first` 是方向；`HTTP JSON + SSE` 是 v0 server API 起点。
- `single-user local/server first` 是 v0 deployment scope。
- supervisor 持久、worker 默认短命但可 promotion，是当前 lifecycle candidate。
- 默认共享偏只读 workspace，高风险写执行升级到 isolated workspace，是当前 workspace policy candidate。
- `write_memory` / `promote_memory` 是推荐 action type 名；硬规则是 durable memory 写入必须走动作链。
- `Memory Query + controlled expand` 是推荐 recall 路径；硬规则是 controlled expand 不能绕过 retrieval policy。
- 当前 `ResourceRef` 顶层 shape、action event 名称、status enum、endpoint list 都是 v0 candidate。
- `ImportedSnapshot`、`snapshot.imported` 和 state 字段三分类是当前推荐建模方式，具体命名和 schema 可以调整。
- model-facing compact protocol / action compiler 应继续作为 v0 candidate 设计，避免要求模型直接稳定输出复杂 canonical JSON。

## Open Questions（开放问题）

- `ActionTypeRegistry` 的精确 schema（结构）和注册生命周期
- `ActionExecution.result` 的统一形状，以及 retry（重试）细节
- `SessionState` 和 `RunState` 的具体字段 schema
- memory retrieval ranking / exposure（检索排序 / 暴露）细节
- model-facing compact protocol 的具体形式：JSON、tool calling、mini DSL，还是多模式
- public server API 里的 approval（审批）细节
- workspace substrate（执行基座）到底先落在哪种实现上：
  - process
  - git worktree
  - container
  - remote executor
- domain pack 怎么接到 kernel 上
- 第一条最小可运行 server slice（服务端纵切片）应该包含哪些能力

## 这一条 Fork 已经和旧的 x-agent 讨论分叉到哪里

当前这条 fork 已经不再把 `x-agent` 当成目标架构本身。

旧的仓库讨论更接近这些问题：

- recipe-oriented execution（配方式执行）
- 像 `dm-run`、`os-run` 这样的显式学科 workflow
- 每多一个任务链，就多写一个 recipe

而现在的 kernel 方向，至少已经在 4 个地方分叉：

1. 顶层目标已经变成 `Isotope`，不是 `x-agent`
2. 主抽象不再是 `recipe/workflow`，而是 `session/run/agent/action/event`
3. delegation 被视为 kernel 级问题，不再只是某个领域里的技巧
4. policy arbitration（策略裁决）、resource refs（资源引用）、memory layering（记忆分层）、replayable execution（可回放执行）已经变成一等 contract

所以现在更准确的说法是：

`x-agent` 仍然很有价值，但它更像是现有设计证据和未来 domain/tool pack 的来源，而不是最终的 kernel 形状。
