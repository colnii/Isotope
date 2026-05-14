# Isotope Platform Kernel Reference Design

状态：`concept reference`

## 1. 摘要

本文是 `Isotope` 作为通用 agent runtime / platform 的早期参考设计。

推荐方向：

- `platform / kernel-first`
- `agent server-first`
- v0 面向 single-user local/server
- supervisor + worker 是一等对象
- worker lifecycle 采用 hybrid：supervisor 持久，worker 默认短命，必要时可升级
- dynamic delegation 由模型提议，但 runtime policy 最终裁决
- workspace 采用 hybrid：默认共享只读，高风险或写操作升级隔离
- 持久化采用 append-only event log + snapshot / materialized view

相关比较：

- [Isotope vs LangGraph vs AutoGen](2026-04-22-isotope-vs-langgraph-vs-autogen.md)
- [Isotope vs Codex vs Claude Code vs OpenClaw](2026-04-22-isotope-vs-codex-claude-code-openclaw.md)
- [Isotope vs GenericAgent](2026-04-24-isotope-vs-genericagent.md)
- [Isotope vs PetGPT](2026-04-24-isotope-vs-petgpt.md)
- [Isotope vs Hermes Agent](isotope-vs-hermes-agent.md)
- [Study Agent Boundaries](2026-04-22-isotope-study-agent-boundaries.md)

## 2. 来源边界

这份文档最早写于 `Isotope` 还在从 `x-agent` 讨论中分离的时候。

历史边界仍然有用：

- `x-agent` 是 recipe-oriented assessment application。
- `Isotope` 是独立的 kernel / platform project。

`x-agent` 可以借鉴更清晰的 tool contract、run / artifact 边界、trace / replay 习惯，但不应该被悄悄改造成平台原型。

## 3. 已经确定的方向

当前讨论已经确定：

- `Isotope` 是通用 agent runtime / platform，不是 grading-only framework。
- kernel 应该 server-first，而不只是 CLI harness。
- delegation 应该动态，但不是模型完全主权。
- runtime 从一开始支持 supervisor -> worker。
- worker 默认 ephemeral，需要时可 persistent。
- execution environment 是 hybrid：共享上下文 + 隔离写入面。
- persistence 是 hybrid：event log 支撑 replay，snapshot 支撑恢复和查询。

这些选择把设计推向 control-plane-oriented kernel，而不是 workflow engine 加一点 agent 包装。

## 4. 目标

`Isotope` 目标：

- 支撑 coding、grading、document review、study companion 等不同 domain。
- 把 delegation、workspace isolation、trace persistence、policy gating 做成一等能力。
- 允许模型驱动行为，但 runtime 保留确定性控制边界。
- 清楚区分 kernel、platform services、domain packs、product shells。
- 吸收真实 agent 产品经验，而不是只从抽象多 agent 理论出发。

## 5. 非目标

v0 不做：

- hosted multi-tenant SaaS kernel
- 纯 graph-authored workflow engine
- 把所有状态塞进 opaque database blob
- 把 grading、coding、study 等 domain model 写死进 kernel
- 复制任何参考项目的产品语义、UI shell 或 persona 形态

## 6. 核心对象模型

### 6.1 Run

一次顶层执行实例。

`Run` 是审计、恢复、回放、交付的基本单位。

### 6.2 AgentSpec

agent 的静态定义：

- system instruction
- 默认 tools
- delegation policy
- memory policy
- workspace policy
- role / capability boundaries

### 6.3 AgentInstance

`AgentSpec` 在某个 run 内的运行态实例。

supervisor 和 worker 都是 `AgentInstance`。

worker 不需要单独成为另一种对象；它可以是带 `parent_agent_id` 的 agent instance。

### 6.4 Thread

上下文容器。

它承载：

- messages
- local memory
- plan
- current goal

`Run != Thread`。

一个 run 可以有 supervisor thread 和多个 worker thread。

### 6.5 Workspace

执行环境句柄。

workspace 不属于 agent，而属于 run 下的可租用资源。

这让 workspace 可以被共享、升级、释放、迁移和审计。

