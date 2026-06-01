# Isotope Kernel Living Spec（动态规格草案）

这份文档记录当前 `Isotope v0` kernel 的动态 contract（可演进约定）。它故意不是最终 spec，而是一份当前真相版本的设计草案。

## 1. Scope（范围）

当前 kernel 负责这些事情：

- session continuity（会话连续性）
- run execution（执行实例运行）
- supervisor 和 worker 的生命周期
- action proposal、policy arbitration（策略裁决）与 execution
- workspace binding（工作空间绑定）和 isolation upgrade（隔离升级）
- event logging（事件记录）和 checkpoints
- state projection（状态投影）和 external ingestion（外部输入摄取）边界
- artifact emission（产物生成）与 provenance（来源溯源）
- structured memory（结构化记忆）
- 通过 canonical refs（规范引用）做 retrieval（检索）
- approval pause / resume（审批暂停与恢复）

当前 kernel 还不打算在这份草案里定义：

- domain pack 的具体实现
- application-level orientation / persona / pedagogy（应用层方向、人格与教学法）
- public UI
- hosted multi-tenant 相关能力
- billing / quota 的产品语义

## 2. Top-Level Model（顶层对象模型）

### 2.1 Session

`Session` 是跨多个 `Run` 的 continuity boundary（连续性边界）。

预期职责：

- 绑定 assistant / policy 的默认值
- 拥有 session memory namespace（会话记忆命名空间）
- 维持用户或项目的连续上下文
- 跟踪当前或最近一次 run

`Session` 不直接承载执行状态。执行状态归 `Run`，session continuity（会话连续性）主要来自 session memory、artifacts、defaults 和最近 run 的引用，而不是无限延长的聊天记录。

当前建议 lifecycle（生命周期，v0 candidate）：

- `idle`
- `run_active`
- `waiting_approval`
- `errored`
- `archived`

### 2.2 Run

`Run` 是 execution boundary（执行边界）。

预期职责：

- 拥有自己的 event log
- 拥有自己的 artifacts
- 拥有 run memory
- 拥有 agent instances 和 threads
- 保存 workspace bindings
- 支持 pause、resume、cancel、replay 和 inspection

`Run` 必须能在没有在线 client 附着的情况下继续运行或恢复。

当前建议 lifecycle（v0 candidate）：

- `queued`
- `running`
- `blocked_on_approval`
- `paused`
- `completed`
- `failed`
- `cancelled`

### 2.3 Agent

当前预期分两层：

- `AgentSpec`
  - 静态 profile（画像 / 定义），包括 instructions、policy defaults、tool defaults
- `AgentInstance`
  - 某个 run 里的运行态 agent 实例

supervisor 和 worker 都属于 `AgentInstance` 的不同角色。

`AgentInstance` 默认只存在于某个 run 内。跨 run 连续性应来自 `Session Memory` 和 `AgentSpec` / profile，而不是复用同一个运行态对象。

### 2.4 Thread

`Thread` 是 context container（上下文容器），不是 `Run`，也不是 `AgentInstance` 本身。

预期职责：

- message history（消息历史）
- local plan（局部计划）
- thread working memory
- current sub-goal（当前子目标）

### 2.5 Workspace

`Workspace` 是 execution resource（执行资源），不是 agent 身份的一部分。

预期职责：

- 共享或隔离的执行模式
- lease / binding metadata（租约 / 绑定元数据）
- substrate-specific state（底层实现相关状态）

## 3. Action Model（动作模型）

### 3.1 ActionProposal

所有模型发起的外部动作，必须先变成一个 canonical `ActionProposal`。

模型侧可以先输出 compact action / intent（紧凑动作 / 意图），但 runtime 必须先把它编译成 canonical `ActionProposal`，再进入 policy 和 execution。

当前最小预期字段：

- ids: `proposal_id`, `run_id`, `agent_id`, `thread_id`
- `action_type`
- `payload`
- `requested_capabilities`
- `justification`
- `priority`
- `blocking`

这里的 `payload` 是 typed action body（带类型的动作体），它是 action-specific（动作特定）的，不是通用 `target`。

### 3.2 PolicyDecision

runtime policy 会对 proposal 进行评估，并返回一个 `PolicyDecision`。

当前最小 outcome 集合：

- `approved`
- `modified`
- `denied`
- `pending_user_approval`
- `expired`

关键 contract：

- 真正执行时使用 `grants`，不是 `requested_capabilities`
- `modified` 是一等结果，不是附属状态
- `pending_user_approval` 不会直接启动执行

### 3.3 ActionExecution

