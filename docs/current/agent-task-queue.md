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
90. Codex Supervisor LLM planner 动作：`advise/supervise --llm-action`
    可让 LLM 在 `monitor`、`send_status`、`send_continue` 和
    `resume_session` 中选择受控动作，输出结构化结果但不自动执行。
91. Codex Supervisor web 模型建议：`web` 页面可手动调用 `/llm-action`，
    展示 LLM planner 动作建议，但不自动发送。
92. Codex Supervisor LLM action 无目标回退：没有可控 Supervisor 目标
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
98. Codex Supervisor web 托管透明区：托管卡片会展示最近输出、
    bell 时间和关联 session，方便确认 Supervisor 实际看到了什么。
99. Codex Supervisor 最近输出修正：终端摘要保留尾部行和换行，
    web 展示时默认滚到底部，避免卡在旧输出中段。
100. Codex Supervisor 最近输出滚动保留：用户手动上翻最近输出后，
    自动刷新会保留滚动位置，不再强行跳回底部。
101. Codex Supervisor 状态汇报高亮：托管卡片关联真实 session 后，
    会使用真实 session 的状态协议分组，并在 web 单独显示状态汇报。
102. Codex Supervisor 协议化状态请求：`send_status` 和
    `send_continue` 会要求托管 Codex 按 `SUPERVISOR_STATUS/SUMMARY/NEXT`
    三行格式汇报。
103. Codex Supervisor LLM action JSON 容错：模型建议可从带解释、
    示例或 fenced code 的输出中提取最后一个动作 JSON。
104. Codex Supervisor tmux 提交修正：`send` 写入文本后用 `C-m`
    提交，避免 Codex TUI 把请求停留在输入区。
105. Codex Supervisor 自动执行第一版：`supervise --auto-execute`
    每轮最多执行一个白名单动作，按状态协议决定询问、续跑或等待。
106. Codex Supervisor 状态协议解析边界：只从 assistant 回复中解析，
    且 `SUPERVISOR_STATUS` 必须是合法值，避免把提示模板当真实状态。
107. Codex Supervisor 托管关联修正：dashboard 关联分数为 0 时不硬连；
    带状态协议的超时 session 仍可匹配托管 tmux lane。
108. Codex Supervisor 多托管关联修正：dashboard 不再只按 cwd 过滤；
    多个托管 lane 会全局打分并一对一关联真实 Codex session，避免互相抢链。
109. Codex Supervisor `/new` 跟随修正：同一 tmux lane 开新 Codex 窗口后，
    dashboard 优先用新 banner 后的活跃终端片段匹配，不再黏住旧 session。
110. Codex Supervisor 绑定依据展示：dashboard/web 输出 `linked_match`，
    显示绑定分数、命中来源和中文解释；当前 pane 明确命中的超时 session
    也可关联。
111. Codex Supervisor 绑定抢占修正：session id 只作弱证据；
    管理窗口提到别人的 id 时，不会抢走对应托管 lane 的真实 session。
112. Codex Supervisor bell hook 修复：新增 `repair-hooks`，
    web 启动时会自动为旧托管 tmux lane 补装 `alert-bell` hook。
113. Codex Supervisor 长输出绑定修正：最近输出会保留新 Codex 窗口锚点
    和最新尾部，消息片段权重高于旧 resume id 和普通标题命中。
114. Codex Supervisor bell hook 健康显示：`scan/dashboard/web` 会输出
    `managed_bell_hook_installed`，web 托管卡片显示 `bell hook` 状态。
115. Codex Supervisor 终端可输入信号：`scan/dashboard/web` 会输出
    `managed_terminal_ready`；真实 Codex 不触发 tmux bell 时，
    Supervisor 仍可识别窗口已回到 `›` 输入态并发状态请求。
116. Codex Supervisor `/new` 绑定修正：通用状态请求和
    “不要继续旧任务”里的旧标题不再算强匹配，避免旧 session 抢走新窗口。
117. Codex Supervisor 卡片来源显示：web 卡片新增“卡片来源”，
    明确普通历史会话与托管 tmux 窗口；bell 文案改成“未收到/收到于”。
118. Codex Supervisor 指定托管 lane 执行：`advise/supervise --name <lane>`
    可把建议、显式执行和自动执行限定到指定托管窗口；名字不存在时不回退。
119. Codex Supervisor CLI 监控提醒：`dashboard/web` 默认隐藏已退出托管
    tmux lane；`watch --bell` 可在建议需要人看时输出终端 bell。
120. Codex Supervisor LLM 执行闭环：`advise/supervise --llm-execute`
    会执行 LLM 选择的 `send_status/send_continue`；`monitor` 只记录跳过，
    且与 `--execute/--auto-execute` 互斥。
121. Workbench Ask 第一片：`WorkbenchAskFlow`、`isotope-ask` 和
    `isotope-demo --scenario workbench-ask` 可用工作台低敏摘要回答一个
    自然语言问题；泛问题搜索为空时会退回使用当前 project/task/file 摘要。
122. Workbench Ask API：`POST /workbench/ask` 可通过注入的 LLM provider
    回答工作台问题；未注入 provider 时返回 `workbench_ask` 未启用。
123. Codex Supervisor 状态协议优先级：`scan --json`、summary counts
    和 dashboard plain 都优先采用合法 `SUPERVISOR_STATUS`，
    已完成窗口不再被 stale/needs_user 文本规则误标。
