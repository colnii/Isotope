# Codex Supervisor 能力地图

状态：`能力详情 / 防止重复造轮子`

本文从原 `supervisor-capability-map.md` 拆出，保留能力分层、工单边界和
后续拆分方向。详细能力清单已拆到
[Supervisor 能力详细清单](./supervisor-capability-inventory.md)。短索引见
[Supervisor 能力地图](./supervisor-capability-map.md)。

原状态：`当前能力登记 / 防止重复造轮子`

## 为什么要有这张图

Codex Supervisor 已经不只是一个小命令。
它是 Isotope 后续的核心管理层：LLM 参与判断和调度，
规则、事件、冷却、tmux 和白名单执行提供工程护栏。

本文件用于登记当前能力和后续拆分方向。
新增 Supervisor 能力时，应先看这里，避免重复造一套相似实现。
同时必须先遵守 `AGENTS.md` 的 AI-first 产品约束：
LLM 不能被降级成可有可无的摘要插件，规则也不能替代产品智能。

## 项目级能力盘点索引

2026-05-22 的 capability inventory（能力盘点）结论已经写入
[Supervisor 架构迁移表](./supervisor-architecture-migration-table.md)。
当前判断如下：

- 主路径已经接入：Web/CLI、goal queue、fanout、current batch、
  dependency batch、worker/integration review、merge dispatch、
  decision/failure ledger adapter、Codex session reader、`capacity plan`、
  `supervisor.request_context` capability、Supervisor state projection
  （状态投影）。
- 半成品或闲置：`agents/loop` 尚未驱动 Supervisor 主循环；
  `llm/capacity_calling.py`、`agents/scheduler/capacity_graph.py`、
  `capabilities/runner.py` 已完成 Supervisor plan-only 第一片，但尚未进入
  常驻 `loop/supervise` 主决策；`runtime/ActionCompiler` 与
  `integrations/codex/CodexCliBackend` 尚未成为 Supervisor 主执行路径。
- 当前最高杠杆方向：把 `agent loop + capacity calling + capabilities`
  打通为主路径，再把 Codex worker 生命周期和状态投影迁出 feature 私有实现。

## 当前分层

