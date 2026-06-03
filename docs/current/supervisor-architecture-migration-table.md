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
| `runner.py` 仍是过大 legacy 入口 | `daemon/up/check/watcher` 的命令层 payload 和 plain renderer 已抽到 `src/isotope/features/supervisor/commands/daemon_command.py`；`start-here/guide/discover` 的上手与接管命令层、以及 loop auto-adopt（自动接管）tmux helper 已抽到 `src/isotope/features/supervisor/commands/onboarding.py`；dashboard payload/plain renderer、managed lane linking 和 current batch projection 已补进 `src/isotope/features/supervisor/commands/dashboard.py`；`trace` 与 `loop` 共用的 lifecycle trace payload/plain renderer 已抽到 `src/isotope/features/supervisor/commands/trace.py`；`scan/watch` 的 report 扫描、changes-only 指纹、bell 和 LLM summary 输出已抽到 `src/isotope/features/supervisor/commands/scan.py`；`advise/supervise` plain rendering（终端文本渲染）已抽到 `src/isotope/features/supervisor/commands/plain_rendering.py`；LLM planner provider/failure glue（模型规划器供应商与失败处理胶水）已抽到 `src/isotope/features/supervisor/commands/llm/planner.py`；`advise/supervise/loop` 复用的 command suggestion（命令建议）与 automation status（自动化状态）已抽到 `src/isotope/features/supervisor/commands/advice/__init__.py`；loop target/scope/actionability（目标、作用域、可行动性）判断已抽到 `src/isotope/features/supervisor/commands/loop_state.py`；loop workspace scope（工作区作用域）过滤与 payload 已抽到 `src/isotope/features/supervisor/commands/workspace_scope.py`；supervise/loop base payload（基础载荷）初始化已抽到 `src/isotope/features/supervisor/commands/supervise/payload.py`；loop LLM context（模型上下文）payload 和 context request 后 follow-up replan 已抽到 `src/isotope/features/supervisor/commands/llm/context.py`；failure ledger guard（失败账本护栏）已抽到 `src/isotope/features/supervisor/commands/failure_guard.py`；supervise/loop planning payload（规划载荷）已抽到 `src/isotope/features/supervisor/commands/supervise/planning.py`；supervise/loop LLM action selection（模型动作选择）已抽到 `src/isotope/features/supervisor/commands/supervise/action.py`；supervise/loop execution dispatch（执行分发）已抽到 `src/isotope/features/supervisor/commands/supervise/execution.py`；loop capacity decision glue（能力决策胶水）已抽到 `src/isotope/features/supervisor/commands/handlers/capacity.py`；旧 command suggestion 执行护栏、run budget 和 prompt cooldown 已抽到 `src/isotope/features/supervisor/commands/advice/advice_execution.py`；LLM action execution（模型动作执行分发）和 failure guard（失败护栏）已抽到 `src/isotope/features/supervisor/commands/llm/action.py`；LLM side-effect execution（模型动作副作用执行）的 `resume/launch/context/ask_user` 与 worktree helper 已抽到 `src/isotope/features/supervisor/commands/llm/execution.py`；fanout orchestration（并行派发编排）的计划、暂停、日志和执行汇总已抽到 `src/isotope/features/supervisor/commands/fanout.py`；merge dispatch orchestration（合并派发编排）与 recursive worker guard（递归 worker 护栏）已抽到 `src/isotope/features/supervisor/commands/merge/dispatch.py`；merge promotion orchestration（合并提升编排）的 promotion gate、CI watch、repair worker lifecycle 已抽到 `src/isotope/features/supervisor/commands/merge/promotion.py`；rule-based auto action（规则自动动作）选择已抽到 `src/isotope/features/supervisor/commands/auto/auto_action.py`；worker failure lifecycle（失败同步、自动重试、retry-limit 拍板和失败 payload）已抽到 `src/isotope/features/supervisor/commands/failure_lifecycle.py`；auto cleanup lifecycle（自动归档集成后的 merge/source worker、merge goal、通知和归档后 worktree 删除串联）已抽到 `src/isotope/features/supervisor/commands/auto/auto_cleanup.py`；`cleanup` 的 worktree 删除护栏和候选扫描已收进 `src/isotope/features/supervisor/commands/cleanup/cleanup_worktree.py`；`decision/context/replan/memory/worker-event/worker-manager` 的只读或状态命令 handler 已抽到 `src/isotope/features/supervisor/commands/handlers/decision.py`、`context.py`、`replan.py` 和 `memory.py`；`memory/worker-event/worker-manager` 的 argparse 注册已从巨型 parser 抽到 `src/isotope/features/supervisor/commands/parser/memory.py`；`runner.py` 仍承载少量 loop validation、goal replenishment、notification webhook 和 context/read-model glue | 让 `runner.py` 只保留入口转发和兼容 glue（胶水代码） | 下一批优先拆 goal replenishment 或剩余 notification/context glue；每次新增 Supervisor 行为前先判断能否落到 `commands/`、`agents/`、`integrations/codex/`、`platform/state/` 或 `workspace/` |
| `capacity.py` 已变成 capacity planning、agent-loop summary 和 plain renderer 的混合文件 | `src/isotope/features/supervisor/commands/handlers/capacity.py` 已超过舒适行数；本轮只复用既有 `agent_loop_json_summary(...)` 增加 memory query 低敏字段，没有新建执行分支 | 保持 capacity path 统一，但后续把 summary extraction / plain rendering 拆成命名 helper 模块 | 下一次改 capacity 输出时优先抽 `capacity_summary.py` 或 `capacity_rendering.py`，避免继续扩大 handler |
| Supervisor 对 `platform/` 复用不足 | 已有 decision/failure ledger 进入 `platform/state/`；`features/supervisor/state/projection.py` 已提供第一片只读状态投影，聚合 active goals、decision、lane failure、worker event 和 notification；snapshot、goal status、lane state、worker event summary 和 notification summary schema 已下沉；dashboard/web/daemon 已读取该模型，loop payload 已带只读 snapshot；但大量 worker 状态、失败策略和控制面仍留在 feature 私有实现 | 只把跨 agent 的状态事实、账本接口和 schema 下沉到 `platform/`；产品视图先通过 read model（读取模型）收敛 | 下一步评估哪些状态事实应下沉到 `platform/state` |
| 新功能容易绕过既有调度模块 | `agents/scheduler/` 已有 goal queue、fanout、dependency graph、dependency batches 和 capacity graph | Supervisor fanout、batch、capacity 相关逻辑默认复用 scheduler 层 | worker 工单必须列出将复用的 scheduler API；不能在 `runner.py` 中再写一套 DAG 或批次判断 |

