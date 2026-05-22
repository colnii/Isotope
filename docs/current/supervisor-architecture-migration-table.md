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

## 迁移表

| 当前职责 | 现有位置 | 目标位置 | 迁移方式 | 备注 |
| --- | --- | --- | --- | --- |
| CLI 参数、命令分发 | `features/supervisor/runner.py`, `commands/` | `features/supervisor/commands/` | 先保留兼容入口，逐个命令拆 handler | `runner.py` 最终只做入口转发和兼容 glue（胶水代码）。 |
| Dashboard / Web 视图 | `features/supervisor/web.py`, `dashboard_html.py`, `runner.py` | `features/supervisor/web/` 或保持 feature 内 | 可以先留在 feature | 这是用户可见产品入口，暂不下沉到底座。 |
| Codex session 扫描 | `features/supervisor/flow.py` | `integrations/codex/session_reader.py` | 抽只读 reader，再由 feature 调用 | 未来支持 Qoder/Minimax worker 时不能绑定在 supervisor feature 内。 |
| Codex exec / resume / launch | `runner.py`, `registry.py` | `integrations/codex/` + `execution/` | 先抽 process 后端和 resume 命令构造 | Codex 是外部集成，不是 Supervisor 核心本体。 |
| managed worker registry | `features/supervisor/registry.py` | `agents/worker_registry.py` 或 `platform/registry/` | 先保留 Codex 字段，抽通用 worker record | 后续 worker 不一定都是 Codex。 |
| goal queue（目标队列） | `features/supervisor/goal_queue.py` | `agents/scheduler/goal_queue.py` | 抽通用 goal model，feature 留 adapter | 目标队列属于 agent 调度，不属于前端功能。 |
| goal planner（目标规划） | `features/supervisor/goal_planner.py` | `agents/planner/` | 先抽 prompt、解析、修复器 | 应接 agent loop 和文档检索，不只服务 Codex Supervisor。 |
| fanout（并行派发） | `features/supervisor/fanout.py`, `runner.py` | `agents/scheduler/fanout.py` | 先迁纯规划函数，再迁执行编排 | fanout 是调度能力，应支持依赖图和并发上限。 |
| merge dispatch / promotion | `merge_dispatch.py`, `merge_promotion.py`, `runner.py` | `workspace/git/` + `agents/integration/` | 先保留工作流，抽 git/worktree 操作 | 合并、CI、worktree 清理属于 workspace/integration。 |
| worker review / integration review | `worker_review.py`, `integration_review.py` | `agents/review/` + `workspace/git/` | 按只读审查和 git 操作拆分 | 可作为通用 worker 完成度审查能力。 |
| decision requests（拍板请求） | `decision_requests.py` | `agents/decision/` 或 `platform/state/` | 先抽账本接口 | 拍板请求是通用 agent 控制面，不应只服务 Supervisor。 |
| context request（上下文请求） | `context.py`, `runner.py` | `rag/` + `agents/context/` | 抽检索接口，feature 留命令包装 | 当前偏 rg/BM25-style，后续可接语义检索。 |
| capacity calling（能力调用） | `llm/capacity_calling.py`, `agents/loop/` | `capabilities/` + `agents/loop/` | 优先打通真实 loop，不再只做原型 | Supervisor planner 应能调用能力，而不是写死动作。 |
| memory view / worker event channel | `features/supervisor/state/`, `memory/worker_event_channel.py` | `memory/` + `platform/state/` | 先统一 store 和事件 schema | 多 worker 协调要复用同一记忆/事件层。 |
| daemon / watcher | `runner.py`, `daemon.py` | `agents/runtime/` 或 `runtime/` | 抽循环运行器和生命周期管理 | 后台循环是运行时能力，不应塞在一个命令文件里。 |
| failure ledger / retry guard | `failure_ledger.py`, `runner.py` | `platform/state/` + `agents/policy/` | 先抽失败账本，再抽重试策略 | 失败记录和策略要能服务其他 agent。 |
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
