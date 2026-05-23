# Supervisor 架构迁移表

状态：`迁移准备 / 可用于逐文件并行实测`

## 核心判断

当前 `features/supervisor` 已经承担了太多系统级职责。
短期它可以继续作为 Codex Supervisor 的产品入口，但长期 Supervisor
应是 Isotope 的高层 agent 管理者，而不是只监督 Codex 窗口的功能模块。

迁移目标不是一次性大搬家，而是逐步把可复用能力下沉到长期目录：

- `features/supervisor/`：保留 CLI、Web、dashboard 和人类入口。
- `agents/`：承接高层 agent、agent loop、任务调度和 worker 编排。
- `capabilities/`：承接能力注册、capacity calling 和能力执行边界。
- `memory/` 与 `platform/state/`：承接长期记忆、事件通道和状态存储。
- `integrations/codex/`：承接 Codex session、resume、exec 和 worktree worker。
- `workspace/`：承接 git worktree、branch、项目文件和产物边界。

## 复用审计与重构债务

本表也是 Supervisor 的 refactoring debt（重构债务）账本。后续所有
Codex worker 在改 Supervisor 前必须先做 reuse audit（复用审计）：

- 先查本表、[能力地图](./supervisor-capability-map.md)、`AGENTS.md`
  和相关代码目录，列出已有模块、helper、schema、状态账本和文档入口。
- 新增代码必须说明复用了什么；不复用已有代码时，要写明 contract
  （契约）、failure mode（失败模式）、层级或 owner（维护归属）不一致。
- 如果为了交付暂时保留重复逻辑、legacy 入口或大文件职责，必须把债务
  写回本节或迁移表，而不是只在对话里说“以后重构”。
- 每个迁移 worker 只能处理自己负责的债务项；完成后更新状态、测试和
  下一个可解锁项。

当前高优先级债务：

| 债务 | 现状证据 | 目标 | 下一步 |
| --- | --- | --- | --- |
| `runner.py` 仍是过大 legacy 入口 | `daemon/up/check/watcher` 的命令层 payload 和 plain renderer 已抽到 `src/isotope/features/supervisor/commands/daemon_command.py`；`start-here/guide/discover` 的上手与接管命令层已抽到 `src/isotope/features/supervisor/commands/onboarding.py`；dashboard payload/plain renderer、managed lane linking 和 current batch projection 已补进 `src/isotope/features/supervisor/commands/dashboard.py`；`trace` 与 `loop` 共用的 lifecycle trace payload/plain renderer 已抽到 `src/isotope/features/supervisor/commands/trace.py`；`advise/supervise/loop` 复用的 command suggestion（命令建议）与 automation status（自动化状态）已抽到 `src/isotope/features/supervisor/commands/advice.py`；LLM action execution（模型动作执行分发）和 failure guard（失败护栏）已抽到 `src/isotope/features/supervisor/commands/llm_action.py`；LLM side-effect execution（模型动作副作用执行）的 `resume/launch/context/ask_user` 与 worktree helper 已抽到 `src/isotope/features/supervisor/commands/llm_execution.py`；fanout orchestration（并行派发编排）的计划、暂停、日志和执行汇总已抽到 `src/isotope/features/supervisor/commands/fanout.py`；merge dispatch orchestration（合并派发编排）与 recursive worker guard（递归 worker 护栏）已抽到 `src/isotope/features/supervisor/commands/merge_dispatch.py`；merge promotion orchestration（合并提升编排）的 promotion gate、CI watch、repair worker lifecycle 已抽到 `src/isotope/features/supervisor/commands/promotion.py`；rule-based auto action（规则自动动作）选择已抽到 `src/isotope/features/supervisor/commands/auto_action.py`；worker failure lifecycle（失败同步、自动重试、retry-limit 拍板和失败 payload）已抽到 `src/isotope/features/supervisor/commands/failure_lifecycle.py`；`cleanup` 的 worktree 删除护栏和候选扫描已收进 `src/isotope/features/supervisor/commands/cleanup_worktree.py`；`decision/context/replan/memory/worker-event/worker-manager` 的只读或状态命令 handler 已抽到 `src/isotope/features/supervisor/commands/decision.py`、`context.py`、`replan.py` 和 `memory.py`；`runner.py` 仍承载 loop、tmux 控制、自动 cleanup 串联和部分状态判断等职责 | 让 `runner.py` 只保留入口转发和兼容 glue（胶水代码） | 下一批优先拆 `runner.py` 中的 tmux 控制、auto cleanup 串联或 loop 状态拼装；每次新增 Supervisor 行为前先判断能否落到 `commands/`、`agents/`、`integrations/codex/`、`platform/state/` 或 `workspace/` |
| Supervisor 对 `platform/` 复用不足 | 已有 decision/failure ledger 进入 `platform/state/`；`features/supervisor/state/projection.py` 已提供第一片只读状态投影，聚合 active goals、decision、lane failure、worker event 和 notification；dashboard/web/daemon 已读取该模型，loop payload 已带只读 snapshot；但大量 worker 状态、失败策略和控制面仍留在 feature 私有实现 | 只把跨 agent 的状态事实、账本接口和 schema 下沉到 `platform/`；产品视图先通过 read model（读取模型）收敛 | 下一步评估哪些状态事实应下沉到 `platform/state` |
| 新功能容易绕过既有调度模块 | `agents/scheduler/` 已有 goal queue、fanout、dependency graph、dependency batches 和 capacity graph | Supervisor fanout、batch、capacity 相关逻辑默认复用 scheduler 层 | worker 工单必须列出将复用的 scheduler API；不能在 `runner.py` 中再写一套 DAG 或批次判断 |

