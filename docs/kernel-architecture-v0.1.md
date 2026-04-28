# Isotope Kernel Architecture v0.1（草案）

状态：`draft`

本文件基于 `kernel-spec-v0.1.md`，只说明当前 contracts 由哪些 runtime modules 实现。它不重新定义 spec，不新增架构大方向。

承诺强度沿用：

- `Hard Contract`：必须被架构边界保证。
- `v0 Implementation Choice`：当前推荐模块拆法或实现方式，可调整。
- `Example / Schema Sketch`：仅解释，不构成协议。
- `Open Question`：尚未收敛。

## 1. Architecture Goal

### Hard Contract

Isotope kernel 必须保证：

- 执行状态归 `Run`，连续性归 `Session`。
- 外部动作进入 canonical action chain。
- runtime policy 是最终裁决者。
- 执行器只能使用 `PolicyDecision.grants`。
- canonical event log 是 `RunState` / `SessionState` 的唯一事实源。
- 外部输入不能直接驱动 state projector。
- 正式协议使用结构化 `ResourceRef`。
- durable memory 必须结构化、可追溯、可审计。

### v0 Implementation Choice

v0.1 runtime 可以按以下模块拆分：

- Server API
- Agent Runtime
- Action Compiler
- Policy Engine
- Executor
- Workspace Manager
- Event Store
- Projector
- Artifact Store
- Retrieval Service
- Memory Service
- External Ingestion Adapter

## 2. Module Map

| Module | Primary Responsibility |
| --- | --- |
| Server API | 接收 client 请求、暴露 session/run/event/artifact/memory/approval 接口 |
| Agent Runtime | 管理 run 内 supervisor / worker loop、delegation 和 agent lifecycle |
| Action Compiler | 将 model-facing compact action 编译成 canonical `ActionProposal` |
| Policy Engine | 对 proposal 做裁决并生成 `PolicyDecision` |
| Executor | 基于 decision grants 创建并运行 `ActionExecution` |
| Workspace Manager | 管理 workspace binding、lease、隔离升级 |
| Event Store | 保存 append-only canonical events |
| Projector | 从 canonical events 投影 `RunState` / `SessionState` |
| Artifact Store | 保存 artifacts、raw external inputs、provenance-linked durable objects |
| Retrieval Service | 将 `ResourceRef` 按授权物化成可见内容 |
| Memory Service | 管理 structured memory、memory query、controlled expand |
| External Ingestion Adapter | 将外部 raw input 规范化为 canonical event、external observation 或 artifact-only |

## 3. Server API

### Hard Contract

Server API 不能绕过 kernel contracts。所有会影响执行或状态的请求，最终必须落到 canonical action chain、canonical event log 或 artifact/provenance 保存路径。

### v0 Implementation Choice

v0.1 采用 server-first。

`HTTP JSON + SSE` 是当前推荐 transport 起点。

Server API 至少面向这些能力域：

- sessions
- runs
- event stream
- artifacts
- approvals
- memory query
- retrieval

具体 retrieval endpoint shape 仍是 Open Question；这里仅表示 Server API 需要能暴露受控 retrieval 能力。

run 可以在没有在线 client 附着的情况下继续运行或恢复。

UI、CLI 和 API client 消费同一套 event stream，避免各自维护不可回放的内部 orchestration state。

### Open Question

- public endpoint 形状。
- auth / identity。
- streaming event envelope。
- pagination / replay cursor。
- approval API 细节。
- retrieval endpoint shape。

## 4. Agent Runtime

### Hard Contract

supervisor / worker 是 kernel 一等概念。delegation 可以由模型动态提出，但 runtime policy 是最终裁决者。

Agent Runtime 不能绕过 Action Compiler、Policy Engine、Executor 或 Event Store。

### v0 Implementation Choice

Agent Runtime 负责：

- 管理 run 内 supervisor / worker loop。
- 维护 agent instance 与 thread 的运行态关系。
- 将模型侧 action intent 交给 Action Compiler。
- 根据 execution result 和 projected state 推进 run 内 agent loop。

### Open Question

- worker promotion 的触发条件和持久化语义。
- agent loop 与 executor registry 的具体边界。

## 5. Action Compiler

### Hard Contract

模型可以输出 compact action / intent，但 policy、execution 和 event log 只消费 canonical objects。

进入 policy 前，runtime 必须把模型侧输出编译、校验并规范化成 canonical `ActionProposal`。

### v0 Implementation Choice

Action Compiler 是 v0.1 推荐模块，用来隔离 model-facing protocol 和 canonical schema。

它负责：

- 解析 compact action / intent。
- 解析或映射 ref handles。
- 补齐 run、agent、thread 等 runtime context。
- 校验 action type 与 payload 形状。
- 生成 canonical `ActionProposal`。
- 在失败时返回可诊断的 compile error。

### Open Question

- compact protocol 用 JSON、tool calling、mini DSL，还是多模式。
- repair / reprompt / escalate 规则。
- `ActionTypeRegistry` 已由 Action Compiler 消费用于 compact tool lookup，并已由 Policy Engine 用于 requirement lookup；registry schema / 版本化仍未定，当前最小边界见 `docs/action-type-registry-v0.1.md`。