124. Codex Supervisor 托管自动化入口：`supervise` 会输出 automation
    状态；当前主线优先识别 process 后台托管，tmux lane 只作为旁观
    或兼容旧窗口；已退出 lane 不再参与建议和自动执行。
125. Codex Supervisor 真实闭环烟测：`launch --backend tmux` 已能启动
    真实托管 lane，`supervise --auto-execute` 可识别并解析其
    `SUPERVISOR_STATUS`；自动策略不会在 lane 仍运行且终端未 ready 时
    仅因缺少协议而提前催促。
126. Codex Supervisor 自动续跑验证：真实 lane 已完成
    `done -> send_continue -> 第二阶段状态协议` 闭环。
127. Codex Supervisor CLI 提醒：`supervise --bell` 可和
    `--auto-execute` 一起使用，只在本轮仍需人看时响；
    自动发送 `send_status/send_continue` 已处理的状态不响。
128. Codex Supervisor 多窗口自动轮转：未指定 `--name` 时，
    `supervise --auto-execute` 会扫描所有活跃托管 lane，
    优先推进可自动处理的窗口，不会被第一个仍在运行的窗口挡住。
129. Codex Supervisor 连续循环冷却修正：自动轮转会避开仍在
    `--prompt-cooldown` 冷却期内的 lane，继续寻找下一个可自动处理窗口；
    显式 `--name` 仍保留冷却跳过提示。
130. Codex Supervisor 可用入口收口：新增 `guide` 命令，按 cwd、
    lane name 和 tmux session 打印启动、接管、自动监督和观察命令。
131. Codex Supervisor 日常 loop 自动化修正：`changes-only` 只限制输出，
    报告不变时仍会执行规则自动策略，冷却结束后可继续请求状态。
132. Codex Supervisor 真实 guide/loop 验收修正：托管 tmux pane
    明确显示 `Working ... esc to interrupt` 时，自动策略不会被同目录旧
    `done` session 误导成终态完成。
133. Codex Supervisor 手动窗口接管验收：手动 tmux 内启动 Codex 后，
    `adopt -> loop -> archive` 已完成真实闭环。
134. Codex Supervisor tmux 窗口发现：`discover` 可只读列出现有 tmux
    会话，筛出疑似 Codex 窗口，并生成可复制的 `adopt` 和 `attach` 命令。
135. Codex Supervisor discover 直接接管：`discover --adopt-first` 和
    `discover --adopt-index <编号>` 可直接接管候选，自动使用建议托管名。
136. Codex Supervisor loop 自动接管：日常 `loop` 默认先发现并接管
    未登记 Codex tmux 窗口，再进入自动监督。
137. Codex Supervisor 后台守护入口：`daemon start/status/stop` 可把日常
    `loop` 放到后台运行，记录 pid（进程号）、状态文件和日志路径。
138. Codex Supervisor watchdog 检查：`daemon watchdog` 可检查后台
    `loop` 是否还活着，异常退出时按原命令重新拉起。
139. Codex Supervisor 周期 watcher：`daemon watcher start/status/stop`
    可启动 watcher（周期看门进程），定期触发 `daemon watchdog`。
140. AI-first 文档护栏：`AGENTS.md`、`docs-map`、Supervisor 当前文档和
    当前状态已明确 AI agent 功能默认 AI-first，规则和白名单只做护栏。
141. Codex Supervisor resume 执行通道：`isotope-supervisor resume`
    可用 `codex exec resume <session> <prompt>` 或 `--last` 恢复历史会话，
    并把后台进程写入托管登记表；tmux 不再是唯一可执行控制通道。
142. Codex Supervisor LLM planner 恢复会话：`--llm-action` 和
    `--llm-execute` 已允许 LLM 选择 `resume_session`，可恢复普通
    Codex 历史会话并发送受控 prompt；没有任何可控目标时才跳过 LLM。
143. Codex Supervisor LLM planner 新开会话：LLM 可选择 `launch_session`，
    自己生成发给新 Codex 的 prompt；工程层只校验 cwd 来自已知工作目录，
    然后用普通 process 托管启动。
144. Codex Supervisor loop 默认 LLM 驱动：`loop` 默认执行 LLM planner
    选择的受控动作；`--rule-execute` 才切回旧规则自动策略。
145. Codex Supervisor 上下文能力：新增 `request_context` 和 `context`
    命令，LLM 可按需检索项目资料，结果记录后供下一轮 planner 使用；
    不再把“读文档”实现成每轮固定塞全文。
146. Codex Supervisor context 检索后端：`context` 当前不是 BM25，
    而是 `rg` 优先、Python 关键词扫描兜底；实测当前仓库检索约
    0.06 秒，Python 兜底约 0.68 秒。
147. Codex Supervisor 同轮上下文闭环：`--llm-execute` 遇到
    `request_context` 时，会同轮检索上下文、再调用一次 LLM planner，
    并执行后续受控动作。
148. Codex Supervisor 拍板 gate：新增 `ask_user` 动作；只有 Codex
    明确请求拍板、LLM 无法从用户既有指示判断、并且上下文检索缺失/
    过时/冲突时，才允许停等用户。
149. Codex Supervisor 拍板可见化：`advise --llm-action` 和 web
    `/llm-action` 读取最近 context 结果；合法 `ask_user` 在 CLI 和
    页面里显式显示“等待拍板”、问题和 `context_status`。
