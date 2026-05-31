# Concept Topics 逐主题重查报告

状态：`review record / committed`

日期：2026-05-30

## 0. 本轮边界

这份报告按 `docs/archive/concepts/` 的主题重新调查，而不是把旧文档换目录。

调查方式：

- 先读旧 concept 全部文件，按主题而不是按文件名归类。
- 再核对 Isotope 当前事实入口：`docs/current/status.md`、
  `docs/current/application-structure-plan.md`、
  `docs/architecture/public-internal-docs-boundary.md`。
- 对涉及外部项目的主题，重新打开官方文档、官方仓库或论文页面。
- 本轮只形成重查报告，不直接迁移旧文档或新建 active concept 文档。

本轮使用的外部资料都只作为 2026-05-30 的刷新依据。外部产品变化快，后续如果
要写 active concept 文档，仍应在写作当日再刷新一次来源。

## 1. Isotope 自身定位：kernel 变成够不够用的问题

对应旧文档：

- `2026-04-21-isotope-platform-kernel-reference-design.md`
- `docs/archive/concepts/README.md`

本地重新核对：

- `docs/current/status.md` 明确写：Isotope 是 local-first AI engineering
  workbench，不是单纯 kernel 项目。
- `docs/current/application-structure-plan.md` 明确写：后续按 AI 应用软件组织目录，
  避免重新回到 `kernel` 或 AI OS 叙事。
- 当前代码也已经按 `core/`、`features/`、`agents/`、`capabilities/`、
  `memory/`、`workspace/`、`execution/` 等应用软件分层展开。

重查结论：

- 旧文档里的 action、policy、artifact、event、workspace、worker handoff
  这些硬边界仍有价值。
- 旧文档的问题不是“kernel 不重要”，而是把 kernel 当成先验主叙事，
  容易让后续工作为了抽象完整性继续扩底层。
- 当前更准确的判断是：Isotope 先要服务真实 AI 工程工作流；kernel / platform
  contract 是支撑应用的底层能力。只要它够用，就不需要为了叙事继续扩张；
  如果 Supervisor、Research、memory promotion、worker handoff 等应用路径暴露
  真实 friction，再反压底层 contract。
- 因此，kernel 不是被降级，而是从 `kernel-first identity` 重新定位为
  application-driven sufficiency boundary（应用驱动的够用性边界）。

建议处理：

- `2026-04-21-isotope-platform-kernel-reference-design.md` 保持 source material。
- 抽取其中仍成立的边界，重写为 `platform-sufficiency` 或 `platform-pressure` brief。
- 不要把这篇原文搬进 `docs/concepts/` 当入口。

## 2. Study Companion：仍是重要应用压力，不是 kernel 需求清单

对应旧文档：

- `2026-04-22-isotope-first-study-companion-spec.md`
- `2026-04-22-isotope-study-agent-boundaries.md`
- `2026-04-22-isotope-marxist-leninist-study-agent-design.md`
- `2026-04-22-study-companion-to-isotope-kernel-requirements.md`
- `2026-04-23-isotope-study-companion-kernel-tension-notes.md`
- `2026-05-11-isotope-chatgpt-share-feedback-notes.md`

外部重新核对：

- 近期学习分析研究仍强调，AI 学习工具应作为 collaborative agent
  辅助 self-regulated learning（自我调节学习），而不是替代教师或学习者：
  <https://learning-analytics.info/index.php/JLA/article/view/9143>
- 近期生成式 AI tutor 研究把 source evaluation（来源评价）和 guided reflection
  （引导反思）放进 scaffolding（脚手架）条件中：
  <https://www.mdpi.com/2227-7102/16/4/651>
- 文档化科学探究中的 source evaluation 研究也继续支持“材料映射、共同标准、
  元认知提示”这类方法：
  <https://www.sciencedirect.com/science/article/pii/S0747563224004151>

重查结论：

- 旧 study companion 方向没有过时。它的核心价值仍然是：长期学习、来源纪律、
  问题拆解、反过早闭合、学习能力建设。
- 旧文档里“应用不应替用户思考，而要让用户更会搜索、比较、记笔记、提问题和规划”
  仍是最重要的产品原则。
- `interest_capture`、`concept_grounding_table`、`claim_card`、
  `historical_density_review` 这些 artifact 方向仍值得保留。
- 但 `Study Companion 对 Isotope Kernel 的要求` 这个标题容易让 AI 误读成
  “因为应用想要，所以立刻扩 kernel”。更准确的标题应是：
  `Study Companion 对 Isotope 平台能力够用性的压力`。

