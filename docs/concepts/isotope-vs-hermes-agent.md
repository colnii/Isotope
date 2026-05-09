# Isotope vs Hermes Agent

状态：`concept comparison`

## 1. 目的

本文比较 `Isotope` 和 [`Hermes Agent`](https://github.com/NousResearch/hermes-agent)。

这里不是判断谁更好，而是回答几个设计问题：

- `Hermes Agent` 实际优化的是哪种系统形态
- 它对 `Isotope` 的 kernel 设计有什么参考价值
- 哪些东西值得学习
- 哪些东西不应该直接搬进 `Isotope` kernel

短结论：

- `Hermes Agent` 更像一个已经产品化的 self-improving agent product / harness，重点是长期运行、记忆、skills、gateway、多平台入口和大量现实工具。
- `Isotope` 当前更像 policy-governed event-sourced kernel prototype，重点是 action lifecycle、policy grants、canonical event log、artifact provenance、projector replay 和 checkpoint。
- `Hermes Agent` 很适合作为 `Isotope` 的产品层和应用层压力来源，但不应该成为 kernel 模板。

## 2. 资料依据

本文依据 2026-05-09 查到的公开资料：

- Hermes Agent docs homepage: <https://hermes-agent.nousresearch.com/docs/>
- Hermes Agent features overview: <https://hermes-agent.nousresearch.com/docs/user-guide/features/overview/>
- Hermes Agent memory docs: <https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/>
- Hermes Agent tools docs: <https://hermes-agent.nousresearch.com/docs/user-guide/features/tools/>
- Hermes Agent skills docs: <https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/>
- GitHub repo: <https://github.com/NousResearch/hermes-agent>

下面的比较包含基于公开资料的架构推断。

## 3. Hermes Agent 优化的是什么

`Hermes Agent` 最适合被理解为一个带有强学习闭环的 autonomous agent harness。

公开文档里最突出的点包括：

- 跨 session 的 persistent memory
- agent 能创建并复用 skills
- web、terminal、files、browser、memory、delegation、cron、code execution、messaging 等工具集
- CLI 和 messaging platform 上的 gateway 式入口
- 多种 terminal 和 execution backend
- provider routing、fallback 和 credential pools
- `AGENTS.md`、`CLAUDE.md`、`SOUL.md` 等 context files
- 工作目录变化周围的 checkpoint 和 rollback
- plugins、hooks、MCP integration、external memory providers

关键不是某一个功能，而是整体方向：Hermes 试图让 agent 在长期运行中积累可复用的操作能力。

这种能力来自：

- 用 memory 记录稳定事实和偏好
- 用 skills 固化可复用过程
- 用 gateway 和 scheduler 形成持续存在
- 用工具和执行后端真正作用于外部世界

## 4. 对照表

| 维度 | `Isotope` | `Hermes Agent` |
| --- | --- | --- |
| 第一身份 | kernel / runtime prototype | self-improving agent product / harness |
| 控制中心 | `ActionProposal -> PolicyDecision -> ActionExecution` | agent loop + tools + memory + skills + gateway + plugins |
| 持久化中心 | canonical event log、projector、checkpoint | memory files、skills、session/search memory、external memory providers |
| 工具模型 | typed action registry 和 policy grants 优先 | 大量内置工具和 plugin 生态 |
| workspace 姿态 | policy-bound kernel resource | 真实 terminal、filesystem、backend 执行面 |
| 学习闭环 | 还没有作为产品能力实现 | 核心产品主张：memory + skills + self-improvement |
| delegation | worker lifecycle 和 policy gate 的 first slice | subagent delegation 是实际工具能力 |
| 产品外壳 | 有意推迟 | CLI、gateway、messaging platforms、IDE/API integrations |
| 直接照搬的风险 | 产品功能可能绕开 kernel discipline | 不适用 |

## 5. Isotope 应该学习什么

### 5.1 学习闭环是真实产品需求

Hermes 把 learning loop 做成产品核心。

这提醒 `Isotope`：memory 和 skills 不是装饰功能。严肃的长期 agent platform 迟早需要：

- 可检查、可约束的 durable memory
- 使用后可以改进的 reusable procedures
- 关于“学到了什么、来自哪次 run、为什么仍可信”的 provenance
- 能判断一个 workflow 应该沉淀成 memory、skill 还是 artifact 的 review point

当前 `Isotope` 的 memory boundary 还不足以支撑这种产品需求。它是必要的护栏，但不是最终应用底座。

### 5.2 Skills 不只是 prompt snippet

Hermes 里的 skills 更像 procedural memory：agent 在需要时加载的可复用过程知识。

对 `Isotope` 来说，未来 skill system 至少应该考虑：

- skill 不应该只是文本注入
- skill 应该有 identity、version、provenance、scope，也可能需要 evaluation history
- skill 使用应该在 trace 中可见，并能关联 action outcome
- skill 创建或修改应该是受 policy 约束的 action，并产出 artifact 记录

这更适合通过 artifacts、refs、events 和 policy decisions 表达，而不是藏在 prompt assembly 里。

### 5.3 产品现实需要广泛执行面

Hermes 的实用性来自很多真实入口和执行面：

- terminal
- files
- browser automation
- messaging platforms
- scheduled tasks
- MCP servers
- provider routing
- plugins

`Isotope` 现在不应该实现全部这些东西。

但 Hermes 提醒我们：如果 kernel 永远接不到真实执行面，它会停留在抽象原型。正确转译是：

- kernel 保持窄
- tool protocol、workspace substrate 和 artifact provenance 做扎实
- 让真实执行面以后能接进来，而不是重写 kernel

### 5.4 Context 和 Persona 需要分层

Hermes 很重视 context files 和 personality configuration。

这和 `Isotope` 之前的 study companion 文档是一致的：应用层应该区分 orientation、method、pedagogy、persona。

要学习的不是某个具体文件名，而是：应用身份、行为配置和人格风格必须显式、可加载、可分离，不能混进 kernel。

## 6. Isotope 不应该直接复制什么

### 6.1 不要把产品外壳做成 kernel

Hermes 有很完整的用户侧产品形态。

这些不应该变成 `Isotope` kernel scope：

- messaging platform gateway
- voice mode
- personality presets
- CLI theme / skin
- user-facing cron UX
- plugin marketplace UX
- built-in product tool catalog

这些是 platform 或 product surface，不是 kernel truth。

### 6.2 不要让 memory 变成不透明权威

Hermes 的 memory 很实用，但 `Isotope` 需要更硬的 kernel 纪律。

未来 `Isotope` 的 durable memory 至少应该保留：

- source refs
- basis events
- creating action
- 必要时的 user confirmation
- supersession history
- quality status

kernel 不能把一段 memory text 当成自证正确的事实。

### 6.3 不要让 skills 绕开 policy

如果 skill 能触发工具使用、文件修改、delegation 或 memory mutation，那么 skill 执行仍然必须经过 action proposal、policy decision 和 execution。

skill 不能成为第二套 action system。

### 6.4 不要把 gateway、scheduler 和 runtime 混成一团

Hermes 可以通过很多通信入口和定时任务运行，这作为产品能力很有价值。

但 `Isotope` 需要区分：

- user / session input
- run execution
- scheduler trigger
- worker lifecycle
- tool execution
- approval state

否则 replay 和 audit 会变得很困难。

## 7. 对 Isotope 的压力点

Hermes Agent 提供了几个未来值得压力测试的方向：

| 压力点 | 为什么重要 | Isotope 当前状态 |
| --- | --- | --- |
| skill creation / update as governed action | 检验 procedural memory 能否被 evented 和 policy-bound | 未打开 |
| memory promotion from run artifact | 检验有用知识能否带 provenance 从 artifact 晋升为 durable memory | 只有 boundary |
| scheduled review trigger | 检验长期 agent continuity，而不是隐藏 prompt trick | deferred |
| gateway input as external observation | 检验 messaging input 能否干净进入 canonical state | 只有 external ingestion boundary |
| subagent skill worker | 检验 worker lifecycle、受限 tool grants 和 artifact handoff | 只有 worker first slice |
| real workspace backend | 检验 `shared_ro` boundary 能否发展成真实执行底座 | deferred |
| provider routing / fallback | 检验模型 provider 抽象是否会破坏 action trace | deferred |

近期最有价值的压力测试不是复刻 Hermes。

更合适的是一个很小的 deterministic slice：

- 创建 source artifact
- 产出 study note 或 task note
- 提出 memory 或 skill candidate
- 要求通过 policy approval 才能 promotion
- 产出 durable artifact，解释为什么应该或不应该保留这个 candidate

这能把 Hermes 式学习闭环压力接到 `Isotope` 现有的 action、policy、artifact、replay 架构上。

## 8. 和现有 Isotope demo 的关系

当前 `Isotope` demo 已经证明了 Hermes 所需要的一部分材料：

- action chain
- policy grants
- artifact refs
- controlled retrieval
- checkpoint-assisted rebuild
- approval pause / resume
- workspace read model
- external observation boundary

但它们还没有证明 Hermes 式产品闭环：

- 没有 real LLM loop
- 没有 real memory promotion
- 没有 skill lifecycle
- 没有 real scheduler
- 没有 gateway
- 没有 provider routing
- 没有 real workspace backend

所以正确结论是：

- `Isotope` 已经有一个可以承受 Hermes 式压力的 kernel skeleton。
- 它还不能声称具备 Hermes 式完整 agent product 能力。

## 9. 设计判断

`Hermes Agent` 是 `Isotope` 应用层最相关的参考之一。

它比纯 graph framework 更直接，因为它展示了一个实用的长期 agent 真实需要什么：

- memory
- skills
- tool breadth
- messaging surfaces
- scheduling
- delegation
- provider pragmatism
- user-visible customization

但它对 `Isotope` 的价值是压力来源，不是蓝图。

`Isotope` kernel 应继续围绕这些东西：

- canonical event log
- policy-governed action execution
- typed artifacts and refs
- provenance
- projector replay
- checkpoint-assisted rebuild
- explicit app / domain layers

如果未来 `Isotope` 长出 Hermes 式产品面，kernel 仍然要能解释每一个 durable side effect：它是哪个 evented、policy-bound、replayable action 产生的。