150. Codex Supervisor 拍板通知账本：`--llm-execute` 执行合法
    `ask_user` 时写入 `supervisor/decision_requests.jsonl`；
    dashboard 和 web 读取成稳定“等待拍板列表”。
151. Codex Supervisor 拍板归档入口：新增 `decision list` 和
    `decision archive --request-id <id>`；归档通过追加事件实现，不手删账本。
152. Codex Supervisor 真实 resume 验收修复：LLM 不再把 `done` 会话
    当成 `resume_session` 候选；已完成会话的工作目录仍可用于
    `launch_session` 和 `request_context`。
153. Codex Supervisor Codex CLI 集成修复：`resume` 执行
    `codex exec -C <cwd> --skip-git-repo-check resume ...`，兼容历史会话
    cwd 是非仓库父目录的情况。
154. Codex Supervisor LLM 错误可观测性：模型池失败会显示安全错误摘要，
    模型动作非 JSON 时会显示原始返回摘要，便于定位真实接口问题。
155. Codex Supervisor LLM 工作区范围：`advise`、`supervise` 和 `loop`
    默认只把当前工作区内的会话作为 LLM/action 候选，避免误恢复其他项目
    或 `/home/lumber/Github` 这类父目录会话；`--workspace-root` 可指定范围，
    `--all-workspaces` 可显式放开。
156. Codex Supervisor resume 冷却：`resume_session` 执行后写入 lane state，
    后续短时间重复恢复同一历史会话会被 `--prompt-cooldown` 跳过。
157. Codex Supervisor loop 容错：LLM 模型池空响应、非 JSON 或误选非法目标时，
    记录为可见 `monitor`，不再让常驻 loop 直接退出。
158. Codex Supervisor process 启动修复：`launch` 默认 process 后端改用
    `codex exec -C <cwd> --skip-git-repo-check <prompt>`，避免后台无 TTY
    时交互式 Codex 直接报 `stdin is not a terminal`。
159. Codex Supervisor 上下文后重规划修复：LLM prompt 会显式列出
    `resumable_session_ids`、`completed_session_ids` 和 context history，
    避免把已完成会话当成可恢复目标，或重复检索同一个 cwd/query。
160. LLM provider reasoning-only 容错：OpenAI-compatible provider 遇到
    `finish_reason=length` 且只有 `reasoning_content`、无正文时，会重试
    一次并关闭 thinking，避免 reasoning token 吃完整个输出预算。
161. Codex Supervisor work order A 层：`launch_session` 执行时会把
    LLM 生成的目标包成 `WORK ORDER` prompt，写明 goal、cwd、
    scope、budget hint、完成条件和停等用户条件；这只是提示边界，
    不代表 A 层本身提供真正 `max_minutes`、`max_continue_count`
    或 `max_context_requests` 强制控制。
162. Codex Supervisor 继续次数预算 B 层：新增 `--max-continue-count`，
    lane state 记录 `continue_count` 和 `last_prompt_kind`；当同一 lane
    同一状态下的 `send_continue` 达到显式阈值后，Supervisor 会拦截
    后续继续推进请求，避免无限续跑；默认值 0 表示不限制，
    避免阻碍长任务。当前不覆盖 `max_minutes`。
163. Codex Supervisor 上下文请求预算 B 层：新增
    `--max-context-requests`；显式传入正数时，每个 supervise/loop
    轮次达到阈值后会拦截 `request_context`，避免陷入反复查资料。
164. Codex Supervisor 预算默认宽松：`--max-continue-count` 和
    `--max-context-requests` 默认都为 0，即不启用硬限制；
    预算只做可选护栏，不作为长期托管任务的默认阻碍。
165. Codex Supervisor 多 lane 默认宽松验收：新增 loop 回归测试，
    预置两个已有较高 `continue_count` 的托管窗口，LLM 连续选择
    `send_continue` 推进 lane-a 和 lane-b；默认预算不拦截，
    显式预算测试仍保留。
166. Codex Supervisor process 主线状态修正：loop 的 automation 状态
    会识别后台 process 托管记录，LLM prompt 也会把 process lane
    列入候选目标；tmux 只作为旁观 TUI 或兼容旧窗口，不再作为
    Supervisor 主线默认叙事。
167. Codex Supervisor process log 状态修正：真实 `launch` smoke 验收发现
    `codex exec` 已输出 `SUPERVISOR_STATUS: done`，但 scan 只看 PID
    退出，dashboard 没归入“已完成”；现已读取托管 log 尾部并解析
    状态协议，已退出但明确 `done` 的 process lane 会进入完成组。
168. Codex Supervisor LLM JSON 稳定性：真实 LLM 建议验收发现默认
    512 tokens 会把 `request_context` JSON 截断成半截对象；默认
    Supervisor LLM 输出上限已调到 2048 tokens，避免动作 JSON 被截断。
169. Codex Supervisor launch 冷却：真实 2 轮 process-first loop 验收发现
    LLM 会连续启动同名 `planner-session`；现已让 `launch_session`
    写入 lane state 并遵守 `--prompt-cooldown`，第二轮同名启动会跳过。
170. Codex Supervisor resume 成本提示：真实 `codex exec resume`
    验收确认后台恢复和状态协议解析可用，但一个 92KB session 仍消耗
    约 47K tokens；现已在 `scan` 和 LLM planner 输入里加入
    `source_size_bytes` 与 `resume_context_hint`，提示模型不要无意识恢复
    大历史。