建议处理：

- 新写一篇 `docs/concepts/application-pressure/study-companion-brief.md`。
- 把私有取向、学习方法、artifact、评估面写成应用 brief。
- 只在最后一节列“平台能力够用性检查”：provenance-aware retrieval、
  artifact graph、memory promotion、review/scheduler、pack injection。
- 不打开实现任务，不默认写 persona runtime、real web search 或完整 memory engine。

## 3. Persona / Orientation / Method / Pedagogy：旧判断仍然强

对应旧文档：

- `2026-04-22-isotope-persona-architecture.md`
- study companion 相关文档中的 persona / orientation 段落

外部重新核对：

- OpenAI Codex app 当前也把 personality 做成用户可选风格，并声明能力不随风格改变：
  <https://openai.com/index/introducing-the-codex-app/>
- Claude Code 当前用 `CLAUDE.md`、skills、hooks、auto memory、subagents
  承载项目规则和工作流，而不是把所有行为压进一个角色设定：
  <https://code.claude.com/docs/en/overview>
- Hermes Agent 的 skills 系统把 skill 做成按需加载的知识文档，并用 progressive
  disclosure（渐进披露）减少上下文消耗：
  <https://hermes-agent.nousresearch.com/docs/user-guide/features/skills>

重查结论：

- 旧 `Persona Architecture` 是这批文档里最应该保留的 active concept 之一。
- 它说的四层拆分仍然成立：
  orientation（站在哪里看）、method（怎么分析）、pedagogy（怎么教学）、
  persona（给人的风格）。
- 旧文档还准确指出：persona 可以改善体验，但不能决定 truth；source discipline
  应优先于人格表演。
- 需要更新的是术语位置：不要写“kernel 支持 pack”，应写“应用层可加载 pack；
  platform 只提供来源、版本、作用域、审计和启停边界”。

建议处理：

- 新写 `docs/concepts/application-pressure/persona-pack-boundary.md`。
- 把这篇作为 future app pack 的边界入口。
- 保留旧文档为 source material，不必大改旧文。

## 4. Research / Provenance / Memory：当前主线已经证明这不是空想

对应旧文档：

- study companion 的 source discipline / memory / artifact graph 章节
- GenericAgent / Hermes / PetGPT 比较里的 memory、skill、workspace 压力
- 2026-05-24 web research 方向记忆和当前 ResearchFlow 文档

本地重新核对：

- 当前 `ResearchFlow` 已经落地：`research.*` artifact、provider trace、
  source-backed report、promotion proposal、quality gate 都已经存在。
- 当前 memory write 已要求 approval，事件只投影 summary / refs / provenance，
  不把 raw content 直接塞进长期 memory。
- 当前 durable ingestion 路径已经写成：
  `search/fetch -> research.* artifact / provenance -> retrieval -> optional memory promotion`。

外部重新核对：

- LangGraph 的 persistence 文档把 checkpoint、human-in-the-loop、memory、
  time travel 和 fault tolerance 绑定在一起：
  <https://docs.langchain.com/oss/python/langgraph/persistence>
- RAG source attribution 仍是活跃研究问题，说明“能列来源”不等于真正可归因：
  <https://arxiv.org/abs/2507.04480>
- 近期 agent memory 综述继续强调长期 memory 需要写入过滤、矛盾处理、隐私治理、
  可信反思和可追踪来源：
  <https://arxiv.org/abs/2603.07670>

重查结论：

- 旧 concept 对 provenance-backed memory 的要求是正确方向，而且已经被当前
  Research / memory promotion 主线部分验证。
- 但不要把所有 study artifact 都说成 kernel 内置类型。正确说法是：
  应用定义 artifact 类型；平台只需要保证引用、来源、质量、promotion gate
  和审计这些共性边界够用。
- 当前最应该保留的原则：
  raw web text 不能直接进 durable memory；必须先落 research artifact 或
  accepted observation，再 promotion。

建议处理：

- 新写 `docs/concepts/platform-pressure/artifact-provenance-memory-pressure.md`。
- 这篇可以直接引用当前 `ResearchFlow`，把旧 concept 从抽象要求接回已落地能力。
- 不新增新 provider，不绕开已有 `ResearchFlow`。

## 5. Codex / Claude Code / OpenClaw：旧分类要重写，产品面已经变了

对应旧文档：

- `2026-04-22-isotope-vs-codex-claude-code-openclaw.md`

