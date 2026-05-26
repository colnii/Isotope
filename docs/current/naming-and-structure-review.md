# 命名与目录审计

状态：`当前审计 / 根层入口已复核`

本文只审计命名和目录，不直接要求改代码。
目标是避免 Isotope 再被旧底座叙事、临时兼容入口和不好看的模块名牵着走。

## 当前结论

目前最大问题不是 `src/isotope/` 这个包名，而是包内职责命名还带着迁移痕迹：

- `core/` 已进入产品主流程，先薄包现有单进程运行时。
- `runtime/server.py` 已删除，活跃实现位于 `runtime/in_process/` 子包。
- 包根 `demo` 已迁入 `demo/` 子包：`demo/__init__.py` 是场景入口，
  `demo/demo_format.py` 是 formatter facade，具体 plain text formatter 已按
  core / agent loop / LLM 场景拆到专门模块。
- 一些文件名是历史工作流命名，不像长期产品代码。
- `features/` 还没形成任务、项目、文件、研究等用户功能层。
- `tools/` 旧空包已删除，真实工具能力归入 `capabilities/tools/`。
- 最新目录讨论可以作为目标态蓝图，但不能把 Isotope 当前叙事
  改回 `kernel`、`AI OS` 或 `packages`。

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
2. `core/` 承载产品主流程；当前不承载 agent loop。
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
  core/                 # 产品主流程；当前薄包单进程运行时
  features/             # 用户功能：chat / tasks / projects / files / search / workbench / research
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
| `runtime/server.py` | `server` 太泛 | 已迁到 `runtime/in_process/` 子包 |
| `features/chat/product_chat.py` | product 前缀多余 | 已迁到 `features/chat/flow.py` |
| `integrations/llm/provider.py` | LLM 不是普通外部系统集成 | 已迁到 `llm/provider.py` |
| `integrations/llm/tool_bridge.py` | LLM 工具桥属于模型交互层 | 已迁到 `llm/tool_bridge.py` |
| `execution/terminal_backend.py` | backend 泛，像临时实现 | 已迁到 `execution/terminal_runner.py` |
| `platform/schemas/models.py` | `models` 太泛 | 已拆成 `actions.py`、`artifacts.py`、`memory.py`、`snapshots.py` |
| `platform/errors.py` | 旧 `KernelError` 名称容易带回内核叙事 | 已改用 `IsotopeError`，旧名仅作兼容别名 |
| 顶层 `state`、`events`、`rag`、`workspace` 旧入口 | 纯兼容代理，容易误导活跃路径 | 已删除第一批低风险代理 |
| 顶层 `runtime`、`interface`、`registry`、`execution` 旧入口 | 纯兼容代理，已有真实新路径 | 已删除第二批低风险代理 |
| 顶层 `models/errors`、LLM、chat 旧入口 | 纯兼容代理，已有真实新路径 | 已删除第三批低风险代理 |
| 顶层 terminal 与 `execution.terminal_backend` 旧入口 | 纯兼容代理，已有真实新路径 | 已删除第四批低风险代理 |
| 顶层 capability 旧入口 | 纯兼容代理，正式脚本已指向新路径 | 已删除第五批低风险代理 |
| 顶层 `codex_*` | 纯兼容代理，已有真实新路径 | 已删除第六批低风险代理 |
| agent-loop、core、assistant 旧入口 | 纯兼容代理，已有真实新路径 | 已删除第七批低风险代理 |
| `platform/schemas/models.py` 汇总入口 | `models` 太泛，已拆成具体 schema 模块 | 已删除第八批低风险代理 |
| 顶层 `tools/` 空包 | 只有 docstring，无活跃调用 | 已删除，工具能力归入 `capabilities/tools/` |
| `features/supervisor/registry.py` | 名字表达托管登记和控制通道，当前可接受 | 保留，负责 managed Codex 登记和 tmux send |

## 第一批不要动的东西

这些名字虽然不完美，但现在动它们收益不高或风险偏大：

