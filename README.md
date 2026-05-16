# Isotope

Isotope 是一个面向真实使用的 AI 应用软件。

它会包含 AI 规划、智能体循环、工具调用、终端能力、任务产物、
状态恢复和产品界面。早期从底座能力做起，但项目目标不是只做内核。

当前阶段已经完成主线收束：

- 旧功能分支已完成审计、代码抽取和清理。
- AI 协作规则和当前状态文档已更新。
- `docs/` 已按当前、架构、功能、评审、归档分层。
- 已迁移到 `src/isotope/` 应用包结构。

## 快速开始

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/python -m pytest tests/isotope -q
.venv/bin/python -m isotope.demo --scenario v0.2 --trace
.venv/bin/python -m isotope.features.supervisor.runner scan --limit 3
.venv/bin/isotope-demo --scenario v0.2 --trace
.venv/bin/isotope-supervisor scan --limit 3
.venv/bin/isotope-supervisor scan --limit 3 --llm-summary
.venv/bin/isotope-supervisor advise
.venv/bin/isotope-supervisor supervise --interval 180 --llm-summary
.venv/bin/isotope-supervisor watch --interval 180 --changes-only --llm-summary
.venv/bin/isotope-supervisor launch --name lane-a --cwd /path/to/repo --prompt "继续实现当前任务"
.venv/bin/isotope-supervisor launch --backend tmux --tmux-session isotope-lane-a --name lane-a --cwd /path/to/repo --prompt "继续实现当前任务"
.venv/bin/isotope-supervisor send --name lane-a --text "继续"
```

## 当前可用能力

- 事件记录、审批、产物记录、回放和检查点。
- 受控工具调用和终端命令执行的基础路径。
- 模型服务适配器的基础封装。
- 若干演示场景，用来验证底座能力是否仍可运行。
- Codex Supervisor 监控与托管，可观察本机多个 Codex 会话，
  支持变化触发汇报、结构化建议、托管启动、tmux 会话启动和发送一行指令，
  并可选调用已配置 LLM 输出中文智能汇报。

这些能力是产品的基础，不是产品的全部。

## 当前约束

- 不把当前分支当成项目方向定义。
- 不再把真实产品功能自动降级成预检查或诊断工具。
- 不再堆叠只服务于“看起来安全”的文档和检查。

## 主要入口

- AI 协作规则：[AGENTS.md](AGENTS.md)
- 当前状态：[docs/current/status.md](docs/current/status.md)
- 文档地图：[docs/current/docs-map.md](docs/current/docs-map.md)
- 整备队列：[docs/current/agent-task-queue.md](docs/current/agent-task-queue.md)
- Codex Supervisor：[docs/current/codex-supervisor-readonly.md](docs/current/codex-supervisor-readonly.md)

## 术语

- 智能体循环：AI 多步执行流程。
- 工具调用：AI 请求系统执行某个能力。
- 产物记录：运行中生成并可追溯的结果。
- 检查点：可恢复状态的保存点。
