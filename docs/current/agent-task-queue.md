# Agent 任务队列

状态：`当前入口 / 应用内分层迁移`

## 当前事实

- Isotope 是 AI 应用软件，不是单纯内核项目。
- 本地只保留 `main`，远端只保留 `origin/main`。
- 旧功能分支已完成审计、代码抽取和清理。
- 可迁移代码已进入主线，剩余分支内容只保留历史参考价值。
- `docs/` 已分成 `current/`、`architecture/`、`features/`、`reviews/`、`archive/`。
- 主包已迁移到 `src/isotope/`，后续继续做应用内分层。

## 已完成批次

1. 协作入口清理：`AGENTS.md` 已改成中文主叙述，并控制在 100 行以内。
2. 文档分层整理：`docs/` 根目录没有 Markdown 残留，入口集中到 `docs/current/`。
3. 术语索引：保留英文定位词，补中文解释和主要位置。
4. 应用目录方案：已写 [application-structure-plan](./application-structure-plan.md)。
5. 分支审计清理：结果见 [branch-cleanup](../reviews/branch-cleanup-2026-05-15.md)。
6. 文档二次清理：当前入口已刷新，不再传播旧分支暂停口径。
7. 包名迁移：`src/isotope_kernel/` 已迁到 `src/isotope/`。
8. 应用内分层第一批：平台 schema、平台事件、能力目录已迁入子目录。
9. 聊天功能入口：产品聊天入口已迁入 `src/isotope/features/chat/`。
10. 核心循环入口：`agent_loop_*` 已迁到 `src/isotope/agents/loop/`。
11. 资源层入口：workspace、artifact、RAG、memory 边界已迁入对应目录。
12. 权限与注册表入口：policy、action registry、errors 已迁入新目录。
13. 执行器入口：executor 已迁入 `src/isotope/execution/`。
14. HTTP facade 入口：`http_api.py` 已迁入 `src/isotope/interfaces/`。
15. Codex 集成：Codex task/CLI/server/live smoke 已迁入 `src/isotope/integrations/`。
16. 状态恢复入口：checkpoint store、event store、projector 已迁入 `src/isotope/platform/state/`。
17. 运行入口：活跃实现已迁入 `src/isotope/runtime/in_process.py`。
18. CLI 入口：`apps/cli/` 已建立薄入口，`pyproject.toml` 已声明正式命令。
19. 运行时工具：`action_compiler.py` 迁入 `runtime/`，`ids.py` 迁入 `platform/`，活跃终端引用改到真实实现路径。
20. 平台 schema/event：活跃代码已切到 `platform/schemas/` 与 `platform/events/`，
    事件旧根路径和 `platform.schemas.models` 汇总旧入口已删除。
21. 资源/RAG 兼容入口：`artifact_store.py`、`retrieval.py`、`ingestion.py` 已改为模块代理。
22. `assistant` 命名收束：活跃循环实现已迁入 `agents/loop/`，`assistant/` 旧包已删除。
23. demo 旧叙事清理：活跃 agent-loop demo 统一改用 `app_friction`。
24. 命名与目录审计：已写 [naming-and-structure-review](./naming-and-structure-review.md)。
25. 外部审查吸收：已加入 [chatgpt审查](./chatgpt审查.md) 和 [import-map](./import-map.md)。
26. agent loop 正名：活跃实现已迁入 `src/isotope/agents/loop/`，
    `core`、`assistant` 和顶层旧路径已删除。
27. runtime 命名澄清：活跃实现已迁入 `src/isotope/runtime/in_process.py`，
    `runtime/server.py` 和 `isotope.server` 旧代理已删除。
28. LLM 层拆出：活跃实现已迁入 `src/isotope/llm/`，
    `integrations/llm` 和顶层旧路径已删除。
29. chat flow 正名：活跃实现已迁入 `src/isotope/features/chat/flow.py`，
    `product_chat.py` 和顶层旧路径已删除。
30. terminal runner 正名：活跃实现已迁入 `src/isotope/execution/terminal_runner.py`，
    `terminal_backend.py` 和顶层旧路径已删除。
31. platform schema 拆分：`models.py` 已拆成 `actions.py`、`artifacts.py`、
    `memory.py`、`snapshots.py`，根 `isotope.models` 已删除。