`ActionExecution` 表示一次具体的执行尝试。

关键 contract：

- 必须绑定一个 `decision_id`
- 启动时必须冻结 effective payload 和 grants
- retries（重试）要产生新的 execution id
- artifacts 和 outputs 应该能反向追到 execution id

### 3.4 Action Events

当前预期的事件序列：

- `action.proposed`
- `action.decided`
- `action.execution_created`
- `action.started`
- `action.completed`
- `action.failed`
- `action.cancelled`

approval 相关事件单独记录：

- `approval.requested`
- `approval.resolved`

### 3.5 Model-Facing Protocol Boundary（模型侧协议边界）

canonical schema（规范 schema）面向 runtime、storage、audit 和 replay，不等于模型必须直接输出的 schema。

当前 hard rule：

- policy、execution 和 event log 只消费 canonical objects
- model-facing protocol 可以更紧凑，但必须被 runtime 编译/校验成 canonical objects

当前 v0 candidate：

- `ActionCompiler`
- `RefHandle`
- `RenderedContextView`

这些名字和协议形态还不是最终协议。

## 4. Policy Boundary（策略边界）

当前预期规则：

- 所有外部动作都必须先变成 proposals
- runtime policy 是最终裁决者
- executor 不能读取未经裁决的 `requested_capabilities`
- grants 可以缩减 scope、tools、workspace mode、budgets
- 如果连 payload 本身都要改，应该新建一个 proposal，而不是偷偷改原提案

## 5. Memory Model（记忆模型）

### 5.1 Layers（分层）

- `Thread Working Memory`
  - 局部的、短暂的、面向当前步骤
- `Run Memory`
  - 在单个 run 内持久
- `Session Memory`
  - 跨 run 持久
- `Artifact Index`
  - 一个 retrieval surface，不是 memory 本体

### 5.2 Memory Shape（记忆形状）

memory 应当是结构化的，而且必须能追溯来源。

当前默认约束：

- 存 `content + preview/summary + refs + provenance`
- `content` 是结构化正文，不只是标题、标签或索引卡片
- 默认不内联大块内容
- 更新采用 append + supersession（追加 + 后续覆盖关系），而不是原地替换
- 常见检索路径应支持 `query + controlled expand`，让调用方在一次查询里请求受控展开若干 refs
- 受控展开仍然受 policy 和 ref-first access 约束，不等于绕过 retrieval policy

### 5.3 Promotion（晋升）

worker 默认不应该自由写入 `Session Memory`。

从 `Run Memory` 晋升到 `Session Memory` 应当是显式动作。

当前建议保留两个专门 action type（v0 candidate）：

- `write_memory`
- `promote_memory`

durable memory 写入应走正常动作链：`ActionProposal -> PolicyDecision -> ActionExecution -> canonical event`。

### 5.4 Memory Query（记忆查询）

`Memory Query` 是 read-side recall primitive（读侧回忆原语），不是每个 run 的固定阶段。

默认流程应是：

- 先看当前 thread / run state 是否足够
- 如果不足，再按需 query run / session memory
- query 结果返回 refs、preview/summary 和可选的 controlled expand 内容
- full materialization（完整物化）仍然交给 retrieval / ref-first access 决定

这样常见路径可以是 `query + controlled expand`，而不是强制 `query -> select -> retrieve` 三段式流程。

## 6. Canonical References（规范引用）

### 6.1 ResourceRef

正式的 canonical reference format（规范引用格式）是结构化 `ResourceRef`，不是字符串。

示意结构（Example only，不是最终协议）：

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

URI-like 写法只允许作为 display/debug 记法存在。

不同 `ref_type` 的完整 `locator` schema 还没定稿，但 formal API 里不应该把 artifact/memory/event/thread/workspace link 降级成裸字符串。

### 6.2 Ref-First Access（引用优先访问）

policy、retrieval 和 tool input 都先对 refs 生效。

runtime 解引用之后，再决定调用方最终能拿到：

- summary（摘要）
- full content（全文 / 全量内容）
- structured slice（结构化片段）
- denial（拒绝）

## 7. Persistence Model（持久化模型）

### 7.1 Canonical Event Log

canonical event log（规范事件日志）是 append-only 的，也是 `RunState` / `SessionState` 的唯一 source of truth（事实来源）。

外部原始日志、第三方 callback 原文、provider 原始响应、workspace 文件或数据库快照，都不能直接驱动 state projector（状态投影器）。

durable objects（耐久对象）只有两种方式能影响 `RunState` / `SessionState`：

