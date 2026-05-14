# Isotope 第一个 Study Companion 应用规格

状态：`private application spec`

## 1. 摘要

本文定义 `Isotope` 上第一个具体私有应用：历史与理论学习陪练。

它假设已经接受这些文档的边界：

- [Study Agent Boundaries](2026-04-22-isotope-study-agent-boundaries.md)
- [Marxist-Leninist Study Agent Design](2026-04-22-isotope-marxist-leninist-study-agent-design.md)
- [Persona Architecture](2026-04-22-isotope-persona-architecture.md)
- [Study Companion to Kernel Requirements](2026-04-22-study-companion-to-isotope-kernel-requirements.md)

这个产品不是公开政治产品，不是辩论机器人，也不是角色扮演项目。

它的任务是帮助一个严肃用户：

- 长期学习
- 更认真读书
- 更清楚思考
- 保持纪律
- 积累笔记和综合
- 判断什么值得持续学习
- 把技术、专业、理论学习和长期政治目的、集体斗争、社会主义建设联系起来
- 逐步提高检索、阅读、笔记、规划能力
- 发现 economics、political economy、philosophy、industrial understanding 等短板
- 把短暂兴趣冲动转成可积累的研究路径
- 防止抽象判断过早闭合成结论

## 2. 产品定位

这是 `Isotope` 上第一个 personality-shaped application。

它适合作为第一个应用，因为它需要：

- long-term memory
- retrieval and source discipline
- study planning
- stable analytical orientation
- artifact-based review
- capability-building

人格层不应理解为：

- 历史人物模仿
- 领袖扮演
- 说话风格表演

应该理解为：

- 严肃学习陪练
- 高标准分析伙伴
- 推动用户读材料、做笔记、澄清问题的系统

## 3. 目标用户

第一版用户是：

- 严肃自学者
- 长期学习历史、理论和社会问题
- 正在尝试理解 economics、political economy、philosophy、industrial construction 与社会主义发展之间的关系
- 愿意读难材料
- 愿意做笔记和复盘问题

第一版不面向：

- 大众 onboarding
- casual browsing
- social virality
- ideological branding campaign

## 4. 核心承诺

产品承诺：

- 帮用户更认真读书
- 帮用户提出更好的问题
- 帮用户记住读过什么
- 帮用户形成更连贯的长期路线
- 帮用户判断一条学习线为什么重要
- 帮用户把短期学习目标连接到历史和政治目的
- 帮用户获得更强的学习方法，而不是依赖不透明帮助
- 帮用户发现 economics、philosophy、industrial questions 什么时候需要显式学习
- 帮用户把概念判断压回具体对象、材料、阶段和反例
- 帮用户把兴趣驱动的阅读变成连续学习，而不是一次性聊天

产品不承诺：

- 立刻给确定答案
- 现成教义
- 替代原文阅读
- 现实操作性指导或指挥

## 5. 学习优先级

产品不应要求用户同时平均学习所有有价值的方向。

第一版默认三条线：

- 主业主线
- 方向主线
- 桥梁主线

主业主线：

- computer science
- AI
- systems and engineering ability

方向主线：

- Marxist basic texts
- history
- philosophy

桥梁主线：

- economics
- political economy
- industrial systems
- industrial construction and production
- technology and the labor process

产品要帮助用户：

- 看清当前真实投入主要在哪条线
- 发现哪条线消失太久
- 把专业成长和历史方向连接起来
- 把两者连接到生产、劳动、工业和社会主义建设问题

阶段性不均衡是正常的。

有一段时间技术工作占大部分精力，只维持另外两条线的连续性，是可以接受的。

也会有一段时间必须补 political economy、philosophy 或 industrial understanding，否则技术学习和理论学习会长期分离。

## 6. 核心体验循环

### 6.0 Interest Capture And Concept Grounding

用户不总是从完整计划开始，很多学习会从一个临时兴趣、强烈问题或抽象判断开始。

系统应先把这种输入固定成可积累结构：

- 这个兴趣属于哪条主线或桥梁主线
- 它能缩成哪个最小研究问题
- 它需要哪些时间、机构、人物、文本或材料条件
- 哪些地方只是推断
- 哪些反例必须先找
- 下一步只补哪一块历史砖、材料砖或工程砖

输出可以是：

- `interest_capture`
- `concept_grounding_table`
- `missing_evidence_list`
- `minimal_next_step`

### 6.1 Reading Kickoff

用户开始一个阅读主题。

系统帮助：

- 选择下一步读什么
- 放置文本背景
- 定义小阅读目标
- 提醒要注意的问题

输出可以是：

- `reading_goal`
- `source_context`
- `question_seed`

### 6.2 Guided Reading Session

用户读材料后输入摘录、问题或笔记。

系统帮助：

- 澄清概念
- 标记直接引文和用户解释
- 提出进一步问题
- 连接相关材料

输出可以是：

- `reading_note`
- `concept_card`
- `source_excerpt`

### 6.3 Question Refinement

当用户的问题太大或太模糊时，系统帮助缩小问题。

它应该问：

- 这个问题到底在问历史事实、概念、路线分歧还是现实判断
- 现在缺材料、缺概念，还是缺比较对象
- 哪些问题可以暂时放下

输出可以是：

- `question_thread`
- `refined_question`
- `open_issue`

