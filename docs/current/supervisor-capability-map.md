# Codex Supervisor 能力地图

状态：`当前能力登记 / 防止重复造轮子`

## 为什么要有这张图

Codex Supervisor 已经不只是一个小命令。
它是 Isotope 后续的核心管理层：LLM 参与判断和调度，
规则、事件、冷却、tmux 和白名单执行提供工程护栏。

本文件用于登记当前能力和后续拆分方向。
新增 Supervisor 能力时，应先看这里，避免重复造一套相似实现。

## 当前分层

| 层级 | 当前能力 | 主要位置 | 说明 |
| --- | --- | --- | --- |
| 用户功能层 | `scan`、`dashboard`、`guide`、`web`、`watch`、`advise`、`supervise` | `features/supervisor/runner.py` | 面向人类使用的命令入口 |
| 托管控制层 | `launch`、`adopt`、`send`、托管登记 | `features/supervisor/registry.py` | 管理 Supervisor 登记的 Codex |
| Codex 集成层 | 读取 Codex session（会话记录）、索引标题和 agent 元数据 | `features/supervisor/flow.py` | 当前读取本机 `.jsonl`、`session_index.jsonl` 和 SQLite |
| 扫描优化层 | 最近候选、首尾读取和标题兜底 | `features/supervisor/flow.py` | 避免每次页面刷新全量读历史 |
| tmux 集成层 | tmux 启动、buffer/paste 发送和 bell hook | `bell_events.py`、`flow.py`、`registry.py` | 只控制登记过的 tmux 会话 |
| 状态判断层 | 工作中、等待用户、疑似停住、疑似报错 | `features/supervisor/flow.py` | 规则判断，不等于模型判断 |
| 状态依据层 | `status_evidence` 说明每个状态标签的来源 | `features/supervisor/flow.py` | 避免只给结论、不说明证据 |
| 建议执行层 | `recommendation`、`command_suggestions`、`--execute` | `flow.py`、`runner.py` | 只允许白名单动作 |
| 模型管理层 | `LLM summary`、`LLM action` 和 TOML 号池 | `llm_summary.py` | 摘要和白名单动作建议 |
| 状态协议层 | `SUPERVISOR_STATUS` 等状态协议 | `flow.py`、`registry.py` | 给被托管 Codex 主动汇报状态 |
| 状态账本层 | lane state（窗口状态）和限频 | `lane_state.py` | 避免重复催促和刷屏 |
| 本地前端层 | `web`、`/dashboard.json`、`/events`、`/managed/send`、`/llm-action` | `features/supervisor/web.py` | 本机视图、bell 事件、白名单发送和手动模型建议入口 |

## 已有轮子

- 读取本机 Codex `.jsonl` 会话记录。
- 读取 SQLite `threads.title` 和 `session_index.jsonl` 的标题。
- 解析匹配当前 session 的 `thread_name_updated`。
- 忽略 JSONL 中其他 thread id 的标题更新事件。
- 标题缺失时，使用首条用户消息截断标题，最后才退回短 hash。
- 扫描优先读取最近候选 session，不再默认全量解析历史 JSONL。
- 超过阈值的大 session 文件只读取开头和尾部。
- 读取 `agent_nickname` 和 `agent_role`，补充 agent 元数据。
- 识别工作中、等待用户、疑似停住、疑似报错、空闲和已退出。
- 每个状态带 `status_evidence`，说明来自状态协议、文本规则、超时、bell 或托管检查。
- 输出中文 plain 报告和 JSON 报告。
- `dashboard` 按需要看、已完成和工作中分组。
- `dashboard/web` 默认隐藏已退出的托管 tmux lane；`scan` 保留审计信息。
- `dashboard` 保留可读标题、短 hash、Codex 标题和 agent 元数据。
- `dashboard` 为每个窗口输出完整 `resume_command`。
- `dashboard` 会把托管 lane 和最近真实 Codex session 合并展示。
- 关联托管 lane 时不只依赖 cwd，而是全局候选打分后做一对一分配。
- 关联优先使用只读 tmux pane 文本、标题和用户消息；session id 只作弱证据。
- 管理窗口只是在讨论别人的 session id 时，不应抢走别的托管 lane 绑定。
- 同一 tmux lane 执行 `/new` 后，关联优先使用新 Codex banner
  之后的活跃终端片段，避免被旧 session 的 resume 行误导。