外部重新核对：

- Codex 现在是 OpenAI 明确定位的 coding agent：支持 app、CLI、IDE、web/mobile、
  CI/CD SDK，并有 built-in worktrees、cloud environments、skills、automations：
  <https://openai.com/codex/>
- Codex CLI 当前官方文档写明它是本地 terminal agent，可读、改、运行目录内代码：
  <https://developers.openai.com/codex/cli>
- Codex app 文档强调系统级 sandboxing、目录/分支编辑限制，以及需要提权时请求许可：
  <https://openai.com/index/introducing-the-codex-app/>
- Claude Code 当前是多表面 coding 工具：terminal、IDE、desktop、browser；
  支持 MCP、skills、hooks、auto memory、agent teams、background agents、schedule：
  <https://code.claude.com/docs/en/overview>
- Claude Code security 文档明确 read-only default、显式 permission、sandboxed bash、
  write-scope restriction、prompt injection 防护：
  <https://code.claude.com/docs/en/security>
- Claude Code subagents 文档明确 foreground/background subagents、并行 research、
  以及 subagent system prompt / tool restriction / model 的隔离：
  <https://code.claude.com/docs/en/sub-agents>
- OpenClaw 当前官方定位是 self-hosted gateway，连接多种 chat/channel surface 到
  AI coding agents；Gateway 是 session、routing、channel connection 的 source of truth：
  <https://docs.openclaw.ai/>
- OpenClaw security 文档明确一个 Gateway 不应被当作敌对多租户隔离边界，建议按
  trust boundary 拆 gateway / host / OS user：
  <https://docs.openclaw.ai/gateway/security>

重查结论：

- 旧文档“Codex 是 coding product，Claude Code 是 coding harness，OpenClaw 是
  assistant/gateway product”这个大方向仍成立。
- 但旧文档把 Isotope 对照列写成 `kernel / platform`，需要重写为
  “应用产品 + 底层够用性边界”的对照。
- 现在更准确的对照是：
  Codex / Claude Code / OpenClaw 都在做可用产品面；Isotope 当前也应该以产品面
  解释自己，即 Codex Supervisor + local engineering workbench。
- 需要学习的不是“做一个更抽象的 kernel”，而是判断现有底层边界是否足够支撑：
  多 agent/worktree 管理、权限/approval、subagent isolation、gateway/channel
  风险、sandbox 和 source-of-truth 边界。

建议处理：

- 旧文档不应原样恢复。
- 新文档应叫 `reference-pressure/coding-agent-products-refresh.md`。
- 重点从“Isotope 和它们谁更像 kernel”改成“这些成熟产品暴露了 Isotope
  应用层必须解决的运营和安全问题，以及现有底层 contract 是否够用”。

## 6. LangGraph / AutoGen：旧判断基本成立，但不应变成 Isotope 自证

对应旧文档：

- `2026-04-22-isotope-vs-langgraph-vs-autogen.md`

外部重新核对：

- LangGraph 官方文档把自己定位为 orchestration runtime（编排运行时），关注
  durable execution、streaming、human-in-the-loop、persistence：
  <https://docs.langchain.com/oss/python/langgraph/overview>
- LangGraph Graph API 仍以 state、nodes、edges 建模 agent workflow：
  <https://docs.langchain.com/oss/python/langgraph/graph-api>
- AutoGen Core 官方文档把自己定位为 event-driven、distributed、scalable、
  resilient AI agent systems，并基于 Actor model：
  <https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/index.html>
- AutoGen message docs 明确 agents 通过 messages 通信，消息是 serializable data，
  direct messaging 和 broadcast 是主要通信形态：
  <https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/framework/message-and-communication.html>
- AutoGen intervention handler cookbook 说明可以拦截 tool execution 并请求用户批准：
  <https://microsoft.github.io/autogen/dev/user-guide/core-user-guide/cookbook/tool-use-with-intervention.html>

重查结论：

- 旧文档对 LangGraph / AutoGen 的抽象判断基本仍成立：
  LangGraph 偏 graph/state/checkpoint；AutoGen 偏 agent/message/runtime。
- 旧文档的问题是用它们来证明 Isotope 必须是 action-governance-first kernel，
  而不是先问当前应用是否真的需要继续扩底层边界。
- 现在应该改成：
  LangGraph 和 AutoGen 是 reference pressure，提醒 Isotope 应用层不要忽视
  durable state、resume、human approval、agent messaging 和 observability。
