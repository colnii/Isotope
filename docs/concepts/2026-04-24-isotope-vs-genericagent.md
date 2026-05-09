# Isotope vs GenericAgent

状态：`concept comparison`

## 1. 摘要

本文把 [`GenericAgent`](https://github.com/lsdefine/GenericAgent) 当作 `Isotope` 的参考对象来分析。

目标不是排名，而是回答：

- `GenericAgent` 实际优化的是什么
- `Isotope` 应该从它学什么
- 哪些部分不应直接复制

短结论：

- `GenericAgent` 更像 self-evolving execution engine。
- 它特别重视 layered memory、SOP crystallization、context budget 和 execution-verified memory。
- 它对 `Isotope` 的价值在于提醒我们：agent 不应该只执行一次任务，还应该从执行中沉淀高密度上下文和可复用经验。
- 但 `Isotope` 不应把 file-SOP memory 或 prompt obedience 当成 kernel truth。

## 2. GenericAgent 优化的是什么

公开项目给人的核心印象是：

- core 很小
- 工具集相对原子化
- agent 在真实计算机环境中执行任务
- 完成任务后把经验沉淀成可复用 skill / SOP
- memory 分层，强调长期复用

它的中心不是 typed event kernel，而是：

- 怎么让 agent 在有限 context 内保持高信息密度
- 怎么把成功任务转成可复用过程
- 怎么让系统越用越会做事

这对 `Isotope` 很重要，因为 `Isotope` 如果只做 action chain 和 event log，而没有学习、压缩、沉淀能力，长期会变成干净但贫血的 runtime。

## 3. 对照表

| 维度 | `Isotope` | `GenericAgent` |
| --- | --- | --- |
| 第一身份 | policy-governed kernel | self-evolving execution engine |
| 持久化中心 | canonical event log + artifacts + checkpoint | layered memory + SOP / skills |
| 执行中心 | action proposal / decision / execution | agent loop + atomic tools |
| 学习机制 | 尚未产品化 | 从任务中沉淀 skills / SOP |
| 强项 | 可审计、可回放、policy-bound | 信息密度、经验沉淀、上下文管理 |
| 风险 | 过抽象、缺少学习闭环 | memory / SOP 可能变成非 typed truth |

## 4. Isotope 应该学习什么

### 4.1 Active Context Density

`GenericAgent` 很强调当前上下文的密度。

这对 `Isotope` 的启发是：kernel 不能只保留所有事件，还要支持应用层把有用信息整理成可用上下文。

未来可能需要：

- context summary artifact
- run digest
- worker handoff summary
- memory candidate
- skill candidate
- evidence-backed compact note

但这些都应该是 typed artifact 或 memory record，而不是随手塞进 prompt 的文本。

### 4.2 Execution-Verified Memory

GenericAgent 的重要直觉是：可靠 memory 应该来自执行结果，而不是模型想当然写下来的偏好。

`Isotope` 可以转译成：

- memory write 必须有 source refs 或 basis events
- memory promotion 应该来自完成的 run / artifact / review
- memory 需要 quality status
- memory 应该可 supersede
- memory 写入本身应该是 action

这和 `Isotope` 的 evented / provenance-first 方向一致。

### 4.3 Skills As Reusable Operational Knowledge

`GenericAgent` 的 SOP / skill 思路提醒 `Isotope`：skill 不只是 prompt。

未来 `Isotope` 的 skill 可以被理解为：

- 一种可版本化 artifact
- 一种受 policy 控制的可调用能力
- 一种可以记录创建依据、使用历史和效果的 procedural memory

skill 创建、更新、调用都应该进入 event log。

## 5. 不应该复制什么

### 5.1 不要让文件 SOP 成为 kernel truth

SOP 文件适合作为 product / app 层的能力，但不应该替代：

- canonical event log
- typed artifact
- policy decision
- run state projection

`Isotope` 可以读取 SOP，也可以生成 SOP，但 kernel truth 仍应来自 canonical events。

### 5.2 不要把 prompt obedience 当成 policy

GenericAgent 式系统容易依赖“agent 应该遵守 SOP”。

`Isotope` 的 policy 不能停留在 prompt 层。

外部动作必须通过：

- proposal
- decision
- grants
- execution

### 5.3 不要把自我进化当成无边界写入

系统能改进自己是重要方向，但不能让 agent 随便修改 memory、skill、prompt 或 tool。

所有这些修改都应该：

- 有 action basis
- 有 provenance
- 有 approval 或 policy profile
- 能回放
- 能撤销或 supersede

## 6. 对 Isotope 的压力点

`GenericAgent` 暴露出这些 `Isotope` 迟早要面对的问题：

| 压力点 | 对 Isotope 的含义 |
| --- | --- |
| context budget | 需要 digest / compaction / retrieval policy |
| layered memory | 需要区分 run memory、session memory、skill memory |
| skill crystallization | 需要 skill artifact 和 promotion flow |
| self-evolution | 需要 governed mutation，而不是自由改写 |
| execution verification | 需要 memory 与完成 action / artifact 绑定 |

## 7. 近期可做的最小转译

不要现在复制完整 GenericAgent。

更合适的近期 deterministic spike 是：

1. 从一个完成的 run 里选取 artifact。
2. 生成 `memory_candidate` 或 `skill_candidate` artifact。
3. 记录它来自哪些 source refs 和 execution。
4. 通过 policy 决定是否允许 promotion。
5. 即使不真正启用 memory store，也把 promotion decision 写进 event / artifact。

这能测试 `Isotope` 是否能承受“经验沉淀”压力，而不打开完整 memory engine。

## 8. 设计判断

`GenericAgent` 对 `Isotope` 的价值不是具体实现，而是提醒：

- 长期 agent 需要学习闭环。
- context density 是真实工程问题。
- memory 必须和执行结果建立关系。
- skill 应该是可追踪的 procedural knowledge。

`Isotope` 应吸收这些问题意识，但仍坚持自己的 kernel 边界：

- action governance
- canonical event log
- policy grants
- typed artifacts
- provenance
- replay / checkpoint

这样才能在以后支持 self-improving agent，而不是把 kernel 变成一堆 prompt 和 SOP 文件。