32. 结构化错误正名：活跃代码改用 `IsotopeError` / `IsotopePermissionError`，
    `KernelError` / `KernelPermissionError` 仅作为兼容别名。
33. 兼容代理审计：显式测试导入已切到新路径，旧代理清单见
    [compat-proxy-audit](./compat-proxy-audit.md)。
34. 空壳 runtime 链删除：`core/runtime.py`、`agent_runtime.py`、
    `assistant/runtime.py` 已删除。
35. 包级测试导入迁移：普通测试已从 `from isotope import xxx`
    改成新路径导入；终端旧入口测试已删除。
36. 兼容代理测试：新增 `tests/isotope/test_compat_proxy_imports.py`，
    覆盖根目录、旧 agent loop、LLM、Codex、terminal 和已删除空壳入口。
37. 第一批低风险代理删除：`state`、`events`、`schema refs`、
    `workspace artifact`、`rag` 和 `tool protocol` 顶层旧路径已删除。
38. 第二批低风险代理删除：`runtime`、`interface`、`registry`、
    `execution` 和 `ids` 顶层旧路径已删除。
39. 第三批低风险代理删除：`models/errors` 根入口、LLM 旧入口、
    chat 旧入口已删除。
40. 第四批低风险代理删除：terminal 顶层旧入口和
    `execution.terminal_backend` 已删除。
41. 第五批低风险代理删除：capability 顶层旧入口已删除，
    CLI 测试改用 `python -m isotope.capabilities.runner`。
42. 第六批低风险代理删除：Codex 顶层旧入口已删除，
    活跃测试继续使用 `integrations.codex`。
43. 第七批低风险代理删除：agent-loop、core 和 assistant
    旧入口已删除，`core` 已清出给后续产品主流程。
44. 第八批低风险代理删除：`platform.schemas.models` 汇总入口已删除，
    测试直接使用 `actions`、`memory`、`snapshots` 等具体 schema 模块。
45. 根层入口复核：`src/isotope/` 根层只剩 `__init__.py`、`demo.py`
    和 `llm_live_smoke.py`，没有已确认应继续删除的旧代理。
46. 真实功能分层审计：`apps/cli/` 已确认是薄入口；`core/`
    等真实主流程出现再建文件；`tools` 旧空包已删除，工具能力归入
    `capabilities/tools/`。
47. 目标态目录蓝图吸收：第一版大结构作为长期蓝图；当前仍以
    `src/isotope/` 承担平台代码包，不新增 `packages/`、`aios`
    或 `kernel` 主叙事。
48. core 薄产品主流程：`ProductCore` 已包住现有
    `InProcessServer`，提供 session、run 和用户消息提交入口。
49. core 对话状态：`ProductCore` 已提供 conversation（对话）、
    message（消息）和 turn（回合）状态；当前 conversation 可跨多个已完成 run。
50. core 任务状态：`ProductCore` 已提供 task（任务）目标、状态、
    关联 conversation 和结果摘要。
51. tasks 功能薄入口：`features/tasks/flow.py` 已提供 `TaskFlow`
    和 `TaskSummary`，把 core task 包成用户功能摘要。
52. tasks CLI 入口：`isotope-task` 已接到 `TaskFlow`，可运行一条
    task 并输出低敏 JSON 摘要。
53. tasks API 入口：`POST /tasks` 和 `GET /tasks/{task_id}` 已接到
    `TaskFlow`，CLI 与 API 共用 core task 状态。
54. tasks 摘要索引与历史：`TaskFlow` 已提供 `list_tasks()`，并把
    `TaskSummary` 低敏摘要持久化到本地索引；`isotope-task get/list`
    和 `GET /tasks` 已接入。
55. files 功能薄入口：`features/files/flow.py` 已提供 `FileFlow`
    和 `FileSummary`，可保存文本为 artifact-backed file summary。
56. files 摘要索引：`FileFlow` 已提供 `list_files()`，并把
    `FileSummary` 低敏摘要持久化到本地索引。
57. files CLI/API 入口：`isotope-file`、`POST /files`、`GET /files`
    和 `GET /files/{file_id}` 已接到 `FileFlow`。
58. projects 功能薄入口：`features/projects/flow.py` 已提供
    `ProjectFlow` 和 `ProjectSummary`，可创建项目摘要并关联 task/file id。
