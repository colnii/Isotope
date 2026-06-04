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
| 开工前查重复 worktree | `isotope-supervisor worktree-audit --repo-root .` |
| 看当前整体状态 | `isotope-supervisor check`、`dashboard`、`state`、`goal list` |
| 追加或归档目标 | `goal add`、`goal list`、`goal archive` |
| 提交用户拍板答案 | `decision list`、`decision answer` |
| 托管 worker | `launch`、`resume`、`adopt`、`send`、`archive` |
| 内部 Agent 群聊 | `agent-group create/send/tick/list/inspect` |
| 后台常驻和看门 | `loop`、`daemon start/status/watchdog/watcher/stop` |
| 审查 worker 合入状态 | `worker-review`、`integration-review`、`replan`、`merge-work-order` |
| 受限清理 worktree | `cleanup list`、`cleanup delete-worktree` |
| 规划或执行 capability | `capacity plan`、`capacity plan --execute-agent-loop`、`isotope-capability search/plan/run` |
| 查询本地 memory preview | `memory --query <query>` |
| 代理 Research flow | `research --root . --query "..." --provider codex --json`、`research list --root .`、`research inspect --root . --run-id <run> --artifact-id <artifact>` |

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
| `start-here` / `guide` / `discover` | 打印可复制的上手、接管和观察命令。 | [quick start](./codex-supervisor-guide.md)、[capability details](./supervisor-capability-details.md) |
| `up` / `loop` / `daemon` / `check` | 日常监督入口，负责后台 loop、watchdog、状态摘要和活跃目标读取。 | [operations runbook](./supervisor-operations-runbook.md) |
| `goal` / `decision` / `state` | 持久目标队列、用户拍板账本和统一结构化 state projection（状态投影）。 | [capability inventory](./supervisor-capability-inventory.md)、[architecture migration table](./supervisor-architecture-migration-table.md) |
| `agent-group` | 创建、发送、tick 和查看 Supervisor 内部 Agent group chat。 | [terminology](./terminology.md) |
| `worktree-audit` | 查看本地 worktree/branch 主题词，提示可能重复开发的候选；删除、合并和文件修改由后续显式命令处理。 | 本文 |
| `dashboard` / `web` / `events` | 本机 dashboard、web 页面、bell 事件和受控按钮入口。 | [quick start](./codex-supervisor-guide.md)、[operations runbook](./supervisor-operations-runbook.md) |
| `advise` / `supervise` / `llm-action` | LLM planner（模型规划器）建议、白名单动作选择和显式执行。 | [capability inventory](./supervisor-capability-inventory.md) |
| `launch` / `resume` / `adopt` / `send` / `archive` | 托管 Codex worker、tmux lane 和状态协议交互。 | [operations runbook](./supervisor-operations-runbook.md) |
| `worker-review` / `integration-review` / `replan` | 审查 worker、测试结果、合入候选和下一步建议。 | [capability details](./supervisor-capability-details.md) |
| `merge-work-order` / `merge-dispatch` / `promotion` | 生成 merge worker 工单、派发合并、CI watch 和 promotion gate。 | [architecture migration table](./supervisor-architecture-migration-table.md) |
| `cleanup` | 只在 done、archived、already_integrated 且路径安全时删除 worktree。 | [capability inventory](./supervisor-capability-inventory.md) |
| `capacity` | 生成 capacity decision；显式执行时通过 tick driver 运行一次 `call_capability`。 | [capability inventory](./supervisor-capability-inventory.md)、[agent-loop tick driver boundary](../architecture/agent-loop-tick-driver-boundary-v0.2.md) |
| `isotope-capability` | 搜索、检查或运行 capability；`supervisor.goal_plan` 复用目标规划，`supervisor.worker_review` / `supervisor.integration_review` 复用既有审查路径，`memory.query` / `screen.observe` / `screen.report` 复用既有结构化查询、观察和报告边界。 | [capability inventory](./supervisor-capability-inventory.md) |
| `memory` / `worker-event` / `worker-manager` | 查询本地 memory preview、worker event、multi-worker read model 和 supervised capacity run 摘要。 | [terminology](./terminology.md)、[capability inventory](./supervisor-capability-inventory.md) |
| `research` | 代理 shared Research flow，支持 search / list / inspect；成功写 `research.report`，provider 失败只写 `research.provider_trace`。 | [application structure plan](./application-structure-plan.md)、[terminology](./terminology.md) |
| `isotope-screen inspect/report` / `screen` | 读取 screen artifact 或生成 run 级结构化 observe/control plan 摘要；Supervisor `screen report/inspect` 复用同一 screen artifact report 边界。 | [application structure plan](./application-structure-plan.md)、[terminology](./terminology.md) |

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

### 开工前协调

```bash
.venv/bin/isotope-supervisor worktree-audit --repo-root .
.venv/bin/isotope-supervisor worktree-audit --repo-root . --json
```

`worktree-audit` 读取 `git worktree list --porcelain` 和每个 worktree 的
`git status --porcelain=v1`，按 branch/path 里的非泛化主题词提示可能重复开发的
worktree，也会报告多个 dirty worktree 是否修改了同一个文件。它是 human review
（人工复查）入口；删除 worktree 和合并分支走后续显式命令。`launch_session`
执行路径会复用同一套主题匹配；发现同主题 worktree 时会跳过新启动并返回
需要确认的候选。