| 层级 | 当前能力 | 主要位置 | 说明 |
| --- | --- | --- | --- |
| 用户功能层 | `start-here`、`scan`、`dashboard`、`trace`、`guide`、`up`、`discover`、`web`、`watch`、`advise`、`supervise`、`loop`、`daemon` | `features/supervisor/runner.py`、`features/supervisor/commands/` | 面向人类使用的命令入口；dashboard、trace、decision、context、replan、memory、worker event 等命令的 handler/payload/rendering 已迁出 runner |
| 托管控制层 | `launch`、`adopt`、`send`、`archive`、托管登记 | `features/supervisor/registry.py` | 管理 Supervisor 登记的 Codex |
| Worker 审查层 | `worker-review`、`integration-review`、`replan` | `features/supervisor/worker_review.py`、`features/supervisor/integration_review.py`、`features/supervisor/replan.py`、`features/supervisor/commands/handlers/replan.py` | 汇总已托管 worker 的 worktree、branch、状态协议、改动、复查提示、合并提示、只读集成分组和下一轮候选 |
| Merge 工单层 | `merge-work-order` builder、merge dispatch、merge promotion | `features/supervisor/merge_work_order.py`、`features/supervisor/merge_dispatch.py`、`features/supervisor/merge_promotion.py`、`features/supervisor/commands/merge/dispatch.py`、`features/supervisor/commands/merge/promotion.py`、`features/supervisor/runner.py` | 根据 `integration-review` 生成动态 merge worker 工单；命令层负责 loop 派发、递归 worker guard、promotion gate、CI watch 和兼容接线 |
| Codex 执行通道 | `resume`、`codex exec resume`、`--last` | `features/supervisor/runner.py`、`features/supervisor/registry.py` | 不依赖 tmux 恢复历史会话并投喂新 prompt |
| 上下文能力层 | `context`、`request_context`、`supervisor.request_context`、上下文结果记录 | `features/supervisor/context.py`、`features/supervisor/commands/handlers/context.py`、`capabilities/catalog.py`、`capabilities/runner.py` | LLM 按需请求检索项目资料，BM25 后端按 query 对文档和代码候选排序，不固定注入全文；能力目录已提供 workspace read-only wrapper，会写入既有 Supervisor context store |
| Codex 集成层 | 读取 Codex session（会话记录）、索引标题和 agent 元数据 | `features/supervisor/flow.py` | 当前读取本机 `.jsonl`、`session_index.jsonl` 和 SQLite |
| 扫描优化层 | 最近候选、首尾读取和标题兜底 | `features/supervisor/flow.py` | 避免每次页面刷新全量读历史 |
| tmux 集成层 | tmux 启动、buffer/paste 发送和 bell hook | `bell_events.py`、`flow.py`、`registry.py` | 只控制登记过的 tmux 会话 |
| 状态判断层 | 工作中、等待用户、疑似停住、疑似报错 | `features/supervisor/flow.py` | 规则提供候选和证据，不替代 LLM 判断 |
| 状态依据层 | `status_evidence` 说明每个状态标签的来源 | `features/supervisor/flow.py` | 避免只给结论、不说明证据 |
| 建议执行层 | `recommendation`、`command_suggestions`、`--execute` | `flow.py`、`commands/advice/__init__.py`、`commands/supervise/execution.py`、`commands/llm/action.py`、`commands/llm/execution.py`、`runner.py` | command suggestion（命令建议）、supervise/loop execution dispatch（执行分发）、LLM action dispatch（模型动作分发）和 LLM side-effect execution（副作用执行）已拆到命令层；tmux send 执行护栏仍复用 `runner.py` |
| 模型管理层 | `LLM summary`、`LLM planner` 和 TOML 号池 | `llm_summary.py` | 承担判断、调度和动作选择的 AI 路径 |
| 状态协议层 | `SUPERVISOR_STATUS` 等状态协议 | `flow.py`、`registry.py` | 给被托管 Codex 主动汇报状态 |
| 状态账本层 | lane state（窗口状态）和限频 | `lane_state.py` | 避免重复催促和刷屏 |
| 状态投影层 | `build_supervisor_state_snapshot(...)` | `features/supervisor/state/projection.py`、`platform/state/supervisor_snapshot.py`、`platform/state/active_goal.py`、`platform/state/decision_request.py`、`platform/state/goal_status.py`、`platform/state/lane_state.py`、`platform/state/worker_event_summary.py`、`platform/state/notification_summary.py` | 只读聚合 active goals、decision requests、lane failure、worker events 和 notifications；dashboard/web/daemon 已读取，loop payload 已带只读 snapshot；输出结构复用 `SupervisorStateSnapshot`、`SupervisorActiveGoal`、`SupervisorDecisionRequest`、`SupervisorGoalStatus`、`SupervisorLaneState`、`SupervisorWorkerEventSummary` 和 `SupervisorNotificationSummary` schema |
| 生命周期观测层 | `trace --json`、`loop.lifecycle_trace` | `features/supervisor/commands/trace.py`、`features/supervisor/runner.py` | 只读汇总 goal、worker、decision、merge/repair 和 cleanup 台账；payload/rendering 已迁出 runner |
| 通知桥接层 | Supervisor event notifications/webhooks | `features/supervisor/notifications.py`、`features/notifications/flow.py` | 把 goal/decision/integration-review 事件派生成低敏通知或外部 POST |
| 本地前端层 | `web`、`dashboard`、`/dashboard.json`、`/events`、`/managed/send`、`/llm-action`、`/goal/add`、daemon/watcher 控制接口 | `features/supervisor/web.py`、`features/supervisor/commands/dashboard.py` | 本机视图、bell 事件、目标写入、白名单发送、后台循环控制和手动模型建议入口；dashboard payload/plain renderer 已在命令层集中 |

## 已有轮子

详细能力清单已拆到 [Supervisor 能力详细清单](./supervisor-capability-inventory.md)。
本文件只保留能力分层、工单边界、迁移判断和登记规则，降低多人同时补充
能力列表时的冲突面。

## Work Order 分层设计

`work order` 是 Supervisor 发给被托管 Codex 的任务单。
它用于说明本次执行的目标、工作区、允许范围、禁止范围、预算、
完成条件和停等用户条件。

当前已做 A 层：把这些边界写进 `launch_session` 的 prompt。
这只能提高 worker 自觉遵守的概率，不代表 Supervisor 已经能强制预算。
不得把 A 层描述成真正的 `max_run_minutes`、`max_continue_count` 或
`max_context_requests` 控制。

B 层预算控制由 Supervisor 自己记录并拦截。当前已落地
`--max-continue-count`、`--max-context-requests` 和
`--max-run-minutes`、worker 自动重启上限 `--max-worker-retry-count`，
以及失败重试护栏 `--max-failure-retries`：
`--max-continue-count` 用 lane state 记录 `continue_count`，
限制同一 lane 同一状态下的继续推进；`--max-context-requests`
限制同一 supervise/loop 轮次里 `request_context` 的执行次数；
`--max-run-minutes` 按托管登记的
`started_at` 判断同名 lane 是否已超时，超时后纳入 worker 自动重启路径；
`--max-worker-retry-count` 默认 2，耗尽后生成 `worker_retry_failed` 拍板请求；
`--max-failure-retries` 默认 3，超过后生成 `needs_user` 类拍板请求。
`--max-continue-count`、`--max-context-requests` 和 `--max-run-minutes`
默认值都是 0，表示不启用限制；只有显式传入正数阈值时才会拦截，
避免阻碍需要长时间运行的任务。`--max-worker-retry-count` 默认开启，
用于减少需要人工手动重启 worker 的场景。
当前回归测试已覆盖默认宽松预算下，多 lane loop 连续推进不同
托管窗口。