- 被 canonical event 引入、注册并钉住
- 或者作为 canonical event 自己携带的规范化事实

### 7.2 Checkpoints And Materialized Views

checkpoints（检查点）和 materialized views（物化视图）都由 canonical events 推导出来，主要用于：

- recovery（恢复）
- inspection（检查）
- 更高效的 API 读取

这些视图的完整 schema 目前仍然开放，但它们的 source-of-truth 边界已经确定：只能由 canonical events 投影出来。

### 7.3 External Ingestion And ImportedSnapshot（外部摄取与导入快照）

外部输入必须先经过 ingestion（摄取 / 规范化），不能直接更新 `RunState` / `SessionState`。

ingestion 只有三种结果：

- 变成本地 `CanonicalEvent`
- 变成 typed `ImportedSnapshot`，并由 canonical event 注册/引用
- 只作为 `Artifact` / `Provenance` 保存，不参与状态推进

`ImportedSnapshot` 不是第二个事实源。它只是某个外部系统在某一时刻的受限观察，已经由 adapter 规范化，但仍然保留“外部观察”的身份。这个名字和 `snapshot.imported` 事件名属于 v0 candidate。

它和 checkpoint snapshot 必须区分：

- `Checkpoint` 是内生事件重放后的恢复快照
- `ImportedSnapshot` 是外部观察对象，不参与恢复事实的生成

最小准入流程：

1. 外部原始输入先落成 raw artifact。
2. adapter 读取 raw artifact，产出 typed `ImportedSnapshot`。
3. runtime 校验 schema、identity mapping、timestamp、provenance 和 adapter version。
4. 校验通过后写入 `snapshot.imported` canonical event。
5. projector 只消费 `snapshot.imported` event，不直接读 raw artifact。

最小准入条件：

- `source_system`
- `captured_at`
- `adapter_version`
- `content_schema_ref`
- `raw_artifact_ref`
- `quality.confidence`
- `quality.coverage`
- 可解释的 identity mapping，比如外部 run id 映射到本地 run id

如果 canonical event 只引用 snapshot ref，则该 ref 必须 version-pinned（版本钉住）或 content-addressed（内容寻址），并能校验 digest/schema/version。否则重放会依赖可变对象，破坏 event log 的事实边界。

### 7.4 State Projection Rules（状态投影规则）

`RunState` / `SessionState` 里的字段分三类。

`native_only`：只能由本地 canonical events 推进。

- `Run.status`
- `AgentInstance.status`
- `ActionExecution.status`
- `PolicyDecision`
- `Approval`
- `WorkspaceBinding`
- `Checkpoint`
- `Session.defaults`
- `Session.policy_profile`
- `Session.current_run`

外部 snapshot 不能直接覆盖这些字段。比如外部系统说“完成了”，但本地还没有 `action.completed`，那只能记录为 external observation（外部观察），不能直接把本地 `ActionExecution.status` 改成 `completed`。

如果 adapter / reconciler（调和器）验证外部状态足以确认本地执行结果，runtime 必须先追加本地 canonical event，例如 `action.completed` 或 `action.failed`，再由 projector 更新 native state。

`imported_eligible`：可以由 `ImportedSnapshot` 形成观察值。

- external provider status
- remote task progress
- remote token usage
- external step summary
- imported artifact availability
- external error diagnostics
- freshness / coverage / confidence

这些字段应挂在 `observations`、`external_status` 或 `diagnostics` 一类的观察域下，并带 `basis_refs`。

`derived`：可以由 native events 和 imported observations 共同计算，但必须标明质量。

- progress summary
- health indicator
- “可能卡住”
- “外部执行已结束但本地未确认”
- “状态不一致”

所有 derived 字段都必须带 observation metadata（观察元数据）：

- `source_kind`: `native_event | imported_snapshot | derived`
- `confidence`: `high | medium | low`
- `coverage`: `complete | partial | sparse`
- `freshness_at`
- `basis_refs`

冲突规则：

- native canonical event 永远优先于 imported snapshot
- imported snapshot 不覆盖 native state，只能补充 observation
- 多个 imported snapshots 冲突时，标记 conflict，不能合并成假确定性
- projector 输出的精度不能超过 adapter 标注的 quality

## 8. Server Model（服务端模型）

当前方向：

- `server-first`
- `HTTP JSON + SSE` 对 `v0` 已经足够，但不是永久 transport contract
- run 应该能在没有附着 client 的情况下继续运行和恢复

最小 API surface（接口面）现在还没完全定稿，但至少应覆盖：