171. Codex Supervisor worker 成本参数：真实 `launch` 小流量验收确认
    process backend 可托管真实 `codex exec` 并解析 `done`，但短任务仍因
    继承本机 `gpt-5.5 xhigh` 消耗约 31K tokens；现已给
    `launch/resume` 增加 `--codex-model/--codex-config`，并给
    `supervise/loop/daemon start` 增加
    `--worker-codex-model/--worker-codex-config`，让 LLM 自动 worker
    也能显式传模型和推理强度配置。
172. Codex Supervisor daemon 日志刷新：真实 daemon 目标验收发现
    LLM 已启动 worker，但 `daemon.log` 为空；根因是后台 Python stdout
    文件输出缓冲。现已让 `daemon start` 生成 `python -u -m ... loop`
    命令，确保常驻自动动作能及时写入日志。

## 最近完成：Codex Supervisor process-first loop 验收

完成内容：

- 用 `launch` 默认 process 后端启动真实短任务，确认 `codex exec`
  可在后台运行并输出状态协议。
- 修复 `scan` 只看 PID、不读 process log 的问题；现在可从托管 log
  解析 `SUPERVISOR_STATUS/SUMMARY/NEXT`。
- `dashboard` 已能把已退出但明确 `done` 的 process lane 放入“已完成”。
- 真实 LLM 建议在 512 tokens 下会输出半截 JSON；默认上限已调到
  2048 tokens。
- 真实 LLM + fake Codex 两轮 loop 已验证：第一轮
  `request_context -> launch_session`，第二轮同名 `launch_session`
  被 `prompt-cooldown` 拦截，不会重复开同名后台任务。

下一步：

- 做更长的混合 loop 验收，确认恢复旧会话、新开会话和上下文检索
  可以稳定共存，且 LLM 会避开高成本 resume。

## 最近完成：Codex Supervisor 真实 resume 执行验收修复

完成内容：

- 真实只读 LLM 测试发现模型会选择已完成会话作为 `resume_session`。
- 已完成/已归档会话从恢复候选里移除，避免反复唤醒旧验收窗口。
- 真实执行发现 `codex exec resume` 在非仓库父目录会被 Codex 拒绝。
- `resume` 现已带 `--skip-git-repo-check`，真实日志确认 Codex 收到状态请求并输出三行状态。
- 增加模型池失败和非 JSON 返回的可读错误摘要。
- LLM/action 候选默认按当前工作区收窄；真实只读验证中，总报告仍有 10 个窗口，
  但 LLM 候选只剩当前 Isotope 工作区 3 个会话。
- 真实 2 轮 loop 验收发现同一 session 会被连续恢复；已给
  `resume_session` 接入 `--prompt-cooldown`。
- 真实 2 轮 loop 验收还发现模型池空响应和非法目标会导致退出；
  现已降级为可见 `monitor`，loop 不再崩掉。

下一步：

- 做更长时间的 loop 验收，观察多轮 LLM 是否会合理选择 resume、launch、
  context 和 ask_user，而不是只验证单次 resume。

## 最近完成：Codex Supervisor 拍板归档入口

完成内容：

- 新增 `decision list` 查看活跃拍板项。
- 新增 `decision archive --request-id <id>` 归档已处理拍板项。
- `decision_requests.jsonl` 同时保存 request 和 archive 事件，读取活跃列表时过滤已归档项。
- web “等待拍板列表”提供可复制的归档命令。

下一步：

- 做一次真实本机 loop 验收：制造或复用一个 `ask_user` 场景，
  验证记录、展示、归档完整闭环。

## 最近完成：Codex Supervisor 拍板通知账本

完成内容：

- 新增 `decision_requests.jsonl` 账本。
- `ask_user` 真正执行时记录 `session_id`、`target_name`、问题、原因、
  `context_status` 和 gate 证据。
- `dashboard --json` 输出 `decision_requests`。
- dashboard plain 和 web 页面显示“等待拍板列表”。

## 最近完成：Codex Supervisor 拍板可见化

完成内容：

- web `/llm-action` 会把最近 `request_context` 结果交给 LLM planner。
- `advise --llm-action` 同样会读取最近 context 结果。
- 合法 `ask_user` 在 CLI 输出“等待拍板”和上下文状态。
- 页面模型建议区域增加 `ask_user` 专门渲染，不再只显示一段普通 JSON 摘要。

## 最近完成：Codex Supervisor 拍板 gate

完成内容：

- 新增 `ask_user` 受控动作。
- `ask_user` 必须带 `session_id`、`question`、
  `codex_requested_decision=true`、`instructions_exhausted=true`
  和 `context_status=missing|outdated|conflict`。
- 代码会校验目标 session 确实处于 `needs_user` 或带用户拍板语义的
  `blocked` 状态。
- 没有先做上下文检索时，`ask_user` 会被拒绝。

## 最近完成：Codex Supervisor 上下文能力

完成内容：

- 新增 `request_context` 动作。
- 新增 `context` 命令，用 query 检索工作区资料并记录结果。
- `context` 优先调用 `rg`，不可用时回退到 Python 关键词扫描。
- `loop` 下一轮会把最近上下文检索结果交给 LLM planner。
- `--llm-execute` 已支持同轮“请求上下文 -> 再决策 -> 执行后续动作”。
- 这不是固定读取 `status.md` 或 `agent-task-queue.md`；
  文档只是可被检索的资料来源。

下一步：