- 最近输出很长时，会保留新 Codex 窗口锚点和最新尾部，避免截掉绑定依据。
- `linked_match` 会展示绑定依据、分数和命中来源，方便排查错配。
- 当前 tmux pane 明确命中的超时 session 也可关联，即使没有状态协议。
- 关联分数为 0 时不会硬连，避免把托管 lane 误配到旧窗口。
- 带状态协议的超时 session 仍可作为关联候选。
- 合并卡片若关联到真实 `SUPERVISOR_STATUS`，分组和状态字段使用真实 session。
- `web` 启动本机页面，复用 `dashboard` 分组 JSON。
- `web` 优先展示可读标题，同时保留短 hash 方便辨认窗口。
- `web` 显示“卡片来源”，区分普通历史会话和托管 tmux 窗口。
- `web` 会把 `SUPERVISOR_STATUS/SUMMARY/NEXT` 单独显示成“状态汇报”。
- `web` 可复制完整 `codex resume <session_id>`。
- `web` 可分别复制 attach、状态请求和继续命令，
  也可对白名单 send 动作发起本机 POST。
- `web` 托管卡片显示 bell 是否收到、bell hook 安装状态、
  终端可输入状态、关联 session 和最近输出；
  最近输出保留尾部行并默认滚到底部，手动上翻后会保留滚动位置。
- `web` 可手动请求 `/llm-action`，展示 LLM 白名单动作建议。
- `web` 会高亮模型建议对应的 send 按钮，但不会自动点击。
- `web` 会通过 `/events` 接收 bell 事件并立刻刷新 dashboard。
- `/managed/send` 成功发送后会更新 lane state。
- `guide` 会按 cwd、lane name 和 tmux session 打印可复制工作流命令。
- `watch --changes-only` 只在状态变化时输出。
- `watch --bell` 可在建议目标变化时输出终端 bell，不按固定 interval 重复响。
- `supervise --bell` 可配合 `--auto-execute` 使用，只在本轮仍需要人看时响；
  已自动处理的 `send_status/send_continue` 不触发提醒。
- 本机托管登记表 `managed_sessions.jsonl`。
- `launch` 支持普通进程和 tmux 会话。
- `adopt` 可接管已存在的 tmux 会话。
- `send` 支持向登记过的 tmux 会话发送文本。
- tmux 发送使用 buffer/paste 写入文本，短暂等待后用 `C-m` 提交，
  避免请求停留在输入区。
- `scan` 可识别托管 tmux 会话的 bell（提醒）信号。
- `scan` 可从托管 tmux pane 尾部识别 Codex 是否回到输入提示符。
- `launch/adopt` 会安装 tmux `alert-bell` hook。
- `repair-hooks` 可为旧托管 tmux 记录补装 `alert-bell` hook。
- `web` 启动时会自动补装一次已登记托管 tmux lane 的 bell hook。
- bell hook 会写入 `bell_events.jsonl`，让提醒不只依赖轮询。
- `launch` 会注入 `SUPERVISOR_STATUS/SUMMARY/NEXT` 汇报要求。
- `scan` 会从 Codex `.jsonl` 解析状态协议字段。
- 状态协议只从 assistant 回复中解析，并校验 status 合法值。
- 合法状态协议会覆盖 stale timeout 和确认类文本规则，
  `scan --json`、统计计数和 dashboard plain 展示使用同一状态口径。