59. projects CLI/API 入口：`isotope-project`、`POST /projects`、
    `GET /projects`、`GET /projects/{project_id}`、
    `POST /projects/{project_id}/tasks` 和
    `POST /projects/{project_id}/files` 已接到 `ProjectFlow`。
60. projects 组合查询入口：`ProjectDetail`、`isotope-project detail`
    和 `GET /projects/{project_id}/detail` 可返回关联 task/file 低敏摘要。
61. search 功能第一片：`SearchFlow`、`isotope-search search` 和
    `POST /search` 可统一搜索 project/task/file 低敏摘要。
62. search 可控查询：`SearchFlow.search(...)`、`isotope-search`
    和 `POST /search` 已支持类型过滤和结果数量限制。
63. workbench 功能第一片：`WorkbenchFlow`、`isotope-workbench show`、
    `GET /workbench` 和 `POST /workbench` 可返回产品首页低敏汇总。
64. workbench demo：`isotope-demo --scenario workbench --trace`
    可展示创建项目/任务/文件、搜索和工作台汇总的人类可读过程。
65. workbench 产品化小片：`WorkbenchView` 已包含 `empty_state`
    和 `updated_at`，CLI/API/demo 都可看到空状态和最近更新时间。
66. project workspace 组合工作流：`ProjectWorkspaceFlow`、
    `isotope-project workspace`、`POST /projects/workspace` 和
    `isotope-demo --scenario project-workspace --trace` 可一次创建项目、
    任务、文件并返回 project detail 与 workbench 两个视图。
67. project workspace 复用已有项目：`append_to_project(...)`、
    `isotope-project workspace-add`、`POST /projects/{project_id}/workspace`
    和 `isotope-demo --scenario project-workspace-append` 可给已有项目追加
    新 task/file，并刷新 project detail 与 workbench。
68. apps/api 薄后端边界：`ApiApp`、`create_api_app(...)`、
    `isotope-api routes` 和 `apps/api/` 已建立，当前以 ASGI 转发到
    `interfaces/http.py`，不监听端口，也不引入完整 FastAPI 服务。
69. apps/api 请求体验：ASGI 入口已支持 query string（查询参数）转 body、
    JSON 响应头、`x-isotope-api` 识别头和稳定 invalid JSON 错误。
70. Codex Supervisor 监控与托管启动：`CodexSupervisorFlow`、
    `isotope-supervisor scan/watch/launch` 和 `apps/cli/isotope_supervisor.py`
    已建立，可读取本机 `~/.codex/sessions`，输出多个 Codex 会话的
    中文状态汇报；`--llm-summary` 可通过本机 TOML 号池做智能摘要；
    `watch --changes-only` 可持续运行且只在变化时输出；`launch`
    可启动 Codex 并写入本机托管登记；`launch --backend tmux`
    可在本机 tmux 会话中启动 Codex。
71. Codex Supervisor 控制通道：`isotope-supervisor send` 可向
    Supervisor 登记的 tmux 会话发送一行文本并回车，已用真实 tmux
    会话烟测中文输入。
72. Codex Supervisor 结构化建议：`scan --json` 已输出
    `recommendation` 建议对象，LLM 摘要输入也会携带该对象。
73. Codex Supervisor 建议面板：`isotope-supervisor advise` 可只输出
    当前建议和多条命令草案，不自动执行。
74. Codex Supervisor 显式执行：`advise --execute send_status` 和
    `advise --execute send_continue` 可执行对应 send 类草案。
75. Codex Supervisor 监控小闭环：`supervise` 可循环执行扫描、建议、
    可选 LLM 摘要和显式 send。
76. Codex Supervisor 能力地图：已新增
    [supervisor-capability-map](./supervisor-capability-map.md)，登记
    现有轮子、不要重复实现的边界和后续拆分顺序。
77. Codex Supervisor 结束信号识别：`scan` 已识别托管 tmux 会话的
    bell（提醒）信号，并写入 plain、JSON、LLM 摘要输入和变化指纹。
78. Codex Supervisor 状态协议：`launch` 已注入
    `SUPERVISOR_STATUS/SUMMARY/NEXT` 汇报格式，`scan` 已能从 `.jsonl`
    解析状态协议字段。
79. Codex Supervisor 接管已有 tmux：`adopt` 可把已有 tmux session
    登记成托管 lane，后续复用 `scan/watch/send/supervise`。