当前 A 层字段：

- `goal`：本次要完成什么。
- `cwd`：执行所在工作区。
- `allowed_scope`：允许改哪些目录或模块。
- `forbidden_scope`：明确不碰什么。
- `budget_hint`：写给 worker 的时间、轮次和上下文请求提醒。
- `done_conditions`：什么证据算完成。
- `completion_template`：写清 `done`、`needs_user`、`blocked`
  的使用条件，并要求 summary 带验证证据、提交哈希和剩余风险；
  这里只描述 status value，不写会被日志解析器误判的状态示例行。
- `integration_review_marker`：要求 worker 保持 worktree 干净，并把最终
  commit 写进 summary；base 分支包含该 commit 或等价补丁后，
  `integration-review` 会归入 `already_integrated`。
- `ask_user_conditions`：只有哪些情况能停下来问用户。
- `report_protocol`：最后按 `SUPERVISOR_STATUS/SUMMARY/NEXT` 汇报。

## Merge Worker 交接边界

动态合并 worker 分成四个职责，不要混在一个入口里：

- `integration-review`：只读扫描 managed worker，按
  `ready_to_integrate`、`already_integrated`、`needs_review` 和
  `conflict_risk` 分组；它负责回答“哪些 worker 看起来能进合并复查”，
  不执行 merge/push/delete。
- `replan`：读取 worker 审查、活跃目标和集成分组，生成下一轮建议和
  merge candidates；它负责回答“下一轮应该复查哪些候选”，不自动合并、
  不归档、不删除分支。
- `merge-work-order`：把 ready 候选渲染成专门给 merge worker 的工单；
  它负责回答“merge worker 应按什么步骤复查、cherry-pick、测试和
  watch CI”，但 builder 本身不碰 git 状态。
- merge dispatch：已接入 `loop` 的派发层；它负责在候选明确时自动启动
  merge worker，并把 `merge-work-order` 交给 worker。

当前阶段的安全线：Supervisor 可以自动启动 merge worker；当 merge worker
的验证分支 CI 成功且它汇报 `done` 后，runner 可受控 fast-forward `main`、
push `main` 并等待 main CI；除此之外 runner 不直接
cherry-pick、删除 worker 分支或来源历史。唯一允许的删除动作是
`delete_worktree`：只清理已完成、已归档、已集成的
`.worktrees/supervisor/<worker>`，不 force push，不 rebase 已共享分支，
不重写远端历史。
`launch_session` 的通用工单默认禁止主动 push；merge dispatch worker
例外，只允许按 `merge-work-order` 推送当前合并分支用于 CI watch。

merge worker 成功合入后的交接边界也要分清：

- merge worker 可在工单范围内完成 diff review、cherry-pick、组合测试、
  推送验证分支和 CI watch；只有验证分支 CI 明确通过并能给出提交哈希、
  CI run id 和 conclusion 时，才能汇报 `SUPERVISOR_STATUS: done`。
  CI 失败或超过 30 分钟未结束时必须汇报 `blocked`，并保留 merge worktree
  供后续复查。
- `loop` 会在主工作区看到 done merge worker 后，确认验证分支 CI 为
  `success`，再要求当前工作区位于干净的 `main`，执行 `git merge --ff-only`
  到 merge worker 提交、`git push origin main`，并等待 main CI 成功；
  promotion 结果会写入 `merge_promotions`。验证分支 CI、main 工作区、
  fast-forward、push 或 main CI 任一 gate 失败时，会写入
  `merge_promotion_failed` 拍板请求，并在请求的 gate 中保留失败原因、
  分支、worker commit 和 CI payload。用户回答“放弃/不再/abandon/drop”
  后，`loop` 会把该 merge worker 标记为 `skipped_by_decision`，
  不再重复查 CI 或重复生成同一拍板请求；用户回答“修复/fix/repair”后，
  `loop` 会在独立 worktree 启动 `worker_role=merge_repair` 的 repair
  worker；该 repair worker 汇报 done 后，后续 loop 会带上
  `repair_completed` 证据并重新走 promotion gate；promotion 成功后会
  归档对应 repair worker 的 managed 记录；用户回答“重试/retry”后，
  后续 loop 也会重新走 promotion gate。
- `cleanup list/archive/delete-worktree` 是生命周期清理入口；`list` 会展示
  可归档项和可删除 worktree 候选，`archive` 只把已完成的 goal、managed
  worker 或通知标记为已处理，`delete-worktree` 复用 `delete_worktree`
  护栏删除已归档且已集成的 Supervisor worktree。它不删除 Codex 历史、
  不删除 git branch。
