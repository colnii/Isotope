# Codex Supervisor 能力地图

状态：`当前能力登记 / 防止重复造轮子`

## 为什么要有这张图

Codex Supervisor 已经不只是一个小命令。
它是 Isotope 后续的核心管理层：LLM 参与判断和调度，
规则、事件、冷却、tmux 和白名单执行提供工程护栏。

本文件用于登记当前能力和后续拆分方向。
新增 Supervisor 能力时，应先看这里，避免重复造一套相似实现。
同时必须先遵守 `AGENTS.md` 的 AI-first 产品约束：
LLM 不能被降级成可有可无的摘要插件，规则也不能替代产品智能。

## 当前分层

| 层级 | 当前能力 | 主要位置 | 说明 |
| --- | --- | --- | --- |
| 用户功能层 | `scan`、`dashboard`、`guide`、`up`、`discover`、`web`、`watch`、`advise`、`supervise`、`loop`、`daemon` | `features/supervisor/runner.py` | 面向人类使用的命令入口 |
| 托管控制层 | `launch`、`adopt`、`send`、`archive`、托管登记 | `features/supervisor/registry.py` | 管理 Supervisor 登记的 Codex |
| Codex 执行通道 | `resume`、`codex exec resume`、`--last` | `features/supervisor/runner.py`、`features/supervisor/registry.py` | 不依赖 tmux 恢复历史会话并投喂新 prompt |
| 上下文能力层 | `context`、`request_context`、上下文结果记录 | `features/supervisor/context.py`、`features/supervisor/runner.py` | LLM 按需请求检索项目资料，`rg` 优先、Python 兜底，不固定注入全文 |
| Codex 集成层 | 读取 Codex session（会话记录）、索引标题和 agent 元数据 | `features/supervisor/flow.py` | 当前读取本机 `.jsonl`、`session_index.jsonl` 和 SQLite |
| 扫描优化层 | 最近候选、首尾读取和标题兜底 | `features/supervisor/flow.py` | 避免每次页面刷新全量读历史 |
| tmux 集成层 | tmux 启动、buffer/paste 发送和 bell hook | `bell_events.py`、`flow.py`、`registry.py` | 只控制登记过的 tmux 会话 |
| 状态判断层 | 工作中、等待用户、疑似停住、疑似报错 | `features/supervisor/flow.py` | 规则提供候选和证据，不替代 LLM 判断 |
| 状态依据层 | `status_evidence` 说明每个状态标签的来源 | `features/supervisor/flow.py` | 避免只给结论、不说明证据 |
| 建议执行层 | `recommendation`、`command_suggestions`、`--execute` | `flow.py`、`runner.py` | 只允许白名单动作 |
| 模型管理层 | `LLM summary`、`LLM planner` 和 TOML 号池 | `llm_summary.py` | 承担判断、调度和动作选择的 AI 路径 |
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
- `dashboard/web` 和 `supervise` plain 视图默认隐藏已退出的托管
  tmux lane；`scan` 保留审计信息。
- `dashboard` 保留可读标题、短 hash、Codex 标题和 agent 元数据。
- `dashboard` 为每个窗口输出完整 `resume_command`。
- `dashboard` 会把托管 lane 和最近真实 Codex session 合并展示。
- 关联托管 lane 时不只依赖 cwd，而是全局候选打分后做一对一分配。
- 关联优先使用 launch 登记的原始 prompt、只读 tmux pane 文本、
  标题和用户消息；session id 只作弱证据。
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
- `web` 可手动请求 `/llm-action`，展示 LLM planner 的受控动作建议。
- `web` 会高亮模型建议对应的 send 按钮，但不会自动点击。
- `web` 会通过 `/events` 接收 bell 事件并立刻刷新 dashboard。
- `/managed/send` 成功发送后会更新 lane state。
- `guide` 会按 cwd、lane name 和 tmux session 打印可复制工作流命令。
- `loop` 是日常常驻入口，默认由 LLM planner 判断并执行受控动作。
- `loop --rule-execute` 可切回旧规则自动策略。
- `launch` 默认 process 后端使用 `codex exec` 非交互启动，tmux 后端继续
  使用交互式 Codex；process 后端是后台托管主线，tmux 仅用于旁观
  同一个 TUI 或兼容旧窗口。
