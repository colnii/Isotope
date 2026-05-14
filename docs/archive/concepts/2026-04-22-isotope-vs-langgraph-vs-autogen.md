# Isotope vs LangGraph vs AutoGen

状态：`concept comparison`

## 1. 摘要

这份文档比较 `Isotope`、`LangGraph` 和 `AutoGen Core` 的内核抽象差异。

最短结论：

- `LangGraph` 是 graph-first runtime，中心是 state、node、edge、checkpoint。
- `AutoGen Core` 是 actor/message-first runtime，中心是 agent、message、topic、event-driven runtime。
- `Isotope` 目标是 action-governance-first kernel，中心是 `ActionProposal -> PolicyDecision -> ActionExecution`。

这不是 API 喜好差异，而是“系统第一性抽象”不同。

## 2. 资料依据

参考资料：

- LangGraph overview: <https://docs.langchain.com/oss/python/langgraph>
- LangGraph Graph API: <https://docs.langchain.com/oss/python/langgraph/graph-api>
- LangGraph durable execution: <https://docs.langchain.com/oss/python/langgraph/durable-execution>
- AutoGen Core overview: <https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/index.html>
- AutoGen message and communication: <https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/framework/message-and-communication.html>
- AutoGen intervention handler: <https://microsoft.github.io/autogen/dev/user-guide/core-user-guide/cookbook/tool-use-with-intervention.html>

本文包含基于公开资料的架构推断。

## 3. 第一性抽象

| 系统 | 第一性抽象 | 典型问题 |
| --- | --- | --- |
| `LangGraph` | graph + state | 图怎么走，状态怎么更新，在哪里 checkpoint |
| `AutoGen Core` | agents + messages + runtime | agent 之间怎么发消息，runtime 怎么分发和调度 |
| `Isotope` | proposal + decision + execution | 模型提出的外部动作如何被裁决、授权、执行、审计和回放 |

`LangGraph` 先问“流程图和状态迁移是什么”。

`AutoGen` 先问“agent 如何通信和协作”。

`Isotope` 先问“任何有副作用的动作是否经过了治理边界”。

## 4. 控制面差异

`LangGraph` 的主控制面是 graph。即使可以动态分支，系统理解仍围绕节点、边和状态更新。

`AutoGen` 的主控制面是 message runtime。agent 接收消息，产生消息，runtime 负责分发、订阅、topic 和 event-driven execution。

`Isotope` 的主控制面是 action lifecycle：

1. model 或 system 产生 `ActionProposal`
2. runtime policy 产生 `PolicyDecision`
3. executor 只能读取 `PolicyDecision.grants`
4. 实际执行成为 `ActionExecution`
5. artifact、worker、tool output、workspace change 都必须能反向追到 execution

这意味着 `Isotope` 把“想做什么”“允许怎么做”“实际做成什么”拆得更硬。

## 5. 治理模型差异

`LangGraph` 很强在 durable execution、checkpoint、human-in-the-loop 和 graph orchestration。

`AutoGen` 很强在 event-driven multi-agent communication、distributed runtime 和 intervention/approval hooks。

`Isotope` 想把治理本身放进 kernel：

- 模型发起的外部动作必须先变成 proposal。
- 真正能执行的权限只能来自 decision grants。
- policy 可以 `approved`、`modified`、`denied`、`pending_user_approval`。
- executor 不能直接消费模型 requested capabilities。
- proposal、decision、execution 都必须进 event log。

因此 `Isotope` 的治理强度更像执行控制面，而不是普通 trace 或 callback。

## 6. 持久化和回放

`LangGraph` 的 durable execution 和 checkpoint 是非常值得学习的能力。

`AutoGen` 的 event-driven runtime 对分布式 agent 和 observable system 很有参考价值。

`Isotope` 需要的持久化更具体：

- append-only canonical event log 是事实源。
- checkpoint / snapshot 只是恢复和查询优化，不是第二事实源。
- `ActionProposal`、`PolicyDecision`、`ActionExecution` 必须可回放。
- artifact、worker、workspace、memory、approval 都应该从 event 投影出来。

这让 `Isotope` 更像一个受治理的 execution kernel。

## 7. Workspace 和执行基座

`LangGraph` 通常把 workspace 和执行环境放在 integration 或 tool 层。

`AutoGen` 有 executor、extension 和 distributed runtime，但其核心语言仍是 agent/message。

`Isotope` 希望把 workspace 当成 kernel 对象：

- workspace 是 policy-bound execution resource。
- 共享只读、隔离读写、远端执行等都应由 grants 控制。
- workspace upgrade 应该是 action，而不是 shell tool 的隐式副作用。
- artifact capture 应该有 provenance。

这不是说其他系统做不到，而是 `Isotope` 的设计重心不同。

## 8. Isotope 应该学习什么

从 `LangGraph` 学：

- durable execution
- checkpoint / resume
- graph 和 state 的可解释性
- human-in-the-loop 的 runtime 处理

从 `AutoGen` 学：

- event-driven 多 agent runtime
- actor-like agent communication
- distributed runtime 和 observability
- intervention handler / approval 的设计经验

但 `Isotope` 不应该变成：

- graph workflow engine
- actor/message framework
- 只靠 transcript 和 callbacks 的 agent shell

`Isotope` 应该把这些经验转译成自己的 kernel 语言：proposal、decision、execution、artifact、workspace、event、checkpoint。

## 9. 对照总结

| 维度 | `Isotope` | `LangGraph` | `AutoGen Core` |
| --- | --- | --- | --- |
| 核心对象 | action lifecycle | graph state | agents and messages |
| 调度模型 | model proposes, runtime arbitrates | graph edges / control flow | event-driven message routing |
| 副作用治理 | policy grants first | node/tool-level control | intervention / runtime hooks |
| 持久化 | event log + snapshot | checkpoint / durable execution | event/runtime observability |
| workspace | kernel resource | integration detail | executor / extension surface |
| 目标形态 | governed agent kernel | orchestration runtime | multi-agent runtime |

## 10. 设计判断

`LangGraph` 和 `AutoGen` 都是重要参考，但它们不是 `Isotope` 的模板。

`Isotope` 的差异化应该是：

- action-governance-first
- policy is kernel
- workspace is kernel object
- artifacts and refs are first-class
- every durable side effect is evented and replayable

如果以后借鉴 `LangGraph` 或 `AutoGen`，应借它们的工程经验，而不是放弃 `Isotope` 的治理中心。
