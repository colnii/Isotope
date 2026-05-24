# Supervisor 命令参考

状态：`当前入口 / 命令索引`
更新时间：2026-05-24

本文只保留 Supervisor 命令族、常用入口、边界归属和更新规则，不再维护长篇逐命令说明。
旧完整说明已归档到
[supervisor-command-reference-full-2026-05-24](../archive/current/supervisor-command-reference-full-2026-05-24.md)。

拆分原因：完整命令参考同时覆盖 capability（能力）、web、daemon、runbook、LLM
动作和 merge/cleanup 流程，更新频率高、重复来源多，容易在多分支持续合入 `main`
时滞后或冲突。当前文件只回答“先用哪个命令、细节去哪里看”。

## 先看哪里

| 场景 | 入口 |
| --- | --- |
| 第一次启动 Supervisor | `isotope-supervisor start-here --goal "..."` |
| 日常唤起后台和看状态 | `isotope-supervisor up --goal "..."` |
| 浏览本机页面 | `isotope-supervisor web --host 127.0.0.1 --port 8765` |
| 看当前整体状态 | `isotope-supervisor check`、`dashboard`、`state`、`goal list` |
| 追加或归档目标 | `goal add`、`goal list`、`goal archive` |
| 提交用户拍板答案 | `decision list`、`decision answer` |
| 托管 worker | `launch`、`resume`、`adopt`、`send`、`archive` |
| 后台常驻和看门 | `loop`、`daemon start/status/watchdog/watcher/stop` |
| 审查 worker 合入状态 | `worker-review`、`integration-review`、`replan`、`merge-work-order` |
| 受限清理 worktree | `cleanup list`、`cleanup delete-worktree` |
| 规划或执行 capability | `capacity plan`、`capacity plan --execute-agent-loop` |
| 查询本地 memory preview | `memory --query <query>` |
| 代理 Research flow | `research --root . --query "..." --provider fake --json` |

安装后优先使用：

```bash
.venv/bin/isotope-supervisor <command>
```

源码树内调试时使用：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner <command>
```

## 命令族

| 命令族 | 当前职责 | 详细来源 |
| --- | --- | --- |
| `start-here` / `guide` / `discover` | 打印可复制的上手、接管和观察命令；不启动任务、不发送指令。 | [quick start](./codex-supervisor-readonly.md)、[capability details](./supervisor-capability-details.md) |
| `up` / `loop` / `daemon` / `check` | 日常监督入口，负责后台 loop、watchdog、状态摘要和活跃目标读取。 | [operations runbook](./supervisor-operations-runbook.md) |
| `goal` / `decision` / `state` | 持久目标队列、用户拍板账本和统一低敏 state projection（状态投影）。 | [capability inventory](./supervisor-capability-inventory.md)、[architecture migration table](./supervisor-architecture-migration-table.md) |
| `dashboard` / `web` / `events` | 本机 dashboard、web 页面、bell 事件和受控按钮入口。 | [quick start](./codex-supervisor-readonly.md)、[operations runbook](./supervisor-operations-runbook.md) |
| `advise` / `supervise` / `llm-action` | LLM planner（模型规划器）建议、白名单动作选择和显式执行。 | [capability inventory](./supervisor-capability-inventory.md) |
| `launch` / `resume` / `adopt` / `send` / `archive` | 托管 Codex worker、tmux lane 和状态协议交互。 | [operations runbook](./supervisor-operations-runbook.md) |
| `worker-review` / `integration-review` / `replan` | 只读审查 worker、测试结果、合入候选和下一步建议。 | [capability details](./supervisor-capability-details.md) |
| `merge-work-order` / `merge-dispatch` / `promotion` | 生成 merge worker 工单、派发合并、CI watch 和 promotion gate。 | [architecture migration table](./supervisor-architecture-migration-table.md) |
| `cleanup` | 只在 done、archived、already_integrated 且路径安全时删除 worktree。 | [capability inventory](./supervisor-capability-inventory.md) |
| `capacity` | 生成 capacity decision；显式执行时通过 tick driver 运行一次 `call_capability`。 | [capability inventory](./supervisor-capability-inventory.md)、[agent-loop tick driver boundary](../architecture/agent-loop-tick-driver-boundary-v0.2.md) |
| `memory` / `worker-event` / `worker-manager` | 查询本地 memory preview、worker event 和 multi-worker read model。 | [terminology](./terminology.md)、[capability inventory](./supervisor-capability-inventory.md) |
| `research` | 代理 shared Research flow，成功写 `research.report`，provider 失败只写 `research.provider_trace`。 | [application structure plan](./application-structure-plan.md)、[terminology](./terminology.md) |

## 常用闭环

### 日常启动

```bash
.venv/bin/isotope-supervisor start-here --goal "继续推进当前项目目标"
.venv/bin/isotope-supervisor up --goal "继续推进当前项目目标"
.venv/bin/isotope-supervisor web --host 127.0.0.1 --port 8765
```

### 查看和拍板

```bash
.venv/bin/isotope-supervisor check
.venv/bin/isotope-supervisor dashboard --limit 5
.venv/bin/isotope-supervisor state --json
.venv/bin/isotope-supervisor goal list
.venv/bin/isotope-supervisor decision list
.venv/bin/isotope-supervisor decision answer --request-id <request-id> --answer "..."
```

### 过夜和早上收口

```bash
.venv/bin/isotope-supervisor goal add --cwd /path/to/repo "过夜要推进的目标"
.venv/bin/isotope-supervisor up
.venv/bin/isotope-supervisor daemon start --interval 30
.venv/bin/isotope-supervisor daemon watcher start --interval 60

.venv/bin/isotope-supervisor daemon status
.venv/bin/isotope-supervisor daemon watcher status
.venv/bin/isotope-supervisor integration-review
.venv/bin/isotope-supervisor cleanup list
```

长流程细节、夜间 smoke 和状态协议看
[Supervisor operations runbook](./supervisor-operations-runbook.md)。

## 当前边界

- Supervisor 不是纯规则脚本；LLM planner 应参与判断、调度和下一步建议。
- 自动动作必须走白名单、cooldown（冷却）、state ledger（状态账本）和 workspace
  boundary（工作区边界）。
- 普通 worker 不应主动 push；merge worker 只能按 `merge-work-order` 工单推送验证分支。
- runner 不直接重写历史、不 force push、不删除未确认集成的 worktree。
- `delete_worktree` 只有在 done、archived、already_integrated 且路径安全时才允许。
- `web` 默认只监听本机地址；`/managed/send` 只接受受控动作。
- `decision answer` 只写拍板答案账本，下一轮 LLM planner 再读取答案继续判断。
- `capacity plan --execute-agent-loop` 只允许已标记可执行的 `call_capacity`
  通过单 tick driver 跑一次 `call_capability`，不打开自动多轮循环。
- `memory --query` 只返回 summary / refs / provenance preview，不返回 raw content。
- `research` provider 失败时只保存 `research.provider_trace`，不生成成功 report。

## 更新规则

- 新增命令族或改变用户入口时，更新本文。
- 单个命令的长参数、smoke 步骤、夜间流程优先写
  `supervisor-operations-runbook.md`，不要把本文扩成长手册。
- 能力字段、payload、状态协议和 LLM action 细节优先写
  `supervisor-capability-inventory.md` 或 `supervisor-capability-details.md`。
- 历史完整命令说明只用于追溯，不作为当前事实。
