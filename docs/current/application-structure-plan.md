# 应用目录迁移方案

状态：`应用内分层进行中`

主包已从 `src/isotope_kernel/` 迁移到 `src/isotope/`。
后续 Isotope 应继续按 AI 应用软件组织目录，而不是围绕 `kernel` 命名。
新目录应优先服务可应用、可落地和多分支并行开发。

## 目标结构

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

## 初步映射

- `core/`：预留给产品主流程，负责 session、conversation、dispatch 和 response；当前不承载 agent loop。
- `features/`：真实可用功能，如聊天、任务、项目、文件、研究和自动化。
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
- 先迁移低风险模块，再迁移入口、包名和测试路径。
- 保持测试可运行，不做一次性大爆炸重命名。
- 每次迁移都更新导入路径、测试路径和文档入口。
- 历史包名不再作为活跃导入路径。
- `src/isotope/` 是 Python 包命名空间，不是重复叙事。
- 不采用 `src/core/`、`src/features/` 这类无项目命名空间的顶层包。
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

## 第一批建议

优先建立：

- `apps/cli/`
- `apps/api/`
- `src/isotope/core/`
- `src/isotope/agents/loop/`
- `src/isotope/features/chat/`
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
