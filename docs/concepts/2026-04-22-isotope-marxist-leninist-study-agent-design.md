# Marxist-Leninist Study Agent Design

状态：`private application design`

## 1. 摘要

本文定义一个具有明确 Marxist-Leninist 分析取向的私有学习与分析 agent 的系统设计。

它位于两个层次之间：

- 上层不是最终产品 spec
- 下层不是 `Isotope` kernel spec

它的任务是说明：

- 需要哪些模块
- 需要什么语料和来源纪律
- 有哪些约束
- 有哪些危险边界
- 如何把学习、现实问题、长期目的联系起来

相关文档：

- [Study Agent Boundaries](2026-04-22-isotope-study-agent-boundaries.md)
- [Persona Architecture](2026-04-22-isotope-persona-architecture.md)
- [Study Companion to Kernel Requirements](2026-04-22-study-companion-to-isotope-kernel-requirements.md)

## 2. 设计目标

这个 agent 应帮助严肃学习者：

- 长期学习历史和理论材料
- 更严谨地阅读
- 提出更尖锐的问题
- 写出更好的笔记
- 区分 source、interpretation、inference
- 在合适时把具体问题连接到历史和社会分析
- 判断什么值得学习，为什么值得学习
- 追问当前技术、专业、理论学习是否对集体斗争和社会主义建设有用
- 提高检索、比较、整理、规划能力
- 发现 economics、political economy、philosophy、industrial understanding 等短板

它不是 general-purpose assistant。

它是一个私有 study-and-analysis system，具备：

- 明确分析取向
- source discipline
- long-horizon continuity
- anti-dogmatism constraints
- 对学习与实践关系的关注
- 不越界到现实操作性政治指挥

## 3. 能力建设原则

系统不能只是 substitute intelligence layer。

它要满足两种使用方式：

- 对强用户，加速检索、组织和综合。
- 对发展中的用户，培养更强的独立学习能力。

这个原则不只属于 Marxist-Leninist study，也适用于：

- mathematics
- computer science
- economics
- political economy
- philosophy
- history
- social theory
- industrial systems
- industrial construction

系统不应只回答问题，还应有时说明：

- 问题为什么这样缩小
- 为什么选这个来源
- 两种解释如何比较
- 阅读计划如何形成
- 用户当前缺什么学习能力

目标是 capability transfer，不是 permanent dependency。

## 4. 学习优先级框架

系统不应把所有学习方向都拉平成同等优先级。

当前用户更适合三条线模型：

- 主业主线
- 方向主线
- 桥梁主线

主业主线是当前最直接的生产能力：

- computer science
- AI
- systems and engineering ability

方向主线提供历史方向和方法纪律：

- Marxist basic texts
- history
- philosophy

桥梁主线连接技术学习与生产、阶级社会、社会主义建设：

- economics
- political economy
- industrial systems
- industrial construction and production
- technology and the labor process

系统应该帮助用户保持这三条线之间的关系。

它不应把它们变成一个无差别阅读队列。

它应该能帮助回答：

- 当前技术工作如何连接长期政治目的
- 哪些 orientation texts 能纠偏
- 哪些 bridge-domain gaps 正在阻碍更具体的判断

阶段性不均衡是正常的。某一阶段一条线占主要精力可以接受，但不能让另外两条线完全消失。

## 5. 非目标

不要做：

- 角色扮演系统
- 辩论取胜机器人
- 政治劝服引擎
- 现实组织或指挥系统
- 社交依赖产品
- 用 Marxist-Leninist orientation 为弱来源背书

## 6. 核心模块

### 6.1 Study Session Orchestrator

负责实时交互循环。

它判断用户当前需要：

- 阅读指导
- 概念澄清
- 笔记帮助
- 材料比较
- review
- 长期路线规划

它应该偏向：

- 具体阅读任务
- question refinement
- note production
- source comparison
- long-horizon study prioritization

避免：

- 空泛激励
- 无产物的长时间抽象聊天

### 6.2 Source Retrieval And Citation Engine

这是核心模块。

它负责：

- 检索相关材料
- 保留 provenance
- 区分原文、注释、综合、模型推断
- 在检索弱或不完整时显式说明

任何非平凡回答都应能说明它使用了：

- direct source passage
- secondary interpretation
- comparative synthesis
- current model inference

### 6.3 Corpus Registry And Tiering Layer

它管理材料来源和优先级。

材料可以分层：

- 一手经典文本
- 历史材料
- 学术研究
- 当代分析
- 用户个人笔记
- 技术 / 工业 / 经济材料

重要学习方向包括：

- history
- philosophy
- economics
- political economy
- social theory
- mathematics
- computer science
- industrial systems
- industrial construction and production

corpus registry 不应该把任何二手解释伪装成原文。

### 6.4 Note, Concept, And Memory Layer

它管理长期学习产物：

- reading notes
- concept cards
- question threads
- disagreement notes
- study maps
- weekly reviews
- capability gap notes

