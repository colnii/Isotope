# Study Companion 与 Kernel 的张力笔记

状态：`concept note`

## 1. 摘要

本文记录 study companion 应用和 `Isotope` kernel 之间的几个关键张力。

这些张力不是 blocker，而是设计约束：

- 私有应用可以有强分析取向，但 kernel 必须保持取向中立。
- dynamic delegation 很有用，但不能削弱引用和来源纪律。
- long-term memory 很重要，但不能把用户训练成依赖 agent 的判断替身。

这些张力说明：`Isotope` 需要 kernel / application 分层，而不是把一切写成一个 prompt chatbot。

相关文档：

- [Platform Kernel Reference Design](2026-04-21-isotope-platform-kernel-reference-design.md)
- [Study Agent Boundaries](2026-04-22-isotope-study-agent-boundaries.md)
- [Persona Architecture](2026-04-22-isotope-persona-architecture.md)
- [Study Companion to Kernel Requirements](2026-04-22-study-companion-to-isotope-kernel-requirements.md)
- [First Study Companion Spec](2026-04-22-isotope-first-study-companion-spec.md)

## 2. 通用平台 vs 私有分析取向

第一个 study companion 可以有私有 Marxist / Marxist-Leninist 分析取向。

这和 `Isotope` 作为通用平台并不矛盾，前提是 orientation 留在应用层。

kernel 不应该包含：

- ideology-specific default prompts
- ideology-specific source-priority rules
- ideology-specific corpus bundles
- ideology-specific evaluation labels
- ideology-specific artifact type names
- ideology-specific UI or product copy

kernel 可以提供：

- pack loading
- pack provenance
- artifact registration
- retrieval and citation infrastructure
- policy gates
- memory and event persistence
- evaluation / export surfaces

私有应用可以提供：

- orientation pack
- method pack
- pedagogy pack
- persona pack
- private corpus configuration
- private evaluation rubrics
- private product naming

目标不是保证公开发布时只删一个文件就能完成剥离。

更严格的目标是：

- 没有私有 orientation layer 时，reusable kernel 仍能运行。
- 移除 private corpus 和 prompt packs 后，generic study tools 仍能运行。
- private pack 的影响应该显式、可追踪。
- kernel tests 不依赖私有意识形态内容。

规则：

- private orientation 可以存在于 application layer。
- orientation leakage 不能进入 kernel。

## 3. Dynamic Delegation vs Citation Discipline

dynamic delegation 很有价值。

supervisor 可以把检索、综合、笔记修改、复习、方法解释交给不同 worker。

但 unrestricted delegation 会削弱来源纪律。

坏模式是：

- worker 非正式阅读材料
- worker 只返回一段 prose summary
- supervisor 把这段总结当成 source-grounded claim 复述
- 后续 review 无法知道结论来自哪里

严肃 study companion 不能这样做。

action boundary 应该保留 provenance：

- `retrieve_sources` 产出带 provenance 的 `source_excerpt` artifact。
- `synthesize_with_provenance` 消费 `ResourceRef` 输入。
- `create_artifact` / `update_artifact` 附带 source refs 和 reasoning refs。
- `write_memory` 存 summary + refs，而不是不透明 source text。
- 非平凡 claim 要么有 refs，要么明确标成 model inference。

worker 应该交付 durable artifacts，而不是只返回 terminal chat summary。

study-domain worker 至少应该返回其中一种：

- source excerpts with provenance
- grounded synthesis with cited refs
- linked note mutations
- disagreement notes
- method notes

kernel-level rule：

- delegation 可以动态。
- content authority 必须 ref-first and provenance-aware。

supervisor 可以整合 worker 输出，但不能把 worker prose 当成证据，除非它指向 approved refs 或产生了 artifact。

## 4. Long-Term Memory vs Dependency

study companion 需要长期记忆。

它要记住：

- 用户读过什么
- 哪些问题还没解决
- 哪些概念反复出现
- 哪些学习目标被修改过
- 哪些 review 形成了耐久结论

如果应用有稳定分析取向和合适 pedagogy，这种 memory 很有价值。

风险不是 alignment 本身，而是把 agent 变成用户判断的替身。

memory 和 review 系统应该支持：

- 直接阅读
- 笔记
- source comparison
- question refinement
- method exposure
- user-owned judgment
- capability transfer

不应该优化：

- guilt-based compliance
- dependency on constant approval
- pseudo-devotional attachment
- 用 agent summary 替代 source reading
- 用 agent instruction 替代人的政治责任

这不要求 agent 情绪平淡或意识形态中立。

它要求应用把 pedagogy 写清楚：

- 可以严格
- 可以和私有 orientation 对齐
- 可以推动纪律
- 但压力应该基于 artifact、study output 和用户可控的 review，而不是心理控制

有用的 safeguards：

- scheduled review 用户可见且可关闭
- session memory 可检查、可编辑
- durable personal claims 需要 provenance 或 user confirmation
- review output 指向 artifact，而不是心理评判
- capability-building notes 解释方法，而不只是给答案

目标不是最低限度 attachment。

目标是纪律化帮助，让用户独立能力随着时间增强。

## 5. Kernel 含义

这些张力要求 kernel 支持：

- pack injection 显式且可追踪
- `ResourceRef` 作为跨对象引用形式
- retrieval 返回有 provenance 的授权 materialization
- worker 通过 artifact handoff，而不是 hidden state
- memory write 是结构化 action，不是 transcript leakage
- scheduled review 是 first-class trigger，而不是后台 prompt trick
- policy 在应用层区分 analysis、planning 和 operational instruction

## 6. 应用层含义

study companion 应用自己拥有：

- 具体私有 orientation
- source-priority preferences
- study-review prompts
- pedagogy rules
- persona style
- capability-building curriculum
- private evaluation rubrics

不要因为第一个应用需要这些，就把它们提升进 kernel。

## 7. 最小评审问题

未来实现至少应该回答：

- kernel 能否在没有 private orientation pack 时运行
- generic study tool 能否在没有 private corpus 时运行
- worker 产出的 claim 是否能追到 refs 或标成 inference
- memory record 是否可检查、编辑、supersede 或删除
- review output 是否指向 artifacts 和 study goals，而不是 guilt
- 系统是否提升了用户学习能力，而不是只让用户消费答案
