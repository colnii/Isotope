# 应用目录迁移方案

状态：`目标蓝图已吸收 / 应用内分层进行中`

主包已从 `src/isotope_kernel/` 迁移到 `src/isotope/`。
后续 Isotope 应继续按 AI 应用软件组织目录，而不是围绕 `kernel` 命名。
新目录应优先服务可应用、可落地和多分支并行开发。

## 目标结构

这个结构是目标态蓝图，不要求第一天写满。
当前落地方式仍是 Python `src` layout：核心代码放在
`src/isotope/`，而不是新增 `packages/` 或改名成 `aios`。
完整平台化结构里的大边界可以作为方向，但要翻译成 Isotope
自己的应用软件语义，避免重新回到 `kernel` 或 AI OS 叙事。

```text
apps/
  cli/
  api/
  web/
src/
  isotope/
    core/
    features/
      chat/
      tasks/
      projects/
      files/
      research/
      automation/
      capability_building/
    agents/
      loop/
    capabilities/
      tools/
      skills/
    llm/
    rag/
      ingestion/
      retrieval/
    memory/
    workspace/
    execution/
    runtime/
    integrations/
      mcp/
      codex/
    interfaces/
    policy/
    platform/
      schemas/
      events/
      registry/
      state/
      lifecycle/
    common/
tests/
docs/
docker/
deployments/
datasets/
notebooks/
scripts/
```

## 目标态和当前子集

目标态可以很大，当前子集必须很薄。

- `apps/` 是入口层；入口只调用 `src/isotope/` 的稳定模块。
- `src/isotope/` 承担完整版本里 `packages/` 的角色。
- `core/` 已开始承载产品主流程，当前提供 session、conversation、
  task、run、turn、dispatch 和 response 的薄层。
- `features/` 只放用户能感知的功能，不提前建空功能目录。
- `capabilities/` 描述 AI 能做什么；`runtime/` 描述在哪里、
  以什么权限和隔离方式运行。
- `memory/` 是长期状态；未来如需一次模型调用的上下文打包，
  再考虑 `context/` 或放入更明确的模块。
- `policy/` 从现在保留，因为审批、权限和审计会穿过多个层级。

暂不落地但保留为远期蓝图的方向：

- 顶层 `skills/`、`agents/`、`workflows/`、`connectors/`
  可作为用户资产或项目资产目录，但要等加载协议出现后再建。
- `observability/`、`evolution/`、`context/`、`sandboxes/`
  先作为概念保留，不为目录好看提前展开。
- `apps/web`、`apps/desktop`、`apps/daemon` 等入口等真实端侧需求出现后再建。

## 初步映射

- `core/`：产品主流程，负责 session、conversation、task、turn、dispatch 和 response；当前薄包单进程运行时，不承载 agent loop。
- `features/`：真实可用功能，如聊天、任务、项目、文件、研究和自动化；当前已有聊天和任务薄入口。
- `agents/`：子 agent 定义、角色、任务委派和 agent loop。
- `capabilities/`：工具、技能和能力注册，不再使用顶层 `tools/` 空包。
- `llm/`：LLM、embedding、rerank 等模型服务 provider，不放 Pydantic schema 或数据库模型。
- `rag/`：外部资料接入、检索、切分和索引等资料问答能力。
- `execution/`：shell、python、浏览器、桌面、沙箱等执行环境。
- `runtime/`：进程内运行入口，串起会话、策略、执行、事件和状态读取。
- `workspace/`：项目、文件、artifact 产物和 git 工作树边界。
- `memory/`：长期记忆存储、总结和共享上下文，不把所有检索都塞进这里。
- `integrations/`：Codex、MCP、GitHub、浏览器、VS Code 等外部系统接入。
- `interfaces/`：当前只保留库内 HTTP facade，不扩张成 CLI / SDK。
- `policy/`：权限、风险、审批和审计。
- `platform/`：事件、schema、registry、state、lifecycle 等底座雏形。
- `common/`：通用工具，但不能变成无边界杂物目录。

`assistant` 可以描述 Isotope 的产品体验，但不再作为新目录名扩张。
旧 `src/isotope/assistant/` 已删除。
agent loop 活跃实现已迁到 `src/isotope/agents/loop/`。
旧 `core/loop_*` 已删除。

## 迁移原则

- 先固化目标骨架，再迁移旧包名。
- 骨架目录可以先建，但要对应近期迁移目标或明确负责人。
- 骨架不要求一开始都有完整实现，但不能长期无人使用、无人解释。
- 允许先按目标态设计边界，但代码只落当前 MVP 子集。
- 先迁移低风险模块，再迁移入口、包名和测试路径。
- 保持测试可运行，不做一次性大爆炸重命名。
- 每次迁移都更新导入路径、测试路径和文档入口。
- 历史包名不再作为活跃导入路径。
- `src/isotope/` 是 Python 包命名空间，不是重复叙事。
- 不采用 `src/core/`、`src/features/` 这类无项目命名空间的顶层包。
- 不新增 `packages/`；Python 项目里由 `src/isotope/` 承担平台代码包。
- 不使用 `aios`、`kernel` 作为当前包名或主叙事。
- 不新增 `*_assistant` 功能目录，功能目录用职责名：`projects/`、`files/`、`research/`。
- 同一概念只能有一个主目录，其他位置只能是 adapter 或 compatibility proxy。
- 兼容代理需要登记到 [import-map](./import-map.md)，并写明计划删除节点。

## 已落地试点

此前迁移分支 `feature/app-terminal-exec-migration` 已 fast-forward 合入 `main`。
本轮已把该试点并入 `src/isotope/` 命名空间。