- 让 LLM planner 在读到上下文后能继续执行后续动作，
  形成“请求上下文 -> 判断 -> 恢复/启动/继续/问用户”的闭环。

## 最近完成：Codex Supervisor LLM planner 新开会话

完成内容：

- 新增 `launch_session` 动作。
- LLM action prompt 会携带 `available_workspaces`。
- LLM 可自己生成新 Codex 会话的 prompt，不再只能套固定状态/继续文案。
- `--llm-execute` 可把 `launch_session` 执行为普通 process 托管启动。

## 最近完成：Codex Supervisor loop LLM 默认驱动

完成内容：

- `loop` 默认改为执行 LLM planner 选择的受控动作。
- 报告无变化时，`loop` 仍会让 LLM planner 判断是否需要继续推进。
- `--rule-execute` 可显式切回旧规则自动策略。
- 规则层继续负责冷却、工作目录和动作白名单护栏。

## 最近完成：Codex Supervisor 周期 watcher

完成内容：

- 新增 `daemon watcher start/status/stop`。
- 新增 `daemon watcher run` 前台循环入口，供后台 watcher 复用。
- watcher 定期触发 `daemon watchdog`，不直接判断业务状态。
- watcher 状态写入 `~/.codex/supervisor/watcher.json`。

下一步：

- 做开机自启动或一键启动组合，让 `daemon start` 和 `watcher start`
  更接近日常无感使用。

## 最近完成：Codex Supervisor watchdog 检查

完成内容：

- 新增 `daemon watchdog`。
- 进程仍在运行时只汇报 `alive`，不重复启动。
- 进程异常退出时复用 `daemon.json` 里的原始命令重新拉起。
- 状态文件会更新到新的 pid（进程号）。

## 最近完成：Codex Supervisor 后台守护入口

完成内容：

- 新增 `daemon start/status/stop`。
- `daemon start` 会在后台启动日常 `loop`。
- 状态写到 `~/.codex/supervisor/daemon.json`。
- 日志写到 `~/.codex/supervisor/logs/daemon.log`。
- `guide` 现在优先给出后台启动命令，同时保留前台 `loop` 作为调试入口。

## 最近完成：Codex Supervisor loop 自动接管

完成内容：

- `loop` 默认启用自动发现接管，不再要求人先跑 `discover/adopt`。
- 自动接管会跳过已经登记过的 tmux session，避免重复接管或捞回归档窗口。
- 接管时读取 tmux pane 当前目录作为 cwd，减少错绑工作目录。
- `supervise --auto-adopt` 可显式开启同样能力。
- `loop --no-auto-adopt` 可只监督已登记窗口。

## 最近完成：Codex Supervisor discover 直接接管

完成内容：

- `discover` 默认仍是只读，不接管、不发送、不修改窗口。
- `--adopt-first` 会直接接管第一个疑似 Codex tmux 候选。
- `--adopt-index <编号>` 会按列表编号接管候选。
- 接管时自动使用建议托管名，不需要手填 name 或 tmux session。
- 接管成功后输出 attach、loop 和 archive 后续命令。

下一步：

- 用真实 tmux Codex 窗口跑 `discover --adopt-first -> loop`，
  验证是否已经足够日常使用；若还有摩擦，再做一键启动 loop。

## 最近完成：Codex Supervisor tmux 窗口发现

完成内容：

- 新增 `isotope-supervisor discover --cwd <repo>`。
- 默认只列出 pane 文本像 Codex 的 tmux session。
- 输出建议托管名、`adopt` 接管命令、`attach` 打开命令和最近终端片段。
- 没有 tmux server 时返回空候选，不报错。

下一步：

- 在真实多窗口使用中验证 `discover -> adopt -> loop` 是否足够顺手；
  若还要手填太多，再做自动命名或一键接管薄封装。

## 最近完成：Codex Supervisor 手动窗口接管验收

完成内容：

- 不通过 `launch`，直接手动创建 `manual-adopt-check` tmux Codex 窗口。
- 用 `adopt` 接管已有窗口，确认已安装 bell hook 并进入托管登记表。
- `loop` 在窗口运行时只监控，完成后识别 `SUPERVISOR_STATUS: done`
  和 `SUPERVISOR_NEXT: 等待 Supervisor 归档`。
- 用 `archive` 归档托管记录，并关闭测试 tmux session。

下一步：

- 把这条路径变成更省心的日常入口，例如围绕用户已有 tmux session
  自动生成接管名、归档建议和下一批真实工作任务模板。

## 最近完成：Codex Supervisor 真实 guide/loop 验收修正

完成内容：

- 按 `guide` 生成命令，启动真实 `real-use-check` 托管 Codex lane。
- `loop` 能在窗口工作时保持监控，窗口可输入时发送状态请求。
- 验收发现首轮可能被同目录旧 `done` session 误导，已修正为优先相信
  当前 tmux pane 的 `Working ... esc to interrupt` 信号。

下一步：

- 把真实验收扩展到“接管用户已手动开的 tmux Codex 窗口”，
  验证 `adopt -> loop -> archive` 是否足够顺手。

## 最近完成：Codex Supervisor 日常 loop 自动化修正

完成内容：

- 发现 `loop` 默认 `--changes-only` 时，报告无变化会跳过整轮自动策略。
- 修正后，`changes-only` 只减少输出，不再阻断规则自动推进。
- 如果托管窗口仍可输入但没回应，冷却期结束后仍会再次发送状态请求。