## 6. Policy Engine

### Hard Contract

runtime policy 是 delegation 和 execution 的最终裁决者。

执行时只能使用 `PolicyDecision.grants`，不能使用未经裁决的 requested capabilities。

`PolicyDecision.modified` 是一等 outcome。Policy Engine 可以缩减 scope、tools、workspace mode 和 budget 后批准。

### v0 Implementation Choice

Policy Engine 输入 canonical `ActionProposal`，输出 canonical `PolicyDecision`。

它负责：

- 判断 action 是否允许。
- 生成 grants。
- 将 requested capabilities 降权为 effective grants。
- 判断是否需要 user approval。
- 记录 denied / modified / pending 的 reason。

### Open Question

- policy profile 的格式和版本化。
- approval 与 policy decision 的状态关系。
- policy 是否按 action type registry 分层。

## 7. Executor

### Hard Contract

Executor 必须基于 `PolicyDecision.grants` 执行。

Executor 不能读取或依赖未经裁决的 requested capabilities。

每次实际执行必须形成 `ActionExecution`，并通过 canonical event 记录执行开始、完成、失败或取消。

artifacts 和 outputs 必须能追溯到 execution。

### v0 Implementation Choice

Executor 是 action-type aware 的运行模块。

它负责：

- 创建 `ActionExecution`。
- 固化 effective payload 和 grants。
- 调用 workspace、retrieval、artifact、memory 等服务。
- 发出 execution lifecycle events。
- 将 outputs / artifacts 关联回 execution。

### Open Question

- `ActionExecution.result` 的统一形状。
- retry / cancel / supersede 语义。
- executor registry 和 action type registry 是否合并。

## 8. Workspace Manager

### Hard Contract

Workspace 是 execution resource，不是 agent 身份的一部分。

workspace 访问、绑定和升级必须受 runtime policy 控制。

### v0 Implementation Choice

Workspace Manager 负责：

- 创建或绑定 workspace。
- 管理 shared / isolated workspace mode。
- 管理 workspace lease。
- 将 workspace binding 关联到 run、agent 或 execution。
- 为 executor 提供受 grants 约束的 workspace handle。

当前推荐策略是默认共享偏只读，写操作、长任务或高风险工具升级到 isolated workspace。

### Open Question

- 第一版 substrate：process、git worktree、container 还是 remote executor。
- path safety。
- 文件变更追踪。
- workspace cleanup 和 artifact capture。

## 9. Event Store

### Hard Contract

Event Store 保存 append-only canonical event log。

canonical event log 是 `RunState` / `SessionState` 的唯一 source of truth。

外部 raw log、provider response、callback 原文、workspace 文件或数据库快照不能直接驱动 state projector。

### v0 Implementation Choice

Event Store 负责：

- append canonical events。
- 提供按 run/session 查询事件流。
- 支持 replay cursor。
- 支持 checkpoint 生成所需的事件读取。
- 保存 proposal、decision、execution、approval、artifact、memory、ingestion 相关事件。

### Open Question

- event envelope schema。
- event ordering 和 idempotency。
- event compaction 策略。
- event store 物理存储选型。

## 10. Projector

### Hard Contract

Projector 只能消费 canonical events。

`RunState` / `SessionState` 是 materialized views，不是新的事实源。

外部 observation 不能覆盖 native state。

imported / derived observation 一旦影响展示或派生状态，必须保留质量、来源和新鲜度信息。

### v0 Implementation Choice

Projector 负责：

- 从 event log 投影 `RunState`。
- 从 event log 投影 `SessionState`。
- 应用 checkpoint 加速重建。
- 将 external observation 投影到 observation / diagnostics 区域。
- 暴露 conflict / stale / partial observation 状态。

### Open Question

- `RunState` 字段 schema。
- `SessionState` 字段 schema。
- checkpoint 格式、频率和迁移。
- checkpoint ownership：由 Projector 产出、Event Store 管理，还是后续独立为 checkpoint service。
- projection rebuild 策略。

## 11. Artifact Store

### Hard Contract

Durable objects 只有在被 canonical event 引入、注册、钉住，或作为 canonical event 携带的规范化事实时，才能影响状态。

外部 raw input 如果不能规范化，只能作为 artifact / provenance 保存，不能推进 state。

### v0 Implementation Choice

Artifact Store 负责：

- 保存 artifacts。
- 保存 raw external inputs。
- 保存 imported observation payloads。
- 保存 tool outputs 或其 durable handles。
- 维护 artifact provenance。
- 提供可被 `ResourceRef` 定位的 artifact identity。

### Open Question

- artifact schema 和 artifact type registry。
- artifact version pinning / content addressing。
- binary artifact handle。
- artifact retention 策略。

## 12. Retrieval Service

### Hard Contract

正式访问资源必须使用结构化 `ResourceRef`。

policy、retrieval、tool input 都先对 refs 生效。

runtime 解引用后，再决定调用方能拿到 summary、full content、structured slice 或 denial。

URI-like 写法只用于 display/debug。

### v0 Implementation Choice