## 2026-05-22 能力盘点与架构对齐审计

本次审计结论：Supervisor 不是缺少底座，而是主路径还没有统一收口。
`agents/scheduler`、`platform/state`、`capabilities`、`runtime` 和
`integrations/codex` 已经各自长出部分可复用能力，但
`features/supervisor/runner.py` 与周边模块仍承担太多系统级编排。

| 能力区 | 已接入主路径 | 半成品或闲置 | 对齐动作 |
| --- | --- | --- | --- |
| `features/supervisor/` | CLI/Web、daemon/loop、goal queue、fanout 调用、worker review、integration review、merge dispatch、decision request、failure ledger adapter、Codex 托管登记 | `runner.py` 仍有大量命令实现、状态拼装、自动动作执行、merge/cleanup 编排；LLM action 仍是私有 JSON 动作体系 | 保留用户入口，把通用编排迁到 `agents/`、`integrations/codex/`、`workspace/` 和 `platform/state/` |
| `agents/loop/` | `step.py` 可通过 `CapabilityRunner` 执行 `call_capability`；`capacity plan --execute-agent-loop` 已能从 Supervisor 入口打到 agent loop | 还没有成为 Supervisor loop 的主执行循环；Supervisor 常驻 loop 仍主要走 `llm_summary.py` 的动作解析与 runner 执行 | 把 Supervisor planning/execution 改成 agent loop 驱动，而不是继续扩写私有 LLM action |
| `agents/scheduler/` | `fanout.py` 已复用 dependency graph；`current_batch.py` 已调用 dependency batch；goal queue view 已被 Supervisor adapter 使用 | `capacity_graph.py` 仍偏原型；goal queue 的持久化事件仍在 feature adapter | 让 fanout、batch、capacity graph 成为唯一调度层，禁止 runner 再写批次/DAG 判断 |
| `capabilities/` | `CapabilityRunner` 可列出、搜索、规划和受控运行少量 allowlist 能力；Supervisor `capacity plan` 已复用 launch plan；runner `plan/run` 会按 `input_contract` 拒绝未声明输入键并检查当前支持的 type/enum 约束 | 能力目录目前很薄，真实 Supervisor worker/merge/context 能力尚未注册进 catalog | 把可复用操作登记成能力，由 LLM 选择能力，再由 runner/loop 执行 |
| `llm/capacity_calling.py` | 已接入 Supervisor `capacity plan`：LLM 选择 capacity，再生成 capacity graph 和 capability launch plan | 尚未接入 `supervise/loop` 常驻主循环；仍要求严格 JSON | 下一步接入 goal planner 或 loop 的一个真实决策点，继续避免私有 LLM action 膨胀 |
| `platform/state/` | `DecisionRequestLedger`、`FailureLedger`、`FileMemoryStore`、worker event channel、multi-worker read model 和 `SupervisorStateSnapshot` schema 已被 Supervisor adapter 复用；event/memory/checkpoint/projector 已服务 runtime | lane state、goal status、notification index 仍多为 feature 私有 JSONL | 继续统一跨 worker 事实、事件、记忆和拍板账本，dashboard 读取投影而不是拼散表 |
| `runtime/` | `InProcessServer` 串起 session/run/policy/executor/memory；`ActionCompiler` 可把模型意图编译成动作提案 | Supervisor 没有通过 runtime action/policy 主链路托管 Codex worker；很多命令仍直接 subprocess/git | 后续 Supervisor 应请求 runtime/capability 执行动作，而不是自己直接做执行层 |
| `integrations/codex/` | `session_reader.py` 只读读取 Codex JSONL/索引/SQLite；`CodexCliBackend` 和 `CodexTaskAdapter` 已有受控 Codex task 边界 | Supervisor worker launch 仍主要在 `registry.py` 和 runner；`CodexCliBackend` 首片只支持 shared_ro/read-only | 把 Codex launch/resume/session/log 变成集成层合同，Supervisor 只发 worker 请求 |
| `workspace/` | `ArtifactStore` 已被 runtime 使用；`WorkspaceManager` 目前提供 shared_ro 边界 | worktree、branch、cherry-pick、cleanup、CI 观察仍在 Supervisor feature 文件内 | 把 git/worktree/产物边界搬到 workspace/integration，merge worker 只调用这些能力 |