下一步：

- 用真实工作任务按 `guide` 启动或接管窗口，验证常驻 `loop`
  能否稳定跟进你的真实 Codex 工作窗口。

## 最近完成：Codex Supervisor 可用入口收口

完成内容：

- 新增 `isotope-supervisor guide`，只打印命令，不启动 tmux、
  不调用模型、不发送指令。
- `guide --cwd <repo> --name <lane>` 会生成推荐工作流：
  新开托管窗口、接管已有 tmux、启动自动监督循环、打开 web 或 attach。
- 支持 `--json`，便于后续前端或脚本复用同一套入口命令。

下一步：

- 用真实工作任务按 `guide` 输出的命令跑一次端到端，
  从“能监督测试窗口”推进到“能监督你的真实 Codex 工作窗口”。

## 最近完成：Codex Supervisor 连续循环冷却修正

完成内容：

- 真实连续循环发现：lane A 被自动催促后进入冷却期，
  后续轮次仍反复选择 A 并跳过，导致 lane B 没被推进。
- 修正后，未指定 `--name` 的自动轮转会跳过冷却中的候选，
  继续寻找其他可自动处理的 lane。
- 真实复测：`supervisor-loop-a` 处于 cooldown 后，
  Supervisor 成功选择 `supervisor-loop-b` 发送 `send_continue`，
  并拿到第二阶段 `SUPERVISOR_STATUS: done`。

下一步：

- 已完成；下一阶段用真实工作窗口验证 guide 工作流。

## 最近完成：Codex Supervisor 多窗口自动轮转

完成内容：

- 修正 `supervise --auto-execute` 只看第一个托管 lane 的问题。
- 未指定 `--name` 时，自动策略会在所有活跃 lane 里优先选择
  `send_status/send_continue` 这类可自动处理动作。
- 真实烟测：`supervisor-multi-a` 仍在 `sleep` 工作中时，
  Supervisor 成功选择已完成的 `supervisor-multi-b`，
  发送 `send_continue` 并拿到第二阶段 `SUPERVISOR_STATUS: done`。

下一步：

- 已完成连续循环冷却修正；下一阶段整理可直接使用的命令入口。

## 最近完成：Codex Supervisor CLI 自动监控提醒

完成内容：

- 真实验证 `supervise --auto-execute` 在 `SUPERVISOR_STATUS: done`
  后会发送 `send_continue`。
- 被托管 Codex 收到继续指令后执行第二阶段只读检查，并重新输出
  `SUPERVISOR_STATUS: done`。
- `supervise --bell` 支持和 `--auto-execute` 合用：
  需要人看时响一次，自动处理的 `send_status/send_continue` 不响。

下一步：

- 已完成单轮真实多窗口轮转；下一阶段验证连续循环体验。

## 最近完成：Codex Supervisor 真实闭环烟测

完成内容：

- 用 `launch --backend tmux` 启动 `supervisor-smoke` 真实 Codex lane。
- lane 完成只读 `git status --short --branch` 检查，并输出
  `SUPERVISOR_STATUS: done`。
- `dashboard/supervise` 能识别真实 lane、读取 tmux 尾部、关联真实
  Codex session，并解析状态协议。
- 发现并修复自动策略问题：lane 仍在运行且终端未回到可输入态时，
  不再因为缺少状态协议就发送 `send_status`。
- 测试 lane 已清理，当前没有遗留 tmux session。

下一步：

- 已完成；下一阶段转向多 lane 连续监控验收。

## 最近完成：Codex Supervisor 托管自动化入口

完成内容：

- `supervise --json` 新增 `automation` 字段，说明是否存在可控托管
  tmux lane。
- `supervise` plain 输出新增“托管自动化”区块，没有 lane 时给出
  `launch --backend tmux` 和 `adopt` 命令形状。
- 自动策略、建议和命令草案都会忽略已退出的旧托管 tmux lane。
- 本机真实烟测确认：tmux server 不存在时，不再尝试发送指令，
  而是跳过并提示 `no managed tmux lane`。

下一步：

- 用默认 process `launch` 启动真实测试 lane，验证 LLM loop 能继续管理后台 Codex。

## 最近完成：Codex Supervisor 状态协议优先级

完成内容：

- `SUPERVISOR_STATUS=done/blocked/needs_user/working` 现在会覆盖
  stale timeout 和确认类文本规则。
- `scan --json` 的 `status`、`status_label`、`reason` 和 summary counts
  与主动状态协议保持一致。
- `dashboard` plain 输出使用中文状态标签，原始协议值仍保留在“依据”里。
- 已用本机真实 Codex 历史验证：`python版本升级评估` 现在显示为已完成，
  `测试` 显示为等待用户，不再混成疑似停住。

下一步：

- 做 Supervisor 可用性入口：没有托管目标时优先提示 process `launch`，tmux 只作为旁观旧窗口入口。

## 最近完成：Workbench Ask API

完成内容：

- `create_http_app(..., workbench_ask_provider=...)` 可注入问答 provider。
- `POST /workbench/ask` 返回 answer、provider、model 和低敏 context。
- 未注入 provider 时，路由稳定返回 `501 not_enabled`。
- `workbench-ask` demo 已改为走 HTTP facade，证明 API 路径可用。

下一步：

- 把 Workbench Ask 接到页面或真实 TOML 号池配置。

## 最近完成：Codex Supervisor LLM 执行闭环