80. Codex Supervisor lane state：已新增 lane state 小账本，
    记录最近状态、最近催促时间和催促次数；`--prompt-cooldown`
    可避免短时间重复发送。
81. Codex Supervisor bell hook：`launch/adopt` 会安装 tmux
    `alert-bell` hook，把 bell 事件写入 `bell_events.jsonl`；
    `scan` 会优先读取事件并突出显示。
82. Codex Supervisor 建议动作优化：`SUPERVISOR_STATUS=blocked/done/needs_user`
    和 bell 事件已接入 `recommendation`。
83. Codex Supervisor 人类汇总视图：`dashboard` 可按 `需要看`、
    `已完成` 和 `工作中` 分组输出，并保留前端可复用 JSON 字段。
84. Codex Supervisor 本地前端薄入口：`web` 可启动本机页面，
    复用 `/dashboard.json` 展示需要看、已完成和工作中三组窗口。
85. Codex Supervisor 可读标题：`scan` 已解析 Codex 的
    SQLite `threads.title`、`session_index.jsonl` 标题、匹配当前 session
    的 `thread_name_updated` 事件和 agent 元数据；`dashboard` 与 `web`
    会优先显示托管名、Codex 标题、agent 名和短 session id。
86. Codex Supervisor resume 复制：`dashboard` 已输出完整
    `resume_command`；`web` 可复制 `codex resume <session_id>`。
87. Codex Supervisor 刷新优化：`scan` 已改为最近候选读取，
    大 JSONL 只读开头和尾部；标题缺失时用首条用户消息截断兜底。
88. Codex Supervisor 状态依据：`scan`、`dashboard` 和 `web`
    已输出 `status_evidence`，说明状态标签来自状态协议、文本规则、
    超时、bell 或托管检查。
89. Codex Supervisor web 受控操作：`dashboard` 已给托管 tmux lane
    输出 `control_commands`，`web` 可复制 attach/send 命令，并通过
    `/managed/send` 执行 `send_status` 和 `send_continue`。
90. Codex Supervisor LLM 白名单动作：`advise/supervise --llm-action`
    可让 LLM 在 `monitor`、`send_status`、`send_continue` 中选择建议动作，
    输出结构化结果但不自动执行。
91. Codex Supervisor web 模型建议：`web` 页面可手动调用 `/llm-action`，
    展示 LLM 白名单动作建议，但不自动发送。
92. Codex Supervisor LLM action 无目标回退：没有可控托管 tmux lane
    时直接返回 `monitor`，不调用 LLM。
93. Codex Supervisor dashboard 托管去重：同一工作目录下的托管 lane
    和最近真实 Codex session 会合并成一个可控卡片。
94. Codex Supervisor web 控制按钮整理：复制状态和复制继续按钮使用
    不同文案，并移除重复的 `tmux attach` 展示行。
95. Codex Supervisor web 模型建议高亮：模型建议命中托管 lane 时，
    页面高亮对应 send 按钮，但不自动执行。
96. Codex Supervisor web bell 即时刷新：`/events` 会监听
    `bell_events.jsonl` 变化，并让前端立刻刷新 dashboard。
97. Codex Supervisor 托管关联增强：托管 tmux lane 会只读 pane 文本，
    优先按标题和用户消息匹配真实 Codex session。

## 最近完成：Codex Supervisor 托管关联增强

完成内容：

- `scan` 为托管 tmux lane 读取最近 pane 文本摘要。
- `/dashboard.json` 合并托管 lane 时优先用 pane 文本匹配真实 session。
- 匹配字段包含 Codex 标题、首条用户消息和最近消息。
- 同目录多个 Codex 窗口时，命中 pane 文本的 session 优先。
- 没有命中文本时，仍退回同目录最近窗口。

上一批已完成：

## Codex Supervisor web bell 即时刷新

完成内容：

- 新增 `/events` SSE（服务器推送事件）入口。
- 事件流只监听 `bell_events.jsonl` 的时间戳和大小变化。
- 收到 bell 变化后推送 `bell` 事件，前端立即刷新 `/dashboard.json`。
- 事件流带轻量心跳，浏览器断开后旧连接会退出。
- `/events` 不执行控制动作，不向托管 Codex 发送指令。

上一批已完成：

## Codex Supervisor web 模型建议高亮

