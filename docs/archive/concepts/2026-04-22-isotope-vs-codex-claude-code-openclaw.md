# Isotope vs Codex vs Claude Code vs OpenClaw

状态：`concept comparison`

## 1. 摘要

本文比较 `Isotope` 与 `Codex`、`Claude Code`、`OpenClaw`。

短结论：

- `Codex` 更像 coding agent product。
- `Claude Code` 更像 coding harness product。
- `OpenClaw` 更像 assistant / gateway platform product。
- `Isotope` 目标是 policy-governed agent kernel / platform。

因此 `Isotope` 可以学习它们的产品经验、权限经验、workspace 经验和 subagent 经验，但不应该直接复刻它们的产品外壳。

## 2. 资料依据

参考资料：

- Codex docs hub: <https://developers.openai.com/>
- Codex use cases: <https://developers.openai.com/codex/use-cases>
- Claude Code overview: <https://code.claude.com/docs/en/overview>
- Claude Code subagents: <https://code.claude.com/docs/en/sub-agents>
- Claude Code security: <https://code.claude.com/docs/en/security>
- Claude Code sandboxing: <https://code.claude.com/docs/en/sandboxing>
- OpenClaw README: <https://github.com/openclaw/openclaw/blob/main/README.md>
- OpenClaw security guide: <https://github.com/openclaw/openclaw/blob/main/docs/gateway/security/index.md>

部分结论是基于公开资料的架构推断。

## 3. 一眼对照

| 维度 | `Isotope` | `Codex` | `Claude Code` | `OpenClaw` |
| --- | --- | --- | --- | --- |
| 第一身份 | kernel / platform | coding agent product | coding harness product | assistant / gateway product |
| 中心任务 | governed execution | 完成 coding task | 本地 agentic coding loop | session、channel、device、assistant continuity |
| 控制面 | `ActionProposal -> PolicyDecision -> ActionExecution` | task / review / worktree / local env | permissions、subagents、local tools、sandbox | gateway、sessions、skills、nodes、sandbox policy |
| domain 中心 | domain-neutral | coding-first | coding-first | assistant-first |
| workspace 姿态 | kernel object | product feature | working directory + permissions | host / sandbox execution |
| 产品面 | deferred | app / IDE / CLI / web | terminal / IDE / desktop / browser | gateway / companion apps / channels |

## 4. 和 Codex 的差异

`Codex` 是强 coding 产品。

它优先回答的问题是：

- 如何把 coding task 分派给 agent
- 如何让 agent 在 worktree / local environment 中工作
- 如何审查修改
- 如何和 IDE / CLI / app / web 产品面结合

这些能力对 `Isotope` 很有参考价值，尤其是：

- worktree / local environment 的产品化经验
- review flow
- task scoping
- agent approval / security
- coding workflow 的交付闭环

但 `Isotope` 不应该把 coding 作为 kernel 的默认 domain。

`Isotope` 需要保留更底层的问题：

- 任何外部动作如何被 proposal / decision / execution 记录
- workspace 权限如何由 grants 控制
- artifact 和 trace 如何可回放
- domain pack 如何挂载而不污染 kernel

## 5. 和 Claude Code 的差异

`Claude Code` 是成熟的本地 coding harness。

它非常值得学习：

- 默认只读或低权限开始
- 写文件、执行命令、危险操作需要权限或 sandbox
- subagents 有上下文隔离和任务边界
- skills / commands / hooks 让产品可扩展
- checkpoint 和回退增强本地 coding 安全感

但这些在 Claude Code 中主要服务于 coding product。

`Isotope` 应把它们抽象为更通用的 kernel 能力：

- approval boundary
- workspace lease / binding / artifact capture
- worker lifecycle
- tool protocol
- evented trace
- policy profile

换句话说，Claude Code 展示了“优秀 coding harness 应该怎么用”，`Isotope` 要回答“支撑这种 harness 的通用 runtime 边界是什么”。

## 6. 和 OpenClaw 的差异

`OpenClaw` 更接近 assistant / gateway platform。

它关注：

- 多渠道入口
- gateway control plane
- sessions
- skills
- sandbox policy
- companion apps
- assistant continuity

这些对 `Isotope` 的参考价值很高，尤其是：

- gateway / session / channel 的边界
- skill registry
- sandbox 和 host execution 的切换
- long-running assistant 的产品结构

但 `OpenClaw` 的第一身份仍是 assistant/gateway product。

`Isotope` 的第一身份应该是 kernel：

- session / run / agent / worker / workspace / artifact / event 都是 typed runtime objects
- user-facing gateway 不应该成为事实源
- product session 不应该绕开 canonical event log
- skills 和 tools 不应该绕开 policy

## 7. Isotope 应该学习什么

从 `Codex` 学：

- coding task scoping
- worktree / local environment 的用户体验
- review / approval / diff 的产品闭环
- agent 结果如何呈现给用户

从 `Claude Code` 学：

- subagent UX
- permissions and sandboxing
- local tool safety
- checkpointing
- skills / commands / hooks 的使用方式

从 `OpenClaw` 学：

- gateway / session / channel 的产品组织
- assistant continuity
- skills registry
- sandbox / host execution policy
- remote surfaces 和 companion apps

## 8. Isotope 不应该复制什么

不要直接复制：

- coding-first product shell
- assistant-first gateway semantics
- 具体 UI / CLI 形态
- 具体人格或 companion product 叙事
- 以工作目录或聊天记录作为唯一事实源
- 让 tool / skill / subagent 绕开 policy grants

这些都可以成为 application 或 product 层，不应成为 kernel truth。

## 9. 对 Isotope 的设计约束

比较这些项目后，`Isotope` 应坚持：

- kernel-first，而不是 product-shell-first
- domain-neutral，而不是 coding-only 或 assistant-only
- policy-gated execution，而不是工具自由调用
- workspace as resource，而不是 agent 自带人格空间
- event log as truth，而不是聊天 transcript 或 workspace file 作为事实源
- artifacts and refs as handoff boundary，而不是只传 prose summary

## 10. 结论

`Codex`、`Claude Code` 和 `OpenClaw` 都比 `Isotope` 当前 demo 更产品化，也更接近真实用户场景。

但它们的强项是产品闭环，`Isotope` 的目标是把这些产品背后需要的 runtime 控制面抽象出来。

所以 `Isotope` 不应该问“如何做一个新的 Codex / Claude Code / OpenClaw”，而应该问：

- 支撑这类产品的通用 action governance 是什么
- workspace、tool、memory、skill、approval、worker 如何被统一审计和回放
- domain pack 如何接入而不污染 kernel

这才是 `Isotope` 的区别。
