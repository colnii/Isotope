# 应用目录迁移方案

状态：`方案收敛中 / 尽快迁移 isotope_kernel`

当前 `src/isotope_kernel/` 是历史遗留包名。
后续 Isotope 应按 AI 应用软件组织目录，而不是继续围绕 `kernel` 命名。
新目录应优先服务可应用、可落地和多分支并行开发。

## 目标结构

```text
apps/
  cli/
  api/
  web/
src/
  isotope/
    assistant/
    features/
      chat/
      project_assistant/
      file_assistant/
      research_assistant/
      capability_builder/
    agents/
    capabilities/
      tools/
      skills/
    memory/
    workspace/
    execution/
    integrations/
      mcp/
    policy/
    platform/
      schemas/
      events/
      registry/
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

- `assistant/`：产品级助手入口，负责会话、消息循环、任务循环和响应。
- `features/`：真实可用功能，如聊天、项目助手、文件助手、研究助手。
- `capabilities/`：工具、技能和能力注册，不把所有东西都塞进 `tools/`。
- `execution/`：shell、python、浏览器、桌面、沙箱等执行环境。
- `workspace/`：项目、文件、工作区快照和 git 工作树边界。
- `memory/`：记忆存储、检索、总结和共享上下文。
- `agents/`：子 agent 定义、角色和任务委派。
- `integrations/`：MCP、GitHub、浏览器、VS Code 等外部接入。
- `policy/`：权限、风险、审批和审计。
- `platform/`：事件、schema、registry、lifecycle 等底座雏形。
- `common/`：通用工具，但不能变成无边界杂物目录。

## 迁移原则

- 先固化目标骨架，再尽快迁移 `src/isotope_kernel/`。
- 骨架目录可以先建，但要对应近期迁移目标或明确负责人。
- 骨架不要求一开始都有完整实现，但不能长期无人使用、无人解释。
- 先迁移低风险模块，再迁移入口、包名和测试路径。
- 保持测试可运行，不做一次性大爆炸重命名。
- 每次迁移都更新导入路径、测试路径和文档入口。
- 历史包名可保留短期兼容层，但不作为长期方向。
- `src/isotope/` 是 Python 包命名空间，不是重复叙事。
- 不采用 `src/core/`、`src/features/` 这类无项目命名空间的顶层包。

## 已落地试点

此前迁移分支 `feature/app-terminal-exec-migration` 已 fast-forward 合入 `main`。
这只代表终端执行能力完成一片试点，不代表长期目录结构已经定稿。

第一片：

- `src/agents/tools/terminal.py`
- `src/agents/executor/terminal_backend.py`
- `tests/agents/test_terminal_tool.py`
- `tests/agents/test_terminal_backend.py`

目标：先把终端执行能力放入应用化目录。
旧 `src/isotope_kernel/` 路径暂不删除，避免一次性破坏现有入口。

下一步应把 `src/isotope/` 骨架定下来，然后开始迁移 `isotope_kernel`。

## 第一批建议

优先建立：

- `apps/cli/`
- `apps/api/`
- `src/isotope/assistant/`
- `src/isotope/features/chat/`
- `src/isotope/features/project_assistant/`
- `src/isotope/capabilities/tools/`
- `src/isotope/execution/`
- `src/isotope/workspace/`
- `src/isotope/policy/`
- `src/isotope/platform/schemas/`
- `src/isotope/platform/events/`
- `src/isotope/common/`

暂缓完整展开：

- `apps/web/`
- `features/research_assistant/`
- `features/capability_builder/`
- `integrations/github/`
- `integrations/browser/`
- `integrations/vscode/`
- 复杂多 agent 编排和自我改造机制。