Retrieval Service 负责：

- 校验 `ResourceRef`。
- 解引用 artifact、memory、event、workspace 或 tool output。
- 根据 principal / purpose / grants / policy profile 执行 retrieval-time authorization checks。
- 在不扩大 `PolicyDecision.grants` 的前提下决定 served materialization。
- 返回被授权的 materialized view。
- 记录 retrieval 相关审计事件或可追溯记录。

### Open Question

- `ResourceRef` 完整 locator / selector 变体。
- requested view / served view 的最终形状。
- ranking、裁剪、budget、expand 降级策略。
- retrieval event 是否必须对所有读取落盘。

## 13. Memory Service

### Hard Contract

Memory 不是 transcript dump。

`MemoryRecord` 必须有结构化 content 和 provenance。

Durable memory 写入必须可审计、可追溯，并进入 canonical action/event 路径。

Memory 默认不内联大块 artifact 内容。

### v0 Implementation Choice

Memory Service 负责：

- 管理 thread / run / session memory。
- 写入 structured memory。
- 处理 append + supersession。
- 支持 memory query。
- 支持 controlled expand。
- 通过 Retrieval Service 获取 source refs 的授权物化内容。

Memory Service 不能绕过 action chain 直接提交 durable memory。durable memory write 必须由已授权 execution 触发，并通过 canonical event 进入可审计路径。

当前推荐 action type 名是 `write_memory` 和 `promote_memory`，但名称不是硬协议。

### Open Question

- `MemoryRecord` 最终 schema。
- memory ranking / exposure。
- session memory promotion policy。
- controlled expand 的预算、裁剪、降级和审计事件。
- memory 与 artifact graph 的索引关系。

## 14. External Ingestion Adapter

### Hard Contract

外部输入必须先经过 ingestion，不能直接更新 `RunState` / `SessionState`。

ingestion 只有三种结果：

- canonical event。
- 被 canonical event 接纳的 external observation。
- artifact / provenance-only。

外部 observation 不是第二事实源，不能覆盖 native state。

imported / derived observation 一旦影响展示或派生状态，必须保留足够的质量、来源和新鲜度信息，不能伪装成 native state。

### v0 Implementation Choice

External Ingestion Adapter 负责：

- 接收 provider response、callback、external logs 等 raw input。
- 将 raw input 保存为 artifact。
- 尝试规范化为 canonical event 或 external observation。
- 附带 adapter quality / provenance 信息。
- 将可接受结果交给 Event Store 记录 canonical event。

当前推荐 external observation 建模方式是 `ImportedSnapshot`，推荐事件名是 `snapshot.imported`。

### Open Question

- external observation 最终对象名。
- adapter 准入和版本化。
- schema migration。
- conflict resolution 的读模型。

## 15. Runtime Flow

### v0 Implementation Choice

一个典型动作路径如下：

1. Server API 接收用户输入或 client 请求。
2. Agent Runtime 推进 supervisor / worker loop，并产生或接收模型侧 action intent。
3. Action Compiler 将 compact action 编译为 canonical `ActionProposal`。
4. Event Store 记录 proposal event。
5. Policy Engine 生成 `PolicyDecision`。
6. Event Store 记录 decision event。
7. Executor 基于 grants 创建并运行 `ActionExecution`。
8. Executor 通过 Workspace Manager、Retrieval Service、Artifact Store、Memory Service 执行具体工作。
9. Event Store 记录 execution lifecycle events。
10. Projector 从 canonical events 更新 `RunState` / `SessionState`。
11. Server API 通过 query 或 stream 暴露 materialized state 和 events。

### Example / Schema Sketch

以上 flow 是模块协作示例，不是最终 event schema 或 API 协议。

## 16. Open Questions Summary

v0.1 architecture 不解决以下问题：

- `ActionTypeRegistry` 的 executor integration、schema 和版本化；compiler lookup 与 policy requirement lookup 已实现，当前最小边界见 `docs/action-type-registry-v0.1.md`。
- `ActionExecution.result` 形状。
- retry / cancel / supersede 语义。
- worker promotion 与 agent runtime loop 边界。
- `RunState` / `SessionState` 字段 schema。
- checkpoint ownership。
- `ResourceRef` 完整变体。
- retrieval policy 细节。
- compact model protocol 形态。
- approval API 和 approval state machine。
- workspace substrate。
- artifact schema / type registry。
- memory ranking 和 promotion policy。
- domain pack 接口。
- 第一条最小可运行 vertical slice。

## 17. Conflict Check

本 architecture draft 不改变 `kernel-spec-v0.1.md` 的 contracts。

需要避免的误读：

- 模块名不是最终 package 名。
- `HTTP JSON + SSE` 是 v0 implementation choice，不是永久 transport contract。
- `ImportedSnapshot` 是 v0 implementation choice，不是 external observation 的永久名称。
- `write_memory` / `promote_memory` 是推荐 action type 名，不是硬协议。
- flow 示例不是 event schema。
- module boundary 可以调整，但不能破坏 hard contracts。
- Agent Runtime 承接 supervisor / worker lifecycle，但不能拥有 policy / execution 的绕行权限。