完成内容：

- send 按钮新增动作类型和 lane 名标识。
- `/llm-action` 返回建议后，会高亮对应的“请求状态”或“继续”按钮。
- 页面自动刷新后会重新应用最近一次模型建议高亮。
- 高亮只是提示，不会自动调用 `/managed/send`。

上一批已完成：

## Codex Supervisor web 控制按钮整理

完成内容：

- `send_status` 的复制按钮改为“复制状态”。
- `send_continue` 的复制按钮改为“复制继续”。
- `tmux_attach` 仍显示“复制 attach”。
- 删除卡片底部重复显示的 `tmux attach` 命令文本。
- 保留“请求状态”和“继续”两个直接发送按钮。

上一批已完成：

## Codex Supervisor dashboard 托管去重

完成内容：

- `/dashboard.json` 会在视图层合并托管 lane 和真实 Codex session。
- 合并后只显示一张卡片，保留托管控制按钮。
- 卡片标题和 resume 命令优先使用真实 Codex session。
- 卡片保留 `managed_display_title`、`linked_session_id` 和
  `linked_resume_command`，方便追踪两种视角。
- 底层 `scan` 仍保留原始事实，不在扫描层删除 session。

上一批已完成：

## Codex Supervisor LLM action 无目标回退

完成内容：

- 修复无托管 tmux lane 时模型建议报 `target_name` 的体验问题。
- `generate_llm_action_decision(...)` 会先检查是否存在可控目标。
- 没有目标时直接返回 `monitor`。
- 该路径不调用 LLM，避免无意义消耗 token。
- 非法动作校验仍保留在存在托管目标的路径上。

上一批已完成：

## Codex Supervisor web 模型建议

完成内容：

- 本地页面新增“模型建议”按钮。
- 点击后才调用 `/llm-action`，页面 5 秒刷新不会调用模型。
- `/llm-action` 复用 `LLM action` 白名单校验。
- 接口只返回 `monitor`、`send_status` 或 `send_continue` 的建议。
- 接口不调用 `/managed/send`，不会自动向托管 Codex 发指令。
- 无效模型动作会返回稳定 JSON 错误。

上一批已完成：

## Codex Supervisor LLM 白名单动作

完成内容：

- 新增 `build_llm_action_messages(...)`，只发送压缩状态、候选命令和候选目标。
- 新增 `generate_llm_action_decision(...)`，校验模型 JSON 和动作白名单。
- `advise --llm-action --json` 可输出 `llm_action`。
- `supervise --llm-action --json` 可在循环 payload 里输出 `llm_action`。
- LLM 只能选择 `monitor`、`send_status` 或 `send_continue`。
- 不在白名单内、缺少目标或目标不是托管 tmux lane 时会报错。
- 当前只建议，不自动执行；执行仍走 `--execute` 或 web 按钮。

上一批已完成：

## Codex Supervisor web 受控操作

完成内容：

- `dashboard --json` 和 `/dashboard.json` 给托管 tmux 窗口输出
  `control_commands`。
- 本地页面新增复制 attach、复制状态、复制继续、请求状态和继续按钮。
- `/managed/send` 只接受 `send_status` 和 `send_continue`。
- 发送仍复用 `send_to_managed_codex` 和 tmux `send-keys`。
- 成功发送后会记录 lane state 的最近催促时间和次数。
- 页面不提供任意文本发送框。

上一批已完成：

## Codex Supervisor 状态依据

完成内容：

- 会话摘要新增 `status_evidence` 状态依据字段。
- `scan --json`、`dashboard --json` 和 `/dashboard.json` 都保留该字段。
- plain 输出会在原因后显示“依据”。
- 本地页面会在每个窗口卡片里显示判断依据。
- 主动 `SUPERVISOR_STATUS` 的依据显示为状态协议。
- 普通规则会区分确认类文本、静默超时、最近事件、空闲窗口和错误文本。
- 托管会话会区分 tmux bell、tmux 会话状态和普通进程状态。

上一批已完成：

## Codex Supervisor 可读标题

完成内容：

- `CodexSupervisorFlow` 解析 `thread_name_updated` 事件。
- 标题源包括 SQLite `threads.title` 和 `session_index.jsonl` 的 `thread_name`。
- 只接受匹配当前 session id 的 `thread_name_updated`，避免被迁移历史污染。
- 再没有标题时，使用首条真实用户消息的短标题，跳过 AGENTS 和环境上下文。
  最后才回退短 hash。