- 当前自动边界到“派发 merge worker”、“验证分支成功后 fast-forward main
  并 watch main CI”、“集成后归档 source/merge worker”和“清理本轮刚归档且
  已集成的 source/merge worktree”为止；
  普通 ready/already-integrated worker 不由 `loop` 自动归档或删除；
  删除 worktree 仍必须走显式 cleanup/delete-worktree 护栏或后续专门清理工单。
- `git worktree remove` 仍属于受控清理动作：需要先确认来源工作已被目标分支包含、
  没有未提交改动、没有活跃 managed record 仍在运行，再由 loop cleanup 或显式
  `delete_worktree` 执行。

## Runner 接线边界

本节只登记后续接入 `features/supervisor/runner.py` 时的分工。
`runner.py` 当前仍是 Supervisor CLI 入口和受控动作编排层，
不应被扩成新的目标队列、worker registry、LLM provider 或真实代码合并器。

当前 runner 拆分边界：兼容 re-export 集中在
`features/supervisor/compat_api.py`；默认 prompt、profile 和 marker 常量在
`features/supervisor/constants.py`；Web 命令入口在
`features/supervisor/web_runner.py`；loop/report 指纹在
`features/supervisor/supervise/fingerprint.py`；goal 状态同步在
`features/supervisor/supervise/goal_lifecycle.py`；supervise/loop 主循环在
`features/supervisor/supervise/loop.py`；payload 组装管线在
`features/supervisor/supervise/payload.py`；命令分发主干在
`features/supervisor/commands/dispatch.py`。后续继续优先迁出
`scan/report`、goal replenishment 和剩余 notification glue，让
`runner.py` 只保留入口与路由。

### 现有输入与归属

| 接线点 | 当前归属 | 后续接入边界 |
| --- | --- | --- |
| `current_batch` | dashboard/web read model（读取模型） | 只展示仍活跃的 `active_goals` 和当前托管 worker；不启动 worker、不改目标状态、不替代 cleanup。 |
| `fanout` | `loop` 与 `goal plan --fanout-execute` | 把多个活跃目标或 `parallel_recommendations` 展开成一批受控 `launch_session`；复用 goal queue、managed registry、prompt cooldown 和预算 gate，不另建队列。 |
| `replan` | `commands/llm/context.py::maybe_replan_after_context_request` | 只在同一轮 `request_context` 成功后追加最近上下文，再让 LLM planner 重新选择一次受控动作；不得无限循环，不得绕过 `ask_user` gate。 |
| `merge dispatch` | 已接入 runner loop | 读取 `ready_to_integrate` 候选，生成 `merge-work-order`，再用现有 `launch_session` 路径启动专门 merge worker；登记表写入 `worker_role=merge_dispatch`，runner 本身不得直接 cherry-pick、delete branch 或改写历史。 |

### 建议调用顺序

`current_batch`、低水位补任务、`fanout`、`replan` 接进 runner 时，顺序保持：

1. `scan/report`：先读取 Codex session、managed registry、目标状态和工作区存在性。
2. `low-water goal replenishment`：活跃目标低于显式阈值时，先让 LLM
   根据当前文档补充目标队列。
3. `current_batch`：投影当前仍可推进的目标和 worker，过滤 done、已归档、已删除 worktree。
4. `fanout planning/execution`：如果存在多个可推进目标或 goal plan 的 `parallel_recommendations`，生成受控候选并在并发上限内执行；跳过已有同名运行中 worker 的目标。
5. `merge dispatch`：fanout 不适用且 `integration-review` 给出
   `ready_to_integrate` 候选时，生成 `merge-work-order` 并启动专门
   merge worker；如果当前工作区本身是 `merge_dispatch`、`merge_repair`
   或 cleanup worker，则跳过自动 cleanup、promotion 和新的 merge
   dispatch，避免递归嵌套。
6. `LLM planner`：fanout 和 merge dispatch 都不适用时，在 `active_goals`、recent context、worker review 和白名单命令内选择一个动作。
7. `execute`：只执行通过校验的 `request_context`、`launch_session`、`resume_session`、send 或 `ask_user`。
8. `replan`：只有本轮执行的是成功的 `request_context` 时，才把检索结果加入 prompt，再执行一次 follow-up 动作。
9. `current_batch refresh`：fanout 或 merge dispatch 同轮执行了 `launch_session` 后，
   `loop --json` 会刷新一次 `current_batch`；下一轮 dashboard/web
   继续反映 worker、goal status 或 decision request 的变化。

### 验收命令

