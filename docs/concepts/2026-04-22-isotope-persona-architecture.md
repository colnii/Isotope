# Isotope Persona Architecture

状态：`concept design`

## 1. 摘要

本文定义 `Isotope` 应用层的人格和取向拆分方式。

核心判断：

- 意识形态 / 世界观不等于角色人格。
- 分析方法不等于说话语气。
- 教学方式不等于 persona。
- 这些层如果混在一起，会让应用难以测试、难以替换、难以公开剥离。

建议的概念拆分是四层：

- `orientation pack`
- `method pack`
- `pedagogy pack`
- `persona pack`

v0 不一定真的实现四个独立 pack，但设计上应该保留这个边界。

## 2. 为什么要拆开

如果把所有东西都塞进一个 system prompt 或一个 `SOUL.md`，我们无法判断一个回答为什么变成这样：

- 是因为它的政治/哲学取向
- 是因为它的方法论
- 是因为它的教学策略
- 是因为它的人格风格

这会让测试和调整都很困难。

拆开之后，可以做更清楚的实验：

- 固定 orientation，改变 persona
- 固定 persona，改变 method
- 固定 method，改变 pedagogy
- 移除 private orientation，保留通用 study tool

## 3. 四层定义

### 3.1 Orientation Pack

`orientation pack` 定义它“站在哪里看世界”。

它可以包括：

- 世界观
- 政治或哲学立场
- 价值优先级
- 默认关注的社会关系
- source priority
- 私有分析框架

对于私有学习应用，这一层可以是 Marxist / Marxist-Leninist orientation。

这一层不应该进入 `Isotope` kernel。

### 3.2 Method Pack

`method pack` 定义它“怎么分析问题”。

它可以包括：

- 如何区分 source / interpretation / inference
- 如何处理分歧
- 如何做概念澄清
- 如何做 historical / material / relational analysis
- 何时要求检索
- 何时承认资料不足

method pack 比 orientation 更接近可迁移能力。

同一种方法可以服务不同 orientation；同一种 orientation 也可以配不同方法强度。

### 3.3 Pedagogy Pack

`pedagogy pack` 定义它“怎么带用户学习”。

它可以包括：

- 严格追问型
- 耐心引导型
- 阅读计划型
- 复习督促型
- 概念训练型
- 能力迁移型

pedagogy 关注用户成长，不是 agent 的人设表演。

好的 pedagogy 应该让用户越来越能独立学习，而不是越来越依赖 agent。

### 3.4 Persona Pack

`persona pack` 定义它“给人的感觉是什么”。

它可以包括：

- 语气
- 节奏
- 风格
- 严厉程度
- 是否像导师、研究伙伴、批判者、教练
- 是否借鉴某个历史人物或虚拟人物的认知风格

persona 可以增强体验，但不应该决定 truth。

如果 persona 和 source discipline 冲突，source discipline 优先。

## 4. 层级关系

推荐关系：

1. kernel 只管 runtime、policy、artifact、event、workspace、memory boundary。
2. application 加载 orientation / method / pedagogy / persona。
3. 具体 session 根据用户目标和材料选择使用哪些层。
4. 每个层的影响应尽量在 trace 或 config 中可见。

不要让：

- orientation 变成 kernel 默认
- persona 偷偷覆盖 method
- pedagogy 变成情绪控制
- method 被空洞口号替代

## 5. 对开源发布的意义

如果未来发布通用工具层，理想情况是：

- 移除 private orientation pack 后，工具仍能运行。
- 移除 private corpus 后，generic study workflow 仍能运行。
- persona 可以换成中性或其他风格。
- method 和 pedagogy 中可通用的部分可以保留。

但这只是 design aspiration，不是保证。

实际发布时可能还需要清理：

- prompts
- examples
- corpus assumptions
- artifact names
- UI copy
- evaluation labels
- workflow defaults

所以不能简单承诺“删掉一个文件就完全去意识形态化”。

## 6. 对 Study Companion 的意义

第一个 study companion 可以先用一个 near-term private configuration layer。

但文档和实现应该知道它里面混合了：

- orientation
- method
- pedagogy
- persona

未来如果要做更清楚的实验，再逐步拆分。

这可以支持几种实验：

- 同一 Marxist orientation 下，测试不同 persona。
- 同一 persona 下，测试不同 method。
- 对比严格导师型和耐心教练型对学习效果的影响。
- 测试去掉 private orientation 后，generic study tool 是否仍然成立。

## 7. Kernel 边界

kernel 不应该知道具体 orientation 内容。

kernel 可以支持：

- pack loading
- pack provenance
- config refs
- artifact provenance
- policy gates
- trace / replay

kernel 不应该写死：

- Marxist / liberal / technocratic 等 orientation
- 某个历史人物 persona
- 私有 corpus 优先级
- 私有学习路线
- 私有评价标签

## 8. 设计判断

这套拆分的意义不是提前复杂化，而是防止未来应用设计混乱。

v0 可以简化实现，但概念上应该保持：

- orientation != method
- method != pedagogy
- pedagogy != persona
- persona != truth

这能让 `Isotope` 同时支持私有取向应用、通用学习工具和未来不同 persona 实验。