- 会话摘要新增 `thread_name`、`thread_id`、`agent_nickname` 和 `agent_role`。
- 会话摘要新增 `short_session_id`、`initial_user_title` 和 `display_title`。
- `display_title` 优先级：托管名、Codex 标题、首条用户消息、agent 名、短 session id。
- `display_title` 是截断后的展示标题，原始标题仍保留在 `thread_name`。
- `dashboard --json` 和 `/dashboard.json` 都保留这些字段。
- 本地页面标题改用 `display_title`，元信息里保留短 hash。
- `dashboard --json` 增加 `resume_command`，本地页面可复制完整 resume 命令。
- 扫描不再默认全量解析历史 JSONL；当前本机实测从约 8.5 秒降到约 0.08 秒。
- 同步 [status](./status.md)、[terminology](./terminology.md)、
  [codex-supervisor-readonly](./codex-supervisor-readonly.md) 和
  [supervisor-capability-map](./supervisor-capability-map.md)。

上一批已完成：

- 新增 `src/isotope/features/supervisor/web.py`。
- 新增 `isotope-supervisor web`。
- 默认监听 `127.0.0.1:8765`。
- `/` 返回内联 HTML/CSS/JS 页面。
- `/dashboard.json` 返回和 `dashboard --json` 同源的分组数据。
- 页面按 `需要看`、`已完成` 和 `工作中` 展示窗口。
- 有 tmux session 的条目会显示 `tmux attach` 命令。
- 当前不引入额外前端依赖，不提供远程访问和认证。
- 同步 [status](./status.md)、
  [codex-supervisor-readonly](./codex-supervisor-readonly.md) 和
  [supervisor-capability-map](./supervisor-capability-map.md)。

更早一批已完成：

- 新增 `isotope-supervisor dashboard`。
- plain 输出按 `需要看`、`已完成` 和 `工作中` 分组。
- JSON 输出包含 `counts`、`groups` 和原有 `recommendation`。
- 每个条目保留 session id、托管名、目录、分支、状态、tmux、bell、
  Supervisor 摘要和下一步字段。
- 显式 `SUPERVISOR_STATUS=done` 优先进入已完成分组。
- 阻塞、等待用户、报错、停住和 bell 进入需要看分组。
- 同步 [status](./status.md)、[terminology](./terminology.md)、
  [codex-supervisor-readonly](./codex-supervisor-readonly.md) 和
  [supervisor-capability-map](./supervisor-capability-map.md)。

再早一批已完成：

- `blocked` 状态优先建议 `inspect_blocked`。
- `needs_user` 状态优先建议 `review_user_prompt`。
- bell 事件会建议 `inspect_bell`。
- `done` 状态会建议 `review_done`。
- 推荐理由优先使用 `SUPERVISOR_SUMMARY` 或 bell 事件时间。
- 当前仍只改变建议，不自动发送新指令。
- 同步 [status](./status.md)、[terminology](./terminology.md) 和
  [supervisor-capability-map](./supervisor-capability-map.md)。

更早二批已完成：

- 新增 `features/supervisor/bell_events.py`。
- `launch --backend tmux` 和 `adopt` 会安装 tmux `alert-bell` hook。
- hook 触发时写入 `~/.codex/supervisor/bell_events.jsonl`。
- `scan` 会读取最近 bell 事件，并写入 `managed_bell_event_at`。
- plain 报告会额外显示 `bell 事件：...`。
- 真实 tmux 烟测已验证 bell 触发、事件写入和 scan 读取。
- 同步 [status](./status.md)、[terminology](./terminology.md)、
  [codex-supervisor-readonly](./codex-supervisor-readonly.md) 和
  [supervisor-capability-map](./supervisor-capability-map.md)。

更早三批已完成：

- 新增 `features/supervisor/lane_state.py`。
- 默认写入 `~/.codex/supervisor/lane_state.json`。
- `advise/supervise --execute send_status/send_continue` 发送后会记录 lane 状态。
- 冷却期内再次执行同类发送会返回 `skipped`，不再打断同一窗口。
- 默认冷却期是 300 秒，可用 `--prompt-cooldown 0` 关闭。
- plain 输出会显示“已跳过”，避免把跳过误写成已执行。
- 同步 [status](./status.md)、[terminology](./terminology.md)、
  [codex-supervisor-readonly](./codex-supervisor-readonly.md) 和
  [supervisor-capability-map](./supervisor-capability-map.md)。