- `scan --json` 输出结构化建议。
- `SUPERVISOR_STATUS=blocked/done/needs_user` 会影响结构化建议。
- bell 事件会让建议优先提示查看对应托管窗口。
- `advise` 输出建议和命令草案。
- `--execute` 只执行 `send_status` 和 `send_continue`。
- `advise/supervise --name <lane>` 可把建议、显式执行和自动执行收窄到指定托管 lane。
- `send_status/send_continue` 会要求托管 Codex 按三行状态协议汇报。
- `supervise` 循环执行扫描、建议、摘要和显式发送。
- `supervise` 会输出托管自动化是否 ready，没有可控 tmux lane 时给出
  launch/adopt 命令形状。
- `supervise --auto-execute` 每轮最多自动执行一个白名单动作。
- 自动策略：`done` 发 `send_continue`；终端可输入、`stale` 或
  bell 发 `send_status`；`blocked/needs_user/error` 只提醒。
- 未指定 `--name` 时，自动策略会扫描所有活跃托管 lane，
  优先推进可自动处理的窗口，不会被第一个仍在运行的窗口挡住。
- 自动轮转会避开仍在 `--prompt-cooldown` 冷却期内的 lane，
  继续寻找下一个可自动处理的窗口；显式 `--name` 仍会保留冷却跳过提示。
- 如果 lane 仍在运行、终端未回到可输入态且没有 bell/stale 证据，
  自动策略只监控，不会仅因缺少状态协议就催促。
- 已退出的旧托管 tmux lane 不参与建议、命令草案和自动发送。
- lane state 记录最近状态、最近催促时间和催促次数。
- `--prompt-cooldown` 可避免短时间重复催促同一个 lane。
- `--llm-summary` 通过本机 TOML 号池生成中文摘要。
- `--llm-action` 通过本机 TOML 号池选择一个白名单建议动作。
- `--llm-execute` 会执行 LLM 选择的 `send_status/send_continue`，
  `monitor` 只记录跳过。
- LLM 动作提示会携带托管窗口的终端可输入、bell 和状态协议短字段。
- 没有可控托管 tmux lane 时，`LLM action` 直接回退为 `monitor`。
- `LLM action` 会从带说明的模型输出中提取最后一个动作 JSON。

## 当前不要重复实现

- 不要在其他目录再建一套 Supervisor CLI。
- 不要绕过托管登记表直接写新的 tmux 发送器。
- 不要给 Supervisor 再造一套独立 LLM 号池。
- 不要另写状态分类系统，除非同步更新本文件。
- 不要只展示状态标签而不展示判断依据。
- 不要另写一套 dashboard 数据接口，先复用 `/dashboard.json`。
- 不要把 `/events` 做成控制通道；它只负责提醒前端刷新。
- 不要在页面重复展示同一个托管 Codex 的 lane 视角和 session 视角。
- 不要在 web 里放任意文本发送框；先走白名单动作。
- 不要让 `/llm-action` 自动调用 `/managed/send`。
- 高亮模型建议不等于执行动作，执行必须由人类点击或显式参数触发。
- 没有可控托管目标时，不要为了动作建议调用 LLM。
- LLM 动作选择必须落到可审计的白名单能力上。

## 后续拆分方向

- `features/supervisor/status.py`：后续可下沉状态分类和状态依据生成。
- `features/supervisor/advice.py`：建议、命令草案、自动策略和执行白名单。
- `features/supervisor/protocol.py`：后续可下沉状态协议解析和提示语注入。
- `features/supervisor/tmux_control.py`：后续可下沉 tmux 会话、发送和 bell hook。
- `features/supervisor/lane_state.py`：每个窗口的最近状态、催促次数和限频。
- `integrations/codex/session_reader.py`：后续可把 Codex `.jsonl` 读取下沉。

## 下一步顺序

1. 继续观察真实 bell 事件能否稳定触发前端刷新。
2. 后续再决定是否增加人工输入框；默认仍保持白名单。
3. 再拆分 `runner.py` 中的匹配、建议和 tmux 控制代码。

## 登记规则

新增 Supervisor 能力时，至少同步：

- 本文件。
- [当前状态](./status.md)。
- [任务队列](./agent-task-queue.md)。
- 新术语或新命令还要同步 [术语索引](./terminology.md)。