完成内容：

- `--llm-execute` 会先请求 LLM planner 动作，再执行受控动作。
- LLM 返回 `monitor` 时只记录跳过，不发送指令。
- 执行目标使用 LLM 返回的 `target_name`，复用现有 tmux send 和冷却账本。
- LLM 动作提示会携带托管窗口的终端可输入、bell 和状态协议短字段。
  后续已扩展到普通 Codex session 的 `resume_session` 候选。
- `--execute`、`--auto-execute` 和 `--llm-execute` 互斥，避免一轮叠加多套执行策略。

下一步：

- 用真实托管 `test` lane 做一轮只针对测试窗口的 `--llm-execute` 烟测。

## 最近完成：Codex Supervisor CLI 监控提醒

完成内容：

- `dashboard` 和 `/dashboard.json` 不再展示已退出的托管 tmux lane。
- `scan --json` 仍保留已退出托管记录，方便审计登记状态。
- `watch --bell` 在建议目标变化时向 stderr 写终端 bell。
- 变化指纹忽略“多少秒没有新事件”这类纯计时文案，避免按固定 interval 重复响。
- bell 不写入 stdout，避免破坏 plain 或 JSON 输出主体。

下一步：

- 用真实 `watch --changes-only --bell` 跑一段时间，确认提醒频率是否合适。

## 最近完成：Codex Supervisor 指定托管 lane 执行

完成内容：

- `advise --name <lane>` 会只生成指定托管 lane 的 attach、状态和继续草案。
- `advise --name <lane> --execute send_status` 只会向该 lane 发送状态请求。
- `supervise --name <lane> --auto-execute` 只读取并操作该 lane。
- 指定名字不存在时会报错，不会退回到第一个托管窗口。

下一步：

- 再看 web 控制动作是否也需要显式透传 `--name` 的同类保护。

## 最近完成：Codex Supervisor 卡片来源显示

完成内容：

- 每张 web 卡片新增“卡片来源”行。
- 普通 Codex 历史显示为“普通历史会话”。
- 托管窗口显示为“托管窗口 <tmux session>”，并标出身份来源短 hash。
- bell 展示从“bell 时间：无”改为“bell：未收到”，减少误解。

## 最近完成：Codex Supervisor `/new` 绑定修正

完成内容：

- 真实 `test` lane 经 `supervise --auto-execute` 自动发送状态请求后，
  能回到 `SUPERVISOR_STATUS: needs_user`。
- dashboard 重新绑定到 `测试` session，而不是旧的 `python版本升级评估`。
- 通用状态请求不参与最近消息片段匹配。
- 否定语境里的旧标题不参与正向标题匹配。

## 最近完成：Codex Supervisor 终端可输入信号

完成内容：

- 托管 tmux pane 尾部出现 Codex `›` 输入提示符时，
  `scan` 会标记 `managed_terminal_ready=true`。
- plain、JSON、dashboard、web 和 LLM 摘要输入都会携带该字段。
- web 托管卡片新增“终端状态”，区分“运行中”和“可输入”。
- `supervise --auto-execute` 遇到终端可输入时会发 `send_status`，
  弥补真实 Codex 不触发 tmux bell 的情况。

## 最近完成：Codex Supervisor bell hook 修复

完成内容：

- 新增 `isotope-supervisor repair-hooks`，按托管登记表补装 tmux bell hook。
- web 启动时会自动给已登记且仍存在的 tmux lane 补装一次 hook。
- web 托管卡片显示 `bell hook` 安装状态，区分“没响过”和“没接上”。
- 旧托管窗口无需重新 `adopt`，也能接入后续 bell 事件刷新。
- 顺手修正长输出截掉新窗口锚点的问题，`test` 现在会继续绑定
  `测试` session，而不是被旧 `python版本升级评估` 的 resume 行抢回去。

## 最近完成：Codex Supervisor 绑定抢占修正

完成内容：

- 修正管理窗口讨论 `test` 的真实 session id 时，可能抢走 `test` 绑定的问题。
- `Thread renamed` 和最近消息片段仍是强证据，session id 降为弱证据。
- 命中 `Thread renamed` 后不再重复叠加普通标题分，绑定分数更可解释。

## 最近完成：Codex Supervisor 绑定依据展示

完成内容：

- `/dashboard.json` 新增 `linked_match`，包含绑定分数、命中来源和中文解释。
- web 托管卡片新增“绑定依据”，方便判断为什么绑定到这个 session。
- 当前 tmux pane 明确命中的超时 session 也可关联，即使没有状态协议。
- 真实页面数据已验证：`test` 通过 `Thread renamed` 和最近消息片段
  关联到 `测试` session。

## 最近完成：Codex Supervisor `/new` 跟随修正

完成内容：

- 已向 `test` lane 发送 Supervisor 前端测试说明，后续不再沿用
  `python版本升级评估` 的大上下文做测试。
- 修正 `test` lane 执行 `/new` 后仍显示旧 `python版本升级评估` 的问题。
- 匹配逻辑会识别新 Codex banner 和 `Thread renamed to ...` 后的活跃片段。
- 真实页面数据已验证：`test` 当前关联 `测试` session，
  resume 为 `codex resume 019e35a2-e442-75e2-84ab-3761a685a736`。

## 最近完成：Codex Supervisor 多托管关联修正

完成内容：