- Isotope 不需要因为这些对比而自建完整 workflow engine 或 distributed actor runtime。

建议处理：

- 新文档可保留对照，但标题改成 `reference-pressure/orchestration-runtimes-refresh.md`。
- 结论从“Isotope 的 kernel 差异化”改成“Isotope 当前哪些底层能力已经够用、
  哪些因应用 friction 需要补、哪些保持 deferred”。

## 7. GenericAgent：学习闭环是真需求，但不能把 SOP 文件当事实源

对应旧文档：

- `2026-04-24-isotope-vs-genericagent.md`

外部重新核对：

- GenericAgent 官方仓库仍把自己定位为 minimal, self-evolving autonomous agent
  framework，强调约 3K seed code、9 atomic tools、约 100 行 agent loop：
  <https://github.com/lsdefine/GenericAgent>
- README 明确其设计哲学是“不要预加载技能，而是演化技能”；每次解决新任务后将执行路径
  crystallize 成可复用 skill。
- README 的 architecture 部分仍强调 layered memory、minimal toolset、
  autonomous execution loop，以及 L0-L4 memory layers。

重查结论：

- 旧文档判断仍成立：GenericAgent 最有价值的是 active context density、
  execution-verified memory、skill/SOP crystallization。
- 旧文档也正确指出：file-SOP memory 和 prompt obedience 不能成为 Isotope 的事实源。
- 对当前 Isotope 的更新判断是：
  GenericAgent 更像 capability-building / self-evolution pressure，不是 kernel 模板。

建议处理：

- 新文档应叫 `reference-pressure/self-evolving-agent-pressure.md`。
- 把 “skill 候选来自完成任务、需要 provenance、需要 evaluation / supersession”
  写成平台压力。
- 不要现在实现自进化 skill 系统。

## 8. PetGPT：桌面人格壳不是重点，workspace-backed assistant 才是压力

对应旧文档：

- `2026-04-24-isotope-vs-petgpt.md`

外部重新核对：

- PetGPT 官方 README 当前仍定位为 AI desktop pet assistant 和 autonomous social agent：
  <https://github.com/JulesLiu390/PetGPT>
- README 列出统一 LLM provider、custom personality、多 assistant、MCP integration、
  local memory、conversation history / SQLite、multi-window desktop、social agent pipeline。

重查结论：

- 旧文档正确：不要复制桌宠、Tauri shell、persona shell。
- 但 PetGPT 对 Isotope 仍有压力价值：
  本地桌面产品会自然面对 UI 状态、长期会话、MCP 工具、memory toggle、
  per-assistant memory、conversation history、social/group input 风险。
- 对当前 Isotope 来说，它更像 future desktop/frontend 和 workspace state pressure，
  不是底层 contract 蓝图。

建议处理：

- 新 reference brief 应把 PetGPT 放入 `personal-assistant-product-pressure`，
  和 OpenClaw/Hermes 的 gateway/memory/skills 对照。
- 关注可见状态、会话恢复、MCP 工具边界、memory 开关，而不是人格 UI。

## 9. Hermes Agent：长期 agent product 压力很强，尤其是 memory/skills/tools

对应旧文档：

- `isotope-vs-hermes-agent.md`

外部重新核对：

- Hermes Agent 官方 README 当前定位为 self-improving AI agent，强调内置 learning loop、
  经验创建 skills、使用中改进 skills、跨 session 记忆和多平台 gateway：
  <https://github.com/NousResearch/hermes-agent>
- Hermes memory docs 写明 memory 存储在本地 `~/.hermes/memories/`，会在 session
  start 注入 system prompt，并由 agent 用 memory tool 增删改：
  <https://hermes-agent.nousresearch.com/docs/user-guide/features/memory>
- Hermes skills docs 写明 skills 是按需加载知识文档，保存在 `~/.hermes/skills/`，
  可被 agent 修改或删除，并采用 progressive disclosure：
  <https://hermes-agent.nousresearch.com/docs/user-guide/features/skills>
- Hermes tools docs 列出 web、terminal、file、memory、session search、cron、
  messaging、delegation 等工具集，以及 local/docker/ssh/singularity/modal/daytona
  终端后端：
  <https://hermes-agent.nousresearch.com/docs/user-guide/features/tools>

重查结论：

- 旧文档对 Hermes 的关注点仍成立，而且重要性更高：learning loop、skills、
  persistent memory、gateway、scheduled automations、subagent delegation、
  real execution backends。
