# Isotope

Isotope 是一个面向真实使用的 AI 应用软件。

它会包含 AI 规划、智能体循环、工具调用、终端能力、任务产物、
状态恢复和产品界面。早期从底座能力做起，但项目目标不是只做内核。

当前阶段进入项目整备：

- 所有功能分支暂停继续开发。
- 先清理 AI 协作规则和当前状态文档。
- 再整理 `docs/` 目录，归档或删除过期文档。
- 最后逐个审计功能分支，合并正经代码，废弃半成品。

## 快速开始

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/python -m pytest tests/isotope_kernel -q
.venv/bin/python -m isotope_kernel.demo --scenario v0.2 --trace
```

## 当前可用能力

- 事件记录、审批、产物记录、回放和检查点。
- 受控工具调用和终端命令执行的基础路径。
- 模型服务适配器的基础封装。
- 若干演示场景，用来验证底座能力是否仍可运行。

这些能力是产品的基础，不是产品的全部。

## 当前不可做的事

- 不继续功能分支开发。
- 不把当前分支当成项目方向定义。
- 不再把真实产品功能自动降级成预检查或诊断工具。
- 不再堆叠只服务于“看起来安全”的文档和检查。

## 主要入口

- AI 协作规则：[AGENTS.md](AGENTS.md)
- 当前状态：[docs/current/status.md](docs/current/status.md)
- 文档地图：[docs/current/docs-map.md](docs/current/docs-map.md)
- 整备队列：[docs/current/agent-task-queue.md](docs/current/agent-task-queue.md)

## 术语

- 智能体循环：AI 多步执行流程。
- 工具调用：AI 请求系统执行某个能力。
- 产物记录：运行中生成并可追溯的结果。
- 检查点：可恢复状态的保存点。
