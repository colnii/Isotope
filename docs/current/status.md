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
   worker events 和 notifications；dashboard/web/daemon 已接入该读模型，
   worker event payload 已经通过平台 schema 过滤成低敏 summary，loop payload
   已带只读 snapshot，`isotope-supervisor state` 可直接查看，后续入口接入前不要
   重复拼散表。
6. `FileFlow` 文件摘要和 `TaskFlow` 结果摘要读取已通过 platform
   `ResourceRef` + artifact record 校验并刷新本地 index，避免盲信
   `files/index.json` / `tasks/index.json`。
7. `ProjectFlow` 关联、读取和列出 task/file 链接时复用 `TaskFlow.get_task()`
   和 `FileFlow.get_file()` 校验目标可读，避免传播不可解析的本地关联 ID。
8. HTTP artifact summary endpoint 已通过 platform artifact record 返回低敏摘要，
   不再由 HTTP 层直接拼 `artifact.created` event payload。
9. Agent loop 已有单 tick driver：`run_agent_loop_tick(...)` 会先读取
   tick policy，允许继续时只执行一个已解析的 planner-selected step，再返回
   执行后的 tick policy；`agent-loop-tick-driver-trace` demo 已能输出
   `before_policy -> planner_result -> after_policy` 的人类可读 handoff。
   Supervisor 的 `call_capacity` 已通过现有 `planner_output` contract 接入这个
   driver；`supervisor-capacity-handoff-trace` demo 可展示
   `Supervisor action -> planner_output_summary -> tick_result -> persisted policy`。
   它仍不调用真实 LLM，不自动多轮循环。
10. Screen observe/control 已有 policy-gated（策略门控）第一片：
    `screen_observe` / `screen_control` 走 registry、policy、executor 和 artifact
    边界，Windows backend 仅用于手动 smoke；当前不是默认自动 GUI agent。
11. 代码结构继续以 `src/isotope/` 为 Python 主包，不新增 `packages/`、
   `aios` 或 kernel 主叙事。

## 当前入口

- [README](../../README.md)：项目目标和快速开始。
- [文档总入口](../README.md)：`docs/` 目录职责。
- [文档地图](./docs-map.md)：按任务找文档。
- [任务队列](./agent-task-queue.md)：当前可执行任务。
- [Supervisor 监控与托管](./codex-supervisor-readonly.md)：Supervisor 快速入口。
- [Supervisor 命令参考](./supervisor-command-reference.md)：命令索引和边界。
- [Supervisor operations runbook](./supervisor-operations-runbook.md)：夜间 smoke 和长流程验收。
- [Supervisor 能力地图](./supervisor-capability-map.md)：能力索引。
- [Supervisor 能力详情](./supervisor-capability-details.md)：详细能力登记。

## 常用验证

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope -q
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario workbench --trace
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario workbench-ask --trace
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner scan --limit 3
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner dashboard --limit 3
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner state --json
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner check
```

文档-only 改动至少跑 `git diff --check` 和 Markdown link check。
