# Isotope Commitment Levels（承诺强度分层）

这份文档用于防止 exploratory design（探索性设计）里的例子、字段和候选方案被误读成最终架构决定。

## Hard Contract（硬约束）

Hard contract 是当前不应轻易回滚的架构边界。它们通常影响多个模块、长期数据形状、审计/回放能力或安全边界。

当前 hard contracts：

- `Isotope` 是 kernel-first、domain-agnostic runtime，不是 `x-agent` recipe runtime 的延伸。
- `Session` 是 continuity boundary（连续性边界），`Run` 是 execution boundary（执行边界），执行状态归 `Run`。
- supervisor / worker 是 kernel 一等概念；模型可以提出 delegation，但 runtime policy 是最终裁决者。
- 外部动作必须进入 canonical action chain：`ActionProposal -> PolicyDecision -> ActionExecution -> canonical event`。
- 执行时只能使用 `PolicyDecision.grants`，不能使用未经裁决的 requested capabilities。
- `PolicyDecision.modified` 是一等 outcome，runtime 可以缩权后批准。
- 正式协议使用结构化 `ResourceRef`；URI-like 写法只能用于 display/debug。
- `RunState` / `SessionState` 的唯一 source of truth 是 canonical event log。
- 外部 raw log、provider response、callback 原文不能直接驱动 state projector。
- 外部输入必须先经过 ingestion；`ImportedSnapshot` 只是被 canonical event 接纳过的外部观察，不是第二事实源。
- `MemoryRecord` 不能只是索引卡片；它需要结构化 `content` 和 provenance。
- memory 不是 transcript dump，durable memory 写入必须可审计、可追溯。

## v0 Candidate（v0 候选方案）

v0 candidate 是当前推荐推进方式。它可以进入 living spec，但不应被写成不可变协议。

当前 v0 candidates：

- `server-first` 是方向；`HTTP JSON + SSE` 是 v0 起点，不是永久 transport contract。
- `single-user local/server first` 是 v0 deployment scope，不是长期产品边界。
- supervisor 持久、worker 默认短命、必要时 promotion，是当前 lifecycle candidate。
- 默认共享偏只读 workspace，写操作/长任务/高风险任务升级到 isolated workspace，是当前 workspace policy candidate。
- `write_memory` / `promote_memory` 是推荐 action type 名；硬规则是 durable memory 写入必须走动作链。
- `Memory Query + controlled expand` 是推荐 recall 路径；硬规则是 controlled expand 不能绕过 retrieval policy。
- `ResourceRef` 的 `ref_type / scope / locator / selector / version` 是 v0 shape，完整变体仍未定稿。
- `ImportedSnapshot`、`snapshot.imported` 和 state 字段三分类是当前推荐建模方式，具体命名和 schema 可调整。
- `Run` / `Session` lifecycle 枚举、action event 名称、endpoint list 都是 v0 candidate。
- model-facing compact protocol（模型侧紧凑协议）/ action compiler（动作编译器）应作为 v0 candidate 继续设计，用来降低模型直接输出复杂 canonical JSON 的难度。

## Example / Schema Sketch（示例 / 草图）

example / schema sketch 只帮助解释概念，不能当最终协议。

属于 example / sketch 的内容：

- 对话和文档中的 JSON 样例。
- `ActionProposal`、`PolicyDecision`、`ActionExecution`、`ActionTypeRegistry` 的字段示例。
- `MemoryRecord`、`ResourceRef`、`RetrievalRequest/Response`、`MemoryQuery` 的字段示例。
- `RunState` / `SessionState`、`ImportedSnapshot`、observation metadata 的 JSON 示例。
- endpoint list 和 URI-like display examples。
- selector 类型、ref type 变体、view mode、quality enum。

写入文档时应明确标注 `Example only` 或 `v0 candidate shape`。

## Open Question（开放问题）

open question 是还没到锁定时机的问题。它们可以被讨论，但不能因为 AI 写了一版就升级成 decision。

当前 open questions：

- `ActionTypeRegistry` 的 schema、版本化、注册生命周期。
- `ActionExecution.result` 的统一形状、retry / cancel / supersede 语义。
- `RunState` / `SessionState` 的具体字段 schema。
- `ResourceRef` 的完整 locator / selector 变体。
- retrieval policy 的 ranking、裁剪、budget、expand 降级策略。
- model-facing compact protocol 的具体形式：JSON、tool calling、mini DSL，还是多模式。
- approval API、approval event 与 blocked/resume 的细节。
- workspace substrate 第一版用 process、git worktree、container 还是 remote executor。
- domain pack 接口和第一条 vertical slice。

## Conflict Notes（冲突与降级记录）

- `server-first` 是 hard direction；`HTTP JSON + SSE` 只是 v0 candidate。
- durable memory 写入必须走动作链是 hard contract；`write_memory` / `promote_memory` 只是推荐 action type 名。
- `ResourceRef` 是 hard contract；当前 JSON shape 是 v0 candidate，代码块只是 illustrative sketch。
- 模型可以输出 compact action；runtime 必须先编译成 canonical `ActionProposal`，再进入 policy / execution。
- one-pager 和 decision log 应避免把 hard contract、v0 candidate 和 schema sketch 混在同一个“已经决定了”列表里。