- process 后端会读取托管 log 尾部，解析
  `SUPERVISOR_STATUS/SUMMARY/NEXT`，所以后台 `codex exec` 退出后仍能
  在 dashboard 里显示明确完成状态，而不是只显示 PID 已退出；
  已退出进程不会因为日志残留 `working` 被继续算作工作中。
- LLM planner 会看到 process 托管记录作为候选目标，避免状态面板
  误报“只有 tmux 才可控”。
- `launch_session` 会写入 lane state 并遵守 `--prompt-cooldown`，
  发现同名后台 process worker 仍在运行时会跳过，避免长跑时对同一个
  `target_name` 反复启动后台 Codex。
- LLM 自动 `launch_session` 默认把 git 仓库任务放进
  `.worktrees/supervisor/...` 独立工作区；子目录任务会进入隔离
  worktree 里的对应子目录。非 git 工作区不强制隔离，git worktree
  创建失败时跳过启动，避免退回共享工作区抢文件。
- `launch/resume` 可用 `--codex-model`、`--codex-config` 覆盖
  Codex worker 配置；`supervise/loop/daemon start` 可用
  `--worker-codex-model`、`--worker-codex-config` 把同类配置传给
  LLM 自动启动或恢复的后台 worker。
- `supervise/loop/daemon start` 默认给写代码 worker 使用 `gpt-5.5`
  和 `model_reasoning_effort="high"`；`guide` 会生成同样默认值的
  日常 `loop/daemon` 命令。
- Supervisor LLM 默认输出上限是 2048 tokens，给动作 JSON 留足空间；
  单个 TOML provider 仍可用 `max_tokens` 覆盖。
- LLM planner 会看到可恢复会话、已完成会话和最近 context 查询历史，
  避免恢复已完成会话或重复检索同一个 cwd/query。
- `scan` 会为真实 Codex session 输出 `source_size_bytes`；
  LLM planner 会收到 `resume_context_hint`，当 session 文件较大时，
  应优先考虑 `request_context` 或 `launch_session`，避免不必要的
  高成本 `resume_session`。
- 开启 LLM 动作时，面向前端/CLI 的主 `command_suggestion` 会提升为
  `llm_action.command_suggestion`；旧规则建议放在
  `rule_command_suggestion`，只作为对照。
- OpenAI-compatible provider 遇到 reasoning-only 空正文时会重试关闭
  thinking，减少模型池空响应。
- `loop` 默认会自动发现并接管未登记的 Codex tmux 窗口；
  可用 `--no-auto-adopt` 关闭。
- `up` 是日常一键入口：daemon 未运行时启动后台 `loop`，随后显示
  daemon 状态和最近活动。
- `daemon start/status/stop` 可把 `loop` 放到后台常驻，记录
  pid（进程号）、命令、状态文件和日志路径。
- `daemon start` 的后台 loop 使用 Python `-u` 非缓冲输出，避免
  自动动作已经发生但 `daemon.log` 仍为空。
- `daemon status` 会从 `daemon.log` 和托管登记表汇总最近 LLM 动作、
  最近执行结果、最近 worker 模型/配置和状态协议。
- `daemon watchdog` 可按状态文件检查后台 `loop` 是否还活着；
  若异常退出，会用原命令重新拉起。
- `daemon watcher start/status/stop` 可启动 watcher（周期看门进程），
  定期触发 `daemon watchdog`。
- `supervise --auto-adopt` 可显式开启同样的自动发现接管能力。
- `loop` 的 `changes-only` 只限制输出；报告不变时 LLM planner 仍会判断是否推进。
- `watch --changes-only` 只在状态变化时输出。
- `watch --bell` 可在建议目标变化时输出终端 bell，不按固定 interval 重复响。
- `supervise --bell` 可配合 `--auto-execute` 使用，只在本轮仍需要人看时响；
  已自动处理的 `send_status/send_continue` 不触发提醒。
- 本机托管登记表 `managed_sessions.jsonl`。
- 本机后台守护状态文件 `daemon.json`，日志默认写到
  `supervisor/logs/daemon.log`。
- 本机周期 watcher 状态文件 `watcher.json`，日志默认写到
  `supervisor/logs/watcher.log`。
- `launch` 支持普通进程和 tmux 会话。
- `resume` 支持用 `codex exec resume <session> <prompt>` 或 `--last`
  恢复历史会话并登记后台托管进程；执行时会带 `--skip-git-repo-check`，
  兼容历史会话工作目录不是 Git 仓库的情况。