`runner.py` 文件大小分阶段验收：

- 阶段 1 止血：`runner.py` 降到 800-1000 行；已迁出
  `constants.py`、`compat_api.py`、`web_runner.py`、
  `supervise/fingerprint.py` 和 `supervise/goal_lifecycle.py`。
- 阶段 2 健康：`runner.py` 降到 400-600 行；已迁出
  `supervise/loop.py`、`supervise/payload.py` 和
  `commands/dispatch.py` 的命令分发主干。
- `commands/dispatch.py` 已直接导入真实 command handler，不再通过
  `commands/compat_api.py` 进入运行主路径；`compat_api.py` 继续只作为
  `runner.py` 旧 helper re-export 的兼容面。
- 阶段 3 理想：`runner.py` 降到 250-400 行，只保留 `main`、
  parser 调用、顶层 dispatch、少量异常处理和兼容 re-export；`scan/report`
  已抽出，下一步优先拆 goal replenishment 和剩余 notification/context glue。

全局文件大小债务：阶段 1 完成后仍有若干手写 Python 文件超过 600 行，
包括 `commands/parser/__init__.py`、`llm_summary.py`、`flow.py`、`commands/dashboard.py`、
`context.py`、`commands/merge/promotion.py`、`integration_review.py`、`web.py`、
`commands/daemon_command.py`、`commands/llm/execution.py`、`worker_review.py`
和 `registry.py`。后续拆分时普通功能模块目标不超过 350 行，复杂
orchestration 模块目标不超过 450 行。

## 2026-05-22 能力盘点与架构对齐审计

本次审计结论：Supervisor 不是缺少底座，而是主路径还没有统一收口。
`agents/scheduler`、`platform/state`、`capabilities`、`runtime` 和
`integrations/codex` 已经各自长出部分可复用能力，但
`features/supervisor/runner.py` 与周边模块仍承担太多系统级编排。