- sessions
- runs
- event stream
- artifacts
- approvals
- memory query，包括受 policy 约束的 controlled expand

当前建议的 v0 endpoint sketch（接口草图）：

- `POST /v0/sessions`
- `GET /v0/sessions/{session_id}`
- `PATCH /v0/sessions/{session_id}`
- `POST /v0/sessions/{session_id}/inputs`
- `POST /v0/sessions/{session_id}/runs`
- `GET /v0/runs/{run_id}`
- `POST /v0/runs/{run_id}/resume`
- `POST /v0/runs/{run_id}/cancel`
- `GET /v0/runs/{run_id}/events`
- `GET /v0/runs/{run_id}/stream`
- `GET /v0/runs/{run_id}/artifacts`
- `GET /v0/runs/{run_id}/agents`
- `POST /v0/approvals/{approval_id}/resolve`
- `POST /v0/sessions/{session_id}/memory/query`
- `POST /v0/runs/{run_id}/memory/query`

UI、CLI 和 API client 应消费同一套 event stream，不应各自维护一套不可回放的内部 orchestration state（编排状态）。

## 9. Reference And Application Pressure Tests（参考与应用压力测试）

当前主线吸收的是参考项目暴露出来的边界问题，不是照搬它们的架构。

### 9.1 GenericAgent

`GenericAgent` 对 `Isotope` 的主要价值是提醒 kernel 区分：

- active context（当前决策上下文）要高密度
- durable state（耐久状态）要结构化、可追溯、可检索、可回放

不应直接复制：

- file-SOP memory 作为 kernel truth model
- prompt/SOP obedience 作为 runtime policy
- “开发过程 skill” 作为产品运行时 contract

### 9.2 PetGPT

`PetGPT` 对 `Isotope` 的主要价值是 execution-substrate realism（执行基座现实性）：

- workspace-backed state
- path-safe workspace primitives
- user-visible tool/session gating
- tool-loop guardrails
- subagent lifecycle control
- prompt-cache observability
- trace/export discipline

这些模式可以变成 kernel 或 platform service 的压力测试，但 workspace files 不替代 canonical event log、typed artifacts、typed refs、policy decisions 和 state projection。

### 9.3 Hermes Agent

`Hermes Agent` 对 `Isotope` 的主要价值是提醒 kernel 不要只验证一次性工具调用，而要能承受长期 agent product 的压力：

- persistent memory（持久记忆）
- skills / procedural memory（技能与过程记忆）
- gateway / messaging surfaces（网关和消息入口）
- scheduled tasks（调度任务）
- subagent delegation（子 agent 委派）
- provider routing / fallback（模型路由与回退）
- real execution backends（真实执行后端）

这些都是重要压力点，但不应直接变成 kernel product scope。

`Isotope` 应该从中吸收 learning-loop pressure（学习闭环压力），但仍保持 action proposal、policy decision、execution、artifact provenance、event replay 和 checkpoint 是 runtime truth。

详细比较见 [Isotope vs Hermes Agent](../../archive/concepts/isotope-vs-hermes-agent.md)。

### 9.4 Study Companion

study companion 是重要的 first application pressure test（第一应用压力测试），但不是 kernel 本身。

它提出的通用 kernel 要求包括：

- artifact-centric state（以产物为中心的状态）
- artifact graph（产物图）
- provenance-aware retrieval（来源感知检索）
- pack injection（包注入）
- method hooks（方法钩子）
- scheduler / review support（调度与复习支持）
- capability-building surfaces（能力培养界面）

orientation、persona、pedagogy 和具体学习路线应留在 application/domain pack 层。kernel 不写死某种私有 orientation。

## 10. Relationship To x-agent（与 x-agent 的关系）

`x-agent` 依然有价值，但它不再是当前 kernel 的目标形状。

它提供的是：

- recipe-oriented 设计证据
- 领域特定执行链
- 未来可能沉淀成 tool pack / domain pack 的材料

它不负责定义 `Isotope` 的规范对象模型。

## 11. Open Questions（开放问题）

- `ActionTypeRegistry` 应该如何表示、如何版本化？
- `ResourceRef` 的完整变体集合到底有哪些？
- 不同 action types 下，`ActionExecution.result` 应该长什么样？
- retrieval policy 应该如何切片和做内容裁剪？
- 第一版最小 `RunState` 物化视图的具体字段长什么样？
- 第一版最小 `SessionState` 物化视图的具体字段长什么样？
- workspace substrate adapters（执行基座适配器）应该怎么建模？
- 第一条能真正证明 kernel 的 vertical slice（纵向切片）到底是什么？
