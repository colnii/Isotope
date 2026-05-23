# Isotope 当前状态

状态：`主线收束 / Supervisor 产品化推进中`

本文件只记录当前事实和入口。历史状态正文已移到
[status-history](../archive/current/status-history.md)。

## 当前判断

Isotope 是 local-first（本地优先）的 AI engineering workbench（AI 工程工作台），
不是单纯 kernel（内核）项目。当前主线围绕 Codex Supervisor、受控 worker
启动、证据收集、可恢复开发流程和本机 Web dashboard 推进。

项目方向由产品目标决定：先做出可展示、可持续扩展的 AI 应用，再把底层边界
逐步稳定下来。

## 当前分支状态

- `main` 是主线。
- 多 AI 并行开发必须使用独立 worktree。
- 临时分支合并后要清理 worktree、本地分支和远端临时分支。
- 旧暂停分支的可用代码已进入主线；剩余内容只保留历史参考价值。

## 当前重点

1. 保持 `docs/current/` 短入口化，历史流水放入 `docs/archive/current/`。
2. 继续让 Supervisor 成为可日常使用的管理层，而不是只读诊断工具。
3. Supervisor 新能力先查
   [能力地图](./supervisor-capability-map.md) 和
   [架构迁移表](./supervisor-architecture-migration-table.md)，避免重复造轮子。
4. AI agent 功能默认 AI-first；规则、白名单、冷却和工作区边界是 guardrail
   （护栏），不能替代模型主路径。
5. `features/supervisor/state/projection.py` 已提供只读低敏 Supervisor state
   projection（状态投影），统一读取 active goals、decision、lane failure、
   worker events 和 notifications；后续 dashboard/daemon 接入前不要重复拼散表。
6. 代码结构继续以 `src/isotope/` 为 Python 主包，不新增 `packages/`、
   `aios` 或 kernel 主叙事。

## 当前入口

- [README](../../README.md)：项目目标和快速开始。
- [文档总入口](../README.md)：`docs/` 目录职责。
- [文档地图](./docs-map.md)：按任务找文档。
- [任务队列](./agent-task-queue.md)：当前可执行任务。
- [Supervisor 监控与托管](./codex-supervisor-readonly.md)：Supervisor 快速入口。
- [Supervisor 命令参考](./supervisor-command-reference.md)：完整命令和长跑流程。
- [Supervisor 能力地图](./supervisor-capability-map.md)：能力索引。
- [Supervisor 能力详情](./supervisor-capability-details.md)：详细能力登记。

## 常用验证

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope -q
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario workbench --trace
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario workbench-ask --trace
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner scan --limit 3
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner dashboard --limit 3
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner check
```

文档-only 改动至少跑 `git diff --check` 和 Markdown link check。