### 6.4 Anti-Premature-Closure Review

当用户或模型已经快形成结论时，系统应能做一次过早闭合检查。

它应该问：

- 这个判断有没有反例
- 是否把后来结果倒推成历史必然
- 是否把一个国家、时期、技术栈或组织经验套到另一个对象
- 是否混淆了相邻但不同的概念
- 是否用了理论术语但没有给出具体对象
- 是否缺少 source refs、时间、机构、人物或文本

输出可以是：

- `claim_card`
- `counterexample_request`
- `historical_density_review`

### 6.5 Note And Concept Consolidation

系统帮助把分散讨论变成耐久笔记。

输出可以是：

- `concept_card`
- `event_card`
- `actor_card`
- `claim_card`
- `disagreement_note`
- `study_map`
- `reading_summary`

### 6.6 Method Exposure

系统不只是给结果，也要展示方法。

例如：

- 为什么这样检索
- 为什么选择这个材料
- 为什么把问题缩小成这样
- 两种解释如何比较

输出可以是：

- `study_method_note`
- `search_strategy`
- `capability_gap_note`

### 6.7 Weekly Review

周期性 review 应该帮助用户：

- 看本周读了什么
- 哪些问题变清楚
- 哪些问题仍然悬置
- 哪些方向断了
- 下一周应该读什么

输出可以是：

- `weekly_review`
- `next_reading_plan`
- `unresolved_question_list`

### 6.8 Long-Arc Study Mapping

系统应帮助用户维护长期学习图谱。

主题可能包括：

- Marxist basic texts
- history
- philosophy
- economics and political economy
- industrial systems, production, and construction
- computer science and AI
- technology and the labor process

目标不是把所有主题平均推进，而是保持主线之间的关系。

### 6.9 用途与目的复盘

系统应能帮助用户追问：

- 这个主题为什么值得学
- 它是否帮助理解历史、社会、生产或组织问题
- 它和社会主义建设有什么关系
- 它对当前技术/专业学习有什么纠偏作用
- 我是不是在回避真正该补的 economics、philosophy 或 industrial questions

它不能变成：

- 行动指挥系统
- 战术组织工具
- 假装每个主题都有直接革命意义的机器
- 替代人的政治责任和判断

但它可以分析、比较、辩论、复盘现实和历史中的路线、组织、策略、执行问题。

## 7. 主要 Artifact 类型

第一版可用这些 artifact：

- `reading_goal`
- `source_excerpt`
- `reading_note`
- `concept_card`
- `event_card`
- `actor_card`
- `claim_card`
- `interest_capture`
- `concept_grounding_table`
- `missing_evidence_list`
- `counterexample_request`
- `minimal_next_step`
- `historical_density_review`
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

每个 artifact 应尽量保留：

- source refs
- 创建时间
- 创建 run
- 使用的 pack / method
- 是否是 source、interpretation 或 inference

## 8. 所需 Isotope 能力

这个应用需要 `Isotope` 支持：

- artifact-centric state
- artifact graph
- provenance-aware retrieval
- controlled artifact content retrieval
- long-lived memory
- pack injection
- review / scheduler
- worker handoff through artifacts
- policy boundary for operational instruction

这些是应用反压 kernel 的原因。

## 9. 最小实现形态

第一版 spike 不做完整产品。

最小可验证流程：

1. 输入一个 source artifact。
2. controlled retrieval 读取材料。
3. 生成 reading note。
4. 生成 purpose review。
5. 生成 study priority decision。
6. 检查所有输出都能追 source refs。
7. replay / checkpoint 后仍能恢复这些 artifact。

可选但很适合作为第二个 spike 的流程：

1. 输入一个抽象 claim 或临时兴趣。
2. 生成 `concept_grounding_table`。
3. 生成 `claim_card`。
4. 生成 `missing_evidence_list` 或 `counterexample_request`。
5. 输出一个 `minimal_next_step`。
6. 检查这些产物不需要 real web search 也能作为 artifact 持久化。

暂不做：

- real web search
- complete corpus system
- real LLM persona runtime
- durable memory engine
- scheduler
- UI

## 10. 评价标准

不要用“聊得久不久”评价。

应该看：

- 用户是否读了更多原文
- 问题是否更清楚
- 笔记是否更有结构
- claim 是否有来源
- 分歧是否被保留
- 学习路线是否更连贯
- 用户是否更能自己检索和比较
- 技术学习和理论学习是否更能发生联系
- 抽象 claim 是否被压回具体时间、机构、人物、文本、反例和阶段
- 学习产物的 historical density 是否提高

## 11. 失败模式

主要失败模式：

- persona 盖过学习
- 引用不可靠
- 聊天替代读书
- 用口号压平问题
- 用概念替代具体历史对象
- 过早把兴趣或判断闭合成结论
- 用户越来越依赖
- 学习和长期目的脱节
- 每个主题都被强行说成战略重点
- 系统帮用户逃避困难领域

## 12. 设计判断

第一个 study companion 的价值不是“做一个有立场的聊天角色”。

真正价值是验证：

- `Isotope` 能否支持长期学习型应用
- artifact、provenance、retrieval、memory、pack 是否能协作
- agent 能否帮助用户形成能力，而不是替用户成为权威

如果这个应用成立，它可以成为 `Isotope` 第一个严肃应用压力测试。
