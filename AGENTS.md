# 仓库指南

## 项目结构与模块组织

Isotope 是面向真实使用的 AI 应用软件，不是单纯内核项目。
目标是在秋招前搭出可展示、可继续扩展的产品。
现有代码迁移到 `src/isotope/`，测试迁移到 `tests/isotope/`。
`src/isotope/` 是长期 Python 包命名空间。
后续目录应按 AI 应用拆成 `apps/`、`assistant/`、`features/`、
`capabilities/`、`execution/`、`workspace/`、`memory/` 等层级。
文档放在 `docs/`；当前状态先看 `docs/current/status.md`。
文档地图和清理计划看 `docs/current/docs-map.md` 与
`docs/current/agent-task-queue.md`。

## 构建、测试与开发命令

常用命令：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[test]"
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope -q
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario v0.2 --trace
```

按任务风险选择验证范围；不要为了形式运行无关长流程。

## 代码风格与命名

Python 代码使用 4 空格缩进，模块和函数用 `snake_case`。
测试文件用 `test_*.py`，测试函数用 `test_*`。
保持文件职责清楚，不把货架、执行器、界面和诊断混成大文件。
新增依赖可以接受，但要说明用途、维护成本和替代方案。
不要为了“自主实现”重复造轮子。

## 产品导向开发

先确认用户要的最终可用效果，再动手。
不得擅自把产品功能降级成诊断、预检查或半成品。
若需求过大，拆成可运行、可演示的阶段成果。
速度和质量都重要；不要用“稳定”掩盖低效推进。
不为“安全感”堆无意义检查，不重复做已证明的底层铺垫。

用户给出参考产品、仓库或实现时，必须先提炼：
可复用设计、可复制代码、差异点、落地方案。
可以积极参考 GitHub 优秀项目。
满足需求、许可证允许、少量适配即可使用的代码，可以直接复制再改。
参考材料是需求输入，不是背景噪音；忽略前必须说明原因。

## 测试要求

测试使用 `pytest`。
功能开发要有测试，但测试服务于交付，不是拖慢交付的理由。
小改动可做最小验证；共享行为、执行路径或状态恢复改动要跑相关回归。
行为变化后，同步入口文档和相关状态说明。

## 提交与合并请求

提交信息遵守 Conventional Commits。
提交前运行 `git diff --check` 和必要测试。
保持线性历史，优先 rebase 或 fast-forward。
不要在共享分支制造无说明的 merge commit。
不要主动合并、删除或重写分支；分支处理先做状态审计。
分支和清理状态以 `docs/current/status.md` 为准，不写进本文件。

## AI 协作规则

当前分支只表示代码位置，不代表项目方向。
多 AI 并行开发时必须使用独立 worktree（工作树）。
遇到不确定点，优先向用户对齐，不要自作主张绕远路。
判断要收窄范围时，先说明原因并等待用户同意。
术语可保留英文以便搜代码，但首次出现要配中文说明。
未经用户批准，不随意扩写 `AGENTS.md`、`README.md` 等参考文档。
每次结束回复时，用一句话说明建议的下一步。

临时术语锚点：
`agent loop` 智能体循环；`tool call` 工具调用；
`artifact` 产物记录；`checkpoint` 检查点；
`provider` 模型服务适配器；`planner` 规划器；
`executor` 执行器；`policy` 权限策略；
`capability` 能力；`workspace` 工作区；
`terminal_exec` 终端执行能力。
完整术语索引应在文档整理阶段从真实代码和文档抽取。