更早四批已完成：

- 新增 `isotope-supervisor adopt`。
- `adopt` 会先确认 tmux session 存在，再写入托管登记表。
- 接管不会启动新 Codex，也不会改动已有 tmux 窗口内容。
- 接管后的 lane 可被 `scan/watch/send/supervise` 继续使用。
- 这让用户可以一边 attach（连接查看）同一个 tmux 窗口，
  一边让 Supervisor 监管和发送指令。
- 同步 [status](./status.md)、[terminology](./terminology.md)、
  [codex-supervisor-readonly](./codex-supervisor-readonly.md) 和
  [supervisor-capability-map](./supervisor-capability-map.md)。

更早五批已完成：

- 托管 `launch` 会把状态汇报格式追加到 Codex prompt 末尾。
- 登记表仍保存用户原始 prompt，不把协议提示当成用户需求。
- `scan` 可解析 `SUPERVISOR_STATUS`、`SUPERVISOR_SUMMARY`
  和 `SUPERVISOR_NEXT`。
- plain 报告、JSON 输出和 LLM 摘要输入都会携带状态协议字段。
- `watch --changes-only` 的变化指纹包含状态协议字段。
- 当前协议只增强可观察性，不直接触发自动发送。
- 同步 [status](./status.md)、[terminology](./terminology.md)、
  [codex-supervisor-readonly](./codex-supervisor-readonly.md) 和
  [supervisor-capability-map](./supervisor-capability-map.md)。

更早六批已完成：

- `CodexSessionSummary` 新增 `managed_bell` 字段。
- 托管 tmux 会话运行时会读取 `#{window_bell_flag}`。
- plain 报告会显示 `bell=响过` 或 `bell=无`。
- JSON 输出和 LLM 摘要输入会携带 `managed_bell`。
- `watch --changes-only` 的变化指纹包含 bell 状态。
- 当前 bell 只作为弱信号，不直接改变 status，也不自动发送指令。
- 同步 [status](./status.md)、[terminology](./terminology.md)、
  [codex-supervisor-readonly](./codex-supervisor-readonly.md) 和
  [supervisor-capability-map](./supervisor-capability-map.md)。

更早七批已完成：

- 新增 [supervisor-capability-map](./supervisor-capability-map.md)。
- 登记 `scan/watch/advise/supervise`、托管登记、tmux 控制、
  状态判断、显式执行、LLM 摘要和未来协议层。
- 写清当前不要重复实现的新 CLI、tmux 发送器、LLM 号池和状态分类系统。
- 明确后续顺序：先做 tmux bell 信号，再做状态协议、lane state
  和 LLM 白名单决策。
- 同步 [status](./status.md)、[docs-map](./docs-map.md)、
  [terminology](./terminology.md) 和
  [codex-supervisor-readonly](./codex-supervisor-readonly.md)。

更早八批已完成：

- `supervise` 复用 `watch` 的 `--interval`、`--iterations`
  和 `--changes-only`。
- `supervise --llm-summary` 每轮会调用 LLM 生成中文摘要。
- `supervise --execute send_status` 和 `send_continue` 会复用现有
  send 通道执行白名单动作。
- `supervise --json` 输出 report、recommendation、command_suggestions、
  llm_summary 和 executed。
- 当前阶段执行仍走显式白名单。
- 同步 [status](./status.md)、[terminology](./terminology.md) 和
  [codex-supervisor-readonly](./codex-supervisor-readonly.md)。

更早九批已完成：

- `advise --execute send_status` 会向托管 tmux lane 发送“请汇报当前状态”。
- `advise --execute send_continue` 会向托管 tmux lane 发送继续推进指令。
- `--execute` 只支持 `send_status` 和 `send_continue`。
- `tmux_attach` 和 `watch_changes` 仍只作为命令草案，不会被执行。
- 执行仍复用 `send_to_managed_codex`，不解析 shell 字符串。
- `advise` 复用 `scan` 的状态判断，只输出当前建议。
- `advise --json` 输出 `recommendation`、兼容字段
  `command_suggestion` 和多命令字段 `command_suggestions`。