第一片：

- `src/isotope/capabilities/tools/terminal.py`
- `src/isotope/execution/terminal_runner.py`
- `tests/isotope/test_terminal_tool.py`
- `tests/isotope/test_terminal_backend_app.py`

目标：先把终端执行能力放入应用化目录。
旧顶层 `src/agents/` 已清理，不再作为活跃包。

下一步是在 `src/isotope/` 内继续做应用分层，而不是恢复旧包名。

## 已完成分层

- CLI 入口：`apps/cli/` 已建立薄入口，正式脚本在 `pyproject.toml` 的 `[project.scripts]` 中声明。
- 平台 schema：动作、产物、记忆、外部快照、资源引用和工具协议已放入
  `src/isotope/platform/schemas/` 的具体文件；根 `isotope.models` 已删除。
- 平台事件：`events.py`、`event_schema.py` 已迁入 `src/isotope/platform/events/`，活跃导入已切到新路径。
- 能力目录：`capability_catalog.py`、`capability_runner.py` 已迁入 `src/isotope/capabilities/`，旧根路径已删除。
- 产品聊天流程：活跃实现已迁入 `src/isotope/features/chat/flow.py`；
  `src/isotope/features/chat/product_chat.py` 和顶层旧路径已删除。
- 任务功能入口：`src/isotope/features/tasks/flow.py` 已提供
  `TaskFlow` 和 `TaskSummary`，先把 core task 包成用户可读摘要。
- 智能体循环：`agent_loop_*` 与 planner contract 已迁入 `src/isotope/agents/loop/`；
  旧顶层、`core/loop_*` 和 `assistant/` 入口已删除。
- 工作区资源：`workspace.py` 与 `artifact_store.py` 已迁入 `src/isotope/workspace/`，相关旧根路径已删除。
- RAG 边界：`ingestion.py` 与 `retrieval.py` 已迁入 `src/isotope/rag/`，旧根路径已删除。
- 记忆边界：`memory.py` 已迁成 `src/isotope/memory/` 包。
- 权限策略：`policy.py` 已迁成 `src/isotope/policy/` 包。
- 平台注册表与错误：`action_registry.py`、`errors.py` 已迁入 `src/isotope/platform/`。
- 平台工具：`ids.py` 已迁入 `src/isotope/platform/ids.py`。
- 执行器：`executor.py` 已迁入 `src/isotope/execution/executor.py`。
- 终端执行器：活跃实现已迁入 `src/isotope/execution/terminal_runner.py`；
  `src/isotope/execution/terminal_backend.py` 和顶层旧路径已删除。
- 工具能力：`src/isotope/tools/` 旧空包已删除；真实工具能力放入
  `src/isotope/capabilities/tools/`，动作声明放入平台注册表。
- 接口层：`http_api.py` 已迁入 `src/isotope/interfaces/http.py`。
- LLM 层：模型 provider 和 tool bridge 已迁入 `src/isotope/llm/`；
  `src/isotope/integrations/llm/` 和顶层旧路径已删除。
- Codex 集成：`codex_task.py`、`codex_cli.py`、`codex_server.py`、`codex_live_smoke.py` 已迁入 `src/isotope/integrations/`，旧根路径已删除。
- 状态恢复：`checkpoint_store.py`、`event_store.py`、`projector.py` 已迁入 `src/isotope/platform/state/`。
- 运行入口：活跃实现已迁入 `src/isotope/runtime/in_process.py`；
  `src/isotope/runtime/server.py` 旧代理已删除。
- 动作编译：`action_compiler.py` 已迁入 `src/isotope/runtime/action_compiler.py`。
- 旧根路径和旧空包已完成当前已知清理；后续新增兼容代理需先登记。
- 产品 core：`ProductCore`、`RuntimeDispatch`、`CoreSession`、
  `CoreRun` 和 `CoreTurnResponse` 已加入 `src/isotope/core/`，
  先包住 `InProcessServer`，提供单进程会话、run 和用户消息提交入口。
- 对话状态：`CoreConversation`、`CoreTurn` 和
  `CoreConversationState` 已加入 `src/isotope/core/`；当前
  conversation 可跨多个 completed run（已结束运行），以适配现有运行时语义。
- 任务状态：`CoreTask` 和 `CoreTaskState` 已加入 `src/isotope/core/`；
  `features/tasks/` 已有第一片薄入口，但还不是完整任务管理系统。

## 第一批建议

优先建立：

- `apps/cli/`
- `apps/api/`
- `src/isotope/core/`
- `src/isotope/agents/loop/`
- `src/isotope/features/chat/`
- `src/isotope/features/tasks/`
- `src/isotope/features/projects/`
- `src/isotope/features/files/`
- `src/isotope/capabilities/tools/`
- `src/isotope/llm/`
- `src/isotope/rag/`
- `src/isotope/execution/`
- `src/isotope/runtime/`
- `src/isotope/workspace/`
- `src/isotope/memory/`
- `src/isotope/policy/`
- `src/isotope/platform/schemas/`
- `src/isotope/platform/events/`
- `src/isotope/platform/registry/`
- `src/isotope/platform/state/`
- `src/isotope/interfaces/`，仅保留当前库内 HTTP facade
- `src/isotope/common/`，仅在出现真实跨层通用代码时再建

暂缓完整展开：

- `apps/web/`
- `features/research/`
- `features/capability_building/`
- `integrations/github/`
- `integrations/browser/`
- `integrations/vscode/`
- 复杂多 agent 编排和自我改造机制。
