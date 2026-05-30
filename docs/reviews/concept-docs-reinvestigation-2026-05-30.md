# Concept Docs 重新调查报告

状态：`investigation report / no move`

## 1. 调查目的

本报告重新调查 `docs/archive/concepts/` 的放置和内容定位。

触发问题是：这些文档早期写作时把 Isotope 过度理解为 `kernel`
（内核、底层运行契约）项目；但当前项目事实已经转向应用层：
Isotope 是 local-first AI engineering workbench（本地优先的 AI 工程工作台），
当前主线围绕 Codex Supervisor、受控 worker、证据收集、可恢复开发流程和
Research artifact 展开。

因此，本报告不做简单迁移，也不把旧文件换个目录名后继续使用。目标是回答：

- 哪些旧 concept（概念）材料仍然是当前需要的参考。
- 哪些判断来自早期 `kernel-first` 假设，需要降级或重写。
- 后续如果建立 active concepts 入口，应该怎样避免“新瓶装旧酒”。

## 2. 调查范围

本轮读取和比对了这些材料：

- `docs/archive/concepts/` 下全部 Markdown 文件。
- 当前事实入口：[Current Status](../current/status.md)、
  [Agent Task Queue](../current/agent-task-queue.md)、
  [Application Structure Plan](../current/application-structure-plan.md)、
  [Docs Map](../current/docs-map.md)。
- 文档迁移边界：[Docs Migration Plan](docs-migration-plan.md)、
  [Deferred Docs Placement Review](deferred-docs-placement-review.md)、
  [Kernel Archive Placement Review](kernel-archive-placement-review.md)。
- 概念公开边界：[Public / Internal Docs Boundary](../architecture/public-internal-docs-boundary.md)。
- 当前 kernel 草案中已经吸收的参考压力：
  [Kernel Living Spec](../architecture/kernel-living-spec.md)。
- 当前代码目录，用来确认项目已按应用软件结构组织到 `src/isotope/core/`、
  `src/isotope/features/`、`src/isotope/agents/`、`src/isotope/capabilities/`、
  `src/isotope/memory/`、`src/isotope/workspace/` 等层级。

本轮没有重新验证外部项目官网或仓库的最新状态。因此所有外部产品比较文档
只能评估为“当前 repo 内部是否还需要这类参考”，不能视为 2026-05-30
仍然准确的外部资料结论。若后续要恢复为 active reference，需要单独做
source refresh（来源刷新）。

## 3. 关键结论

`docs/archive/concepts/` 不能继续整体理解为纯 archive（历史归档）。
里面至少有三类仍然有用的材料：

1. application-pressure（应用层压力）：
   study companion、persona、orientation、学习方法、来源纪律和长期记忆需求。
2. reference-project pressure（参考项目压力）：
   Codex、Claude Code、LangGraph、AutoGen、GenericAgent、PetGPT、Hermes Agent、
   OpenClaw 等项目暴露出的产品层和执行层问题。
3. platform capability pressure（平台能力压力）：
   artifact、provenance（来源溯源）、memory、retrieval、workspace、policy、
   worker handoff 等能力对底层 contract 的要求。

但是，这些材料不应该原样恢复成当前事实入口。原因是旧文档里大量措辞仍把
Isotope 的第一身份写成 `kernel / platform`，这和当前
`docs/current/status.md` 的判断冲突：Isotope 现在应先按 AI 应用软件推进，
底层边界服务于产品路径，而不是让产品路径服务于抽象 kernel 叙事。

最稳妥的判断是：

- 旧目录保留为 source material（来源材料）。
- 新 active concept 入口应该是重写后的短文，不是旧文档搬家。
- 新文档应从应用层问题出发，再说明它给 platform / runtime 带来的压力。
- `kernel` 只在需要讨论 action、policy、event、artifact、workspace 等硬边界时使用，
  不能作为 Isotope 的主叙事。

## 4. 当前放置问题

### 4.1 `archive` 路径会误导后续 AI

[Archive README](../archive/README.md) 说 archive 是已经退出当前入口的材料，
主要用于追溯。这对旧 plans、旧 status 流水和废止规则是正确的。

但 `docs/archive/concepts/README.md` 又说这些 concept 用于“给未来产品和应用层工作施加概念压力”。这和 archive 的主定义冲突：

- 如果它们只是 archive，后续 agent 会低估其参考价值。
- 如果它们仍施加概念压力，它们就不应只埋在 archive 下。

更明显的是，[Public / Internal Docs Boundary](../architecture/public-internal-docs-boundary.md)
已经把 `docs/concepts/` 作为 `concept/application-pressure` 类别举例，但当前仓库并没有
`docs/concepts/`，实际文件却在 `docs/archive/concepts/`。这说明早期已经意识到
concept 应该有独立层级，只是后来被归档路径覆盖了。

### 4.2 旧文档不是完全过期，而是解释框架过期