- 但 Hermes 的 memory 注入模式和 skill 可被 agent 修改，也正好说明 Isotope
  需要更硬的 provenance / approval / source artifact 边界。
- 对 Isotope 当前主线的直接启发不是“复刻 Hermes”，而是让 Supervisor /
  Research / memory promotion 这些已经存在的路径逐步形成可靠学习闭环。

建议处理：

- 新 brief 应把 Hermes 和 GenericAgent 放在同一组：learning-loop pressure。
- 明确哪些能力是产品层：gateway、messaging、cron、desktop / mobile entry。
- 明确哪些能力是平台压力：memory provenance、skill identity/version/scope、
  skill use trace、tool execution evidence。

## 10. Open issue：政治/意识形态私有应用边界

对应旧文档：

- `2026-04-22-isotope-marxist-leninist-study-agent-design.md`
- `2026-04-22-isotope-study-agent-boundaries.md`
- `2026-04-23-isotope-study-companion-kernel-tension-notes.md`

重新核对：

- 旧文档自身已经把 private orientation 放在应用层，不放进 kernel。
- 当前 public/internal docs boundary 也把 private application orientation 归为
  未来公开前需要 audit 的 concept/application-pressure 内容。

重查结论：

- 这组内容不能按公开产品文档处理。
- 它仍然可以保留为 private application concept，因为它描述的是用户私有学习方向、
  学习方法、来源纪律和行动边界。
- 对主线有可复用价值的是方法层：
  source / interpretation / inference 区分、反口号化、反过早闭合、
  concept grounding、historical density。
- 不应把具体政治取向、私有 corpus、source priority、persona voice 写成
  Isotope 通用能力。

建议处理：

- 新 active docs 里只放可泛化的 study method / artifact / boundary。
- 私有 orientation 只保留为 source material 或 internal/private concept。
- 如果未来开源，必须单独做 public docs audit。

## 11. 建议的新 active concept 目录

不建议整目录搬迁。建议先写少量重写后的 active brief：

```text
docs/concepts/
  README.md
  application-pressure/
    study-companion-brief.md
    persona-pack-boundary.md
  platform-pressure/
    artifact-provenance-memory-pressure.md
  reference-pressure/
    coding-agent-products-refresh.md
    orchestration-runtimes-refresh.md
    learning-loop-products-refresh.md
```

旧 `docs/archive/concepts/` 保持原样，作为 source material。

## 12. 每个旧主题的处置表

| 旧主题 | 新判断 | 动作 |
| --- | --- | --- |
| Platform/kernel reference design | 边界有价值，但应按应用够用性来判断是否继续扩 | 保留旧文，抽取边界重写为 platform sufficiency / pressure |
| First study companion | 应用方向仍有价值 | 重写为 application-pressure brief |
| Marxist-Leninist study agent | 私有应用材料，不是公开产品叙事 | 只抽可泛化方法层，私有取向留 source material |
| Persona architecture | 高价值，基本仍成立 | 优先重写为 active pack boundary |
| Study agent boundaries | 高价值，需改成应用驱动的够用性 framing | 重写为 private study app boundary |
| Study companion kernel requirements | 标题和 framing 有风险 | 改写为平台能力够用性压力 |
| Study companion tension notes | 张力仍成立 | 改写为 application/platform boundary notes |
| ChatGPT share feedback notes | 应用 artifact 方向有价值 | 吸收到 study companion brief |
| Codex / Claude / OpenClaw | 外部产品已变化，仍是强参考 | source refresh 后重写 |
| LangGraph / AutoGen | 抽象判断基本成立 | 重写成 orchestration pressure，不作 Isotope 自证 |
| GenericAgent | 学习闭环压力成立 | 重写成 self-evolving / skill pressure |
| PetGPT | workspace-backed assistant 压力成立 | 放入 personal assistant / desktop pressure |
| Hermes Agent | 长期 agent product 压力成立 | 与 GenericAgent 合并为 learning-loop pressure |

## 13. 最小下一步

如果继续做，不要先迁移旧目录。建议只做：

1. 新建 `docs/concepts/README.md`。
2. 新建 `docs/concepts/application-pressure/persona-pack-boundary.md`。
3. 新建 `docs/concepts/application-pressure/study-companion-brief.md`。
4. 在两个新 brief 里链接旧 archive 原文。
5. 跑 Markdown 链接检查。

这样可以先纠正 archive 路径造成的参考价值弱化，同时避免旧 kernel-first
叙事原样复活。