- `platform/events/`：当前语义清楚。
- `platform/state/`：checkpoint、event store、projector 放这里合理。
- `workspace/artifacts.py`：可接受。
- `rag/ingestion.py`、`rag/retrieval.py`：可接受。
- `capabilities/catalog.py`：可接受。
- `interfaces/http.py`：当前测试和 demo 大量使用，先保留为库内 facade；
  具体 route handler 已拆进 `http_artifact_routes.py`、`http_llm_routes.py`、
  `http_product_routes.py` 和 `http_run_routes.py`。
- `integrations/codex/`：外部接入语义明确。
- `assistant/` 兼容代理：已删除。
- `tools/` 旧空包：已删除。

## 推荐迁移批次

### 批次一：agent loop 正名

状态：已执行。

目标：

- 新建 `src/isotope/agents/loop/`。
- 将原 `core/loop_*` 活跃实现迁入该目录。
- `core/` 先清空旧 agent loop 入口，不新增空的产品主流程文件。
- 旧路径 `isotope.core.*`、`isotope.assistant.*`、`isotope.agent_loop_*` 已删除。
- 同步 [import-map](./import-map.md)，记录旧路径、新路径和计划删除节点。

这是最该先做的一批，因为它直接修正 `core` 误用。

### 批次二：runtime 命名澄清

状态：已执行。

目标：

- 将 `runtime/server.py` 改成更准确的名字。
- 采用 `runtime/in_process/` 子包。
- 旧 `isotope.server` 和 `isotope.runtime.server` 已删除。

采用 `runtime/in_process/` 子包，因为当前 `InProcessServer` 本来就不是真 HTTP server。

### 批次三：LLM 层拆出

状态：已执行。

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

状态：chat flow 正名已执行，terminal runner 正名已执行。

目标：

- 将 `features/chat/product_chat.py` 改成更自然的 `flow.py`。
- 将 `execution/terminal_backend.py` 改成更自然的 `terminal_runner.py`。
- 需要有真实 tasks / projects / files 功能时，再建对应目录。
- 不为了目录漂亮提前建一堆空功能。

### 批次五：兼容代理清单

状态：第一轮已执行，兼容代理测试已建立，且前八批低风险代理已删除，见
[compat-proxy-audit](./compat-proxy-audit.md)。

目标：

- 给顶层兼容代理建立清单。
- 将普通测试导入切到新路径。
- 当前没有已确认应继续删除的旧代理。
- 明确哪些只是旧路径，哪些仍被外部或测试使用。
- 每个兼容代理写明新路径和计划删除节点。
- 后续若发现剩余旧代理，再按风险分组删除。

### 批次六：真实功能分层

状态：当前进入审计阶段。

目标：

- `apps/cli/` 继续保持薄入口，只转发到 `src/isotope/` 稳定模块。
- `core/` 已建立真实主流程薄层：会话、对话、任务、run、turn、调度和低敏响应。
- `features/tasks/` 已建立第一片用户可感知任务入口。
- 后续 `features/` 子目录仍只在出现用户可感知功能时建立。
- `capabilities/tools/` 放可被注册、授权、执行的工具能力。
- 不再新增顶层 `tools/`、`utils/` 这类容易失控的目录。

### 批次七：目标态蓝图吸收

状态：已吸收最新目录讨论。

目标：

- 第一版“大结构”作为目标态蓝图，不作为立即铺满的目录清单。
- `src/isotope/` 对应平台代码包，不再新增 `packages/`。
- 顶层 `skills/`、`agents/`、`workflows/`、`connectors/`
  未来可作为用户资产目录，但要等加载协议出现后再建。
- `observability/`、`evolution/`、`context/` 等保留为远期边界，
  当前不建空目录。

### 批次八：core 薄产品主流程

状态：已执行前三片。

目标：

- 新增 `ProductCore` 作为产品主流程门面。
- 新增 `CoreSession`、`CoreRun`、`CoreTurnResponse` 和
  `RuntimeDispatch`，先包住现有 `InProcessServer`。