| 能力区 | 已接入主路径 | 半成品或闲置 | 对齐动作 |
| --- | --- | --- | --- |
| `features/supervisor/` | CLI/Web、daemon/loop、goal queue、fanout 调用、worker review、integration review、merge dispatch、decision request、failure ledger adapter、Codex 托管登记 | `runner.py` 仍有大量命令实现、状态拼装、自动动作执行、merge/cleanup 编排；LLM action 仍是私有 JSON 动作体系 | 保留用户入口，把通用编排迁到 `agents/`、`integrations/codex/`、`workspace/` 和 `platform/state/` |
| `agents/loop/` | `step.py` 可通过 `CapabilityRunner` 执行 `call_capability`；`capacity plan --execute-agent-loop` 已能从 Supervisor 入口打到 agent loop；`loop --capacity-decisions --llm-execute` 已可在 LLM planner 选择 `call_capacity` 后复用 agent loop 执行 | Supervisor 常驻 loop 还没有整体成为 agent loop 主循环；`llm_summary.py` 仍承担私有动作解析 | 把 Supervisor planning/execution 改成 agent loop 驱动，而不是继续扩写私有 LLM action |
| `agents/scheduler/` | `fanout.py` 已复用 dependency graph；fanout status summary 已拆到 `fanout_status.py`；`current_batch.py` 已承接 current batch 纯投影并调用 dependency batch；goal queue view 和 goal event parsing 已被 Supervisor adapter 使用 | `capacity_graph.py` 仍偏原型；goal queue 的写入和持久化文件仍在 feature adapter | 让 fanout、batch、capacity graph、current batch projection 和 goal event parsing 成为唯一调度层，禁止 runner 再写批次/DAG 判断 |
| `capabilities/` | `CapabilityRunner` 可列出、搜索、规划和受控运行少量 allowlist 能力；Supervisor `capacity plan` 已复用 launch plan；LLM capacity calling 只会收到 preflight 后可启动或缺少输入的 offered capabilities；runner `plan/run` 和 LLM capacity calling 共用 `platform/schemas/input_contract.py` 读取 contract properties / required keys，并校验 required/key-level contract、type、enum 和 optional provider/model metadata；`CapabilityCatalog` 会拒绝 malformed inputs/listing flags，并在 manifest 输出时 deep-copy nested contracts，避免调用方污染 catalog 原始定义；`capacity_call_specs` 只从 ready 且 launchable（可启动）的 plan 生成 | 能力目录目前很薄，真实 Supervisor worker/merge/context 能力尚未注册进 catalog | 把可复用操作登记成能力，由 LLM 选择能力，再由 runner/loop 执行 |
| `llm/capacity_calling.py` | 已接入 Supervisor `capacity plan`：LLM 选择 capacity，再生成 capacity graph 和 capability launch plan；`capacity_decisions` 已进入 `supervise/loop` 的 LLM planner，并可触发 ready 的 `call_capacity` | 仍要求严格 JSON；capacity action 还是 LLM action 的一类私有动作 | 下一步把更多 Supervisor 操作注册成 capability，减少私有 LLM action 膨胀 |
| `platform/state/` | `DecisionRequestLedger`、`FailureLedger`、`FileMemoryStore`、worker event channel、multi-worker read model、`SupervisorStateSnapshot`、`SupervisorActiveGoal`、`SupervisorDecisionRequest`、`SupervisorGoalStatus`、`SupervisorLaneState`、`SupervisorWorkerEventSummary` 和 `SupervisorNotificationSummary` schema 已被 Supervisor adapter 复用；event/memory/checkpoint/projector 已服务 runtime；checkpoint validation chain 已从 checkpoint mixin 拆到 `projector_checkpoint_validation.py` | lane state 持久化、goal queue 持久化、notification index 写入仍多为 feature 私有 JSONL | 继续统一跨 worker 事实、事件、记忆和拍板账本，dashboard 读取投影而不是拼散表 |
| `runtime/` | `InProcessServer` 串起 session/run/policy/executor/memory；`ActionCompiler` 可把模型意图编译成动作提案；workspace lease、workspace artifact capture 和 worker handoff 已从 `in_process/workspace.py` 拆到专门 helper，旧路径只保留兼容 facade | Supervisor 没有通过 runtime action/policy 主链路托管 Codex worker；很多命令仍直接 subprocess/git | 后续 Supervisor 应请求 runtime/capability 执行动作，而不是自己直接做执行层 |
| `integrations/codex/` | `session_reader.py` 只读读取 Codex JSONL/索引/SQLite；`CodexCliBackend` 和 `CodexTaskAdapter` 已有受控 Codex task 边界；task request shape 与 adapter contract 已从 `task.py` 拆到 `task_request.py` / `task_contract.py`；Supervisor CLI command builder 和 validation helper 已拆到 `cli_supervisor.py` / `cli_validation.py` | Supervisor worker launch 仍主要在 `registry.py` 和 runner；`CodexCliBackend` 首片只支持 shared_ro/read-only | 把 Codex launch/resume/session/log 变成集成层合同，Supervisor 只发 worker 请求 |
| `workspace/` | `ArtifactStore` 已被 runtime 使用；`WorkspaceManager` 目前提供 shared_ro 边界 | worktree、branch、cherry-pick、cleanup、CI 观察仍在 Supervisor feature 文件内 | 把 git/worktree/产物边界搬到 workspace/integration，merge worker 只调用这些能力 |