### 6.6 Tool / ToolCall

`Tool` 是可调用能力的注册定义。

`ToolCall` 是一次具体调用。

两者必须分开，否则 trace、retry、approval、replay 都会混乱。

### 6.7 Artifact

运行过程中产生的结构化对象。

例如：

- 文件
- 报告
- JSON
- source excerpt
- reading note
- review result
- trace summary

artifact 属于 run，但要记录来源 agent、thread、tool_call 或 execution。

### 6.8 Event

append-only 事件。

message、handoff、spawn、tool call、workspace upgrade、approval、artifact emitted 都是 event。

### 6.9 Checkpoint

从 event log 物化出来的快照。

checkpoint 用于 resume 和快速查询，不是事实源。

## 7. 硬分层

必须区分：

- `Run != Thread`
- `AgentSpec != AgentInstance`
- `Tool != ToolCall`
- `Workspace != Agent`
- `Proposal != Decision != Execution`
- `Event log != Snapshot`
- `Kernel != Domain Pack`
- `Application Persona != Runtime Policy`

这些区分是为了避免以后所有东西都变成聊天 transcript 或一堆隐式状态。

## 8. Action 三件套

`Isotope` 的核心执行闭环是：

1. `ActionProposal`
2. `PolicyDecision`
3. `ActionExecution`

### 8.1 ActionProposal

模型或系统提出的动作意图。

字段应该包括：

- `proposal_id`
- `run_id`
- `agent_id`
- `thread_id`
- `action_type`
- `payload`
- `requested_capabilities`
- `justification`
- `priority`
- `blocking`

`payload` 是动作参数，不叫 `target`，因为不同 action type 的结构完全不同。

### 8.2 PolicyDecision

runtime policy 对 proposal 的裁决。

结果至少包括：

- `approved`
- `modified`
- `denied`
- `pending_user_approval`
- `expired`

关键点是 `modified` 必须是一等结果。

runtime 很多时候不是完全拒绝，而是降权批准：

- 去掉 `edit_file`
- 把 `shared_rw` 降成 `isolated_rw`
- 把 `all_context` 缩成 `selected_artifacts_only`
- 降低 token / time budget

executor 只能读取 `PolicyDecision.grants`，不能读取 proposal 的 requested capabilities。

### 8.3 ActionExecution

一次实际执行尝试。

它必须绑定：

- `proposal_id`
- `decision_id`
- `action_type`
- `payload_snapshot`
- `effective_grants_snapshot`
- `workspace_binding`
- status
- result / failure

重试时创建新的 execution，用 `retry_of_execution_id` 串起来。

## 9. Action 事件流

最小事件流：

- `action.proposed`
- `action.decided`
- `action.execution_created`
- `action.started`
- `action.completed`
- `action.failed`
- `action.cancelled`

如果有人类审批：

- `approval.requested`
- `approval.resolved`

审批通过后应产生新的 decision 或明确的 decision supersession，而不是修改旧 decision。

## 10. 内核不变量

必须坚持：

- 所有模型发起的外部动作先进入 `ActionProposal`。
- 执行能力边界只能来自 `PolicyDecision.grants`。
- executor 不能读取未经裁决的 `requested_capabilities`。
- proposal、decision、execution 都必须进入 event log。
- execution 启动时固化 `effective_grants_snapshot`。
- artifact、tool output、worker id 必须反向挂回 execution。
- 未注册 action type 不允许执行。

## 11. ActionTypeRegistry

`ActionTypeRegistry` 不只是动作名字表。

它定义：

- `action_type`
- payload schema
- requested capabilities schema
- grant schema
- result schema
- executor kind
- default policy profile
- allowed callers
- cancellation support
- idempotency mode
- possible artifact types

v0 内置 action type 可以先很少：

- `spawn_worker`
- `call_tool`
- `handoff`
- `emit_artifact`
- `upgrade_workspace`

规则：

- decision 只能缩权 grants，不改 payload。
- 如果 payload 本身需要改，应该重新提 proposal。

## 12. Delegation 模型

推荐模式是 policy-gated dynamic delegation。