- 新增 `CoreConversation`、`CoreTurn` 和 `CoreConversationState`，
  让产品层可以表达连续消息和回合状态。
- 新增 `CoreTask` 和 `CoreTaskState`，让产品层可以表达任务目标、
  状态、关联 conversation 和结果摘要。
- 对外暴露 `start_session`、`start_run`、`submit_user_message`
  以及 `start_conversation`、`submit_message`、`get_conversation`、
  `start_task`、`submit_task_message`、`get_task`。
- 响应只返回状态、产物引用、摘要和事件数量，不把全文内容默认抛到外层。
- 现有普通输入会结束 run，所以 conversation 当前允许跨多个 completed run（已结束运行）。
- `features/tasks/flow.py` 已将 core task 包成用户功能摘要。
- 暂不迁移 `runtime/in_process/` 内部实现，后续再按真实需求拆分。

### 批次九：tasks 功能薄入口

状态：已执行前四片。

目标：

- 新增 `TaskFlow` 作为任务功能入口。
- 新增 `TaskSummary` 作为用户可读任务摘要。
- 复用 `ProductCore`，不绕过 core 直接碰 runtime。
- 默认只返回任务状态、回合数量、run 列表、结果摘要和资源引用。
- 新增 `list_tasks()` 和本地低敏摘要索引。
- 新增 `isotope-task run/get/list` CLI，可从终端运行、读取和列出任务摘要。
- 新增 `POST /tasks`、`GET /tasks` 和 `GET /tasks/{task_id}`，
  可通过 HTTP facade 创建、读取和列出任务摘要。
- 暂不做完整任务管理、用户界面或独立 FastAPI 服务。

### 批次十：files 功能薄入口

状态：已执行前三片。

目标：

- 新增 `FileFlow` 作为文件功能入口。
- 新增 `FileSummary` 作为用户可读文件摘要。
- 复用 `ProductCore` 和现有 artifact 写入能力。
- 默认只返回文件名、摘要、artifact 引用和 run id。
- 新增 `list_files()` 和本地低敏摘要索引。
- 新增 `isotope-file create/get/list` CLI。
- 新增 `POST /files`、`GET /files` 和 `GET /files/{file_id}` HTTP facade。
- 暂不做完整文件管理、目录树、用户界面或独立 FastAPI 服务。

### 批次十一：projects 功能薄入口

状态：已执行前三片。

目标：

- 新增 `ProjectFlow` 作为项目功能入口。
- 新增 `ProjectSummary` 作为用户可读项目摘要。
- 新增 `ProjectDetail` 作为项目组合摘要，展开关联 task/file 的低敏信息。
- 复用 `ProductCore`，保持项目索引和现有运行根目录一致。
- 默认只返回项目名、摘要、task id 列表和 file id 列表。
- 新增本地低敏项目摘要索引。
- 新增 `isotope-project create/get/list/add-task/add-file/detail` CLI。
- 新增 `POST /projects`、`GET /projects`、`GET /projects/{project_id}`、
  `GET /projects/{project_id}/detail`、
  `POST /projects/{project_id}/tasks` 和
  `POST /projects/{project_id}/files` HTTP facade。
- 暂不做完整项目管理、成员权限、UI 或独立 FastAPI 服务。

### 批次十二：search 功能薄入口

状态：已执行前三片。

目标：

- 新增 `SearchFlow` 作为跨功能低敏摘要搜索入口。
- 新增 `SearchResult` 作为用户可读搜索结果。
- 复用 `ProjectFlow`、`TaskFlow` 和 `FileFlow` 的低敏摘要索引。
- 默认只匹配 id、标题和摘要，不读取任务消息、文件正文或 artifact 全文。
- 支持按 `project`、`task`、`file` 做类型过滤。
- 支持 `limit` 控制最多返回数量。
- 新增 `isotope-search search` CLI。
- 新增 `POST /search` HTTP facade。
- 暂不做全文检索、RAG、复杂排序、分页游标或独立 FastAPI 服务。

