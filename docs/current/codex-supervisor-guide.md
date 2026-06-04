# Codex Supervisor 监控与托管

状态：`当前入口 / quick start`

命令索引和运行边界见 [Supervisor 命令参考](./supervisor-command-reference.md)，
当前可执行任务见 [任务队列](./agent-task-queue.md)，术语定位见
[术语索引](./terminology.md)。

## 目标

Codex Supervisor 是 Isotope 的本机管理层：观察多个 Codex 会话，启动和接管
worker，汇总证据，生成下一步建议，并通过白名单动作进行受控推进。

它不是纯规则脚本。LLM planner（模型规划器）应参与判断、调度和下一步建议；
规则、冷却、状态协议、tmux 和工作区边界只提供 guardrail（护栏）。

## 最短路径

```bash
.venv/bin/isotope-supervisor start-here --goal "继续推进当前项目目标"
.venv/bin/isotope-supervisor up --goal "继续推进当前项目目标"
.venv/bin/isotope-supervisor web --host 127.0.0.1 --port 8765
```

常用查看：

```bash
.venv/bin/isotope-supervisor check
.venv/bin/isotope-supervisor scan --limit 5
.venv/bin/isotope-supervisor dashboard --limit 5
.venv/bin/isotope-supervisor goal list
.venv/bin/isotope-supervisor decision list
```

常用托管：

```bash
.venv/bin/isotope-supervisor launch --cwd /path/to/repo --name lane-a --prompt "执行一个明确任务"
.venv/bin/isotope-supervisor resume --cwd /path/to/repo --name lane-a --last --prompt "继续推进并汇报状态"
.venv/bin/isotope-supervisor worker-review
.venv/bin/isotope-supervisor integration-review
```

Research 测试入口：

```bash
.venv/bin/isotope-supervisor research --root /tmp/isotope-research --query "agent memory retrieval" --provider codex
.venv/bin/isotope-supervisor research list --root /tmp/isotope-research
.venv/bin/isotope-supervisor research inspect --root /tmp/isotope-research --run-id run_001 --artifact-id artifact_002
```

## 当前边界

- 自动动作必须走白名单、cooldown（冷却）和 workspace（工作区）边界。
- merge worker 按工单推送验证分支；普通 worker 把结果留在本地分支等待集成。
- runner 不直接重写历史、不 force push、不删除未确认集成的 worktree。
- `delete_worktree` 只有在 done、archived、already_integrated 且路径安全时才允许。
- 新增 Supervisor 能力前先查 [Supervisor 命令参考](./supervisor-command-reference.md)
  和 [术语索引](./terminology.md)。
- `research` 只代理 artifact/provenance-backed Research flow；search 成功写
  `research.report`，失败写 `research.provider_trace`，不直接写 durable memory。

## 相关文档

- [Supervisor 命令参考](./supervisor-command-reference.md)
- [任务队列](./agent-task-queue.md)
- [术语索引](./terminology.md)
