# Isotope vs PetGPT

状态：`concept comparison`

## 1. 摘要

本文把 [`PetGPT`](https://github.com/JulesLiu390/PetGPT) 当作 `Isotope` 的实践参考。

目标不是说 `PetGPT` 已经等于 `Isotope` kernel，而是回答：

- `PetGPT` 实际优化的是什么
- `Isotope` 应该学什么
- 哪些不应直接复制

短结论：

- `PetGPT` 更像 workspace-backed personal assistant runtime。
- 它对 `Isotope` 的价值主要在执行基座现实性：workspace state、path-safe file primitives、tool/session guardrails、subagent lifecycle control、trace/export discipline。
- 但 `Isotope` 不应该继承它的产品语义、Tauri shell、桌宠/社交形态或 persona shell。

## 2. PetGPT 优化的是什么

公开项目呈现的是一个本地 AI 桌面助手产品：

- 桌宠 / assistant shell
- 多 LLM backend
- MCP tool runtime
- group chat / social agent 能力
- workspace-backed memory 和 personality
- 本地文件、工具、会话和导出能力

从架构角度看，它最有价值的不是“桌宠形态”，而是：

- agent 真的要面对本地 workspace
- 文件路径和权限必须可控
- 工具循环需要 guardrails
- subagent 生命周期需要可见
- trace/export 对调试和信任很重要

## 3. 对照表

| 维度 | `Isotope` | `PetGPT` |
| --- | --- | --- |
| 第一身份 | kernel / runtime prototype | personal assistant runtime / desktop product |
| workspace | policy-bound kernel resource | user-visible workspace state |
| 工具执行 | action / policy / executor | 本地工具、MCP、workspace 操作 |
| persona | application layer | product identity 的一部分 |
| trace | canonical event + projector | trace/export discipline |
| 强项 | 治理、回放、typed boundary | 真实执行面、用户可见状态 |
| 直接复制风险 | 不适用 | 产品语义会污染 kernel |

## 4. Isotope 应该学习什么

### 4.1 Workspace 必须现实

`Isotope` 当前有 workspace read model 和 `shared_ro` first slice，但还没有真实 filesystem、container、git worktree 或 remote executor。

`PetGPT` 提醒我们：长期 agent 如果不能和真实 workspace 打交道，就很难成为真实产品。

但转译到 `Isotope` 时，workspace 仍应是：

- policy-bound resource
- 有 lease / binding / release
- 有 path-safety
- 有 artifact capture
- 有 provenance
- 可 replay / checkpoint

### 4.2 文件原语要安全

本地 assistant 很容易出问题的地方是文件读写。

`Isotope` 应把未来 file operations 设计成受控工具协议，而不是裸 shell：

- read / write / patch / delete / move 应该有明确 action type
- 路径必须经过 workspace policy
- 写入应该产生 artifact 或 diff record
- 高风险操作需要 approval
- 执行结果要能进入 event log

### 4.3 Tool Loop 需要 Guardrails

现实工具循环会遇到：

- 重复执行
- 工具失败
- 输出过长
- 上下文污染
- 隐式状态漂移

`Isotope` 的对应机制应该是：

- action lifecycle
- retry / cancel / supersede
- controlled artifact content retrieval
- event schema compatibility
- policy reason codes
- trace / replay

### 4.4 Subagent 生命周期要可见

PetGPT 的 subagent lifecycle 对 `Isotope` 有启发。

`Isotope` 已有 worker first slice，但未来还需要：

- worker goal
- worker grants
- worker workspace binding
- worker result artifact
- worker completion / failure / cancellation
- supervisor handoff

不能只把 subagent 当成一次函数调用。

### 4.5 Trace / Export 是信任基础

对本地 agent 来说，用户需要知道它做了什么。

`Isotope` 应继续坚持：

- event log 是事实源
- trace 可以人读
- artifact 可以引用
- checkpoint 可以恢复
- export 不暴露不该暴露的 full content

## 5. 不应该复制什么

不要把这些变成 kernel：

- 桌宠产品语义
- Tauri shell 结构
- social-pet vocabulary
- persona-first runtime
- UI 状态作为事实源
- workspace 文件作为唯一 truth

`Isotope` 可以以后做自己的 product shell，但 kernel 不应该绑定任何一种产品叙事。

## 6. 对 Isotope 的压力点

`PetGPT` 暴露的压力点：

| 压力点 | 对 Isotope 的含义 |
| --- | --- |
| 真实 workspace | 需要从 read model 走向真实 substrate |
| path safety | workspace policy 需要成为硬边界 |
| file mutation | 写操作需要 action + approval + artifact |
| subagent handoff | worker 结果应通过 artifact / ref 回传 |
| trace/export | 用户侧可解释性不能只靠内部日志 |
| product shell | kernel 和 product UI 必须分层 |

## 7. 近期可做的最小转译

不要现在做完整本地 workspace product。

更合理的近期方向是：

1. 设计 Tool Protocol Boundary。
2. 定义 read/write/patch 这类 future tool 的最小 contract。
3. 保持真实 filesystem mutation deferred。
4. 先用 deterministic artifact capture 模拟 workspace output。
5. 检查 replay、checkpoint、policy grants 是否还能成立。

这样可以吸收 PetGPT 的执行基座现实性，而不提前打开真实文件系统风险。

## 8. 设计判断

`PetGPT` 对 `Isotope` 的最大价值是让我们不要只停留在纸面 kernel。

一个 agent runtime 迟早要面对：

- 文件
- workspace
- 工具
- subagent
- trace
- 用户可见状态

但 `Isotope` 的回答应该更 kernel 化：

- workspace 是受 policy 约束的资源
- tool call 是 action execution
- file output 应进入 artifact / provenance
- UI 和 workspace file 都不是事实源
- replay 和 checkpoint 必须能恢复状态

所以：学它的现实感，不学它的产品语义。