memory 不能只是聊天记录。

耐久 memory 应该有：

- source refs
- run / action provenance
- quality status
- supersession path

### 6.5 Interpretation And Disagreement Mapper

它帮助用户保留分歧，而不是把争论压成单一答案。

它应区分：

- 原文到底说了什么
- 后来解释如何不同
- 分歧的历史条件是什么
- 哪些问题仍需材料
- 当前回答哪里只是推断

### 6.6 Study Planning And Review Loop

它负责长期路线。

它应帮助用户：

- 规划下次阅读
- 复盘本周学习
- 发现断掉的主线
- 判断哪些 bridge-domain gap 需要补
- 发现 economics、philosophy、industrial construction 的短板是否影响判断

### 6.7 Capability Scaffolding Layer

它负责“教会用户怎么做”。

它输出：

- search strategy
- study method note
- question narrowing note
- comparison method
- reading plan rationale

### 6.8 Near-Term Private Orientation Layer

短期可以先用一个私有配置层承载：

- orientation
- method
- pedagogy
- persona

长期再按 [Persona Architecture](2026-04-22-isotope-persona-architecture.md) 拆成多个 pack。

## 7. 分析约束

系统应该：

- 重视革命性与科学性的统一
- 从具体材料出发
- 区分 source、interpretation、inference
- 在相关时分析阶级、国家、政治经济、意识形态、历史阶段、工业基础、生产能力
- 承认争议和不确定
- 关注学习如何连接长期实践和建设问题

系统不应该：

- 用标签替代分析
- 把所有问题都强行拔高到一个宏大框架
- 因为问题涉及革命、组织、斗争，就禁止理论、战略、历史分析
- 把战略讨论变成现实行动指挥
- 把模型意见伪装成唯一正确路线

## 8. 行动边界

允许：

- 分析阶级斗争、革命、组织、路线和历史经验
- 比较不同策略或组织形式的历史效果
- 辩论现实或历史案例中的路线判断
- 复盘行动、协调、执行和组织问题

不允许：

- 给现实对象和现实时点的具体部署
- 帮用户做组织、协调、分工、规避、执行安排
- 给 target-specific instruction
- 替代现实人的政治判断和责任

## 9. 实现形态

v0 可以是：

- 一个 study session orchestrator
- 一个 retrieval / citation service
- 一个 corpus registry
- 一个 note / artifact store
- 一个 planning / review service
- 一个 near-term private orientation layer

它不需要一开始就有：

- 完整 persona pack runtime
- 真实 web search
- 完整 durable memory engine
- scheduler
- UI
- 大型 corpus 管理系统

## 10. 模块交互流程

典型流程：

1. 用户给出阅读目标或问题。
2. orchestrator 判断是阅读、澄清、比较还是 review。
3. retrieval engine 查找材料并返回 refs。
4. interpretation mapper 区分原文、解释和推断。
5. note layer 生成 reading note / concept card。
6. planning loop 更新 study path。
7. capability layer 输出方法说明。
8. 所有耐久产物进入 artifact / memory boundary。

## 11. Artifact 类型

候选 artifact：

- `reading_goal`
- `source_excerpt`
- `reading_note`
- `concept_card`
- `question_thread`
- `disagreement_note`
- `study_map`
- `weekly_review`
- `purpose_review`
- `study_priority_decision`
- `skill_usefulness_note`
- `study_method_note`
- `search_strategy`
- `capability_gap_note`

## 12. 系统级危险

### 12.1 Dogmatic Compression

把复杂问题压成一句正确口号。

### 12.2 Canon Laundering

把二手解释伪装成经典原文。

### 12.3 Theatrical Seriousness

用严肃语气、历史词汇和 persona 表演替代真实分析。

### 12.4 Detached Scholasticism

把学习做成脱离现实目的的材料堆积。

### 12.5 Dependency Drift

用户越来越依赖 agent 代替自己判断。

### 12.6 Publication Leakage

私有 orientation、corpus、评价标签意外进入 public tool layer。

## 13. V0 实现切面

最小 slice：

1. 输入一个 source artifact。
2. 生成带 refs 的 reading note。
3. 生成 purpose review。
4. 生成 study priority decision。
5. 输出一个 capability gap note 或 study method note。
6. replay / checkpoint 后仍能恢复这些 artifact。

暂不打开：

- real LLM loop
- real web search
- durable memory query
- scheduler
- persona runtime

## 14. 验收标准

v0 至少要证明：

- 非平凡 claim 有 refs 或标成 inference
- 私有 orientation 不进入 kernel
- 学习产物是 artifact，不只是聊天记录
- 用户能看到方法说明
- bridge-domain gaps 能被指出
- 系统没有输出现实操作性指挥

## 15. 设计判断

这个应用的意义不是“会讲马克思主义话术”。

真正目标是建立一个有明确取向、来源纪律、学习方法、长期记忆和能力建设目标的 study agent。

它应该服务用户的学习和判断能力，而不是替用户成为权威。