### 批次十三：workbench 工作台薄入口

状态：已执行前三片。

目标：

- 新增 `WorkbenchFlow` 作为产品首页/工作台汇总入口。
- 新增 `WorkbenchView` 作为用户可读工作台视图。
- 聚合 `ProjectFlow`、`TaskFlow`、`FileFlow` 的低敏摘要。
- 可选复用 `SearchFlow`，返回 `search_results`。
- 新增 `isotope-workbench show` CLI。
- 新增 `GET /workbench` 和 `POST /workbench` HTTP facade。
- 新增 `isotope-demo --scenario workbench`，展示创建摘要、搜索和工作台汇总。
- 新增 `empty_state` 和 `updated_at`，让工作台空数据和最近更新时间可展示。
- 暂不做完整 Web UI、权限分组、排序策略或独立 FastAPI 服务。

### 批次十四：project workspace 组合工作流

状态：已执行前两片。

目标：

- 新增 `ProjectWorkspaceFlow` 作为 project/task/file 的薄组合入口。
- 新增 `ProjectWorkspace`，同时返回 `project_detail` 和 `workbench`。
- 新增 `isotope-project workspace` CLI。
- 新增 `POST /projects/workspace` HTTP facade。
- 新增 `isotope-demo --scenario project-workspace`，展示组合流程。
- 新增 `isotope-project workspace-add` 和
  `POST /projects/{project_id}/workspace`，支持复用已有 project。
- 运行时启动时会推进已有 ID 计数器，避免 CLI 跨进程追加时撞号。
- 暂不做完整项目模板、成员权限、UI 或长期 workspace 资产协议。

### 批次十五：apps/api 薄后端边界

状态：已执行第一片。

目标：

- 新增 `src/isotope/apps/api.py` 作为可安装 API 应用入口。
- 新增 `apps/api/` 薄入口目录和说明。
- 新增 ASGI 兼容 `ApiApp`，把真实请求转发到 `interfaces/http.py`。
- 新增 `isotope-api routes`，用于检查当前后端路由。
- ASGI 入口已支持 query string、JSON 响应头和稳定 invalid JSON 错误。
- 暂不引入 FastAPI / Uvicorn，不监听端口，不把业务逻辑放进 `apps/`。

### 批次十六：Codex Supervisor 监控入口

状态：已执行第一片。

目标：

- 新增 `src/isotope/features/supervisor/` 作为用户可感知监督器功能。
- 新增 `CodexSupervisorFlow`，读取本机 Codex session 并生成状态摘要。
- 新增 `isotope-supervisor scan/watch/launch` CLI，输出中文报告或 JSON。
- 新增 `apps/cli/isotope_supervisor.py` 薄入口。
- 新增 `watch --changes-only`，连续监控时只在会话变化后输出。
- 新增本机托管登记，记录 Supervisor 启动的 Codex pid、cwd 和日志路径。
- 新增 `launch --backend tmux`，可创建本机 tmux session 并登记。
- 新增 `--llm-summary`，读取本机 TOML 号池中的 provider、base URL、
  model 和 key，实际 TOML 不提交。
- 当前不自动向普通终端窗口输入指令。
- 暂不接 SSH 服务器内部状态，不做远程 agent 调度。

## 当前推荐决策

我建议先确认这一条：

> 原 `core/loop_*` 不应长期留在 `core/`，已迁到 `agents/loop/`。
> 当前 `core/` 已开始承接产品主流程，但仍只是薄层，不替代 runtime。

这一步改动范围可控，也改善了“目录不好看”的核心问题。

## 验收口径

每批迁移至少满足：

- 新路径是活跃导入路径。
- 若保留旧路径，必须有明确计划；若已删除，则测试应覆盖不可导入。
- 相关测试通过。
- 全量测试在共享路径迁移后通过。
- `docs/current/` 同步更新。
- 不把历史文档里的旧词当成当前规则。