### 已确认的复用不足

- `llm_summary.py` 的 TOML 号池 adapter 已拆到
  `features/supervisor/llm_pool.py`，并复用 `llm/pool.py` 的通用解析；
  LLM action prompt（动作提示词）的 schema/rules 已拆到
  `features/supervisor/llm_action_prompt.py`；JSON payload 解析、action alias
  normalize（归一化）和字段校验已拆到
  `features/supervisor/llm_action_payload.py`；动作目标、ask_user/context gate
  和 delete_worktree candidate 的 guard helper 已拆到
  `features/supervisor/llm_action_guards.py`；但 LLM action decision 的主分发
  仍留在 `llm_summary.py`，与
  `llm/capacity_calling.py` 和后续 agent loop 主路径重叠。
- `registry.py` 直接拼 `codex exec`、tmux、日志和托管登记，
  与 `integrations/codex/cli.py`、`integrations/codex/task.py` 的边界重叠。
- `merge_dispatch.py`、`merge_promotion.py`、`integration_review.py` 和 runner
  里存在 git/worktree/CI 编排，应该逐步迁到 `workspace/` 和 `agents/integration/`。
- `context.py` 已有 BM25-style 项目检索，但仍是 Supervisor 私有能力，
  没有注册为通用 capability，也没有接入 runtime memory/query 统一边界。
- `current_batch.py` 已经复用 dependency batch，这是正确方向；
  但 batch 展示、goal queue 写入、fanout 启动还没有完全收敛为同一调度合同。
- `loop --capacity-decisions` 的 goal 到 `capacity_decisions` /
  `capacity_call_specs` 生产 glue 已抽到 `commands/handlers/capacity.py`；`call_capacity`
  仍经 LLM action 分发，后续应继续评估是否下沉到 scheduler adapter 或
  agent loop planner，避免继续扩写私有动作体系。
- `loop/supervise` 传给 LLM planner 的上下文 payload（最近 context、拍板答案、
  capacity decision、worker review 和 delete-worktree 候选）以及成功
  `request_context` 后的 follow-up replan 已收口到 `commands/llm/context.py`，
  `runner.py` 仍负责主循环编排和调用时机。
- `loop/supervise` 的 planning payload（current batch、fanout status/plan、
  merge dispatch 和 recursive worker guard）已收口到
  `commands/supervise/planning.py`，底层仍复用 dashboard/fanout/merge_dispatch
  既有 helper，不重写调度和合并规则。
- LLM execute 后刷新 `current_batch` 的重复 payload 更新已收口到
  `commands/supervise/payload.py`，`runner.py` 只在 fanout/merge dispatch
  分支中调用该 helper。
- `loop/supervise` 的 LLM action selection 已收口到
  `commands/supervise/action.py`，只编排 fanout、merge dispatch、worker guard、
  idle loop 和 LLM planner 的既有 action builder，不进入执行层。
- `loop/supervise` 的 execution dispatch 已收口到
  `commands/supervise/execution.py`，只负责选择既有 fanout、merge dispatch、
  LLM action、rule-based auto action 和旧 advice execution 入口，不重新实现
  launch/resume/context/ask_user 副作用。
