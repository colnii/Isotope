# 命名与目录审计

状态：`当前审计 / 批次二已执行`

本文只审计命名和目录，不直接要求改代码。
目标是避免 Isotope 再被旧底座叙事、临时兼容入口和不好看的模块名牵着走。

## 当前结论

目前最大问题不是 `src/isotope/` 这个包名，而是包内职责命名还带着迁移痕迹：

- `core/` 现在只保留 agent loop 兼容代理，不承载活跃实现。
- `runtime/server.py` 已变成兼容代理，活跃实现位于 `runtime/in_process.py`。
- 根目录还有大量旧兼容代理，看起来像真实模块。
- 一些文件名是历史工作流命名，不像长期产品代码。
- `features/` 还没形成任务、项目、文件、研究等用户功能层。

所以，下一步不应继续机械搬文件，而应先定一版更稳的命名规则。

## ChatGPT 设想和真实代码的错位

ChatGPT 设想的 `core/` 是产品主流程：

```text
core/
  session.py
  conversation.py
  task.py
  dispatch.py
  response.py
```

批次一执行前，真实代码里的 `core/` 是 agent loop 边界：

```text
core/
  loop_control.py
  loop_step.py
  loop_planner_adapter.py
  real_planner_contract.py
  runtime.py
```

这两个不是一回事。
如果继续把 loop 代码叫 `core`，后续真正的产品主流程会没有好位置。

## 推荐命名原则

1. 目录名表达职责，不表达宣传词。
2. `core/` 预留给产品主流程；当前不承载 agent loop。
3. `agents/` 放智能体角色和智能体循环。
4. `features/` 放用户可感知功能。
5. `capabilities/` 放可注册、可调用能力。
6. `execution/` 放命令、进程、沙箱等执行环境。
7. `integrations/` 放外部系统接入。
8. `platform/` 放事件、状态、schema、错误等共享底座。
9. 兼容代理必须薄，且文档里标明不是活跃实现。
10. 不为了好看做大爆炸重命名，每批必须可验证。
11. 同一概念只能有一个主目录，其他位置只能是 adapter 或 compatibility proxy。

## 建议目标结构

近期不要一次性建满空目录，但目标语义可以先定：

```text
src/isotope/
  core/                 # 预留给产品主流程；当前不承载 agent loop
  features/             # 用户功能：chat / tasks / projects / files / research
  agents/               # 智能体角色与 agent loop
    loop/
  capabilities/         # 能力注册、能力运行、工具与技能
    tools/
    skills/
  llm/                  # LLM / embedding / rerank provider
  rag/                  # 已有资料接入和检索能力；暂不扩张空目录
  memory/               # 长期记忆、总结、上下文
  workspace/            # 项目、文件、artifact、git 工作区
  execution/            # terminal / process / sandbox / browser
  integrations/         # Codex / MCP / GitHub / VS Code 等外部系统
  interfaces/           # 当前库内 HTTP facade；暂不扩张 SDK / CLI 层
  runtime/              # 进程内运行容器和启动边界
  platform/             # events / schemas / state / registry / errors / ids
  common/               # 少量无业务含义的通用工具
```

## 建议归位

| 当前路径 | 问题 | 建议归位 |
| --- | --- | --- |
| `core/loop_control.py` | 不是产品 core | 已迁到 `agents/loop/control.py` |
| `core/loop_step.py` | 不是产品 core | 已迁到 `agents/loop/step.py` |
| `core/loop_planner_adapter.py` | 名字过长 | 已迁到 `agents/loop/planner_adapter.py` |
| `core/real_planner_contract.py` | `real` 不像长期命名 | 已迁到 `agents/loop/planner_contract.py` |
| `core/runtime.py` | 和 `runtime/` 撞名 | 删除空壳或并入 `agents/loop/` |
| `runtime/server.py` | `server` 太泛 | 已迁到 `runtime/in_process.py` |
| `features/chat/product_chat.py` | product 前缀多余 | `features/chat/flow.py` 或 `features/chat/service.py` |
| `integrations/llm/provider.py` | LLM 不是普通外部系统集成 | `llm/provider.py` |
| `integrations/llm/tool_bridge.py` | LLM 工具桥属于模型交互层 | `llm/tool_bridge.py` |
| `execution/terminal_backend.py` | backend 泛，像临时实现 | `execution/terminal_runner.py` |
| `platform/schemas/models.py` | `models` 太泛 | `platform/schemas/domain.py` 或拆成 `actions.py` |
| `platform/errors.py` | `KernelError` 残留 | 后续评估 `CoreError` 兼容迁移 |
| 顶层 `codex_*`、`llm_*`、`capability_*` | 兼容代理太多 | 保留薄代理，活跃导入只用子目录 |