### 已确认的复用不足

- `llm_summary.py` 自带 TOML 号池、模型动作、JSON 修复和上下文请求策略，
  与 `llm/provider.py`、`llm/capacity_calling.py` 和后续 agent loop 主路径重叠。
- `registry.py` 直接拼 `codex exec`、tmux、日志和托管登记，
  与 `integrations/codex/cli.py`、`integrations/codex/task.py` 的边界重叠。
- `merge_dispatch.py`、`merge_promotion.py`、`integration_review.py` 和 runner
  里存在 git/worktree/CI 编排，应该逐步迁到 `workspace/` 和 `agents/integration/`。
- `context.py` 已有 BM25-style 项目检索，但仍是 Supervisor 私有能力，
  没有注册为通用 capability，也没有接入 runtime memory/query 统一边界。
- `current_batch.py` 已经复用 dependency batch，这是正确方向；
  但 batch 展示、goal queue 写入、fanout 启动还没有完全收敛为同一调度合同。

### 最高杠杆的后续任务

1. **打通 `agent loop + capacity calling + capabilities` 主路径。**
   让 LLM 先选择 capability（能力）并填参数，再由 agent loop 执行。
   这会把 Supervisor 从“写死动作的 Codex 管理器”推进到“能选择系统能力的高层 agent”。
   进展：已完成第一片 `capacity plan`，默认 plan-only；显式
   `--execute-agent-loop` 时可通过 agent loop 调用低风险 allowlist 能力，
   把 selection `arguments` 作为 structured `inputs` 传入，并返回 tick policy handoff。

2. **把 Codex worker 生命周期收口到 `integrations/codex` 与 `workspace`。**
   Codex launch/resume/session/log、worktree、branch、merge、cleanup 应有稳定合同。
   这样未来 worker 不只限于 Codex，Supervisor 也不用继续背 subprocess/git 细节。