- `loop/supervise` 的最终 payload 附加（decision requests 和 loop lifecycle
  trace）已收口到 `commands/supervise/payload.py`，`runner.py` 仍只负责调用时机。

### 最高杠杆的后续任务

1. **打通 `agent loop + capacity calling + capabilities` 主路径。**
   让 LLM 先选择 capability（能力）并填参数，再由 agent loop 执行。
   这会把 Supervisor 从“写死动作的 Codex 管理器”推进到“能选择系统能力的高层 agent”。
   进展：已完成第一片 `capacity plan`，默认 plan-only；显式
   `--execute-agent-loop` 时可通过 agent loop 调用低风险 allowlist 能力；
   `loop/supervise --capacity-decisions --llm-execute` 也可在 LLM planner
   选择 ready 的 `call_capacity` 后，把 selection `arguments` 作为
   structured `inputs` 传入 agent loop，并返回 tick policy handoff。

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
| CLI 参数、命令分发 | `features/supervisor/runner.py`, `commands/` | `features/supervisor/commands/` | 已拆出 parser、dashboard payload/rendering、trace lifecycle payload、goal/cleanup/merge/promotion/capacity、daemon、onboarding、advice suggestion、decision/context/replan/memory/worker-event/worker-manager 命令层；memory 相关 parser 注册已进入 `commands/parser/memory.py`；继续保留 runner 兼容导出，逐个命令拆 handler | `runner.py` 最终只做入口转发和兼容 glue（胶水代码）。 |
| Dashboard / Web 视图 | `features/supervisor/web.py`, `dashboard_html.py`, `runner.py` | `features/supervisor/web/` 或保持 feature 内 | 可以先留在 feature | 这是用户可见产品入口，暂不下沉到底座。 |
| Codex session 扫描 | `features/supervisor/flow.py` | `integrations/codex/session_reader.py` | 抽只读 reader，再由 feature 调用 | 未来支持 Qoder/Minimax worker 时不能绑定在 supervisor feature 内。 |
| Codex exec / resume / launch | `runner.py`, `registry.py` | `integrations/codex/` + `execution/` | 先抽 process 后端和 resume 命令构造 | Codex 是外部集成，不是 Supervisor 核心本体。 |
| managed worker registry | `features/supervisor/registry.py` | `agents/worker_registry.py` 或 `platform/registry/` | 先保留 Codex 字段，抽通用 worker record | 后续 worker 不一定都是 Codex。 |
| goal queue（目标队列） | `features/supervisor/goal_queue.py` | `agents/scheduler/goal_queue.py`, `agents/scheduler/goal_events.py` | goal queue view 和 goal event parsing 已下沉到 scheduler；feature 继续负责 `goals.jsonl` 写入、归档和 notification adapter | 目标队列属于 agent 调度，不属于前端功能。 |
| current batch（当前批次） | `features/supervisor/current_batch.py` | `agents/scheduler/current_batch.py` | current batch 纯投影已下沉到 scheduler；feature 只保留兼容导出 | 当前批次是调度读模型，不应绑定在 Supervisor 前端模块内。 |
| goal planner（目标规划） | `features/supervisor/goal_planner.py` | `agents/planner/` | 先抽 prompt、解析、修复器 | 应接 agent loop 和文档检索，不只服务 Codex Supervisor。 |
| fanout（并行派发） | `features/supervisor/fanout.py`, `features/supervisor/commands/fanout.py` | `agents/scheduler/fanout.py`, `agents/scheduler/fanout_status.py` | 纯规划和 status summary 已在 scheduler，命令层编排已迁出 runner；下一步再统一 goal queue 持久化事件 | fanout 是调度能力，应支持依赖图、并发上限和可复用状态摘要。 |
| merge dispatch / promotion | `merge_dispatch.py`, `commands/merge/dispatch.py`, `commands/merge/promotion.py`, `merge_promotion.py`, `runner.py` | `workspace/git/` + `agents/integration/` | merge dispatch loop 编排与 promotion gate/CI watch/repair worker lifecycle 已迁出 runner；下一步把 git/worktree 细节从命令层继续下沉 | 合并、CI、worktree 清理属于 workspace/integration。 |
| worker review / integration review | `worker_review.py`, `integration_review.py` | `agents/review/` + `workspace/git/` | 按只读审查和 git 操作拆分 | 可作为通用 worker 完成度审查能力。 |
| decision requests（拍板请求） | `decision_requests.py` | `platform/state/decision_ledger.py`、`platform/state/decision_request.py` | 账本接口已在 `DecisionRequestLedger`，state projection 复用 `SupervisorDecisionRequest` 生成 active decision payload；feature 继续保留通知、timeout 和命令 adapter | 拍板请求是通用 agent 控制面，不应只服务 Supervisor；当前不改 `decision_requests.jsonl` 格式。 |
| context request（上下文请求） | `context.py`, `runner.py` | `rag/` + `agents/context/` | 抽检索接口，feature 留命令包装 | 当前偏 rg/BM25-style，后续可接语义检索。 |
| capacity calling（能力调用） | `llm/capacity_calling.py`, `agents/loop/` | `capabilities/` + `agents/loop/` | 优先打通真实 loop，不再只做原型 | Supervisor planner 应能调用能力，而不是写死动作。 |
| memory view / worker event channel | `features/supervisor/state/`, `memory/worker_event_channel.py` | `memory/` + `platform/state/` | memory status / worker status 只读投影已下沉到 `memory/views.py`；`FileMemoryStore`、worker event channel、`WorkerEvent` schema 和 multi-worker read model 已归到 `platform/state`；`isotope.memory.worker_event_channel` 保留兼容导出，旧 Supervisor state 代理已删除 | 多 worker 协调复用同一记忆/事件层。 |
| goal queue / status（目标队列/状态） | `features/supervisor/goal_queue.py` | active goal snapshot schema 已下沉到 `platform/state/active_goal.py`，goal status schema 已下沉到 `platform/state/goal_status.py`；写入和旧 JSONL 读取仍留在 feature adapter | `record_supervisor_goal_status(...)` 继续写 `goals.jsonl` 和通知；state projection 复用 `SupervisorActiveGoal` 生成 active goal payload，`read_latest_supervisor_goal_statuses(...)` 复用 `SupervisorGoalStatus` 生成低敏 `last_status` payload | 当前不迁 goal queue 持久化，不改 `goals.jsonl` 格式。 |
| lane state（窗口状态） | `features/supervisor/lane_state.py` | schema 已下沉到 `platform/state/lane_state.py`，写入和旧 JSON 读取仍留在 feature adapter | prompt cooldown、continue budget、failure、worker retry 和 decision timeout 仍复用原 feature 函数；state projection 的 failed lane payload 复用 `SupervisorLaneState` | 当前不迁 lane state 持久化，不改 `lane_state.json` 格式。 |
| state projection（状态投影） | `features/supervisor/state/projection.py` | builder 先留在 `features/supervisor/state/`，snapshot、active goal、decision request、goal status、lane state、worker event summary 和 notification summary schema 已下沉到 `platform/state/` | 已新增只读 snapshot 聚合 active goals、decision requests、lane failure、worker events 和 notifications；dashboard/web/daemon 已读取，loop payload 已带只读 snapshot；输出结构复用 `SupervisorStateSnapshot`、`SupervisorActiveGoal`、`SupervisorDecisionRequest`、`SupervisorGoalStatus`、`SupervisorLaneState`、`SupervisorWorkerEventSummary` 和 `SupervisorNotificationSummary` | 当前只做 read model，不新增账本、不改写入格式；避免让 `platform/state` 反向依赖 Supervisor feature。 |
| daemon / watcher | `commands/daemon_command.py`, `daemon.py`, `runner.py` | `agents/runtime/` 或 `runtime/` | 命令层 payload/plain renderer 已从 runner 抽出；下一步再抽循环运行器、活动投影和生命周期管理 | 后台循环是运行时能力，不应塞在一个命令文件里。 |
| failure ledger / retry guard | `failure_ledger.py`, `commands/failure_lifecycle.py` | `platform/state/` + `agents/policy/` | 失败同步与重试命令层已从 runner 抽出；下一步再把跨 agent 的重试 policy 下沉 | 失败记录和策略要能服务其他 agent。 |
| 通知桥 | `features/supervisor/notifications.py` | `features/notifications/` + adapter，snapshot payload 复用 `platform/state/notification_summary.py` | 已有薄整合，state projection 里的 notification 低敏字段过滤已下沉为 schema | 通知是产品能力，Supervisor 只负责派生事件；notification index 写入仍留在 feature flow。 |

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
