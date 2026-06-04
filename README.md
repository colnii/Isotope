# Isotope

Isotope 是一个面向本地 AI 编程工作流的 Agent Supervisor / AI 工程工作台。

目标是解决 AI 辅助开发中的一个实际问题：
当多个 Codex / Agent 窗口并行工作时，用户很难持续判断它们分别在做什么、
是否卡住、是否需要拍板、下一步该继续还是回收。

Isotope 通过本地会话扫描、状态识别、LLM 规划、受控 worker 启动和
Web dashboard，把这些分散的 AI 编程过程组织成可观察、可恢复、可审查的工作流。

## 核心能力

- **Codex 会话扫描**：读取本机 Codex session 记录，识别工作目录、分支、最近消息和状态证据。
- **状态判断**：区分 `working`、`needs_user`、`stale`、`done` 等状态，并输出中文摘要。
- **LLM-driven supervision**：让模型在受控动作集合中选择 `monitor`、`request_context`、`launch_session`、`ask_user` 等下一步动作。
- **多 worker 托管**：可启动后台 Codex worker 或接管 tmux 会话，并跟踪 worker 的状态协议和日志输出。
- **目标队列**：支持把长期目标写入队列，由后台 daemon 动态消费、推进、归档或等待用户拍板。
- **集成审查**：查看已完成 worker 的分支、提交、diff、合并风险和后续验证建议。
- **Web research substrate**：通过 `isotope-research` 或 Supervisor 代理入口执行 search / list / inspect，结果先落为 `research.*` artifact 和 provenance 证据，长期 memory 写入走 promotion/action 路径。
- **Webhook 通知**：`loop`、`supervise`、`daemon start`、`integration-review` 和 `decision answer` 可用 `--webhook-url` 发送结构化事件，`--webhook-secret` 会添加 HMAC 签名。
- **Web dashboard**：本地页面展示和新增目标、查看 worker 详情、处理等待拍板，并可控制后台循环。

## 使用场景

- 同时开多个 AI 编程窗口时，快速判断哪些任务还在跑、哪些需要人处理。
- 把“继续推进当前项目”拆成多个受控 worker，并在完成后回收 diff、测试和提交。
- 在长期任务中记录用户拍板，避免模型反复询问或重复启动同名 worker。
- 用摘要和结构化事件保留可审查证据，而不是只依赖聊天窗口记忆。

## 快速开始

需要 Python `3.13` 或更新版本。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/python -m pytest tests/isotope -q
```

第一次试 Supervisor，先生成一条最短试用路径：

```bash
.venv/bin/isotope-supervisor start-here --goal "继续推进当前项目目标"
```

它会打印四类命令：启动后台、打开页面、查看状态、停止后台。
之后通常只需要先跑其中的启动命令，再打开本地 Web dashboard。

扫描最近的 Codex 会话：

```bash
.venv/bin/isotope-supervisor scan --limit 5
```

直接启动本地 Web dashboard：

```bash
.venv/bin/isotope-supervisor web --host 127.0.0.1 --port 8765
```

把一个目标交给后台 Supervisor：

```bash
.venv/bin/isotope-supervisor up --goal "继续推进当前项目目标"
```

查看目标和等待拍板项：

```bash
.venv/bin/isotope-supervisor goal list
.venv/bin/isotope-supervisor decision list
```

测试 research artifact 闭环：

```bash
.venv/bin/isotope-research providers
.venv/bin/isotope-research search --root /tmp/isotope-research --query "agent memory retrieval" --provider fake
.venv/bin/isotope-research list --root /tmp/isotope-research
.venv/bin/isotope-supervisor research inspect --root /tmp/isotope-research --run-id run_001 --artifact-id artifact_002
```

## 架构概览

```text
Codex sessions / tmux lanes / managed workers
        ↓
Supervisor scanner
        ↓
status evidence + workspace context
        ↓
LLM planner + rule guardrails
        ↓
controlled actions
        ↓
worker launch / context request / decision request / archive
        ↓
CLI report + Web dashboard + local event logs
```

核心设计原则：

- **AI-first, guardrail-backed**：让 LLM 参与判断和调度，但所有动作都经过白名单和工作区边界约束。
- **Local-first**：优先服务本机开发流程，不依赖中心化服务即可运行。
- **Evidence-oriented**：状态判断要带证据来源，worker 完成后要能回看分支、diff 和验证建议。
- **Recoverable workflow**：重要目标、拍板、worker 状态和 daemon 日志都落到本地账本，便于恢复。

## 当前状态

项目当前处于个人开发阶段，主线能力集中在 Codex Supervisor：

- CLI 和本地 Web dashboard 已可运行。
- 目标队列、拍板记录、后台 daemon、worker 启动和集成审查已形成闭环。
- Research 测试入口已形成 artifact-backed search / list / inspect 闭环，并可从 Supervisor 侧代理查看。
- 仍在迭代产品交互、README 展示、前端可视化和更稳定的任务回收流程。

这不是一个成熟商业产品，而是一个围绕真实 AI 编程工作流持续演进的工程项目。

## 主要入口

- 项目状态：[docs/current/status.md](docs/current/status.md)
- Supervisor 说明：[docs/current/codex-supervisor-guide.md](docs/current/codex-supervisor-guide.md)
- 文档地图：[docs/current/docs-map.md](docs/current/docs-map.md)
- 任务队列：[docs/current/agent-task-queue.md](docs/current/agent-task-queue.md)
- 协作规则：[AGENTS.md](AGENTS.md)
