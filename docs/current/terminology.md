# 术语索引

状态：`当前索引 / 按新代码继续扩展`

本索引保留英文定位词，方便搜索代码和历史文档。
中文解释用于避免 AI 和人把项目重新误读成单纯底座工程。

| 英文定位词 | 中文解释 | 主要层级 | 主要位置 |
| --- | --- | --- | --- |
| `core` | 产品主流程，串起会话、对话循环、调度和响应 | 应用核心 | `src/isotope/core/` |
| `ProductCore` | 产品主流程门面，先包住单进程运行时供上层调用 | 应用核心 | `src/isotope/core/conversation.py` |
| `RuntimeDispatch` | 运行时调度薄层，把产品级调用转发到当前运行入口 | 应用核心 | `src/isotope/core/dispatch.py` |
| `CoreConversation` | 产品级对话，当前用一个 session 串起多个 run | 应用核心 | `src/isotope/core/session.py` |
| `CoreTurn` | 对话回合，一条用户消息和一次产品级响应 | 应用核心 | `src/isotope/core/response.py` |
| `CoreConversationState` | 对话状态，包含 run 列表、回合列表和最新响应 | 应用核心 | `src/isotope/core/response.py` |
| `CoreTask` | 产品级任务，记录目标并关联一个 conversation | 应用核心 | `src/isotope/core/task.py` |
| `CoreTaskState` | 任务状态，包含目标、状态、对话和结果摘要 | 应用核心 | `src/isotope/core/task.py` |
| `CoreTurnResponse` | 产品级回合响应，只暴露低敏状态、产物引用和摘要 | 应用核心 | `src/isotope/core/response.py` |
| `TaskFlow` | 任务功能入口，把 core task 包成用户可用的任务摘要流程 | 产品功能 | `src/isotope/features/tasks/flow.py` |
| `TaskSummary` | 任务摘要，面向用户展示状态、回合数量和结果引用 | 产品功能 | `src/isotope/features/tasks/flow.py` |
| `isotope-task` | 任务命令行入口，可运行、读取和列出任务摘要 | 应用入口 | `src/isotope/features/tasks/runner.py`, `apps/cli/isotope_task.py` |
| `POST /tasks` | 任务 API 入口，创建并运行一条任务 | 接口 | `src/isotope/interfaces/http.py` |
| `GET /tasks` | 任务 API 入口，列出任务摘要 | 接口 | `src/isotope/interfaces/http.py` |
| `GET /tasks/{task_id}` | 任务 API 入口，读取任务摘要 | 接口 | `src/isotope/interfaces/http.py` |
| `task index` | 任务摘要索引，持久化低敏任务摘要，供重启后查询 | 产品功能/任务 | `src/isotope/features/tasks/flow.py` |
| `FileFlow` | 文件功能入口，把文本保存成有摘要和引用的文件记录 | 产品功能 | `src/isotope/features/files/flow.py` |
| `FileSummary` | 文件摘要，面向用户展示文件名、摘要、产物引用和 run id | 产品功能 | `src/isotope/features/files/flow.py` |
| `isotope-file` | 文件命令行入口，可创建、读取和列出文件摘要 | 应用入口 | `src/isotope/features/files/runner.py`, `apps/cli/isotope_file.py` |
| `POST /files` | 文件 API 入口，创建一个文件摘要 | 接口 | `src/isotope/interfaces/http.py` |
| `GET /files` | 文件 API 入口，列出文件摘要 | 接口 | `src/isotope/interfaces/http.py` |
| `GET /files/{file_id}` | 文件 API 入口，读取单个文件摘要 | 接口 | `src/isotope/interfaces/http.py` |
| `file index` | 文件摘要索引，持久化低敏文件摘要，供重启后查询 | 产品功能/工作区资源 | `src/isotope/features/files/flow.py` |
| `artifact-backed file summary` | 由 artifact 存储承载正文、外层只暴露摘要和引用的文件摘要 | 产品功能/工作区资源 | `src/isotope/features/files/flow.py`, `src/isotope/workspace/artifacts.py` |
| `ProjectFlow` | 项目功能入口，把任务和文件关联成用户可感知项目摘要 | 产品功能 | `src/isotope/features/projects/flow.py` |
| `ProjectSummary` | 项目摘要，面向用户展示项目名、摘要、task id 和 file id | 产品功能 | `src/isotope/features/projects/flow.py` |
| `ProjectDetail` | 项目组合摘要，展开关联 task/file 的低敏摘要信息 | 产品功能 | `src/isotope/features/projects/flow.py` |
| `ProjectWorkspaceFlow` | 项目工作区组合流，可创建或复用 project，追加 task/file 并返回项目详情和工作台视图 | 产品功能 | `src/isotope/features/projects/workspace.py` |
| `ProjectWorkspace` | 项目工作区组合结果，包含 `project_detail` 和 `workbench` 两个视图 | 产品功能 | `src/isotope/features/projects/workspace.py` |
| `isotope-project` | 项目命令行入口，可创建、读取、列出、关联、查看组合摘要、创建 workspace 和追加 workspace 内容 | 应用入口 | `src/isotope/features/projects/runner.py`, `apps/cli/isotope_project.py` |
| `POST /projects` | 项目 API 入口，创建一个项目摘要 | 接口 | `src/isotope/interfaces/http.py` |
| `POST /projects/workspace` | 项目工作区 API 入口，一次创建项目、任务、文件并返回两个视图 | 接口 | `src/isotope/interfaces/http.py` |
| `POST /projects/{project_id}/workspace` | 项目工作区 API 入口，给已有项目追加任务和文件并返回两个视图 | 接口 | `src/isotope/interfaces/http.py` |
| `GET /projects` | 项目 API 入口，列出项目摘要 | 接口 | `src/isotope/interfaces/http.py` |
| `GET /projects/{project_id}` | 项目 API 入口，读取单个项目摘要 | 接口 | `src/isotope/interfaces/http.py` |
| `GET /projects/{project_id}/detail` | 项目 API 入口，读取项目及关联 task/file 低敏摘要 | 接口 | `src/isotope/interfaces/http.py` |
| `POST /projects/{project_id}/tasks` | 项目 API 入口，把 task id 关联到项目摘要 | 接口 | `src/isotope/interfaces/http.py` |
| `POST /projects/{project_id}/files` | 项目 API 入口，把 file id 关联到项目摘要 | 接口 | `src/isotope/interfaces/http.py` |
| `project index` | 项目摘要索引，持久化低敏项目摘要，供重启后查询 | 产品功能/项目 | `src/isotope/features/projects/flow.py` |
| `SearchFlow` | 搜索功能入口，统一搜索 project/task/file 的低敏摘要，可过滤类型和数量 | 产品功能 | `src/isotope/features/search/flow.py` |
| `SearchResult` | 搜索结果，包含类型、id、标题、摘要和低敏 item | 产品功能 | `src/isotope/features/search/flow.py` |
| `isotope-search` | 搜索命令行入口，可搜索低敏摘要并使用 `--type` / `--limit` 控制结果 | 应用入口 | `src/isotope/features/search/runner.py`, `apps/cli/isotope_search.py` |
| `POST /search` | 搜索 API 入口，按 query 返回低敏摘要结果，支持 `types` 和 `limit` | 接口 | `src/isotope/interfaces/http.py` |
| `WorkbenchFlow` | 工作台功能入口，聚合 project/task/file 摘要和可选搜索结果 | 产品功能 | `src/isotope/features/workbench/flow.py` |
| `WorkbenchView` | 工作台视图，包含摘要列表、搜索结果、空状态、最近更新时间和 counts 数量 | 产品功能 | `src/isotope/features/workbench/flow.py` |
| `empty_state` | 空状态，工作台没有内容时给用户的下一步提示 | 产品功能 | `src/isotope/features/workbench/flow.py` |
| `updated_at` | 最近更新时间，当前来自项目、任务和文件摘要索引的最新修改时间 | 产品功能 | `src/isotope/features/workbench/flow.py` |
| `isotope-workbench` | 工作台命令行入口，可读取产品首页低敏汇总 | 应用入口 | `src/isotope/features/workbench/runner.py`, `apps/cli/isotope_workbench.py` |
| `GET /workbench` | 工作台 API 入口，读取无搜索条件的低敏汇总 | 接口 | `src/isotope/interfaces/http.py` |
| `POST /workbench` | 工作台 API 入口，可带 query/types/limit 读取汇总和搜索结果 | 接口 | `src/isotope/interfaces/http.py` |
| `POST /workbench/ask` | 工作台问答 API 入口，用注入的 LLM provider 回答工作台问题 | 接口/模型 | `src/isotope/interfaces/http.py`, `src/isotope/features/ask/flow.py` |
| `workbench demo` | 工作台 demo 场景，展示创建摘要、搜索和工作台汇总流程 | 应用验证 | `src/isotope/demo.py`, `tests/isotope/test_workbench_demo_scenario.py` |
| `Workbench Ask` | 工作台问答，用低敏工作台摘要回答一个自然语言问题 | 产品功能/模型 | `src/isotope/features/ask/flow.py` |
| `WorkbenchAskFlow` | 工作台问答功能入口，组装摘要上下文、调用 LLM provider 并返回答案 | 产品功能/模型 | `src/isotope/features/ask/flow.py` |
| `isotope-ask` | 工作台问答命令行入口，可用 mock 或 OpenAI-compatible provider 回答问题 | 应用入口 | `src/isotope/features/ask/runner.py`, `apps/cli/isotope_ask.py` |
| `workbench-ask demo` | 工作台问答 demo 场景，展示项目摘要进入问答上下文并产出中文答案 | 应用验证 | `src/isotope/demo.py`, `tests/isotope/test_workbench_ask_demo_scenario.py` |
| `NotificationFlow` | 通知功能入口，维护本地低敏通知摘要索引 | 产品功能/通知 | `src/isotope/features/notifications/flow.py` |
| `NotificationSummary` | 通知摘要，面向用户展示类型、标题、未读状态、时间和低敏来源引用 | 产品功能/通知 | `src/isotope/features/notifications/flow.py` |
| `isotope-notification` | 通知命令行入口，可创建、列表、筛选和标记已读通知 | 应用入口 | `src/isotope/features/notifications/runner.py` |
| `source_ref` | 低敏来源引用，用 JSON 对象说明通知来自哪个 worker、decision 或其他事件 | 产品功能/通知/状态账本 | `src/isotope/features/notifications/flow.py` |
| `notification index` | 通知摘要索引，持久化低敏通知摘要，写入时用临时文件替换 | 产品功能/通知 | `src/isotope/features/notifications/flow.py` |
| `Supervisor notification bridge` | Supervisor 通知桥，把 goal 状态、decision request/answer 和通过 integration-review 的 done worker 派生成低敏通知或 webhook；通知失败不影响原账本 | 产品功能/通知/状态账本 | `src/isotope/features/supervisor/notifications.py` |
| `Codex Supervisor` | Codex 监督器，Isotope 后续核心管理层，让 LLM 参与判断和调度，工程规则提供护栏 | 产品功能 | `src/isotope/features/supervisor/flow.py` |
| `isotope-supervisor` | Codex Supervisor 命令行入口，支持扫描、dashboard 汇总、本机 web 页面、建议面板、supervise 小闭环、定时汇报、变化触发、托管启动、恢复历史会话、接管 tmux 和发送指令 | 应用入口 | `src/isotope/features/supervisor/runner.py`, `apps/cli/isotope_supervisor.py` |
| `start-here` | Supervisor 第一次试用入口，打印启动后台、打开页面、查看状态、反馈观察点和停止后台的最短路径 | 应用入口/可用性 | `src/isotope/features/supervisor/runner.py` |
| `Codex session` | Codex 会话记录，本机通常保存在 `~/.codex/sessions` | 外部集成 | `src/isotope/features/supervisor/flow.py` |
| `managed Codex` | Supervisor 启动、恢复或接管并登记的 Codex 会话，可通过 pid、tmux session、resume 目标和日志路径追踪 | 产品功能/外部集成 | `src/isotope/features/supervisor/registry.py` |
| `recommendation` | 结构化建议，表达下一步建议动作、优先级和目标窗口，不等于自动执行 | 产品功能/控制策略 | `src/isotope/features/supervisor/flow.py` |
| `payload` | Supervisor 每轮整理出的运行状态包，通常是 Python `dict`，包含扫描结果、候选命令、LLM 动作、执行结果和上下文检索结果 | 产品功能/控制策略 | `src/isotope/features/supervisor/runner.py` |
| `active_goals` | 本轮仍活跃的目标列表，会带上最近 `last_status`、摘要和下一步，作为 LLM planner 的输入；存在时动作校验会收窄到目标相关命令 | 产品功能/模型/状态账本 | `src/isotope/features/supervisor/goal_queue.py`, `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/llm_summary.py` |
| `current batch` | 当前批次视图，把仍活跃目标和当前托管 worker 从历史 done/stale session 中分离 | 产品功能/视图/状态判断 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/web.py` |
| `status_evidence` | 状态依据，解释 Supervisor 为什么把窗口判为工作中、等待用户、停住或报错 | 产品功能/状态判断 | `src/isotope/features/supervisor/flow.py`, `src/isotope/features/supervisor/web.py` |
| `supervisor_protocol` | 状态依据来源，表示被托管 Codex 主动写了 `SUPERVISOR_STATUS` | 产品功能/状态判断 | `src/isotope/features/supervisor/flow.py` |
| `状态汇报` | web 卡片里的结构化状态区，单独展示 `SUPERVISOR_STATUS/SUMMARY/NEXT` | 产品功能/视图/状态判断 | `src/isotope/features/supervisor/web.py` |
| `attention_marker` | 状态依据来源，表示最近助手回复命中确认类文本 | 产品功能/状态判断 | `src/isotope/features/supervisor/flow.py` |
| `stale_timeout` | 状态依据来源，表示超过静默阈值没有新事件 | 产品功能/状态判断 | `src/isotope/features/supervisor/flow.py` |
| `recent_event` | 状态依据来源，表示最近仍有 Codex 事件 | 产品功能/状态判断 | `src/isotope/features/supervisor/flow.py` |
| `dashboard` | Supervisor 汇总视图，按需要看、已完成和工作中分组，供人类和后续前端使用 | 产品功能/视图 | `src/isotope/features/supervisor/runner.py` |
| `dashboard web` | Supervisor 本机页面，读取 `/dashboard.json` 并渲染三组窗口 | 产品功能/视图 | `src/isotope/features/supervisor/web.py` |
| `display_title` | Supervisor 截断后的展示标题，优先托管名、Codex 标题、首条用户消息、agent 名和短 session id | 产品功能/视图 | `src/isotope/features/supervisor/flow.py`, `src/isotope/features/supervisor/runner.py` |
| `managed_display_title` | dashboard 合并托管 lane 和真实 session 后保留的托管名 | 产品功能/视图 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/web.py` |
| `managed_terminal_excerpt` | 托管 tmux pane 的只读尾部文本摘要，用于辅助关联真实 Codex session，并在 web 托管卡片中展示最近输出 | 产品功能/视图/外部集成 | `src/isotope/features/supervisor/flow.py`, `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/web.py` |
| `managed_terminal_ready` | 托管 tmux pane 尾部已出现 Codex 输入提示符，表示窗口可接收下一条指令 | 产品功能/视图/状态判断 | `src/isotope/features/supervisor/flow.py`, `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/web.py` |
| `linked_session_id` | dashboard 合并托管 lane 时关联到的真实 Codex session id | 产品功能/视图 | `src/isotope/features/supervisor/runner.py` |
| `linked_match` | dashboard 合并托管 lane 时的绑定依据，包含匹配分数、命中来源和中文解释 | 产品功能/视图/状态判断 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/web.py` |
| `thread_name_updated` | Codex 会话标题更新事件，可解析出窗口 rename 或自带标题 | 外部集成/视图 | `src/isotope/features/supervisor/flow.py` |
| `session_index.jsonl` | Codex 会话索引文件，可在 JSONL 没有标题事件时提供 `thread_name` | 外部集成/视图 | `src/isotope/features/supervisor/flow.py` |
| `state_5.sqlite` | Codex 本地 SQLite 状态库，`threads.title` 是当前标题的重要来源 | 外部集成/视图 | `src/isotope/features/supervisor/flow.py` |
| `initial_user_title` | 首条真实用户消息截断标题，跳过 AGENTS 和环境上下文，在没有 Codex 标题时替代短 hash | 产品功能/视图 | `src/isotope/features/supervisor/flow.py` |
| `short_session_id` | session id 的短 hash，页面辅助辨认窗口 | 产品功能/视图 | `src/isotope/features/supervisor/flow.py` |
| `resume_command` | 完整恢复命令，形如 `codex resume <session_id>`，用于复制后恢复窗口 | 产品功能/视图 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/web.py` |
| `isotope-supervisor resume` | Supervisor 恢复历史会话入口，封装 `codex exec resume <session> <prompt>` 或 `--last` 并登记后台进程 | 产品功能/控制通道 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/registry.py` |
| `codex exec resume` | Codex CLI 原生命令，非交互式恢复历史会话并立刻发送新 prompt | 外部集成/控制通道 | `src/isotope/features/supervisor/registry.py` |
| `agent_nickname` | Codex session 元数据里的 agent 名称，可作为标题兜底 | 外部集成/视图 | `src/isotope/features/supervisor/flow.py` |
| `needs_attention` | dashboard 分组字段，表示需要人类或管理层优先查看的窗口 | 产品功能/视图 | `src/isotope/features/supervisor/runner.py` |
| `inspect_blocked` | 建议动作，优先查看主动汇报阻塞的窗口 | 产品功能/控制策略 | `src/isotope/features/supervisor/flow.py` |
| `inspect_bell` | 建议动作，优先查看刚响铃的托管 tmux 窗口 | 产品功能/控制策略 | `src/isotope/features/supervisor/flow.py` |
| `review_done` | 建议动作，优先审阅已完成的窗口 | 产品功能/控制策略 | `src/isotope/features/supervisor/flow.py` |
| `advise` | 建议面板命令，输出当前建议和一组命令草案，可显式执行 send 类草案 | 产品功能/控制策略 | `src/isotope/features/supervisor/runner.py` |
| `supervise` | 监控小闭环，循环执行扫描、建议、可选 LLM 摘要、显式 send 或规则自动执行 | 产品功能/控制策略 | `src/isotope/features/supervisor/runner.py` |
| `supervisor capability map` | Supervisor 能力地图，登记已实现能力和后续拆分边界 | 文档/产品功能 | `docs/current/supervisor-capability-map.md` |
| `--execute` | 显式执行参数，当前只允许 `send_status` 和 `send_continue` | 产品功能/控制策略 | `src/isotope/features/supervisor/runner.py` |
| `--auto-execute` | 规则自动执行参数，每轮最多执行一个白名单动作 | 产品功能/控制策略 | `src/isotope/features/supervisor/runner.py` |
| `command_suggestions` | 命令草案列表，给人复制执行，当前可包含 attach、汇报状态和继续推进 | 产品功能/控制策略 | `src/isotope/features/supervisor/runner.py` |
| `control_commands` | dashboard/web 使用的受控命令列表；tmux lane 可提供 attach/send 草案，process 托管通过 launch/resume 管理 | 产品功能/控制策略 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/web.py` |
| `/events` | web 事件流入口，用 SSE 推送 bell 提醒，让页面立刻刷新 dashboard | 产品功能/视图/状态判断 | `src/isotope/features/supervisor/web.py` |
| `/managed/send` | web 本机发送入口，只允许 `send_status` 和 `send_continue` 两个白名单动作 | 产品功能/控制通道 | `src/isotope/features/supervisor/web.py` |
| `/decision/answer` | web 本机拍板答案入口，只记录 `decision answer`，不向托管 Codex 直接发送任意文本 | 产品功能/通知/拍板 | `src/isotope/features/supervisor/web.py`, `src/isotope/features/supervisor/decision_requests.py` |
| `/llm-action` | web 手动模型建议入口，只展示 LLM planner 的受控动作建议，不自动发送 | 产品功能/模型/控制策略 | `src/isotope/features/supervisor/web.py` |
| `send_status` | 白名单动作，让托管 Codex 按 `SUPERVISOR_STATUS/SUMMARY/NEXT` 汇报当前状态 | 产品功能/控制通道/状态协议 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/web.py` |
| `send_continue` | 白名单动作，让托管 Codex 继续推进，并在完成或阻塞后按状态协议汇报 | 产品功能/控制通道/状态协议 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/web.py` |
| `send` | Supervisor 控制命令，向登记的 tmux Codex 会话发送一行文本，短暂等待后用 `C-m` 提交 | 产品功能/控制通道 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/registry.py` |
| `adopt` | 接管已有 tmux 会话，把它登记成 Supervisor 可监控和发送指令的 lane | 产品功能/控制通道 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/registry.py` |
| `tmux` | 本机终端复用工具，适合人类透明旁观同一个 TUI；现在是辅助控制通道，不是唯一主通道 | 外部集成/控制通道 | `src/isotope/features/supervisor/registry.py` |
| `attach` | 连接到 tmux 会话查看同一个终端窗口 | 外部集成/人类观察 | `docs/current/codex-supervisor-readonly.md` |
| `set-buffer` / `paste-buffer` | tmux 缓冲区写入和粘贴命令，用于把文本送入托管 Codex 窗口 | 外部集成/控制通道 | `src/isotope/features/supervisor/registry.py` |
| `bell` | tmux 提醒信号，可作为窗口可能结束或需要查看的弱证据 | 外部集成/状态判断 | `src/isotope/features/supervisor/flow.py`, `docs/current/supervisor-capability-map.md` |
| `managed_bell` | 托管 tmux 会话是否出现过 bell 提醒的结构化字段 | 产品功能/状态判断 | `src/isotope/features/supervisor/flow.py` |
| `alert-bell` | tmux bell hook，在窗口响铃时触发并写入 Supervisor 事件文件 | 外部集成/状态判断 | `src/isotope/features/supervisor/bell_events.py`, `src/isotope/features/supervisor/registry.py` |
| `bell_events.jsonl` | Supervisor bell 事件日志，记录哪个托管 tmux session 响铃 | 产品功能/状态判断 | `src/isotope/features/supervisor/bell_events.py` |
| `managed_bell_event_at` | 最近一次 tmux bell hook 事件时间 | 产品功能/状态判断 | `src/isotope/features/supervisor/flow.py` |
| `managed_bell_hook_installed` | 托管 tmux 会话是否已安装 Supervisor bell hook | 产品功能/状态判断 | `src/isotope/features/supervisor/flow.py`, `src/isotope/features/supervisor/web.py` |
| `repair-hooks` | Supervisor 命令，给旧托管 tmux 会话补装 bell hook | 产品功能/控制通道 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/registry.py` |
| `SUPERVISOR_STATUS` | 托管 Codex 主动汇报状态的协议锚点，只从 assistant 回复解析，如 working、done、blocked、needs_user | 产品功能/状态协议 | `src/isotope/features/supervisor/flow.py`, `src/isotope/features/supervisor/registry.py` |
| `SUPERVISOR_SUMMARY` | 托管 Codex 主动汇报的一句中文状态摘要 | 产品功能/状态协议 | `src/isotope/features/supervisor/flow.py`, `src/isotope/features/supervisor/registry.py` |
| `SUPERVISOR_NEXT` | 托管 Codex 主动建议的下一步 | 产品功能/状态协议 | `src/isotope/features/supervisor/flow.py`, `src/isotope/features/supervisor/registry.py` |
| `lane state` | 托管窗口状态账本，记录最近状态、最近催促时间和催促次数 | 产品功能/状态判断 | `src/isotope/features/supervisor/lane_state.py` |
| `--prompt-cooldown` | 催促冷却期，避免短时间重复向同一个 lane 发送状态请求或继续指令 | 产品功能/控制策略 | `src/isotope/features/supervisor/runner.py` |
| `--max-continue-count` | 继续次数预算，同一 lane 同一状态下的 `send_continue` 达到显式阈值后会被 Supervisor 拦截；默认 0 不限制 | 产品功能/控制策略 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/lane_state.py` |
| `--max-context-requests` | 上下文请求预算，同一 supervise/loop 轮次里 `request_context` 达到显式阈值后会被 Supervisor 拦截；默认 0 不限制 | 产品功能/控制策略 | `src/isotope/features/supervisor/runner.py` |
| `--max-run-minutes` | 时间预算，按托管登记的 `started_at` 判断同名 lane 是否超时，超时后拦截继续推进；默认 0 不限制 | 产品功能/控制策略 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/registry.py` |
| `worker_role` | 托管登记表字段，用来区分普通 worker、`merge_dispatch` 等内部 worker；runner 会用它阻止 merge/cleanup worker 递归启动同类调度 | 产品功能/控制策略/状态账本 | `src/isotope/features/supervisor/registry.py`, `src/isotope/features/supervisor/runner.py` |
| `continue_count` | lane state 中的继续推进计数，只统计 `send_continue`，用于限制无限续跑 | 产品功能/状态判断 | `src/isotope/features/supervisor/lane_state.py` |
| `LLM summary` | 大模型摘要，把压缩后的窗口状态和结构化建议交给模型生成中文判断 | 产品功能/模型 | `src/isotope/features/supervisor/llm_summary.py` |
| `LLM planner` | 大模型规划器，从候选状态里选择 `monitor`、send、`resume_session`、`launch_session`、`request_context` 或 `ask_user`，规则只做护栏 | 产品功能/模型/控制策略 | `src/isotope/features/supervisor/llm_summary.py`, `src/isotope/features/supervisor/runner.py` |
| `LLM action` | 大模型规划结果，会容忍 JSON 前后的说明文本，再校验成受控动作 | 产品功能/模型/控制策略 | `src/isotope/features/supervisor/llm_summary.py`, `src/isotope/features/supervisor/runner.py` |
| `rule_command_suggestion` | 旧规则生成的命令草案；开启 LLM 动作时只保留作对照，主 `command_suggestion` 跟随 LLM 选择 | 产品功能/控制策略/输出字段 | `src/isotope/features/supervisor/runner.py` |
| `--llm-action` | 命令行参数，让 LLM planner 读取最近 context 结果并选择一个受控建议动作，但不自动执行 | 产品功能/模型/控制策略 | `src/isotope/features/supervisor/runner.py` |
| `--llm-execute` | 命令行参数，执行 LLM 选择的 send、`resume_session`、`launch_session`、`request_context` 或 `ask_user`；`monitor` 只记录跳过 | 产品功能/模型/控制策略 | `src/isotope/features/supervisor/runner.py` |
| `--goal` | Supervisor 用户目标参数，让 `supervise/loop/up/daemon start` 把目标交给 LLM planner，由模型决定查上下文或启动新 worker | 产品功能/模型/控制策略 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/daemon.py` |
| `--goal-low-water` | 低水位补任务阈值；活跃目标少于该数量时，`loop` 可让 LLM 读当前文档补充目标队列，默认 0 关闭 | 产品功能/模型/控制策略 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/daemon.py`, `src/isotope/features/supervisor/goal_planner.py` |
| `--goal-replenish-limit` | 低水位补任务的单轮写入上限，避免一次补太多 active goals | 产品功能/控制策略 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/daemon.py` |
| `goal_replenishment` | `loop --json` 输出字段，记录本轮是否由低水位触发 LLM 补任务、补了多少、失败原因是什么 | 产品功能/输出字段 | `src/isotope/features/supervisor/runner.py` |
| `goal queue` | 目标队列，保存用户交给 Supervisor 的长期目标，供 daemon/loop 动态消费 | 产品功能/控制策略 | `src/isotope/features/supervisor/goal_queue.py`, `src/isotope/features/supervisor/runner.py` |
| `goals.jsonl` | Supervisor 目标队列事件文件，保存目标添加、状态回写和归档事件 | 产品功能/状态账本 | `src/isotope/features/supervisor/goal_queue.py` |
| `goal add/list/archive` | Supervisor 目标队列命令，用于添加、查看和归档活跃目标 | 产品功能/控制通道 | `src/isotope/features/supervisor/runner.py` |
| `goal status` | 目标状态回写事件，记录 worker 汇报的 `done/blocked/needs_user`，其中 `done` 会触发自动归档 | 产品功能/状态账本 | `src/isotope/features/supervisor/goal_queue.py`, `src/isotope/features/supervisor/runner.py` |
| `cleanup list/archive/delete-worktree` | Supervisor 生命周期清理命令，列出或归档 done goal、done managed worker 和 done 通知；`delete-worktree` 只删除已归档且已集成的 Supervisor worktree，不删除 Codex 历史或 git branch；loop 可自动清理本轮刚归档的 source/merge worktree | 产品功能/控制通道/状态账本 | `src/isotope/features/supervisor/runner.py` |
| `last_status` | `goal list` 和 `daemon status` 展示的目标最近状态字段，来源于 `goals.jsonl` 状态回写事件 | 产品功能/状态账本 | `src/isotope/features/supervisor/goal_queue.py`, `src/isotope/features/supervisor/runner.py` |
| `loop` | Supervisor 日常常驻入口，默认由 LLM planner 驱动受控动作 | 产品功能/控制通道 | `src/isotope/features/supervisor/runner.py` |
| `--codex-model` | `launch/resume` 参数，传给后台 Codex worker 的 `-m/--model`，用于控制 worker 模型 | 产品功能/控制通道/成本控制 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/registry.py` |
| `--codex-config` | `launch/resume` 参数，传给后台 Codex worker 的 `-c key=value`，可重复使用 | 产品功能/控制通道/成本控制 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/registry.py` |
| `--worker-profile` | worker 工作档位，`coding` 保持代码任务默认 `gpt-5.5 high`，`light` 给只读检查、状态汇报和 smoke 降低推理成本 | 产品功能/控制策略/成本控制 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/llm_summary.py` |
| `--worker-codex-model` | `supervise/loop/daemon start` 参数，控制 LLM 自动启动或恢复的 Codex worker 模型 | 产品功能/控制策略/成本控制 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/daemon.py` |
| `--worker-codex-config` | `supervise/loop/daemon start` 参数，给 LLM 自动启动或恢复的 Codex worker 传 `-c key=value` 配置 | 产品功能/控制策略/成本控制 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/daemon.py` |
| `--webhook-url` | Supervisor 外部通知端点，触发 goal 状态、decision request/answer 或通过 integration-review 的 done worker 时发送低敏 HTTP POST；失败只记录 warning | 产品功能/通知/状态账本 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/notifications.py` |
| `--webhook-secret` | Supervisor webhook 共享密钥；配置后用请求 body 生成 `X-Isotope-Signature: sha256=...` HMAC 签名，不写入 payload | 产品功能/通知/安全 | `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/notifications.py` |
| `--rule-execute` | `loop` 的备用参数，切回旧规则自动策略 | 产品功能/控制策略 | `src/isotope/features/supervisor/runner.py` |
| `monitor` | 白名单动作，表示当前没有需要发送的托管指令，只继续观察 | 产品功能/模型/控制策略 | `src/isotope/features/supervisor/llm_summary.py`, `src/isotope/features/supervisor/runner.py` |
| `resume_session` | LLM planner 可选动作，恢复一个普通 Codex 历史会话并发送受控 prompt | 产品功能/模型/控制通道 | `src/isotope/features/supervisor/llm_summary.py`, `src/isotope/features/supervisor/runner.py` |
| `launch_session` | LLM planner 可选动作，由 LLM 生成 prompt 并启动一个新的 Codex 托管会话；git 仓库任务默认进入独立 worktree | 产品功能/模型/控制通道 | `src/isotope/features/supervisor/llm_summary.py`, `src/isotope/features/supervisor/runner.py` |
| `work order` | 托管任务单，描述一次 Codex 托管执行的目标、工作区、允许范围、预算、完成条件和停等用户条件 | 产品功能/控制策略 | `src/isotope/features/supervisor/llm_summary.py`, `src/isotope/features/supervisor/registry.py` |
| `integration-review` | 集成审查命令，只读扫描 managed worker 的 branch、worker HEAD、base ref 包含关系、pytest gate、worktree 干净状态、merge conflict 风险和候选 lint/test 结果；只分组和给理由，不执行 merge、push 或删除 | 产品功能/状态判断/集成审查 | `src/isotope/features/supervisor/integration_review.py`, `src/isotope/features/supervisor/runner.py` |
| `ready_to_integrate` | `integration-review` 输出的就绪分组，表示 worker 已完成、pytest gate 通过、分支干净、base ref 尚未包含该提交、未检测到 merge conflict，并且 lint/test 已通过；这是 merge dispatch 的候选输入，不等于 runner 直接合并授权 | 产品功能/状态判断/集成审查 | `src/isotope/features/supervisor/integration_review.py`, `src/isotope/features/supervisor/replan.py`, `src/isotope/features/supervisor/merge_dispatch.py` |
| `merge-work-order` | 合并工单生成入口，把 `ready_to_integrate` 候选渲染成专门给 merge worker 的任务单，写明 diff review、cherry-pick、组合测试、push/CI watch 和停止规则 | 产品功能/控制策略/集成审查 | `src/isotope/features/supervisor/merge_work_order.py`, `src/isotope/features/supervisor/runner.py` |
| `merge dispatch` | 合并派发层，在 `loop` 中读取 `integration-review` 的 `ready_to_integrate` 候选，生成 `merge-work-order`，再复用 `launch_session` 路径启动专门 merge worker；runner 本身不直接 cherry-pick、delete branch 或改写历史 | 产品功能/控制策略/控制通道 | `src/isotope/features/supervisor/merge_dispatch.py`, `src/isotope/features/supervisor/runner.py` |
| `dynamic merge worker` | 动态合并 worker，由 merge dispatch 按当前集成候选临时启动的 Codex 托管会话；它拿到 `merge-work-order` 后负责复查、合并和验证，完成后仍按 Supervisor 状态协议汇报 | 产品功能/控制通道/开发协作 | `src/isotope/features/supervisor/merge_dispatch.py`, `src/isotope/features/supervisor/merge_work_order.py`, `src/isotope/features/supervisor/registry.py` |
| `request_context` | LLM planner 可选动作，按 query 请求项目上下文检索，不固定注入文档全文 | 产品功能/模型/上下文能力 | `src/isotope/features/supervisor/context.py`, `src/isotope/features/supervisor/llm_summary.py`, `src/isotope/features/supervisor/runner.py` |
| `ask_user` | LLM planner 可选动作，只有 Codex 明确请求拍板、既有用户指示不足且上下文缺失/过时/冲突时才允许停等用户；可绑定 session 或 `goal_id`，执行后会写入拍板列表 | 产品功能/模型/拍板 gate | `src/isotope/features/supervisor/llm_summary.py`, `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/web.py` |
| `decision_gate` | 拍板门槛，要求 Codex 明确请求拍板、LLM 确实无法判断、上下文缺失/过时/冲突，三者同时满足才允许 `ask_user` | 产品功能/模型/拍板 gate | `src/isotope/features/supervisor/llm_summary.py`, `src/isotope/features/supervisor/runner.py` |
| `decision request` | 拍板请求账本项，记录合法 `ask_user` 的问题、session 或 `goal_id`、原因和 gate 证据，供 dashboard 和 web 稳定展示；有答案用 `decision answer`，无需继续才归档 | 产品功能/通知/拍板 | `src/isotope/features/supervisor/decision_requests.py`, `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/web.py` |
| `decision answer` | 用户拍板答案事件，追加写入 JSONL，把请求移出活跃列表，并作为 `recent_decision_answers` 交给 LLM planner 继续推进 | 产品功能/通知/拍板/模型输入 | `src/isotope/features/supervisor/decision_requests.py`, `src/isotope/features/supervisor/runner.py`, `src/isotope/features/supervisor/llm_summary.py`, `src/isotope/features/supervisor/web.py` |
| `decision archive` | 拍板归档事件，追加写入 JSONL，让无需继续的拍板项从活跃列表移走，不直接删除历史 | 产品功能/通知/拍板 | `src/isotope/features/supervisor/decision_requests.py`, `src/isotope/features/supervisor/runner.py` |
| `context` | Supervisor 命令，执行项目上下文检索并记录结果供后续 LLM planner 使用；当前用 BM25 候选索引排序工作区文档和代码文件 | 产品功能/上下文能力 | `src/isotope/features/supervisor/context.py`, `src/isotope/features/supervisor/runner.py` |
| `capability inventory` | 能力盘点，按项目层级确认已有能力、主路径接入、半成品和复用缺口 | 架构审计/能力地图 | `docs/current/supervisor-architecture-migration-table.md`, `docs/current/supervisor-capability-map.md` |
| `architecture alignment audit` | 架构对齐审计，确认功能实现是否落在长期目录和正确抽象层，而不是继续堆在局部 feature | 架构审计/迁移 | `docs/current/supervisor-architecture-migration-table.md` |
| `capacity calling` | 能力调用，让 LLM 在候选能力中选择一个能力并填参数，系统再按护栏执行 | 模型/能力/智能体 | `src/isotope/llm/capacity_calling.py`, `src/isotope/agents/loop/step.py`, `src/isotope/capabilities/runner.py` |
| `capacity graph` | 能力依赖图，把多个能力调用按依赖关系、阶段和合并门槛组织成可执行计划 | 调度/能力/智能体 | `src/isotope/agents/scheduler/capacity_graph.py`, `src/isotope/agents/scheduler/dependency_graph.py` |
| `capacity plan` | Supervisor 低风险能力规划入口，默认只生成能力选择、依赖图和 launch plan，显式开关后才走 agent loop 执行 allowlist 能力 | 产品功能/模型/能力 | `src/isotope/features/supervisor/commands/capacity.py`, `isotope-supervisor capacity plan` |
| `OpenAI-compatible` | 兼容 OpenAI Chat Completions 形状的模型接口 | 模型/外部集成 | `src/isotope/features/supervisor/llm_summary.py` |
| `LLM pool TOML` | 本机模型号池配置，声明 provider、base URL、model 和 key | 产品功能/模型 | `src/isotope/features/supervisor/llm_summary.py` |
| `git worktree` | Git 工作树，同一仓库的独立开发目录，用于多分支并行；Supervisor 自动 worker 默认放在 `.worktrees/supervisor/...` | 工作区/开发协作 | `src/isotope/features/supervisor/runner.py`, `docs/current/status.md`, `AGENTS.md` |
| `assistant` | 助手，只作为产品描述或历史术语，不作为新目录叙事 | 产品描述/历史术语 | 已删除旧目录 |
| `agent loop` | 智能体循环，AI 多步规划、调用工具、读取结果并继续执行 | 应用/智能体 | `src/isotope/agents/loop/step.py`, `docs/features/` |
| `app_friction` | 应用摩擦，应用层试跑暴露的卡点或待收束问题 | 应用验证 | `src/isotope/demo.py`, `docs/features/` |
| `planner` | 规划器，把用户目标转成可执行步骤或工具选择 | 智能体 | `docs/architecture/planner-input-output-contract-v0.2.md`, `src/isotope/agents/loop/planner_adapter.py` |
| `planner adapter` | 规划器适配层，把规划输出接到现有执行循环 | 智能体 | `src/isotope/agents/loop/planner_adapter.py` |
| `tick policy` | 步进策略，决定智能体循环每轮是否继续、暂停或停止 | 智能体 | `src/isotope/agents/loop/control.py`, `docs/architecture/agent-loop-tick-policy-boundary-v0.2.md` |
| `executor` | 执行器，执行已批准的动作或工具调用 | 执行 | `src/isotope/execution/executor.py` |
| `ActionCompiler` | 动作编译器，把紧凑意图转换成可审批的动作提案 | 运行时 | `src/isotope/runtime/action_compiler.py` |
| `tool call` | 工具调用，模型请求系统执行某个能力 | 模型/工具 | `src/isotope/llm/provider.py`, `src/isotope/llm/tool_bridge.py` |
| `terminal_exec` | 终端执行能力，受控运行命令并返回产物 | 工具 | `src/isotope/platform/registry/actions.py` |
| `terminal backend` | 终端后端，历史定位词；活跃实现已作为终端执行器维护 | 工具 | `src/isotope/execution/terminal_runner.py` |
| `provider` | 模型服务适配器，连接外部模型服务 | 模型 | `src/isotope/llm/provider.py` |
| `product chat` | 产品聊天流程，让模型调用工具并返回面向用户的回答 | 产品能力 | `src/isotope/features/chat/flow.py` |
| `CLI` | 命令行入口，给人类和部署脚本直接调用 | 应用入口 | `apps/cli/`, `pyproject.toml` |
| `ASGI` | Python Web 服务通用接口，后续可由 Uvicorn 等服务托管 | 后端入口 | `src/isotope/apps/api.py` |
| `ApiApp` | ASGI 兼容后端应用边界，当前转发到进程内 HTTP facade | 后端入口 | `src/isotope/apps/api.py` |
| `query string` | URL 中 `?` 后的查询参数，当前由 ASGI 入口转成内部 JSON body | 后端入口 | `src/isotope/apps/api.py` |
| `isotope-api` | API 命令行入口，当前用于检查后端路由 | 应用入口 | `src/isotope/apps/api.py`, `apps/api/isotope_api.py` |
| `HttpApiApp` | 进程内 HTTP 风格接口，用于测试和应用边界，不监听端口 | 接口 | `src/isotope/interfaces/http.py` |
| `InProcessServer` | 进程内运行入口，串起会话、run、策略、执行和状态读取 | 运行时 | `src/isotope/runtime/in_process.py` |
| `CanonicalEvent` | 标准事件，所有状态回放的事实来源 | 平台事件 | `src/isotope/platform/events/events.py` |
| `artifact` | 产物记录，保存执行结果摘要和引用 | 平台数据 | `src/isotope/platform/schemas/artifacts.py` |
| `ArtifactStore` | 产物存储，负责保存和读取 artifact 元数据与内容 | 工作区资源 | `src/isotope/workspace/artifacts.py` |
| `ResourceRef` | 资源引用，指向产物等对象而不是直接暴露全文 | 平台数据 | `src/isotope/platform/schemas/refs.py` |
| `RetrievalService` | 检索服务，按权限读取产物摘要或内容 | RAG/检索 | `src/isotope/rag/retrieval.py` |
| `ExternalIngestionService` | 外部输入接入，把结构化原始输入保存为 artifact-only 产物 | RAG/接入 | `src/isotope/rag/ingestion.py` |
| `checkpoint` | 检查点，用于恢复运行状态 | 状态恢复 | `src/isotope/platform/state/checkpoint_store.py` |
| `event log` | 事件日志，记录系统发生过的事实 | 状态恢复 | `src/isotope/platform/state/event_store.py` |
| `projector` | 投影器，把事件日志重建成可读状态 | 状态恢复 | `src/isotope/platform/state/projector.py` |
| `RunState` | 运行状态，投影后的当前视图 | 状态恢复 | `src/isotope/platform/state/projector.py` |
| `ToolInvocation` | 工具调用协议对象，给内部工具处理器传递参数 | 平台 schema | `src/isotope/platform/schemas/tool_protocol.py` |
| `ActionTypeRegistry` | 动作类型注册表，记录工具元数据、能力要求和版本信息 | 平台注册表 | `src/isotope/platform/registry/actions.py` |
| `new_id` | 简单 ID 生成器，给测试和进程内运行生成稳定前缀 ID | 平台工具 | `src/isotope/platform/ids.py` |
| `IsotopeError` | 结构化错误，给 HTTP 和 helper 返回稳定错误码 | 平台错误 | `src/isotope/platform/errors.py` |
| `KernelError` | 旧结构化错误名，仅作为兼容别名保留 | 兼容入口 | `src/isotope/platform/errors.py` |
| `policy` | 权限策略，决定动作是否允许、暂停或拒绝 | 安全/权限 | `src/isotope/policy/` |
| `approval` | 人工确认，敏感动作执行前的暂停和恢复机制 | 权限/产品 | `src/isotope/runtime/in_process.py` |
| `capability` | 能力，产品可发现、可运行的功能单元 | 产品能力 | `src/isotope/capabilities/catalog.py` |
| `capability runner` | 能力运行器，用命令行方式搜索能力、生成计划或启动能力 | 产品能力 | `src/isotope/capabilities/runner.py`, `isotope-capability` |
| `Codex task` | Codex 任务，把外部 Codex 执行封装成可路由能力 | 工具/任务 | `src/isotope/integrations/codex/task.py`, `src/isotope/integrations/codex/cli.py` |
| `workspace` | 工作区，任务运行时读写资源的边界 | 产品/资源 | `src/isotope/workspace/` |
| `memory` | 记忆，后续用于保存和查询长期上下文 | 智能体 | `src/isotope/memory/` |
| `RAG` | 检索增强生成，先检索资料再让模型回答 | 应用能力 | `src/isotope/rag/` |
| `workflow` | 工作流，多个步骤组成的任务流程 | 应用能力 | 待新目录设计 |
| `feature` | 业务功能，如聊天、搜索、工作区、权限 | 产品能力 | 待新目录设计 |

后续整理文档时，应继续补充：

- 用户常用但文档未解释的词。
- 历史文档里反复出现、但当前方向已改变的词。
- 需要从英文保留为代码搜索锚点的类名、模块名和命令名。