流程：

1. supervisor 形成当前计划。
2. 模型提议 spawn / handoff / tool / workspace upgrade。
3. runtime policy 裁决。
4. 通过后生成 event，启动 worker 或 tool。
5. worker 产出 artifact / refs。
6. supervisor 基于新状态继续。

不是让 LLM 随意发挥，而是：

- LLM proposal
- runtime arbitration
- evented execution

## 13. Worker 生命周期

v0 推荐：

- supervisor 常驻
- worker 默认短命
- 必要时可升级为 persistent

可升级条件：

- 长任务
- 需要连续 memory
- 需要独立 workspace
- 用户显式 pin

worker 的结果不应该只是一段聊天总结。

它应该通过 artifact / `ResourceRef` handoff。

## 14. Workspace 模型

workspace 是 kernel resource，不是 agent 人格的一部分。

推荐 hybrid：

- 默认共享只读 context
- 写操作、长任务、高风险工具升级到隔离 workspace

workspace 相关动作应被 event 化：

- workspace bound
- workspace lease created
- workspace released
- workspace artifact captured
- workspace upgrade requested

真实 filesystem、container、git worktree、remote executor 都可以 deferred，但概念上要为它们留好边界。

## 15. 持久化模型

推荐 hybrid：

- 底层 append-only event log
- 定期 snapshot / materialized view

event log 是事实源。

snapshot 用于：

- 快速恢复
- 查询优化
- resume

不能让 external raw log、provider response、workspace file 或 snapshot 直接覆盖 canonical state。

## 16. Tool / Skill / Domain Pack

kernel 只管通用执行能力。

domain pack 可以提供：

- tools
- prompts
- policies
- schemas
- evaluation rules
- corpus config
- persona / pedagogy / orientation

但 domain pack 不能绕开：

- action proposal
- policy decision
- execution
- event log
- artifact provenance

skill 未来可以是 procedural memory，但仍应被治理。

## 17. Study Companion 作为压力测试

study companion 不是 kernel，但能很好地压力测试：

- artifact-centric state
- artifact graph
- provenance-aware retrieval
- pack injection
- method hooks
- scheduler / review support
- capability-building surfaces

orientation、persona、pedagogy 和具体学习路线留在应用层。

kernel 不写死任何私有取向。

## 18. 和参考项目的关系

`Isotope` 应从参考项目学习压力点：

- `LangGraph`：durable execution、checkpoint、graph/state clarity
- `AutoGen`：event-driven multi-agent runtime
- `Codex` / `Claude Code`：coding harness、approval、workspace、review
- `OpenClaw`：gateway、session、skills、assistant continuity
- `GenericAgent`：context density、execution-verified memory、skill crystallization
- `PetGPT`：workspace realism、path-safe tools、trace/export
- `Hermes Agent`：memory + skills + gateway + learning loop

但这些都不是 kernel 模板。

## 19. 近期不应打开的东西

现在不应直接做：

- real HTTP server
- hosted SaaS
- real LLM loop
- provider adapter
- memory query engine
- plugin marketplace
- policy DSL
- full scheduler
- process kill
- real concurrency
- container / git worktree / remote executor
- full product UI

这些都需要更具体的 boundary doc 和测试。

## 20. 评估面

重要评估包括：

- event replay correctness
- checkpoint restore correctness
- action lifecycle correctness
- policy grants enforcement
- worker lifecycle correctness
- workspace isolation correctness
- artifact handoff correctness
- trace completeness
- domain pack 是否没有污染 kernel

domain pack 可以在 kernel 之上加自己的 benchmark。

## 21. 设计判断

`Isotope` 的核心不是“又一个 agent app”，而是一个让 agent 外部动作可提议、可裁决、可执行、可审计、可回放的 runtime control plane。

它应该保持：

- kernel-first
- policy-gated
- event-sourced
- workspace-aware
- artifact/provenance-first
- domain-pack friendly

如果未来长出 coding、study、grading、assistant 等产品，它们都应该建立在这个 kernel 上，而不是反过来把 kernel 改成某个产品的内部实现。