旧文档里很多具体要求仍然成立：

- 私有 orientation / persona 不进底层 contract。
- 学习应用要区分 source、interpretation、inference。
- 长期记忆必须有 source refs 和 provenance。
- worker handoff 应交付 durable artifact，而不是聊天总结。
- 参考项目只能提供压力，不能成为 Isotope 模板。

真正过期的是解释框架：旧文档常把这些要求直接翻译成 `kernel requirements`。
当前更准确的说法应该是：

- 应用层需求先成立。
- 通用能力如果被多个应用或当前 Supervisor / Research 路径证明需要，再沉淀为
  platform/runtime contract。
- 不能因为一个私有应用需要某个能力，就把它升级成主线实现任务。

## 5. 文件级分类

| 文件 | 当前判断 | 后续处理建议 |
| --- | --- | --- |
| [2026-04-21-isotope-platform-kernel-reference-design](../archive/concepts/2026-04-21-isotope-platform-kernel-reference-design.md) | 有历史价值，但 `kernel-first` 主叙事已经不适合作为当前 concept 入口。 | 不直接搬出 archive。后续只抽取 action、policy、artifact、workspace、event 等可复用边界，重写为 platform pressure 摘要。 |
| [2026-04-22-isotope-first-study-companion-spec](../archive/concepts/2026-04-22-isotope-first-study-companion-spec.md) | 仍是重要的私有应用规格材料。 | 应进入新 `docs/concepts/` 的 application-pressure 层，但要重写成当前应用层 brief，并保留旧文档链接。 |
| [2026-04-22-isotope-marxist-leninist-study-agent-design](../archive/concepts/2026-04-22-isotope-marxist-leninist-study-agent-design.md) | 仍是私有 study app 方向材料，不是公开产品叙事。 | 可作为 internal/private application concept。重写时强调能力建设、来源纪律、边界和私有 orientation 分离。 |
| [2026-04-22-isotope-persona-architecture](../archive/concepts/2026-04-22-isotope-persona-architecture.md) | 仍然高度可用。它已经明确说 orientation / method / pedagogy / persona 属于应用层。 | 优先恢复为 active concept brief。它可成为 future app pack 设计的入口。 |
| [2026-04-22-isotope-study-agent-boundaries](../archive/concepts/2026-04-22-isotope-study-agent-boundaries.md) | 仍然可用，尤其是应用边界、政治行动边界和能力建设原则。 | 应重写为 private study app boundary brief，不作为 kernel requirement。 |
| [2026-04-22-study-companion-to-isotope-kernel-requirements](../archive/concepts/2026-04-22-study-companion-to-isotope-kernel-requirements.md) | 内容有价值，但标题和 framing（框架）最容易把 AI 带回 kernel-first。 | 不应原样恢复。应改写为 “Study Companion 对平台能力的压力”，把 `kernel requirements` 降级为 platform/runtime pressure。 |
| [2026-04-23-isotope-study-companion-kernel-tension-notes](../archive/concepts/2026-04-23-isotope-study-companion-kernel-tension-notes.md) | 有价值，尤其是 orientation leakage（取向泄漏）、citation discipline（引用纪律）、memory dependency（记忆依赖）张力。 | 可重写为 application/platform boundary notes，减少 `kernel` 主叙事。 |
| [2026-05-11-isotope-chatgpt-share-feedback-notes](../archive/concepts/2026-05-11-isotope-chatgpt-share-feedback-notes.md) | 有价值，补充了 interest capture、concept grounding、historical density 等应用 artifact。 | 应吸收到 study companion active brief，旧 share 只保留来源。 |
| [2026-04-22-isotope-vs-langgraph-vs-autogen](../archive/concepts/2026-04-22-isotope-vs-langgraph-vs-autogen.md) | 参考方向仍有价值，但外部资料可能已变化。 | 恢复前必须刷新官方资料。新文档应关注 “对 Isotope 应用/平台的压力”，不再证明 Isotope 是 kernel-first。 |
| [2026-04-22-isotope-vs-codex-claude-code-openclaw](../archive/concepts/2026-04-22-isotope-vs-codex-claude-code-openclaw.md) | 参考价值高，但 Codex / Claude Code 等产品变化快。 | 恢复前必须 source refresh。当前 Isotope 已以 Codex Supervisor 为产品主线，对比框架需要重写。 |
| [2026-04-24-isotope-vs-genericagent](../archive/concepts/2026-04-24-isotope-vs-genericagent.md) | 仍有价值：active context density、execution-verified memory、skill/SOP 沉淀。 | 可重写为 “learning loop pressure” 参考，不作为 memory 实现授权。 |
| [2026-04-24-isotope-vs-petgpt](../archive/concepts/2026-04-24-isotope-vs-petgpt.md) | 仍有价值：真实 workspace、文件安全、tool/session guardrails、trace/export。 | 可作为 workspace/product-shell pressure。外部信息需刷新。 |
| [isotope-vs-hermes-agent](../archive/concepts/isotope-vs-hermes-agent.md) | 仍有价值，且已被 `kernel-living-spec` 引用为压力来源。 | 可重写为 long-running agent product pressure。外部信息需刷新。 |
| [README](../archive/concepts/README.md) | 当前索引承认它们有长期概念价值，但放在 archive 下会误导。 | 后续若建立 `docs/concepts/`，应新写索引，不直接搬这个 README。 |