最小回归应覆盖三类接线点：

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/codex/test_codex_supervisor_readonly.py::test_codex_supervisor_dashboard_json_separates_current_batch_from_deleted_worktree_history -q
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/codex/test_codex_supervisor_readonly.py::test_codex_supervisor_runner_loop_fanout_launches_parallel_active_goals -q
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/codex/test_codex_supervisor_readonly.py::test_codex_supervisor_runner_daemon_start_passes_max_fanout_launches_to_loop -q
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/codex/test_codex_supervisor_readonly.py::test_codex_supervisor_runner_loop_suggests_all_active_goals -q
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/codex/test_codex_supervisor_readonly.py::test_codex_supervisor_runner_supervise_request_context_replans_same_iteration -q
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/codex/test_codex_supervisor_readonly.py::test_codex_supervisor_runner_loop_replans_blocked_goal_with_llm_context -q
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/supervisor/test_supervisor_goal_replenishment.py -q
```

fanout 回归必须覆盖：多个 active goals 中已有同名 running worker 时，只能为剩余目标执行
`launch_session`，并且同轮 `loop` payload 与随后 `dashboard` 的
`current_batch` 都能看见当前 worker；所有 fanout worker 同轮完成时要输出
`fanout_status` 完成摘要；任一 fanout worker 汇报 `blocked/needs_user` 时要
暂停 fanout 扩展并保留通知证据；显式 `goal plan --fanout-execute` 和
低水位补任务返回的 `parallel_recommendations` 都必须复用同一条受控
`launch_session` fanout 路径，且不能直接归档任何目标。

## 后续目标补给设计

目标补给是下一阶段让 Supervisor 真正持续工作到明早的 B 层机制。
它不替代现有 `goal add/plan`、`fanout`、`daemon` 和 worker registry，
而是在每轮 `loop` 开头读取一个用户给定的 `goal seed`（目标种子）和
当前活跃目标水位，决定是否补充新的可执行 goal。

推荐规则：

1. `goal seed` 只保存高层方向、允许范围、禁区、预算提示和验收口径。
   它不是正在执行的 goal，也不能被 worker 直接消费；补给器必须把它
   拆成小目标后写入现有 goal queue。
2. 低水位补充以“可推进 active goals 数量”为判断口径，而不是只看
   `goals.jsonl` 行数。`done`、`blocked`、已归档、同名 worker
   正在执行的目标、明确 `needs_user` 且没有新答案的目标，都不计入
   可补给水位。
3. 同一轮补给必须受最大任务数约束：先用全局 active goal 上限控制
   队列规模，再用 `--max-fanout-launches` 控制同轮启动数。补给可以写入
   多个候选 goal，但不能绕过 fanout 上限一次性启动所有 worker。
4. 补给前要做冲突检查：同名或同 scope worker 正在运行时不重复发放；
   `integration-review` 已标记 `conflict_risk` 的分支不再继续生成同一区域
   写代码任务；存在未处理 merge worker 时，优先等待 merge 结果。
5. 停止条件必须比“还有 seed”优先：CI 红灯、merge conflict、worker
   汇报 `blocked/needs_user` 且需要人类拍板、连续补给没有产生完成结果、
   或达到用户给定时间/任务预算时，补给器只能写 decision request 或
   `monitor`，不得继续扩散新任务。

接线位置应保持保守：补给器只在 `scan/report` 之后、`fanout` 之前运行，
产物仍是普通 active goals；后面的 fanout、merge dispatch、LLM planner
继续复用现有动作白名单和 budget gate。这样下一阶段实现时只需要新增
“何时补目标、补几个、何时停”的决策层，不需要再造目标队列或新 worker
启动通道。

## 条件推进与迁移表

Supervisor 后续不能只把目标 `1-10` 排序后全部从当前 `main` 分出分支。
目标队列需要支持 dependency graph（依赖图）：同阶段目标可以并行，
下游目标必须等前置阶段完成、合入并验证后才能启动。

典型节奏是：`A/B/C` 并行完成并合入后，才启动 `D/E`；
`D/E` 通过组合测试和 CI 后，才启动 `F`。任一阶段出现 conflict
（冲突）、CI fail（持续集成失败）或 `needs_user`（需要用户拍板），
后续阶段必须暂停，而不是继续扩散新分支。

架构迁移和逐文件并行实测以
[Supervisor 架构迁移表](./supervisor-architecture-migration-table.md)
为准。该表记录每类职责应从 `features/supervisor` 迁往哪个长期目录，
也记录后续用 Codex Supervisor 跑迁移 worker 时的批次条件。

## 当前不要重复实现

- 不要把规则、白名单或状态协议写成替代 LLM 的最终智能。
- 用户要求 AI 管理、AI 判断或 AI 执行时，必须打磨真实 AI 路径。
- 不要在其他目录再建一套 Supervisor CLI。
- 不要再把 tmux 当成唯一控制通道；优先复用 `codex exec resume`
  这类 Codex CLI 原生命令。
- 不要绕过托管登记表直接写新的 tmux 发送器。
- 不要给 Supervisor 再造一套独立 LLM 号池。
- 不要另写状态分类系统，除非同步更新本文件。
- 不要让 LLM 仅凭“不确定”就停下来问用户；不满足 `ask_user`
  三项 gate 时应继续查上下文、恢复会话、启动会话或推进托管窗口。
- 不要把 `ask_user` 藏在原始 JSON 里；CLI 和 web 必须显式展示问题。
- 不要只依赖一次性终端输出保存拍板请求；需要写入 decision request 账本。
- 拍板已处理后，不要手删 JSONL；有答案用 `decision answer`，
  无需继续才用 `decision archive`。
- 不要只展示状态标签而不展示判断依据。
- 不要另写一套 dashboard 数据接口，先复用 `/dashboard.json`。
- 不要把 `/events` 做成控制通道；它只负责提醒前端刷新。
- 不要在页面重复展示同一个托管 Codex 的 lane 视角和 session 视角。
- 不要在 web 里放任意文本发送框；先走白名单动作。
- web 的拍板答案表单只写 `decision_answer`，不向托管 Codex 直接发任意文本。
- 不要让 `/llm-action` 自动调用 `/managed/send`。
- 高亮模型建议不等于执行动作，执行必须由人类点击或显式参数触发。
- 没有可控托管目标时，不要为了动作建议调用 LLM。
- LLM 动作选择必须落到可审计的白名单能力上。
- 不要把 `integration-review`、`replan` 或 `merge-work-order` 的候选结果
  当成自动删除分支、force push、rebase 已共享分支或重写历史的授权；
  worktree 清理必须走 `delete_worktree` 的归档、集成和路径护栏。

## 后续拆分方向

- `features/supervisor/commands/daemon_command.py`：已承接 `daemon/up/check/watcher`
  的命令层 payload、最近活动摘要和 plain renderer；继续复用
  `features/supervisor/daemon.py` 的进程生命周期 helper，后续再把后台
  loop/runtime 下沉到 `agents/runtime/` 或 `runtime/`。
- `features/supervisor/commands/onboarding.py`：已承接 `start-here`、`guide`
  和 `discover` 的上手/接管命令层 payload、plain renderer，以及 loop
  auto-adopt（自动接管）tmux helper；继续复用 `tmux_discovery.py` 和
  `registry.py` 的既有 contract（契约）。
- `features/supervisor/commands/dashboard.py`：已承接 `dashboard` payload、
  plain renderer、managed lane linking 和 current batch projection；`web.py`
  仍保留本地 HTTP 页面和 API 包装。
- `features/supervisor/commands/trace.py`：已承接 `trace` 命令和 `loop`
  payload 共用的 lifecycle trace 生成、轻量投影和 plain renderer；底层
  goal、decision、cleanup 与 registry 账本继续复用既有模块。
- `features/supervisor/commands/cleanup/__init__.py`：已承接 `cleanup` 命令层、
  可归档项和可删除 worktree 候选展示；继续复用 managed registry、
  goal queue 与 notification。
- `features/supervisor/commands/cleanup/cleanup_worktree.py`：已承接删除确认护栏、
  worktree 候选扫描、integration review 校验和 branch cleanup；继续复用
  现有 `.worktrees/supervisor` 路径边界。
- `features/supervisor/commands/auto/auto_action.py`：已承接 `loop --auto-execute`
  的 rule-based auto action（规则自动动作）选择、continue/run budget
  与 prompt cooldown 判断；执行仍通过 `commands/advice/advice_execution.py`
  的旧 command suggestion 执行护栏。
- `features/supervisor/commands/llm/action.py`：已承接 LLM action execution
  dispatch（模型动作执行分发）、failure guard（失败护栏）、context request
  budget 和 active-goal resume gate；底层 `resume/launch/context/ask_user`
  执行函数继续走 `commands/llm/execution.py`，并保留 `runner.py` 兼容 alias。
- `features/supervisor/commands/llm/planner.py`：已承接 LLM planner
  provider/failure glue（模型规划器供应商与失败处理胶水），包括无 target
  fallback、provider 选择、invalid response 失败记录和 retry-limit 拍板动作；
  继续通过 runner 兼容 alias 复用 `generate_llm_action_decision(...)` 和
  `resolve_summary_provider_from_env(...)`，保护现有 monkeypatch 测试表面。
- `features/supervisor/commands/failure_guard.py`：已承接 failure ledger guard
  （失败账本护栏），包括失败事件记录、retry exhausted（重试耗尽）判断、
  failure decision request action（失败拍板动作）构造、lane name 和 goal id
  归属解析；继续复用 `failure_ledger.py`，不新建账本格式。
- `features/supervisor/commands/llm/execution.py`：已承接 LLM side-effect
  execution（模型动作副作用执行）的 `resume_session`、`launch_session`、
  `request_context`、`ask_user`、worker profile、worktree 准备和运行中
  worker 检查；实现仍通过 `api` 复用 runner 兼容名，保护旧测试和
  monkeypatch 表面。
- `features/supervisor/commands/fanout.py`：已承接 fanout orchestration
  （并行派发编排）的 active goal launch plan、低水位补任务 plan、暂停
  action、fanout log 和批量 launch 执行汇总；纯规划仍复用
  `agents/scheduler/fanout.py`，status summary（状态摘要）复用
  `agents/scheduler/fanout_status.py`，不在命令层再写一套调度算法或摘要。
- `features/supervisor/commands/merge/dispatch.py`：已承接 merge dispatch
  orchestration（合并派发编排）、当前 worktree worker role 判断、recursive
  worker guard（递归 worker 护栏）和 merge dispatch execution 标记；底层
  launch spec 仍复用 `features/supervisor/merge_dispatch.py` 的纯 builder。
- `features/supervisor/commands/merge/promotion.py`：已承接 merge promotion
  orchestration（合并提升编排），包括 blocked merge worker 修复派发、
  promotion gate、CI watch、拍板请求、repair worker lifecycle 和旧
  runner 私有入口兼容；底层 CI/git 判定仍复用
  `features/supervisor/merge_promotion.py` 的 helper。
- `features/supervisor/commands/failure_lifecycle.py`：已承接 worker failure
  lifecycle（worker 失败生命周期），包括 process worker 失败同步、
  非零退出/usage limit/timeout 解析、自动重试、retry-limit 拍板请求和
  lane failure payload；底层继续复用 `lane_state.py`、managed registry、
  decision request 和 runner 兼容 alias，不新建失败账本。
- `features/supervisor/commands/auto/auto_cleanup.py`：已承接 auto cleanup lifecycle
  （自动清理生命周期），包括集成后 merge/source worker 自动归档、关联
  merge goal 归档、低敏通知写入、归档后 worktree 删除串联和 integration
  review 摘要 helper；继续复用 `cleanup.py`、`cleanup_worktree.py`、
  `goal_queue.py`、`notifications.py` 和 managed registry，不绕过删除护栏。
- `features/supervisor/commands/advice/__init__.py`：已承接 `advise`、`supervise`
  和 `loop` 共同使用的 advice payload、automation status 和
  command suggestion 生成；实际发送、预算、cooldown（冷却时间）和托管
  发送护栏已拆到 `features/supervisor/commands/advice/advice_execution.py`。
- `features/supervisor/commands/plain_rendering.py`：已承接 `advise` 和
  `supervise` 的 plain rendering（终端文本渲染），包括 LLM action、
  follow-up action、auto action、fanout execution、ask-user 和旧 command
  suggestion 的人类可读输出；payload 构造和执行仍通过 runner 兼容 alias
  复用既有 helper。
- `features/supervisor/commands/loop_state.py`：已承接 loop target/scope/
  actionability（目标、作用域、可行动性）判断，包括 idle loop reason、
  target session 查找、managed scope 检查、workspace action gate 和
  terminal-done 过滤；继续通过 runner 兼容 alias 复用 advice/auto_action
  的状态判断 contract。
- `features/supervisor/commands/workspace_scope.py`：已承接 loop/advise 共用的
  workspace scope（工作区作用域）过滤、scope payload、workspace root 解析和
  context cwd 选择；保留 runner alias 供 merge dispatch/promotion 等命令层
  复用同一工作区边界。
- `features/supervisor/commands/supervise/payload.py`：已承接 supervise/loop
  base payload（基础载荷）初始化，包括 action report、state snapshot、
  active goals、goal replenishment、advice payload、workspace scope 和固定
  lifecycle 字段。
- `features/supervisor/commands/llm/context.py`：已承接 supervise/loop 传给
  LLM planner 的 context payload（上下文载荷），包括 recent context、
  decision answers、capacity decisions/call specs、worker review 和
  delete-worktree candidates；也承接成功 `request_context` 后的 follow-up
  replan，runner 只保留兼容 alias。
- `features/supervisor/commands/supervise/planning.py`：已承接 supervise/loop
  planning payload（规划载荷），包括 current batch、fanout status/plan、
  fanout log、merge dispatch 和 recursive worker guard；继续复用
  `dashboard.py`、`fanout.py` 和 `merge_dispatch.py` 的 helper，不重写调度规则。
- `features/supervisor/commands/supervise/action.py`：已承接 supervise/loop
  LLM action selection（模型动作选择），按 fanout pause/plan、recursive worker
  guard、merge dispatch、idle loop 和 LLM planner 顺序选择本轮 `llm_action`；
  继续复用既有 action builder 和 `_promote_llm_command_suggestion(...)`。
- `features/supervisor/commands/handlers/capacity.py`：已承接 capacity plan 命令、
  low-risk capability execution（低风险能力执行）和 loop
  `capacity_decisions` / `capacity_call_specs` 生产 glue；plain 输出已补齐
  低敏 planner / tick / artifact handoff summary，JSON payload 已暴露同源
  `agent_loop_summary` helper；继续复用
  `agents/scheduler/capacity_graph.py`、`CapabilityRunner` 和
  `llm.capacity_calling`，不在 runner 中重写 capacity graph。
- `features/supervisor/commands/advice/advice_execution.py`：已承接旧 command
  suggestion 执行路径，包括 `send_status`/`send_continue` 白名单校验、
  tmux target 选择、run budget、prompt cooldown、busy lane 拦截、
  `send_to_managed_codex` 调用和 lane prompt 记录；继续复用 runner
  兼容 alias，保护既有 monkeypatch 测试表面。
- `features/supervisor/commands/handlers/decision.py`：已承接 `decision list/archive/answer`
  的 payload 和 plain renderer；继续复用既有 decision request 账本与
  answer/webhook helper，避免在命令入口重写拍板流程。
- `features/supervisor/commands/handlers/context.py`：已承接 `context` CLI handler；
  继续复用 `features/supervisor/context.py` 的 BM25 检索和结果存储，后续
  再判断是否下沉到通用 RAG 或 capability 层。
- `features/supervisor/commands/handlers/replan.py`：已承接 `replan` CLI handler；
  只聚合 worker review、integration review 和 active goals，不执行 merge、
  归档或删除 worktree。
- `features/supervisor/commands/handlers/memory.py`：已承接 `memory`、
  `worker-event` 和 `worker-manager` CLI handler；底层继续复用 memory view，
  `memory --query` 会返回 summary / refs / provenance 的低敏 recall 结果；
  并通过 `platform/state` 的 worker event channel、`WorkerEvent` schema
  和 multi-worker read model 读取低敏 worker 状态。
- `features/supervisor/commands/parser/memory.py`：已承接 `memory`、
  `worker-event` 和 `worker-manager` 的 argparse（参数解析器）注册；
  `parser.py` 只导入该 helper，避免继续扩大巨型 parser 函数。
- `features/supervisor/state/projection.py`：已承接第一片只读 Supervisor
  state projection，复用 goal queue、decision request、lane state、
  worker event channel 和 notification index；dashboard/web/daemon
  已读取该 snapshot，loop payload 已带只读 snapshot，后续入口不应继续拼散表。
  该 builder 仍留在 feature 层，输出结构改为复用
  `platform/state/supervisor_snapshot.py` 的 `SupervisorStateSnapshot`，
  避免 `platform/state` 反向依赖 Supervisor feature。
- `features/supervisor/goal_queue.py`：仍负责 `goals.jsonl` 写入、去重和
  goal status 通知；state projection 的 active goal payload 已改为复用
  `platform/state/active_goal.py` 的 `SupervisorActiveGoal`，最近状态 payload
  已改为复用 `platform/state/goal_status.py` 的 `SupervisorGoalStatus`，
  当前不迁 goal queue 持久化格式。
- `features/supervisor/lane_state.py`：仍负责 `lane_state.json` 读写、
  prompt cooldown（催促冷却）、continue budget（继续预算）、失败记录、
  worker retry 和 decision timeout；状态结构已改为复用
  `platform/state/lane_state.py` 的 `SupervisorLaneState`，当前不迁
  lane state 持久化格式。
- `features/supervisor/status.py`：后续可下沉状态分类和状态依据生成。
- `features/supervisor/advice.py`：后续可承接自动策略和执行白名单，避免
  `runner.py` 继续扩写动作执行分支。
- `features/supervisor/protocol.py`：后续可下沉状态协议解析和提示语注入。
- `features/supervisor/tmux_control.py`：后续可下沉更底层的 tmux 会话、发送和
  bell hook；loop 自动接管胶水已先并入 onboarding 命令层。
- `features/supervisor/lane_state.py`：每个窗口的最近状态、催促次数和限频。
- `integrations/codex/session_reader.py`：后续可把 Codex `.jsonl` 读取下沉。

## 下一步顺序

1. 继续评估 lane state 持久化、goal queue 持久化和 notification index 中哪些事实还应下沉到
   `platform/state`；当前 notification snapshot payload（通知快照载荷）schema
   已下沉，notification index 写入仍留在 feature flow。
2. 用真实 daemon 长跑验证 cleanup/current dashboard 在多批任务中的稳定性。
3. 后续再决定是否把通知接到更多 worker 生命周期事件。
4. 再拆分 web/bell/notification glue 或继续压缩 `_run_cli_impl`。

## 登记规则

新增 Supervisor 能力时，至少同步：

- 本文件。
- [当前状态](./status.md)。
- [任务队列](./agent-task-queue.md)。
- [Supervisor 架构迁移表](./supervisor-architecture-migration-table.md)
  中的 reuse audit（复用审计）和 refactoring debt（重构债务）条目。
- 新术语或新命令还要同步 [术语索引](./terminology.md)。

登记时必须写清楚：本能力复用了哪些现有模块、没有复用哪些相似模块、
原因是什么，以及是否新增了需要后续迁移或拆分的债务。