## 第一批不要动的东西

这些名字虽然不完美，但现在动它们收益不高或风险偏大：

- `platform/events/`：当前语义清楚。
- `platform/state/`：checkpoint、event store、projector 放这里合理。
- `workspace/artifacts.py`：可接受。
- `rag/ingestion.py`、`rag/retrieval.py`：可接受。
- `capabilities/catalog.py`：可接受。
- `interfaces/http.py`：当前测试和 demo 大量使用，先保留为库内 facade。
- `integrations/codex/`：外部接入语义明确。
- `assistant/` 兼容代理：暂时保留，后续统一删。

## 推荐迁移批次

### 批次一：agent loop 正名

状态：已执行。

目标：

- 新建 `src/isotope/agents/loop/`。
- 将原 `core/loop_*` 活跃实现迁入该目录。
- `core/` 暂时只留空包或兼容代理，不新增空的产品主流程文件。
- 旧路径 `isotope.core.*`、`isotope.assistant.*`、`isotope.agent_loop_*` 保持可导入。
- 同步 [import-map](./import-map.md)，记录旧路径、新路径和计划删除节点。

这是最该先做的一批，因为它直接修正 `core` 误用。

### 批次二：runtime 命名澄清

状态：已执行。

目标：

- 将 `runtime/server.py` 改成更准确的名字。
- 采用 `runtime/in_process.py`。
- 旧 `isotope.server` 和 `isotope.runtime.server` 继续保留代理。

采用 `runtime/in_process.py`，因为当前 `InProcessServer` 本来就不是真 HTTP server。

### 批次三：LLM 层拆出

目标：

- 建立 `src/isotope/llm/`。
- 把 `integrations/llm/provider.py` 和 `tool_bridge.py` 迁过去。
- `integrations/` 继续放 Codex、MCP、GitHub 等外部系统接入。

不采用 `models/llm/` 是为了避免和 Pydantic schema、数据库模型或 `platform/schemas/models.py` 混淆。

### 批次三点五：interfaces 边界收紧

目标：

- 当前 `interfaces/http.py` 先保留，因为 demo 和测试大量使用。
- `interfaces/` 只表示库内 facade，不表示真正 `apps/api/` 或 SDK。
- 不新增 `interfaces/cli.py`、`interfaces/sdk.py`，除非已有明确调用方。

### 批次四：功能层扩展

目标：

- 将 `features/chat/product_chat.py` 改成更自然的 `flow.py` 或 `service.py`。
- 需要有真实 tasks / projects / files 功能时，再建对应目录。
- 不为了目录漂亮提前建一堆空功能。

### 批次五：兼容代理清单

目标：

- 给顶层兼容代理建立清单。
- 明确哪些只是旧路径，哪些仍被外部或测试使用。
- 每个兼容代理写明新路径和计划删除节点。
- 等主线稳定后再删除一批旧代理。

## 当前推荐决策

我建议先确认这一条：

> 原 `core/loop_*` 不应长期留在 `core/`，已迁到 `agents/loop/`。

这一步改动范围可控，也改善了“目录不好看”的核心问题。

## 验收口径

每批迁移至少满足：

- 新路径是活跃导入路径。
- 旧路径仍可导入，直到明确删除。
- 相关测试通过。
- 全量测试在共享路径迁移后通过。
- `docs/current/` 同步更新。
- 不把历史文档里的旧词当成当前规则。
