# Codex Supervisor 能力地图

状态：`当前入口 / 能力索引`

分层和迁移判断见
[Supervisor 能力详情](./supervisor-capability-details.md)，长能力清单见
[Supervisor 能力详细清单](./supervisor-capability-inventory.md)。架构归属和迁移判断见
[Supervisor 架构迁移表](./supervisor-architecture-migration-table.md)。

## 用途

本文件用于回答两个问题：

1. 新增 Supervisor 功能前，现有能力在哪里？
2. 哪些能力已经有实现，不能重复造一套？

## Agent Harness Lens

Agent Harness 只作为工程审计镜头，不替代 Isotope / Supervisor 的现有架构。
新增或调整能力时，用它检查能力、边界、证据和回归风险：

1. State is not context（状态不是上下文）。Durable state（持久状态）必须落在
   events、artifacts、provenance、permissions、decisions 和 verification
   evidence；context 只是当前模型或界面看到的 projection（投影）。
2. ETCLOVG 是 debt table（负债表），不是替代架构。按
   `layer / current capability / missing invariant / risk if absent / evidence signal`
   记录 Execution、Tooling、Context、Lifecycle、Observability、Verification
   和 Governance 的覆盖与缺口。
3. Handoff 必须 resumable（可恢复）。交接内容要包含 objective、permissions、
   workspace scope、artifacts、evidence、risks、unresolved decisions、
   resume checks 和 stop conditions，不能只有文本摘要。
4. Harness change 必须有 deletion story（删除条件）。新增 wrapper、guardrail、
   verifier、planner、reset 或 reviewer 时，说明 failure class、cost、eval
   signal 以及 rollback / deletion condition。

Deferred capability directions（暂缓能力方向，不新增对象）：

- Scoped temporary permission grants：权限应按 task / workspace 临时授予，并且
  auditable、expirable、revocable。
- Lightweight tool ergonomics checks：关键 capability 后续补 `when_to_use` 和
  `when_not_to_use`；高风险 capability 补 1-2 条 negative eval，确认模型知道何时
  不该调用它。

## 当前能力索引

| 能力层 | 入口 | 主要位置 |
| --- | --- | --- |
| 用户入口 | `start-here`、`up`、`check`、`scan`、`dashboard`、`state`、`web` | `features/supervisor/commands/` |
| 托管控制 | `launch`、`resume`、`adopt`、`send`、`archive` | `features/supervisor/registry.py`、`runner.py` |
| 目标队列 | `goal add/list/archive/plan`、goal replenish | `goal_queue.py`、Supervisor commands |
| 拍板系统 | `decision list/answer/archive`、dashboard 等待拍板 | decision ledger、web handlers |
| LLM planner | `--llm-action`、`--llm-execute`、context 后续动作 | `commands/llm/action.py`、`llm_summary.py` |
| 上下文检索 | `context`、`request_context`、`supervisor.request_context` | `context.py`、`capabilities/runner.py` |
| worker 审查 | `worker-review`、`supervisor.worker_review`、`integration-review`、`supervisor.integration_review`、`replan` | `worker_review.py`、`integration_review.py`、`capabilities/runner.py`、`replan.py` |
| memory recall / promotion | `memory --query`、`memory.query`、`memory.promotion.preview` | `memory/__init__.py`、`memory/views.py`、`memory/promotion.py`、`capabilities/memory.py` |
| screen report | `isotope-screen report`、`isotope-supervisor screen report`、`screen.report` | `features/screen/artifacts.py`、`features/supervisor/commands/dispatch.py`、`capabilities/screen.py` |
| merge 工单 | `merge-work-order`、merge dispatch、auto promote | `merge_work_order.py`、`merge_dispatch.py` |
| 状态投影 | `state`、`build_supervisor_state_snapshot(...)` | `features/supervisor/state/projection.py`、`platform/state/supervisor_snapshot.py`、`commands/handlers/state.py` |
| 本机页面 | `/dashboard.json`、`/events`、`/managed/send`、`/llm-action` | `web.py`、dashboard modules |
| cleanup 护栏 | `delete_worktree` deny-by-default | cleanup command modules |

## 复用规则

- 能用 `runner.py` 既有护栏、registry、lane state、goal queue、decision ledger
  和 integration review 的，不另造状态账本。
- 能用 Supervisor state projection（状态投影）读取 active goals、decision、
  lane failure、worker event 和 notification 的，不重新拼散表；dashboard/web
  和 daemon 已读取，loop payload 已带只读 snapshot；命令行直接查看用
  `isotope-supervisor state`。projection builder 仍留在 Supervisor feature，
  但输出结构必须复用 `platform/state` 的 `SupervisorStateSnapshot` schema；
  active goal payload 必须复用 `SupervisorActiveGoal` schema；active goal
  的最近状态 payload 必须复用 `SupervisorGoalStatus` schema；active decision
  payload 必须复用 `SupervisorDecisionRequest` schema；failed lane payload
  必须复用 `SupervisorLaneState` schema；recent worker event payload 必须复用
  `SupervisorWorkerEventSummary` schema；notification summary payload 必须复用
  `SupervisorNotificationSummary` schema。
- 能用 capability runner（能力运行器）的，只加 catalog/plan/run 包装，不开新执行面。
- 能用 `commands/` 内已拆 handler 的，不把新命令继续塞回 runner。
- 新增术语或命令后，同步 [术语索引](./terminology.md) 和
  [Supervisor 架构迁移表](./supervisor-architecture-migration-table.md)。

## 当前不要重复实现

- 不再新增另一套 Codex session reader。
- 不再新增另一套 worker done/blocked 解析协议。
- 不再新增绕过 registry 的 worktree cleanup。
- 不再把 LLM 降级成只读 summary 插件。

## 相关文档

- [Supervisor 能力详情](./supervisor-capability-details.md)
- [Supervisor 能力详细清单](./supervisor-capability-inventory.md)
- [Supervisor 监控与托管](./codex-supervisor-readonly.md)
- [Supervisor 命令参考](./supervisor-command-reference.md)
- [Supervisor operations runbook](./supervisor-operations-runbook.md)
- [任务队列](./agent-task-queue.md)