- `advise`、`supervise` 和 `loop` 默认只让 LLM/action 候选使用当前工作区会话；
  `--workspace-root <path>` 可指定范围，`--all-workspaces` 可显式放开。
- `context` 支持按 query 检索当前工作区资料，当前是 `rg` 优先、
  Python 关键词扫描兜底，并把结果记录给后续 LLM planner 使用。
- `--llm-execute` 执行 `request_context` 后会在同一轮把检索结果交回
  LLM planner，再执行一次后续受控动作；同轮只允许一次上下文检索，避免循环。
- 已完成会话不再作为 `resume_session` 候选，避免 LLM 把旧验收窗口反复唤醒；
  但其工作目录仍可用于 `launch_session` 和 `request_context`。
- `resume_session` 会写入 lane state，并受 `--prompt-cooldown` 和
  `--max-continue-count` 约束；如果目标 session 所在 cwd 已有
  后台 process worker 仍在运行，会跳过恢复，避免同一个工作区被
  多个后台 Codex 重复驱动；已删除 worktree 或不存在 cwd 不再作为
  resume/context/launch 的正常候选，LLM 误选时只记录 skipped；
  LLM 临时空响应或误选非法目标时会记录为 `monitor`，不让常驻 loop 退出。
- `ask_user` 是拍板请求动作，必须同时满足：Codex 明确请求拍板、
  LLM 无法从用户既有指示判断、上下文检索缺失/过时/冲突。
- `advise --llm-action` 和 web `/llm-action` 会读取最近 context
  结果；合法 `ask_user` 会显示“等待拍板”、问题和 `context_status`。
- `--llm-execute` 执行合法 `ask_user` 时会写入
  `supervisor/decision_requests.jsonl`；dashboard 和 web 会读取成
  稳定拍板列表。
- `decision list` 可查看活跃拍板项；`decision archive --request-id <id>`
  会写入归档事件，让已处理拍板项从活跃列表移走。
- `discover` 可只读扫描现有 tmux 会话，筛出疑似 Codex 窗口，
  并生成可复制的 `adopt` 和 `attach` 命令。
- `discover --adopt-first` 和 `discover --adopt-index <编号>` 可直接接管候选，
  自动使用建议托管名，减少手填 name 和 tmux session。
- `adopt` 可接管已存在的 tmux 会话。
- 手动 tmux 内启动 Codex 后，`adopt -> loop -> archive`
  已通过真实闭环验收。
- `send` 支持向登记过的 tmux 会话发送文本。
- `archive` 可把旧托管记录归档，不关闭 tmux，但会让它退出活跃视图。
- 托管登记按 `record_id` 折叠到最后状态，`status=archived`
  的记录不参与活跃扫描。
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
- `supervise` plain 视图复用 dashboard 当前分组，再输出托管自动化
  是否 ready；没有托管目标时优先给出 process `launch` 命令形状，
  tmux adopt 只是旁观旧窗口的兼容入口。
- `supervise --auto-execute` 每轮最多自动执行一个白名单动作。
- `loop` 复用 `supervise` 引擎，默认开启 LLM planner 执行。
- `loop --rule-execute` 才使用旧规则自动策略。
- 自动策略：`done` 默认发 `send_continue`；终端可输入、`stale` 或
  bell 发 `send_status`；`blocked/needs_user/error` 只提醒。
- `changes-only` 不会阻断 LLM planner；无变化轮次仍可执行 LLM 选择的动作。
- 如果 `SUPERVISOR_NEXT` 明确写出可结束、可归档、等待归档或无需继续，
  `done` 只监控，不再自动续跑。
- 未指定 `--name` 时，自动策略会扫描所有活跃托管 lane，
  优先推进可自动处理的窗口，不会被第一个仍在运行的窗口挡住。
- 自动轮转会避开仍在 `--prompt-cooldown` 冷却期内的 lane，
  继续寻找下一个可自动处理的窗口；显式 `--name` 仍会保留冷却跳过提示。
- 如果 lane 仍在运行、终端未回到可输入态且没有 bell/stale 证据，
  自动策略只监控，不会仅因缺少状态协议就催促。
- 如果托管 tmux pane 明确显示 `Working ... esc to interrupt`，
  自动策略优先相信当前终端仍在工作，不会被同目录旧 `done` session 误导。