## 6. 推荐的新文档形态

后续不建议把 `docs/archive/concepts/` 原样移动到 `docs/concepts/`。
更好的目标结构是：

```text
docs/
  concepts/
    README.md
    application-pressure/
      study-companion-brief.md
      persona-pack-boundary.md
      study-companion-artifact-pressure.md
    reference-pressure/
      reference-project-pressure-map.md
      codex-claude-openclaw-refresh.md
      langgraph-autogen-refresh.md
      genericagent-petgpt-hermes-refresh.md
    platform-pressure/
      artifact-provenance-memory-pressure.md
      workspace-worker-handoff-pressure.md
```

这个结构的重点不是目录漂亮，而是把问题顺序改正：

1. 先说应用层问题是什么。
2. 再说这个问题要求哪些可复用能力。
3. 最后才说明哪些能力可能需要 platform/runtime contract。

旧文件可以保留在 `docs/archive/concepts/`，作为每篇新 brief 的 “source material”
链接。等新 brief 写完并经过链接审计后，再决定是否移动、保留 stub，或继续保持 archive。

## 7. 推荐实施顺序

### Phase 1: 建立 active concept 入口

创建 `docs/concepts/README.md` 和 2 到 3 篇短 brief：

- `application-pressure/study-companion-brief.md`
- `application-pressure/persona-pack-boundary.md`
- `reference-pressure/reference-project-pressure-map.md`

每篇 brief 都只写当前判断，并链接旧 archive 原文。不要复制旧文档长段落。

### Phase 2: 重写 study companion 主线

把 study companion 相关旧材料压缩成当前可读的应用层设计：

- 产品目标：长期学习、来源纪律、能力建设、反过早闭合。
- artifact：reading note、claim card、concept grounding table、historical density review。
- 边界：私有 orientation 不进入通用能力；不把 agent 变成权威替身。
- 平台压力：provenance-aware retrieval、memory promotion、review/scheduler、pack injection。

这一步应避免把标题写成 `kernel requirements`。

### Phase 3: 刷新外部参考项目

对外部比较类文档单独 source refresh：

- 只用官方 docs、项目 README 或明确版本的公开资料。
- 每篇记录调查日期。
- 把结论写成 “对 Isotope 的压力点”，不是 “Isotope 应该成为哪个东西”。
- Codex / Claude Code / LangGraph / AutoGen 等变化快的对象，必须按刷新日期判断。

### Phase 4: 再决定是否移动旧文件

只有当新 brief 已经覆盖主要信息，且链接验证通过后，才重新讨论旧文件放置。
可能结果有三种：

- 继续留在 archive，只由新 brief 引用。
- 移到 `docs/concepts/source-material/`，但保留旧路径 stub。
- 拆分吸收后保留 archive 原文，不再作为入口。

不建议一开始就整目录移动。

## 8. 成功标准

后续重构完成时应满足：

- 新读者从 `docs/current/status.md` 和 `docs/concepts/README.md` 不会误以为
  Isotope 是纯 kernel 项目。
- Study companion 相关材料被明确标为 application-pressure 或 private app concept。
- 外部参考项目比较都有调查日期和来源边界。
- `kernel` 只作为底层 contract 词汇出现，不再作为项目第一身份。
- 旧 archive 原文仍可追溯，但不会被当前入口当作实现队列。
- 所有本地 Markdown 链接通过检查。

## 9. 本轮不做的事

本报告只完成重新调查和放置判断，不做以下动作：

- 不移动 `docs/archive/concepts/` 文件。
- 不删除旧文档。
- 不把旧文档原样复制到新目录。
- 不刷新外部网站资料。
- 不打开新的 feature、provider、persona、memory 或 study companion 实现任务。

## 10. 最小下一步

如果继续推进，建议下一步只做一小片：

1. 新建 `docs/concepts/README.md`。
2. 新建 `docs/concepts/application-pressure/study-companion-brief.md`。
3. 新建 `docs/concepts/application-pressure/persona-pack-boundary.md`。
4. 在 `docs/current/docs-map.md` 和 `docs/reviews/README.md` 加入口。

这一步只写当前 brief 和链接旧文档，不移动旧原文。这样可以先解决
“仍有参考价值却被 archive 降级”的问题，同时避免把旧 kernel-first 文档换壳复活。