### Research artifact 闭环

```bash
.venv/bin/isotope-supervisor research providers --root /tmp/isotope-research
.venv/bin/isotope-supervisor research --root /tmp/isotope-research --query "agent memory retrieval" --provider codex
.venv/bin/isotope-supervisor research list --root /tmp/isotope-research --limit 5
.venv/bin/isotope-supervisor research inspect --root /tmp/isotope-research --run-id run_001 --artifact-id artifact_002
```

独立入口同样可用：

```bash
.venv/bin/isotope-research providers
.venv/bin/isotope-research search --root /tmp/isotope-research --query "agent memory retrieval" --provider codex
.venv/bin/isotope-research list --root /tmp/isotope-research --artifact-type research.provider_trace
.venv/bin/isotope-research inspect --root /tmp/isotope-research --run-id run_001 --artifact-id artifact_001
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
- 开工前如果存在多个活跃 worktree，先跑 `worktree-audit`；发现候选重复时先人工
  合并方向或收敛任务，不让多个进程各自实现一套。
- 普通 worker 把结果留在本地分支等待集成；merge worker 按 `merge-work-order`
  工单推送验证分支。
- runner 通过受控 cleanup / merge 流程处理历史、push 和 worktree 删除。
- `delete_worktree` 只有在 done、archived、already_integrated 且路径安全时才允许。
- `web` 默认只监听本机地址；`/managed/send` 只接受受控动作。
- `decision answer` 只写拍板答案账本，下一轮 LLM planner 再读取答案继续判断。
- `capacity plan --execute-agent-loop` 让已标记可执行的 `call_capacity`
  通过单 tick driver 跑一次 `call_capability`；多轮推进交给 finite-step runner
  和 tick policy；JSON 输出会带
  `agent_loop_summary` 结构化字段，供 dashboard / web 复用。
- `supervisor.goal_plan` capability 默认只预览目标规划；只有输入里显式
  `write=true` 才会写入 Supervisor goal queue。
- `memory --query` 返回 summary / refs / provenance preview；plain 输出会标出
  `content_policy`、匹配数量、source refs 和 provenance，raw content 走 expand grant。
- `isotope-capability run memory.query --input-json ...` 复用同一条
  `LocalMemoryQueryService` 结构化 recall 路径，要求 `root/query/run_id` 和
  caller audit；`controlled_expand` 有 expand grant 和正预算时会物化 matched
  `MemoryRecord.content` 的 budgeted `materialized_text`；source artifact full
  content 走 artifact inspect / expansion 路径。
- `write_memory` 是 runtime action，Supervisor 通过 action proposal 调用它；默认 action
  registry 已启用它，但 policy 要求显式 approval。批准后只追加结构化
  `memory.record_created` event，query/read model 返回 summary / refs / provenance。
- `research` 是 artifact/provenance-backed search substrate（基于产物和来源证据的搜索底座），memory 写入走 promotion/action 路径。
- `research` search 成功时保存 `research.raw_transcript` 与 `research.report`；
  source 会带 `source_kind` / `source_authority` 结构化分类字段；
  provider 失败时只保存 `research.provider_trace`，并写入结构化 diagnostics
  （event counts、error messages、是否出现 agent_message、timeout seconds、
  retry attempts），成功 report 只由 successful search 写入。
- `research list` 只列 `research.*` artifact，按最近修改时间倒序；plain 输出给
  可复制的 `run_id` / `artifact_id`，用于后续 `research inspect`。
- `isotope-research inspect --root ... --run-id ... --artifact-id ...` 可读取
  单个 `research.*` artifact 内容；非 research artifact 会被拒绝。Supervisor
  侧 `research inspect` 复用同一边界。
- `isotope-research promote --root ... --run-id ... --artifact-id ... --agent-id ...
  --thread-id ...` 从 `research.report` artifact metadata 与结构化 report quality
  gate 生成 `write_memory` proposal；quality gate 会统计 high-authority 和
  unknown sources，但当前不因 unknown source 单独拒绝；Supervisor 侧
  `research promote` 复用同一 helper。该入口生成提案，memory 写入走 approval，
  raw transcript 正文走 inspect。
- `research providers` 列出 provider registry；当前 `codex` 可运行，
  `tavily` 也可运行但默认 preflight；只有显式 `--tavily-enable-network` 才会请求
  Tavily `/search`。Tavily key 可来自 `--tavily-api-key`、`TAVILY_API_KEY`，或
  git-ignored 的 `src/isotope/features/research/research_tavily.toml`；缺 key 或未开
  网络时会复用 `ResearchFlow` 写 `research.provider_trace`。`searxng` / `browser`
  仍是 planned provider，选择时会 fail closed。
- raw web text 后续要进入 durable memory 时，必须先经过 artifact / provenance /
  retrieval 和显式 promotion policy，不得绕过 Research flow 直接写 memory。

## 更新规则

- 新增命令族或改变用户入口时，更新本文。
- 单个命令的长参数、smoke 步骤、夜间流程优先写
  `supervisor-operations-runbook.md`，不要把本文扩成长手册。
- 能力字段、payload、状态协议和 LLM action 细节优先写
  `supervisor-capability-inventory.md` 或 `supervisor-capability-details.md`。
- 历史完整命令说明只用于追溯，不作为当前事实。
