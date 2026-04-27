# Isotope Kernel Decision Log（决策日志）

这个文件记录当前 `Isotope v0` 方向里，已经做出的关键架构选择。

`Commitment` 表示承诺强度：

- `hard_contract`: 当前不应轻易回滚的架构边界。
- `accepted_direction`: 已接受的方向，但具体实现仍可调整。
- `v0_candidate`: 当前推荐实现赌注，不是最终协议。

## Decision 001: Kernel-first，而不是 domain-first

- 状态: `accepted`
- Commitment: `hard_contract`
- 原因:
  - 目标是一个通用 agent runtime/platform
  - `grading` 应该是未来的 domain pack，而不是整个架构中心
- 放弃的备选:
  - 先做 grading-first runtime，再向外扩

## Decision 002: Supervisor-kernel-first

- 状态: `accepted`
- Commitment: `hard_contract`
- 原因:
  - kernel 必须原生支持 delegation、arbitration（裁决）和 recovery（恢复）
  - graph-centric 设计太容易重新滑回 workflow orchestration（工作流编排）
- 优先级顺序:
  - `A`: supervisor-kernel-first
  - `C`: execution-substrate-first
  - `B`: graph-centric runtime

## Decision 003: Agent server-first

- 状态: `accepted`
- Commitment: `accepted_direction`
- 原因:
  - 目标是 platform/runtime，不只是本地 CLI 工具
  - session continuity（会话连续性）、resume（恢复）和 approvals（审批）更适合 server 形态
- 结论:
  - `server-first` 是 accepted direction
  - run 应该能在没有在线 client 附着的情况下继续运行或恢复
  - UI、CLI 和 API client 应消费同一套 event stream
- v0 candidate:
  - `HTTP JSON + SSE` 是 `v0` 足够好的 server API 起点，但不是永久 transport contract
- 放弃的备选:
  - SDK/library-first
  - CLI-first

## Decision 004: Single-user local/server first

- 状态: `accepted`
- Commitment: `v0_candidate`
- 原因:
  - 先把 runtime semantics（运行时语义）收紧，再谈多租户
- 暂缓:
  - team self-hosted
  - hosted multi-tenant

## Decision 005: Hybrid lifecycle

- 状态: `accepted`
- Commitment: `accepted_direction`
- 原因:
  - 持久 supervisor 能保连续性
  - 默认短命的 worker 能让常见路径更轻
  - promotion（提升为更持久实例）保留了长任务和有状态任务的灵活性
- 结论:
  - supervisor / worker lifecycle 是 kernel 关注点，worker 不是普通函数调用
  - `Session` 是 continuity boundary，不直接承载执行状态
  - `Run` 是 execution boundary，执行状态归 run
  - `Thread` 是 context container，承载消息、局部计划和 working memory
  - `AgentInstance` 默认只存在于某个 run 内，跨 run 连续性来自 `Session Memory` 和 profile
- v0 candidate:
  - supervisor 持久
  - worker 默认短命，但必要时可提升

## Decision 006: Policy-gated dynamic delegation

- 状态: `accepted`
- Commitment: `hard_contract`
- 原因:
  - 动态性应来自模型
  - 控制权和安全边界必须留在 runtime
- 放弃的备选:
  - fully model-driven execution
  - mostly static runtime-driven delegation

## Decision 007: Hybrid workspace model

- 状态: `accepted`
- Commitment: `accepted_direction`
- 原因:
  - 共享上下文更快
  - 隔离写执行更安全
- 结论:
  - workspace 是 policy-bound execution resource
  - workspace isolation / sharing 由 runtime policy 控制
- v0 candidate:
  - 默认共享、偏只读
  - 写操作、长任务或高风险工具切到 isolated workspace

## Decision 008: Event log plus snapshots

- 状态: `accepted`
- Commitment: `hard_contract`
- 原因:
  - replay（回放）、audit（审计）、resume 和 debug 需要不可变的执行事实
  - 但真实恢复和查询仍然需要 snapshots
- 放弃的备选:
  - 纯 event-only，所有状态都靠回放恢复
  - snapshot-first，但事件历史很弱

## Decision 009: Three-part action model

- 状态: `accepted`
- Commitment: `hard_contract`
- 原因:
  - proposal（提案）、authorization（授权）和 execution（执行）必须分开
- 结论:
  - `ActionProposal`
  - `PolicyDecision`
  - `ActionExecution`
- 硬规则:
  - 所有模型发起的外部动作都必须先变成 proposal
  - 真正执行时只能使用 `PolicyDecision.grants`
  - 即使没有真正执行，proposal 和 decision 也必须入事件日志
- 模型侧边界:
  - 模型可以输出 compact action / intent
  - runtime 必须先编译并校验成 canonical `ActionProposal`，再进入 policy / execution

## Decision 010: 用 `payload`，不用 `target`

- 状态: `accepted`
- Commitment: `v0_candidate`
- 原因:
  - 不同 action type 的目标结构差异太大，需要更灵活的结构化 body
- 放弃的备选:
  - 一个泛化的 `target` 字段

## Decision 011: `PolicyDecision` 必须支持 modified approval

- 状态: `accepted`
- Commitment: `hard_contract`
- 原因:
  - runtime 很多时候不是完全拒绝，而是缩权后允许
- 结论:
  - `modified` 是一等 outcome（结果）
  - grants 可以缩减 tools、workspace mode、context scope、budget