3. **统一状态、事件和记忆投影。**
   goal、worker、decision、failure、memory 和 notification 应写成通用状态事实。
   Web/dashboard/daemon 读取投影后，多 worker 协调才不会继续靠 feature 私有 JSONL 拼接。
   进展：`features/supervisor/state/projection.py` 已完成第一片只读
   `build_supervisor_state_snapshot(...)`，先聚合现有账本，不改变写入格式。

## 迁移表

| 当前职责 | 现有位置 | 目标位置 | 迁移方式 | 备注 |
| --- | --- | --- | --- | --- |
| CLI 参数、命令分发 | `features/supervisor/runner.py`, `commands/` | `features/supervisor/commands/` | 已拆出 parser、dashboard payload/rendering、trace lifecycle payload、goal/cleanup/merge/promotion/capacity、daemon、onboarding、advice suggestion、decision/context/replan/memory/worker-event/worker-manager 命令层；继续保留 runner 兼容导出，逐个命令拆 handler | `runner.py` 最终只做入口转发和兼容 glue（胶水代码）。 |
| Dashboard / Web 视图 | `features/supervisor/web.py`, `dashboard_html.py`, `runner.py` | `features/supervisor/web/` 或保持 feature 内 | 可以先留在 feature | 这是用户可见产品入口，暂不下沉到底座。 |
| Codex session 扫描 | `features/supervisor/flow.py` | `integrations/codex/session_reader.py` | 抽只读 reader，再由 feature 调用 | 未来支持 Qoder/Minimax worker 时不能绑定在 supervisor feature 内。 |
| Codex exec / resume / launch | `runner.py`, `registry.py` | `integrations/codex/` + `execution/` | 先抽 process 后端和 resume 命令构造 | Codex 是外部集成，不是 Supervisor 核心本体。 |
| managed worker registry | `features/supervisor/registry.py` | `agents/worker_registry.py` 或 `platform/registry/` | 先保留 Codex 字段，抽通用 worker record | 后续 worker 不一定都是 Codex。 |
| goal queue（目标队列） | `features/supervisor/goal_queue.py` | `agents/scheduler/goal_queue.py` | 抽通用 goal model，feature 留 adapter | 目标队列属于 agent 调度，不属于前端功能。 |
| goal planner（目标规划） | `features/supervisor/goal_planner.py` | `agents/planner/` | 先抽 prompt、解析、修复器 | 应接 agent loop 和文档检索，不只服务 Codex Supervisor。 |
| fanout（并行派发） | `features/supervisor/fanout.py`, `features/supervisor/commands/fanout.py` | `agents/scheduler/fanout.py` | 纯规划已在 scheduler，命令层编排已迁出 runner；下一步再统一 goal queue 持久化事件 | fanout 是调度能力，应支持依赖图和并发上限。 |
| merge dispatch / promotion | `merge_dispatch.py`, `commands/merge_dispatch.py`, `commands/promotion.py`, `merge_promotion.py`, `runner.py` | `workspace/git/` + `agents/integration/` | merge dispatch loop 编排与 promotion gate/CI watch/repair worker lifecycle 已迁出 runner；下一步把 git/worktree 细节从命令层继续下沉 | 合并、CI、worktree 清理属于 workspace/integration。 |
| worker review / integration review | `worker_review.py`, `integration_review.py` | `agents/review/` + `workspace/git/` | 按只读审查和 git 操作拆分 | 可作为通用 worker 完成度审查能力。 |
| decision requests（拍板请求） | `decision_requests.py` | `agents/decision/` 或 `platform/state/` | 先抽账本接口 | 拍板请求是通用 agent 控制面，不应只服务 Supervisor。 |
| context request（上下文请求） | `context.py`, `runner.py` | `rag/` + `agents/context/` | 抽检索接口，feature 留命令包装 | 当前偏 rg/BM25-style，后续可接语义检索。 |
| capacity calling（能力调用） | `llm/capacity_calling.py`, `agents/loop/` | `capabilities/` + `agents/loop/` | 优先打通真实 loop，不再只做原型 | Supervisor planner 应能调用能力，而不是写死动作。 |
| memory view / worker event channel | `features/supervisor/state/`, `memory/worker_event_channel.py` | `memory/` + `platform/state/` | `FileMemoryStore`、worker event channel、`WorkerEvent` schema 和 multi-worker read model 已归到 `platform/state`；旧 `isotope.memory` / Supervisor state 路径保留兼容导出 | 多 worker 协调复用同一记忆/事件层。 |
| state projection（状态投影） | `features/supervisor/state/projection.py` | builder 先留在 `features/supervisor/state/`，snapshot schema 已下沉到 `platform/state/supervisor_snapshot.py` | 已新增只读 snapshot 聚合 active goals、decision requests、lane failure、worker events 和 notifications；dashboard/web/daemon 已读取，loop payload 已带只读 snapshot；输出结构复用 `SupervisorStateSnapshot` | 当前只做 read model，不新增账本、不改写入格式；避免让 `platform/state` 反向依赖 Supervisor feature。 |
| daemon / watcher | `commands/daemon_command.py`, `daemon.py`, `runner.py` | `agents/runtime/` 或 `runtime/` | 命令层 payload/plain renderer 已从 runner 抽出；下一步再抽循环运行器、活动投影和生命周期管理 | 后台循环是运行时能力，不应塞在一个命令文件里。 |
| failure ledger / retry guard | `failure_ledger.py`, `commands/failure_lifecycle.py` | `platform/state/` + `agents/policy/` | 失败同步与重试命令层已从 runner 抽出；下一步再把跨 agent 的重试 policy 下沉 | 失败记录和策略要能服务其他 agent。 |
| 通知桥 | `features/supervisor/notifications.py` | `features/notifications/` + adapter | 已有薄整合，继续减少私有字段 | 通知是产品能力，Supervisor 只负责派生事件。 |

