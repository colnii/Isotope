# Codex Supervisor 能力地图

状态：`当前入口 / 能力索引`

详细能力登记已移到
[Supervisor 能力详情](./supervisor-capability-details.md)。架构归属和迁移判断见
[Supervisor 架构迁移表](./supervisor-architecture-migration-table.md)。

## 用途

本文件用于回答两个问题：

1. 新增 Supervisor 功能前，现有能力在哪里？
2. 哪些能力已经有实现，不能重复造一套？

## 当前能力索引

| 能力层 | 入口 | 主要位置 |
| --- | --- | --- |
| 用户入口 | `start-here`、`up`、`check`、`scan`、`dashboard`、`state`、`web` | `features/supervisor/commands/` |
| 托管控制 | `launch`、`resume`、`adopt`、`send`、`archive` | `features/supervisor/registry.py`、`runner.py` |
| 目标队列 | `goal add/list/archive/plan`、goal replenish | `goal_queue.py`、Supervisor commands |
| 拍板系统 | `decision list/answer/archive`、dashboard 等待拍板 | decision ledger、web handlers |
| LLM planner | `--llm-action`、`--llm-execute`、context 后续动作 | `commands/llm_action.py`、`llm_summary.py` |
| 上下文检索 | `context`、`request_context`、`supervisor.request_context` | `context.py`、`capabilities/runner.py` |
| worker 审查 | `worker-review`、`integration-review`、`replan` | `worker_review.py`、`integration_review.py`、`replan.py` |
| merge 工单 | `merge-work-order`、merge dispatch、auto promote | `merge_work_order.py`、`merge_dispatch.py` |
| 状态投影 | `state`、`build_supervisor_state_snapshot(...)` | `features/supervisor/state/projection.py`、`commands/state.py` |
| 本机页面 | `/dashboard.json`、`/events`、`/managed/send`、`/llm-action` | `web.py`、dashboard modules |
| cleanup 护栏 | `delete_worktree` deny-by-default | cleanup command modules |

## 复用规则

- 能用 `runner.py` 既有护栏、registry、lane state、goal queue、decision ledger
  和 integration review 的，不另造状态账本。
- 能用 Supervisor state projection（状态投影）读取 active goals、decision、
  lane failure、worker event 和 notification 的，不重新拼散表；dashboard/web
  和 daemon 已读取，loop payload 已带只读 snapshot；命令行直接查看用
  `isotope-supervisor state`。
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
- [Supervisor 监控与托管](./codex-supervisor-readonly.md)
- [Supervisor 命令参考](./supervisor-command-reference.md)
- [任务队列](./agent-task-queue.md)
