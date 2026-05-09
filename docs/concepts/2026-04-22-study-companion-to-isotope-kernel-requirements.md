# Study Companion 对 Isotope Kernel 的要求

状态：`kernel requirement pressure`

## 1. 摘要

本文把 study companion 应用方向反压成 `Isotope` kernel requirements。

重点不是现在实现完整应用，而是说明：为了支撑这种应用，kernel 至少要在未来提供哪些能力。

核心判断：

- study companion 不是 kernel。
- 但它能很好地暴露 kernel 是否真的能支撑长期 agent 应用。
- 私有 orientation、corpus、persona 留在应用层。
- artifact、provenance、retrieval、memory、pack injection、review/scheduler 这些能力会反过来要求 kernel 设计更清楚。

## 2. 不能进 kernel 的东西

这些属于应用层或私有 pack，不应进入 kernel：

- Marxist / Marxist-Leninist orientation 内容
- 私有 corpus bundle
- 私有 source-priority rules
- persona voice / style
- ideology-specific evaluation labels
- 私有产品命名
- 具体学习路线

kernel 应该只提供通用能力，不写死某个取向。

## 3. Kernel 必须支持的通用能力

### 3.1 Artifact-Centric State

study companion 不能只靠聊天记录。

它需要长期存在的 artifact：

- reading note
- concept card
- question thread
- disagreement note
- study plan
- source excerpt
- purpose review
- study priority decision

这些 artifact 应该有：

- type
- summary
- content
- source refs
- provenance
- creating action
- supersession / update path

### 3.2 Artifact Graph

学习不是一条线。

一个 source excerpt 可能支持多个 concept card，一个 disagreement note 可能连接多个 reading note，一个 weekly review 可能引用多个 study plan。

因此 kernel 需要支持 artifact graph：

- artifact 之间可以有 typed links
- links 应该有 provenance
- links 可以从 event log 投影
- review 和 retrieval 可以沿 graph 找上下文

### 3.3 Provenance-Aware Retrieval

study companion 的回答必须能追来源。

retrieval 不能只返回裸文本。

它应该返回：

- structured `ResourceRef`
- source metadata
- excerpt / summary
- parse / retrieval diagnostics
- confidence / completeness
- caller context
- purpose

任何非平凡 synthesis 都应该能说明：

- 哪些来自 source
- 哪些来自 interpretation
- 哪些是 model inference

### 3.4 Information Access And Ingestion Substrate

信息访问不是实现细节，而是 kernel-adjacent requirement。

study companion 需要：

- web search
- document fetching
- PDF / HTML / text parsing
- source type detection
- structured excerpt extraction
- parse diagnostics
- ingestion result status

kernel 现在不需要指定：

- 哪个 search provider
- 哪个 parser
- 哪个 chunking 策略
- 哪个 embedding / reranker
- 哪个 index backend

但 kernel 要能区分：

- 没找到材料
- 找到了但没解析出来
- 解析了但不完整
- 解析成功但来源质量弱
- 引用了材料但 evidence 不足

这些状态对学习 agent 很关键。

### 3.5 Pack Injection

应用需要加载不同层：

- orientation pack
- method pack
- pedagogy pack
- persona pack
- corpus config
- evaluation rubric

kernel 不需要理解 pack 的意识形态内容，但需要知道：

- 哪些 pack 被加载了
- 版本是什么
- 作用在哪个 run / session
- 是否进入 trace
- 是否影响 action / artifact / memory

### 3.6 Method Exposure / Capability Building Hooks

应用目标不是只给答案，还要教会用户能力。

因此 kernel 或 platform service 应允许应用产出：

- study method note
- search strategy
- question refinement note
- capability gap note
- review recommendation

这些不一定是 kernel 内置类型，但 artifact system 要能表达。

### 3.7 Review And Scheduler Support

长期学习需要复习和回看。

未来需要：

- scheduled review
- recurring study check
- stale question detection
- unresolved concept resurfacing
- weekly / monthly review artifacts

当前可以 deferred，但设计上不能假设所有 run 都是一次性任务。

### 3.8 Analysis vs Operational Instruction Boundary

应用需要区分：

- 理论分析
- 历史分析
- 战略讨论
- 现实案例复盘
- 现实操作性指挥

前四类可以讨论，最后一类应被应用 policy 限制。

kernel 不需要内置具体政治判断，但要允许应用 policy 使用 reason codes、grants、review state 去表达这个边界。

### 3.9 Evaluation Surface

study companion 的效果不能只看用户聊得久不久。

应该能评估：

- notes 是否有来源
- 用户问题是否更清楚
- concept card 是否变多并可复习
- unresolved questions 是否被追踪
- 用户是否更能自己检索和比较
- 关键 claim 是否有 refs

这些 evaluation 需要 artifact、memory、trace 的共同支持。

## 4. 候选 Kernel 接口

未来可能需要的接口：

- `create_artifact(...)`
- `update_artifact(...)`
- `link_artifacts(...)`
- `retrieve_with_provenance(...)`
- `ingest_source(...)`
- `load_pack(...)`
- `write_memory_candidate(...)`
- `promote_memory(...)`
- `schedule_review(...)`
- `resume_context(...)`

这些只是 requirement pressure，不代表现在都要实现。

## 5. V0 最小切面

为了验证 study companion 方向，最小 slice 可以是：

1. 用已有 helper 创建 source artifact。
2. controlled retrieval 读取 source summary 或 full content。
3. 生成 reading note artifact。
4. 生成 purpose review 或 study priority decision artifact。
5. 记录 source refs 和 provenance。
6. replay / checkpoint 后仍能看到这些 artifact。

暂不打开：

- real web search
- real LLM loop
- durable memory query
- scheduler
- persona pack runtime
- real corpus ingestion

## 6. 设计判断

study companion 对 `Isotope` 的价值是把 kernel 从抽象正确拉向真实应用压力。

它要求 kernel 认真处理：

- artifact graph
- provenance-aware retrieval
- long-lived memory
- pack injection
- review / scheduler
- capability-building outputs

但这些都应该以通用 runtime 能力进入 `Isotope`，而不是把私有意识形态应用直接写进 kernel。