## 条件推进模型

后续 Supervisor 不能只把目标 `1-10` 排序后全部从当前 `main` 分出分支。
目标队列需要支持 dependency graph（依赖图）：用条件判断哪些目标可以并行，
哪些目标必须等前置结果完成。

典型结构：

```text
A, B, C 可并行
A + B + C 完成并合入后，才能启动 D, E
D + E 验证通过后，才能启动 F
任一阶段出现 conflict / CI fail / needs_user，暂停后续阶段
```

最低要求：

- goal 需要有 `depends_on`、`stage`、`scope` 和 `merge_gate`。
- fanout 只启动依赖已满足的目标，不能越过前置阶段。
- worker 必须基于最新可合入基线启动，不应一次性从旧 `main` 分出所有分支。
- merge worker 完成并通过 CI 后，才能解锁下一阶段目标。
- blocked、conflict、CI fail 或 decision request 未处理时，不再补发下游目标。

这不是为了变慢，而是为了避免并行越多、合并越乱。
并行应该是“同阶段可并行”，不是“所有目标无条件并行”。

## 后续实测方式

后续可以把本表作为目标输入，让 Codex Supervisor 按迁移表逐组派发 worker：

1. 先选 2-3 个互不冲突的迁移项。
2. 每个 worker 使用独立 worktree。
3. worker 只迁自己负责的文件，不顺手改其他层。
4. 完成后自测并按 `SUPERVISOR_STATUS/SUMMARY/NEXT` 汇报。
5. merge worker 统一审查 diff、合并、跑组合测试和观察 CI。
6. 合并完成后再解锁下一阶段迁移项。

第一批建议：

- 抽 Codex session reader 到 `integrations/codex/`。
- 抽 goal queue / fanout 的纯调度逻辑到 `agents/`。
- 抽 decision request / failure ledger 的账本接口到 `platform/state/`。