- 修正 `iso_dev` 抢走 `python版本升级评估`、`test` 退回 managed resume 的问题。
- 关联候选不再只按 cwd 过滤，adopt 记录 cwd 不准时仍可匹配真实 session。
- 多个托管 lane 会全局打分后一对一分配，防止一个真实 session 被抢走。
- 真实页面数据已验证：`test` 关联 `python版本升级评估`，
  `iso_dev` 关联 `项目重新整理`。

## 最近完成：Codex Supervisor 托管关联修正

完成内容：

- 修正 `test` 托管 lane 误连旧 `Isotope loop` 的问题。
- dashboard 不再在匹配分数为 0 时强行选择同目录旧 session。
- 有 `SUPERVISOR_STATUS` 的超时 session 仍可作为托管 lane 的关联候选。
- 本地已接管 `iso_dev` 为 `项目重新整理`，`test` 当前关联为
  `python版本升级评估`。

## 最近完成：Codex Supervisor 自动执行第一版

完成内容：

- 新增 `supervise --auto-execute`，和显式 `--execute` 互斥。
- `done` 状态自动发 `send_continue`，推动托管 Codex 继续推进。
- 终端可输入、`stale` 或 bell 时自动发 `send_status`。
- 缺少状态协议但 lane 仍在运行时只监控，不提前催促。
- `blocked`、`needs_user` 和疑似报错只输出跳过原因，不硬推。
- 自动执行仍受 lane state 冷却时间限制，避免短时间重复催促。
- 修正状态协议解析边界，避免工具输出或提示模板污染自动策略。

## 最近完成：Codex Supervisor tmux 提交修正

完成内容：

- 真实 `test` lane 验证发现普通 `Enter` 可能只让输入停在草稿区。
- `send_to_managed_codex` 改为 `set-buffer + paste-buffer + 短暂等待 + C-m`。
- 协议化状态请求保持单行，避免 tmux/Codex TUI 多行输入卡住。
- 真实闭环中 `C-m` 触发后，Codex 写出了三行 `SUPERVISOR_*` 状态协议。

上一批已完成：

## Codex Supervisor 协议化状态请求与 JSON 容错

完成内容：

- `send_status` 不再只发送“请汇报当前状态”，而是要求三行状态协议。
- `send_continue` 也要求完成或阻塞后按三行状态协议汇报。
- 两类请求保持单行发送，让 tmux 提交更稳定。
- LLM action 解析不再用贪婪正则截整段文本。
- 模型输出里有多个 JSON 片段时，优先使用最后一个带 `kind` 的对象。
- 解决模型在 JSON 前后添加说明导致的格式错误。

上一批已完成：

## Codex Supervisor 状态汇报高亮

完成内容：

- 合并托管 lane 和真实 session 时，若真实 session 有
  `SUPERVISOR_STATUS`，dashboard 分组使用真实状态协议。
- `/dashboard.json` 的 `supervisor_status`、`supervisor_summary`、
  `supervisor_next` 和 `status_evidence` 也使用真实 session。
- web 卡片新增“状态汇报”区，单独显示状态、摘要和下一步。
- 控制按钮仍来自托管 lane，不会因为状态汇报而自动发送指令。

上一批已完成：

## Codex Supervisor 最近输出滚动保留

完成内容：

- web 为每个托管输出框记录稳定滚动 key。
- 用户手动上翻时记录 `scrollTop`。
- 自动刷新重建卡片时恢复上次滚动位置。
- 只有首次显示或原本贴近底部时，才自动滚到底部。

上一批已完成：

## Codex Supervisor 最近输出修正

完成内容：

- `managed_terminal_excerpt` 不再走通用标题截断。
- 终端摘要保留尾部若干行，避免丢掉结束位置。
- `tmux capture-pane` 明确截到当前底部。
- web 最近输出框渲染后默认滚到底部。

上一批已完成：

## Codex Supervisor web 托管透明区

完成内容：

- web 托管卡片新增“托管窗口”详情区。
- 详情区展示 bell 时间、关联 session 和最近输出。
- 最近输出来自只读 `tmux capture-pane` 尾部摘要。
- 没有可读输出时显示空态，不影响控制按钮。

上一批已完成：

## Codex Supervisor 托管关联增强

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

## Codex Supervisor LLM planner 动作

完成内容：

- 新增 `build_llm_action_messages(...)`，只发送压缩状态、候选命令和候选目标。
- 新增 `generate_llm_action_decision(...)`，校验模型 JSON 和受控动作。
- `advise --llm-action --json` 可输出 `llm_action`。
- `supervise --llm-action --json` 可在循环 payload 里输出 `llm_action`。
- LLM 可选择 `monitor`、`send_status`、`send_continue` 或 `resume_session`。
- 不在受控动作内、缺少目标或目标不合法时会报错。
- 当前只建议，不自动执行；执行仍走 `--execute` 或 web 按钮。

上一批已完成：

## Codex Supervisor web 受控操作

完成内容：

- `dashboard --json` 和 `/dashboard.json` 给托管 tmux 窗口输出
  `control_commands`。
- 本地页面新增复制 attach、复制状态、复制继续、请求状态和继续按钮。
- `/managed/send` 只接受 `send_status` 和 `send_continue`。
- 发送仍复用 `send_to_managed_codex` 和 tmux buffer/paste 控制通道。
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
  和 LLM planner 决策。
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
- tmux 发送使用 `set-buffer + paste-buffer` 写入原文，短暂等待后发送 `C-m`。
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