## Decision 012: 用结构化 `ResourceRef` 作为规范引用协议

- 状态: `accepted`
- Commitment: `hard_contract`
- 原因:
  - 字符串适合展示，但不适合做正式协议和 policy 裁决
- 结论:
  - 正式 API 统一使用结构化 refs
  - URI-like 字符串只做 display/debug

## Decision 013: Memory 要分层，而且必须 ref-first

- 状态: `accepted`
- Commitment: `hard_contract`
- 原因:
  - transcript（聊天记录）不是足够好的 memory model
  - 大内容应该留在 artifact 或外部存储里
  - memory 如果只有标题、标签和索引信息，无法支撑真实 recall（回忆 / 调用）
- 结论:
  - thread working memory
  - run memory
  - session memory
  - artifact index 只是 retrieval surface（检索入口），不等于 memory 本体
  - `MemoryRecord` 必须有结构化 `content`，同时保留 preview/summary、refs 和 provenance
  - durable memory 写入必须走可审计的 action chain
  - `Memory Query` 是 on-demand recall primitive，不是每个 run 的固定循环阶段
- v0 candidate:
  - `write_memory` / `promote_memory` 是推荐 action type 名
  - 常见路径应支持 `query + controlled expand`，但展开仍然受 policy 和 ref-first access 约束

## Decision 014: `x-agent` 是设计证据，不是 kernel 目标

- 状态: `accepted`
- Commitment: `hard_contract`
- 原因:
  - 当前这条 fork 已经越过了 recipe-oriented runtime 设计
- 结论:
  - 现有 `x-agent` 代码仍然是很有价值的设计证据和未来 domain/tool material
  - 但它不再定义 `Isotope` 的规范架构

## Decision 015: `RunState` / `SessionState` 只能由 canonical event 投影

- 状态: `accepted`
- Commitment: `hard_contract`
- 原因:
  - replay、audit、resume 和 debug 需要一个可重放的事实边界
  - 外部 raw log、provider response、callback 原文的语义和质量不稳定，不能直接成为内核状态
- 结论:
  - `RunState` / `SessionState` 的唯一 source of truth 是 canonical event log
  - checkpoints 和 materialized views 都是由 canonical events 推导出来的读模型
  - durable objects 只有在被 canonical event 引入/钉住，或作为 canonical event 携带的规范化事实时，才能影响状态
  - state projector 不直接读取外部原始内容、workspace 文件或第三方响应来更新状态

## Decision 016: 外部输入必须经过 ingestion，并保留观察质量

- 状态: `accepted`
- Commitment: `hard_contract`
- 原因:
  - 外部系统的状态精度取决于 adapter 质量，kernel 不能假装比外部源更懂
  - 外部半残状态如果被包装成干净 native state，会误导 UI、API 和恢复逻辑
- 结论:
  - ingestion 只有三种结果：canonical event、被 canonical event 接纳的 external observation、或 artifact/provenance-only
  - `ImportedSnapshot` 是当前推荐的 external observation 建模方式；它不是第二个事实源，也不是 checkpoint
  - imported observations 只能进入 `observations`、`external_status`、`diagnostics` 等观察域
  - native state 永远优先；imported snapshot 不覆盖 native state
  - imported / derived 状态必须带 `confidence`、`coverage`、`freshness_at` 和 `basis_refs`

## Decision 017: 参考项目只做 pressure test，不做模板

- 状态: `accepted`
- Commitment: `hard_contract`
- 原因:
  - `GenericAgent`、`PetGPT` 等项目能暴露 Isotope 边界缺口，但它们的产品形态和约束不等于 Isotope kernel
  - 开发流程 skill / SOP 不应被误读成 runtime 架构
- 结论:
  - `GenericAgent` 的可保留原则是 active context density（活跃上下文密度）和 provenance-backed durable memory（有来源的耐久记忆）
  - `PetGPT` 的可保留原则是 workspace-backed state、path-safe primitives、tool/session guardrails、subagent lifecycle control 和 trace/export discipline
  - file conventions、prompt/SOP obedience、开发过程 skill 不能替代 kernel 的 event log、policy decision、typed refs 和 state projection contract

## Decision 018: Study companion 是 kernel 压力测试，不是 kernel 本身

- 状态: `accepted`
- Commitment: `hard_contract`
- 原因:
  - 私有 study companion 方向能很好地压力测试 memory、retrieval、artifact graph、delegation 和 capability-building
  - 但 orientation/persona/method/pedagogy 是 application/domain pack 层关注点
- 结论:
  - kernel 保持 domain-agnostic
  - 私有 orientation、persona、学习方法和能力培养逻辑放在 application/domain pack 层
  - kernel 只承接它们提出的通用需求：ref-first provenance、artifact-centric state、policy-gated delegation、on-demand memory query 和可审计状态投影

## Decision 019: Model-facing protocol 不等于 canonical schema

- 状态: `accepted`
- Commitment: `v0_candidate`
- 原因:
  - canonical schema 适合 runtime、storage、audit 和 replay，不一定适合模型直接稳定输出
  - 低级模型或窄上下文场景可能需要更紧凑的模型侧动作表达
- 结论:
  - 模型可以输出 compact action / intent，但 runtime 必须先编译成 canonical `ActionProposal`
  - policy、execution、event log 只消费 canonical objects
  - `ActionCompiler`、`RefHandle`、`RenderedContextView` 等名字和具体协议形态仍是 v0 candidate / open question