- 当前 `monitor` 会给出继续监控变化的命令草案。
- 能定位到托管 tmux 目标时，会给出 `tmux attach`、
  汇报状态和继续推进三类草案。
- `advise` 不执行命令，也不自动调用 `send`。
- `scan --json` 新增 `recommendation` 对象，包含 action、priority、
  target_session_id、target_name、reason 和 send_text。
- 当前建议动作包括 `review_user_prompt`、`inspect_error`、
  `inspect_stale` 和 `monitor`。
- plain 文本继续显示原中文建议，保持人类阅读体验。
- `--llm-summary` 的压缩上下文会带上结构化建议，不发送完整 session 文件。
- 当前不会自动调用 `send`，只是为后续半自动管理提供稳定字段。
- `send --name <lane> --text <text>` 可给托管 tmux Codex 发送一行文本。
- `send` 只使用 Supervisor 登记表里的最新同名记录，不接管普通终端窗口。
- 非 tmux 托管记录会返回错误，避免对无 stdin 控制通道的进程误发。
- tmux 发送使用 `send-keys -l` 写入原文，再发送 `Enter`。
- 新增 `features/supervisor`，按产品功能而不是底座模块组织。
- 可读取本机 Codex session（会话记录）并按最近事件排序。
- 可识别 `工作中`、`等待用户`、`疑似停住`、`疑似报错` 和 `空闲`。
- `watch --interval` 可定时汇报，`--changes-only` 可只在会话变化时输出。
- `launch` 可启动 Codex 进程，登记 name、pid、backend、cwd、prompt、日志路径。
- `launch --backend tmux` 可创建本机 tmux session 并登记 session 名。
- `--llm-summary` 从本机 TOML 号池读取 provider、base URL、model 和 key。
- 同步 [application-structure-plan](./application-structure-plan.md)、
  [terminology](./terminology.md)、[status](./status.md) 和
  [codex-supervisor-readonly](./codex-supervisor-readonly.md)。

验收：

- `tests/isotope/test_codex_supervisor_readonly.py` 需要通过。
- 共享路径改动后需要跑全量测试。
- `AGENTS.md` 仍需保持 100 行以内。

## 下一批次：Codex Supervisor 页面受控操作

目标：

- 在本地页面显示可执行或可复制的受控操作。
- 先支持 attach、汇报状态和继续推进三类动作。
- 执行仍走已有 `send` 白名单和 cooldown。
- 保持页面透明展示，不做隐藏式自动催促。

初始参考：

- `apps/cli/`：命令行入口，当前包含 demo、capability、LLM smoke 和 task。
- `apps/api/`：后端入口；当前薄 ASGI 入口在 `src/isotope/apps/api.py`，
  真实路由仍复用 `interfaces/http.py`。
- `src/isotope/core/`：产品主流程；当前薄包 `InProcessServer`，
  已有 conversation、turn、task 和 response 状态。
- `src/isotope/agents/loop/`：agent loop 活跃实现目录。
- `src/isotope/assistant/`：旧路径包已删除，不再扩张新实现。
- `src/isotope/features/`：聊天、任务、项目、文件、研究等可用功能；
  当前已有 `chat/`、`tasks/`、`files/`、`projects/`、`search/`
  和 `workbench/`。
- `src/isotope/capabilities/`：工具、技能、能力注册。
- `src/isotope/execution/`：shell、python、浏览器、沙箱执行。
- `src/isotope/runtime/`：进程内运行入口。
- `src/isotope/workspace/`：文件、项目、git 工作区。
- `src/isotope/rag/`：接入、检索、索引。
- `src/isotope/llm/`：模型服务层，优先于 `models/llm/`。
- `src/isotope/memory/`：记忆、总结、上下文。
- `src/isotope/policy/`：权限、审批、风险。
- `src/isotope/platform/`：事件、schema、registry、state、lifecycle。
- `src/isotope/interfaces/`：当前只作为库内 HTTP facade，不扩张成 CLI / SDK。

## 验证命令

文档批次至少运行：

```bash
git diff --check
wc -l AGENTS.md
find docs -maxdepth 1 -type f -name '*.md' -print
```

代码未改时，不必运行完整测试。
代码迁移批次需运行相关测试；共享路径迁移后跑全量测试。