- 已退出或已归档的旧托管 tmux lane 不参与建议、命令草案和自动发送。
- lane state 记录最近状态、最近催促时间和催促次数。
- `--prompt-cooldown` 可避免短时间重复催促同一个 lane。
- `--llm-summary` 通过本机 TOML 号池生成中文摘要。
- `--llm-action` 通过本机 TOML 号池让 LLM planner 选择受控动作。
- `--llm-execute` 会执行 LLM 选择的 `send_status/send_continue`、
  `resume_session` 或 `launch_session`，`monitor` 只记录跳过。
- LLM 动作提示会携带托管窗口的终端可输入、bell、状态协议短字段，
  普通 Codex session 的 `resume` 候选和可启动新会话的工作目录。
- `launch_session` 的 goal 由 LLM 根据上下文生成，执行时会包成
  A 层 `work order` prompt；工程层仍只校验受控动作和工作目录。
- 没有任何可控 Supervisor 目标时，`LLM action` 直接回退为 `monitor`。
- `LLM action` 会从带说明的模型输出中提取最后一个动作 JSON。

## Work Order 分层设计

`work order` 是 Supervisor 发给被托管 Codex 的任务单。
它用于说明本次执行的目标、工作区、允许范围、禁止范围、预算、
完成条件和停等用户条件。

当前已做 A 层：把这些边界写进 `launch_session` 的 prompt。
这只能提高 worker 自觉遵守的概率，不代表 Supervisor 已经能强制预算。
不得把 A 层描述成真正的 `max_run_minutes`、`max_continue_count` 或
`max_context_requests` 控制。

B 层预算控制由 Supervisor 自己记录并拦截。当前已落地
`--max-continue-count`、`--max-context-requests` 和
`--max-run-minutes`：
前者用 lane state 记录 `continue_count`，限制同一 lane
同一状态下的继续推进；后者限制同一 supervise/loop 轮次里
`request_context` 的执行次数；`--max-run-minutes` 按托管登记的
`started_at` 判断同名 lane 是否已超时，超时后拦截自动或 LLM 继续推进。
三者默认值都是 0，表示不启用限制；只有显式传入正数阈值时才会拦截，
避免阻碍需要长时间运行的任务。
当前回归测试已覆盖默认宽松预算下，多 lane loop 连续推进不同
托管窗口。

当前 A 层字段：

- `goal`：本次要完成什么。
- `cwd`：执行所在工作区。
- `allowed_scope`：允许改哪些目录或模块。
- `forbidden_scope`：明确不碰什么。
- `budget_hint`：写给 worker 的时间、轮次和上下文请求提醒。
- `done_conditions`：什么证据算完成。
- `ask_user_conditions`：只有哪些情况能停下来问用户。
- `report_protocol`：最后按 `SUPERVISOR_STATUS/SUMMARY/NEXT` 汇报。

## 当前不要重复实现

- 不要把规则、白名单或状态协议写成替代 LLM 的最终智能。
- 用户要求 AI 管理、AI 判断或 AI 执行时，必须打磨真实 AI 路径。
- 不要在其他目录再建一套 Supervisor CLI。
- 不要再把 tmux 当成唯一控制通道；优先复用 `codex exec resume`
  这类 Codex CLI 原生命令。
- 不要绕过托管登记表直接写新的 tmux 发送器。
- 不要给 Supervisor 再造一套独立 LLM 号池。
- 不要另写状态分类系统，除非同步更新本文件。
- 不要让 LLM 仅凭“不确定”就停下来问用户；不满足 `ask_user`
  三项 gate 时应继续查上下文、恢复会话、启动会话或推进托管窗口。
- 不要把 `ask_user` 藏在原始 JSON 里；CLI 和 web 必须显式展示问题。
- 不要只依赖一次性终端输出保存拍板请求；需要写入 decision request 账本。
- 拍板已处理后，不要手删 JSONL；使用 `decision archive` 追加归档事件。
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

1. 再评估是否补可选 `max_minutes`，若实现也必须默认关闭。
2. 后续再决定是否增加人工输入框；默认仍保持白名单。
3. 再拆分 `runner.py` 中的匹配、建议和 tmux 控制代码。

## 登记规则

新增 Supervisor 能力时，至少同步：

- 本文件。
- [当前状态](./status.md)。
- [任务队列](./agent-task-queue.md)。
- 新术语或新命令还要同步 [术语索引](./terminology.md)。
