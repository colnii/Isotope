# Codex Supervisor 监控与托管

状态：`第二版小切片 / LLM 管理层 + 本机监控 + 显式控制通道`

能力登记和后续拆分边界见
[Codex Supervisor 能力地图](./supervisor-capability-map.md)。

## 目标

Codex Supervisor 是后续 Isotope 的核心管理层。
目标不是把它做成纯规则脚本，而是让 LLM 参与判断和调度，
再用规则、事件、冷却和白名单执行做工程护栏。

当前它能观察、启动和轻量管理本机多个 Codex 进程。
现阶段仍以读取、汇报和受控发送为主。

它解决的问题是：

- 不用反复问每个 Codex “下一步”。
- 快速看到哪些窗口在工作、等待用户、疑似停住或疑似报错。
- 先把状态判断和受控发送跑通，再做后续自动续跑。

## 当前能力

- 从 `~/.codex/sessions` 读取本机 Codex 会话记录。
- 识别 session id、短 hash、Codex 标题、agent 名、工作目录、git 分支和最近消息。
- 标题优先读 SQLite `threads.title` 和 `session_index.jsonl` 的
  `thread_name`，并读取匹配当前 session 的 `thread_name_updated`。
- 如果仍没有标题，使用首条真实用户消息的短标题，跳过 AGENTS 和环境上下文。
  最后才显示短 hash。
- 页面展示标题会截断，原始标题仍保留在 `thread_name` 字段。
- 扫描会优先处理最近候选会话；大 JSONL 只读开头和尾部，避免页面刷新卡顿。
- 按最近事件时间排序，默认展示最近 10 个会话。
- 用规则判断 `工作中`、`等待用户`、`疑似停住`、`疑似报错`、`空闲`。
- 每个状态会带 `status_evidence`（状态依据），说明来自规则、
  状态协议、tmux bell 还是托管进程检查。
- 输出中文报告，也支持 JSON。
- JSON 输出包含 `recommendation` 结构化建议，供后续半自动管理复用。
- `advise` 可只输出当前建议和可复制命令草案。
- `dashboard` 可按 `需要看`、`已完成`、`工作中` 分组显示，
  并保留可读标题和短 hash。
- `dashboard` 会把托管 tmux lane 和最近真实 Codex session 合并成一个
  可控卡片，关联不再只依赖 cwd。
- `web` 可启动本机页面，展示 `dashboard` 的三组窗口和可读标题。
- `web` 会给托管 tmux 窗口显示复制 attach、复制状态、复制继续、
  复制归档、请求状态和继续推进按钮。
- `web` 可手动请求 `/llm-action`，只展示模型建议的白名单动作，
  不自动发送。
- `web` 会连接 `/events` 事件流；托管 tmux 响铃后会立刻刷新页面，
  不必等 5 秒轮询。
- `guide` 会按当前参数打印可复制的启动、接管、日常 loop 和观察命令。
- `loop` 是日常常驻入口，等价于安全默认的自动监督循环。
- `daemon` 可把日常 `loop` 放到后台运行，并提供 start/status/stop。
- `supervise` 可按间隔循环执行扫描、建议、可选 LLM 摘要和显式 send。
- `advise/supervise --name <lane>` 可只针对一个托管 lane 生成建议或执行动作。
- `advise/supervise --llm-action` 可让 LLM 在白名单里选择建议动作，
  但不会自动执行。
- `advise/supervise --llm-execute` 可执行 LLM 选择的白名单 send 动作；
  `monitor` 只记录跳过。
- `--prompt-cooldown` 可避免短时间重复催促同一个托管 lane。
- `watch --changes-only` 可持续运行，只在会话状态变化时重新输出。
- `watch --bell` 可在本轮建议需要人看时输出终端 bell（提醒音）。
- `launch` 可启动一个 Codex 进程，并写入托管登记文件。
- `launch --backend tmux` 可在本机 tmux 会话里启动 Codex。
- `adopt` 可把已有 tmux 会话登记成托管 lane。
- `scan/watch` 可显示托管进程的名称、pid 和是否已退出。
- `scan/watch` 可显示托管 tmux 会话是否有 bell（提醒）信号。
- `scan/watch` 可显示 tmux bell hook 记录的最近提醒事件。
- `scan/watch` 可显示托管 Codex 主动汇报的 Supervisor 状态协议。
- `recommendation` 会优先处理 `blocked`、`needs_user`、bell 和 `done`。
- `send` 可向 `launch --backend tmux` 登记的会话发送一行文本并回车。
- `archive` 可把旧托管记录归档，让它不再进入活跃 dashboard。
- `repair-hooks` 可给旧托管 tmux 记录补装 bell hook。
- 可选 `--llm-summary` 调用已配置 LLM 做中文智能摘要。

## 运行方式

开发态：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner scan
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner dashboard
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner guide --cwd /path/to/repo --name lane-a
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner web
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner advise
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner supervise --interval 180 --llm-summary
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner daemon start --interval 30
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner daemon status
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner daemon stop
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner watch --interval 180
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner watch --interval 180 --changes-only
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner launch --name lane-a --cwd /path/to/repo --prompt "继续实现当前任务"
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner launch --backend tmux --tmux-session isotope-lane-a --name lane-a --cwd /path/to/repo --prompt "继续实现当前任务"
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner adopt --name lane-a --cwd /path/to/repo --tmux-session isotope-lane-a
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner send --name lane-a --text "继续"
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner archive --name lane-a
```

安装后：

```bash
.venv/bin/isotope-supervisor scan
.venv/bin/isotope-supervisor dashboard
.venv/bin/isotope-supervisor guide --cwd /path/to/repo --name lane-a
.venv/bin/isotope-supervisor web
.venv/bin/isotope-supervisor advise
.venv/bin/isotope-supervisor supervise --interval 180 --llm-summary
.venv/bin/isotope-supervisor daemon start --interval 30
.venv/bin/isotope-supervisor daemon status
.venv/bin/isotope-supervisor daemon stop
.venv/bin/isotope-supervisor watch --interval 180
.venv/bin/isotope-supervisor watch --interval 180 --changes-only
.venv/bin/isotope-supervisor launch --name lane-a --cwd /path/to/repo --prompt "继续实现当前任务"
.venv/bin/isotope-supervisor launch --backend tmux --tmux-session isotope-lane-a --name lane-a --cwd /path/to/repo --prompt "继续实现当前任务"
.venv/bin/isotope-supervisor adopt --name lane-a --cwd /path/to/repo --tmux-session isotope-lane-a
.venv/bin/isotope-supervisor send --name lane-a --text "继续"
.venv/bin/isotope-supervisor archive --name lane-a
```

调试 JSON：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner scan --json
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner dashboard --json
```

`dashboard` 是面向人类和后续前端的汇总视图：

- `needs_attention`：需要看的窗口，包含阻塞、等待用户、报错、停住和 bell。
- `done`：主动汇报完成的窗口。
- `working`：仍在推进或暂无明显异常的窗口。
- 已退出的托管 tmux lane 默认不进入 dashboard/web 和 `supervise`
  plain 视图，避免旧登记污染日常视图；`scan --json` 仍保留完整
  审计信息。
- JSON 保留 session id、短 hash、Codex 标题、agent 名、状态、
  状态依据、resume 命令、受控命令、tmux session、bell、摘要和下一步字段。
- 如果托管 lane 能关联到真实 Codex session，`display_title` 和
  `resume_command` 会优先使用真实 session，同时保留 `managed_display_title`
  和 `linked_session_id`。
- 如果关联到的真实 session 有 `SUPERVISOR_STATUS`，dashboard 分组和
  状态字段会优先使用真实 session 的状态协议。
- 关联时会全局候选打分并一对一分配，优先使用 launch 登记的
  原始 prompt、只读 `tmux capture-pane` 摘要、Codex 标题、
  首条用户消息或最近消息；
  session id 只作弱证据，避免管理窗口讨论别人 id 时抢走绑定；
  没有正分命中时不硬连旧窗口。
- 同一 tmux lane 内执行 `/new` 后，会优先使用新 Codex banner
  和 `Thread renamed to ...` 之后的终端片段，不让旧 session 的
  resume 行继续抢占绑定。
- 如果最近输出很长，摘要会保留新 Codex 窗口锚点和最新尾部，
  防止把 `/new` 后的绑定依据截掉。
- 如果当前 tmux pane 明确命中某个超时 session，即使它没有
  `SUPERVISOR_STATUS`，也可以被关联；web 会显示 `linked_match`
  绑定依据、分数和命中来源。

`web` 是当前本地前端薄入口：

```bash
.venv/bin/isotope-supervisor web --host 127.0.0.1 --port 8765
```

页面默认地址是 `http://127.0.0.1:8765/`。
页面会读取 `/dashboard.json`，并按 `需要看`、`已完成`、`工作中`
三组展示窗口。
页面同时连接 `/events`。当 tmux `alert-bell` hook 写入
`bell_events.jsonl` 后，web 服务会推送 `bell` 事件，前端马上重新读取
`/dashboard.json`。
web 启动时会给登记过的活跃 tmux lane 自动补装一次 bell hook。
页面标题优先使用关联到的 Codex 自带标题或首条用户消息。
托管名会显示在路径信息里，方便确认它仍是可控 lane。
页面会单独显示“卡片来源”，区分普通历史会话和托管 tmux 窗口。
绑定托管 lane 时，旧 `codex resume <session_id>`、通用状态请求、
以及“不要继续某旧任务”里的旧标题只作为弱信息处理，
避免 `/new` 后的新窗口被旧 session 抢走。
每个窗口会显示“依据”，用来解释当前标签为什么被判成等待用户、停住或工作中。
如果窗口主动写了 `SUPERVISOR_STATUS/SUMMARY/NEXT`，
页面会单独显示“状态汇报”区，避免只在终端原文里找状态。
托管窗口会额外显示“托管窗口”详情区，包含 bell 是否收到、bell hook
安装状态、终端可输入状态、关联 session 和最近输出；
最近输出来自只读 `tmux capture-pane` 尾部摘要，会保留换行并默认滚到输出底部。
用户手动上翻最近输出后，自动刷新会保留滚动位置，不会强行跳回底部。
每个窗口提供 `复制 resume`，会复制完整 `codex resume <session_id>`。
托管 tmux 窗口还会显示复制 attach、复制状态、复制继续、
复制归档、请求状态和继续按钮。
页面不再额外显示一行 `tmux attach` 命令，避免和复制 attach 按钮重复。
页面发送按钮调用 `/managed/send`，只允许 `send_status` 和 `send_continue`。
成功发送后会更新 lane state（窗口状态账本）的最近催促时间和次数。
`send_status` 会要求托管 Codex 严格按 `SUPERVISOR_STATUS`、
`SUPERVISOR_SUMMARY`、`SUPERVISOR_NEXT` 三行汇报。
`send_continue` 会要求继续推进，并在完成或阻塞后按同样三行格式汇报。
`archive` 不会关闭 tmux，只会追加一条归档记录，让旧 lane 不再参与
活跃扫描、dashboard、建议和自动发送。
页面的“模型建议”按钮会调用 `/llm-action`。
该接口只在点击时请求 LLM，从 `monitor`、`send_status` 和
`send_continue` 中返回建议动作，不会自动调用 `/managed/send`。
模型建议解析会从模型输出中提取带 `kind` 的 JSON 对象；
如果模型在 JSON 前后加说明或 fenced code，也会尽量提取动作对象。
如果模型建议的是某个托管 lane 的 `send_status` 或 `send_continue`，
页面会高亮对应的“请求状态”或“继续”按钮，但仍需人类手动点击。
如果当前没有可控的托管 tmux lane，会直接返回 `monitor`，
不调用 LLM。
当前页面使用 Python 标准库 HTTP server 和内联 HTML/CSS/JS，
不引入额外前端依赖。

`scan --json` 里的 `recommendation` 当前只表达建议动作：

- `review_user_prompt`：先看等待用户确认的窗口。
- `inspect_blocked`：先看主动汇报阻塞的窗口。
- `inspect_error`：先看疑似报错的窗口。
- `inspect_bell`：先看刚响铃的托管窗口。
- `review_done`：先审阅已完成的窗口。
- `inspect_stale`：检查长时间没新事件的窗口。
- `monitor`：当前无需明显介入。

`advise` 是更短的建议面板：

```bash
.venv/bin/isotope-supervisor advise
.venv/bin/isotope-supervisor advise --json
.venv/bin/isotope-supervisor advise --llm-action --json
.venv/bin/isotope-supervisor advise --name lane-a --execute send_status
.venv/bin/isotope-supervisor advise --execute send_status
.venv/bin/isotope-supervisor advise --execute send_continue
```

它只输出建议、动作、优先级和命令草案。
`advise --json` 会保留兼容字段 `command_suggestion`，
并用 `command_suggestions` 返回多条候选命令。
托管 tmux lane 会生成 attach、汇报状态和继续推进三类草案。
默认只生成草案，不会自动运行。
显式传入 `--execute send_status` 或 `--execute send_continue` 时，
只会执行对应的 `send` 类草案；`tmux_attach` 和 `watch_changes`
不会被 `--execute` 执行。
传入 `--name <lane>` 时，建议和执行都只面向这个托管 lane；
如果名字不存在，会报错，不会退回到第一个托管窗口。
`--llm-action` 会把压缩状态、候选命令和目标 lane 发给 LLM，
要求它只返回 `monitor`、`send_status` 或 `send_continue`。
返回结果会被校验；不在白名单内的动作会报错，不会执行。
如果没有可控的托管 tmux lane，会直接回退成 `monitor`，
避免无目标时请求模型或报 `target_name` 错误。

`guide` 是推荐入口，会生成一组可复制命令：

```bash
.venv/bin/isotope-supervisor guide --cwd /path/to/repo --name lane-a
.venv/bin/isotope-supervisor guide --cwd /path/to/repo --name lane-a --tmux-session lane-a
.venv/bin/isotope-supervisor discover --cwd /path/to/repo
.venv/bin/isotope-supervisor discover --cwd /path/to/repo --adopt-first
.venv/bin/isotope-supervisor discover --cwd /path/to/repo --adopt-index 1
```

生成后通常按这个顺序用：

1. `launch --backend tmux` 新开托管 Codex 窗口。
2. 如果已有 tmux 窗口，先用 `discover` 找候选和接管命令。
3. 用 `adopt` 接管已有窗口。
4. `daemon start --interval 30` 后台常驻监控。
5. 需要细看时打开 `web` 或 `tmux attach`。
6. 窗口不用再跟进时，用 `archive --name <lane>` 归档。

手动 tmux 内启动 Codex 后，`adopt -> loop -> archive`
已完成真实闭环验收。
`discover` 是只读入口：它不会接管、发送或修改窗口，只会列出看起来像
Codex 的 tmux 会话，并生成可复制的 `adopt` 和 `attach` 命令。
如果候选明确，可以加 `--adopt-first` 直接接管第一个候选；
多候选时用 `--adopt-index <编号>` 按列表编号接管。
这两种方式都会自动使用建议托管名，不需要手填 name 或 tmux session。

`loop` 是日常入口：

```bash
.venv/bin/isotope-supervisor loop
.venv/bin/isotope-supervisor loop --interval 30
.venv/bin/isotope-supervisor loop --name lane-a
.venv/bin/isotope-supervisor loop --iterations 1 --json
.venv/bin/isotope-supervisor loop --no-auto-adopt
```

它默认启用 `auto-execute`、`changes-only` 和 `bell`：
会自动按规则推进可控托管 lane，只在状态变化时输出，
需要人看时才响铃。`--name <lane>` 可临时只盯一个窗口。
`changes-only` 只压缩输出，不会阻断自动发送；如果窗口一直可输入但没回应，
冷却期结束后仍会再次请求状态。
`loop` 还会默认先扫描现有 tmux Codex 窗口，
自动接管未登记候选，再进入监督和自动推进。
接管时会读取 tmux pane 的当前目录作为 cwd。
如果只想监督已登记窗口，可加 `--no-auto-adopt`。

`daemon` 是后台入口：

```bash
.venv/bin/isotope-supervisor daemon start --interval 30
.venv/bin/isotope-supervisor daemon start --interval 30 --no-auto-adopt
.venv/bin/isotope-supervisor daemon status
.venv/bin/isotope-supervisor daemon stop
```

它会启动一个后台 `loop` 进程，把状态写到
`~/.codex/supervisor/daemon.json`，日志写到
`~/.codex/supervisor/logs/daemon.log`。
`daemon status` 只检查本机进程是否还活着；
`daemon stop` 发送 `SIGTERM`（终止信号）并把状态标成 `stopped`。
这一步还不是系统级自启动，也不负责崩溃后自动拉起。

`supervise` 是当前的监控小闭环：

```bash
.venv/bin/isotope-supervisor supervise --interval 180 --llm-summary
.venv/bin/isotope-supervisor supervise --interval 180 --llm-summary --execute send_status
.venv/bin/isotope-supervisor supervise --interval 180 --execute send_status --prompt-cooldown 300
.venv/bin/isotope-supervisor supervise --interval 180 --auto-execute --prompt-cooldown 300
.venv/bin/isotope-supervisor supervise --interval 30 --auto-execute --changes-only --bell
.venv/bin/isotope-supervisor supervise --interval 180 --llm-execute --prompt-cooldown 300
.venv/bin/isotope-supervisor supervise --interval 30 --auto-adopt --auto-execute --changes-only
.venv/bin/isotope-supervisor supervise --name lane-a --iterations 1 --auto-execute --json
.venv/bin/isotope-supervisor supervise --iterations 1 --llm-action --json
.venv/bin/isotope-supervisor supervise --iterations 1 --llm-summary --json
```

每轮会扫描窗口、生成结构化建议、生成命令草案，
可选调用 LLM 生成中文摘要。
plain 视图会先显示 dashboard 当前分组，再显示托管自动化状态；
JSON 仍保留完整 scan 报告。
只有显式传入 `--execute send_status` 或 `--execute send_continue`
时才会发送指令。
`--auto-execute` 会启用规则自动策略，每轮最多执行一个白名单动作：
`done` 默认发 `send_continue`，终端可输入、`stale` 或 bell 时发
`send_status`，`blocked`、`needs_user` 和疑似报错只提醒不硬推。
如果 `SUPERVISOR_NEXT` 明确写出可结束、可归档、等待归档或无需继续，
`done` 只监控，不再自动续跑。
未指定 `--name` 时，自动策略会扫描所有活跃托管 lane，
优先选择可自动处理且不在 `--prompt-cooldown` 冷却期内的窗口。
如果 lane 仍在运行、终端未回到可输入态且没有 bell/stale 证据，
即使缺少状态协议也只监控，不会提前催促。
如果终端明确显示 `Working ... esc to interrupt`，
自动策略会优先相信当前窗口仍在工作，不使用同目录旧 `done` session 续跑或归档。
配合 `--name <lane>` 时，自动策略只读取并操作这个托管 lane。
`--llm-execute` 会先请求 LLM 白名单动作，再执行
`send_status` 或 `send_continue`；如果 LLM 返回 `monitor`，本轮只记录跳过。
LLM 动作提示会携带托管窗口的终端可输入、bell 和状态协议短字段，
但不会发送完整终端输出。

LLM 摘要：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner scan --limit 3 --llm-summary
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner watch --interval 180 --llm-summary
```

如果同时使用 `watch --changes-only --llm-summary`，无变化的轮次不会调用 LLM。
如果使用 `watch --changes-only --bell`，只有打印出来且建议目标发生变化的
轮次会响铃；同一个阻塞或停住目标不会按固定 interval 重复响。
bell 写到 stderr，不污染 JSON/stdout。

配置文件：

- 默认读取 `src/isotope/features/supervisor/supervisor_llm_pool.toml`。
- 该文件已被 `.gitignore` 忽略，不提交到仓库。
- 也可用 `SUPERVISOR_LLM_POOL_TOML_FILES` 指定一个或多个 TOML 路径，
  多个路径用英文逗号分隔。

示例：

```toml
[[keys]]
provider = "company_pool"
base_url = "https://api.example.com"
model = "chat-model"
api_keys = [
  "env:COMPANY_LLM_API_KEY",
  "sk-local-plaintext-key",
]
```

`api_keys` 支持 `env:VAR_NAME` 或明文 key。
默认 TOML 已被 `.gitignore` 屏蔽，明文 key 只适合放在本机配置里。
`SUPERVISOR_LLM_MAX_TOKENS` 可控制摘要 token 上限，默认 `512`。

`--llm-summary` 只发送压缩后的会话摘要、状态依据和结构化建议，
不发送完整 session 文件。
`--llm-action` 只发送压缩状态、候选命令和候选目标，
要求模型输出一个 JSON 白名单动作。

托管登记：

- 默认写入 `~/.codex/supervisor/managed_sessions.jsonl`。
- 日志默认写入 `~/.codex/supervisor/logs/`。
- 默认进程模式的启动命令形状为 `codex --cd <cwd> --no-alt-screen <prompt>`。
- tmux 模式会执行 `tmux new-session -d -s <session> -c <cwd> ...`。
- `adopt` 会执行 `tmux has-session -t <session>` 确认会话存在。
- `launch/adopt` 会安装 tmux `alert-bell` hook。
- `repair-hooks` 会读取托管登记表，为仍存在的 tmux session 补装 hook。
- 当前登记 backend、pid、tmux session、cwd、prompt、启动时间和日志路径。
- `send` 会执行 `tmux set-buffer`、`paste-buffer`，短暂等待后用 `C-m` 提交。
- `archive` 会向 `managed_sessions.jsonl` 追加 `status=archived`，
  读取活跃 lane 时按 `record_id` 折叠到最后状态。
- `scan` 会读取 `#{window_bell_flag}`，并输出 `managed_bell`。
- `scan` 会检查 `alert-bell` hook，并输出 `managed_bell_hook_installed`。
- `scan` 会只读 `tmux capture-pane` 尾部文本，用于辅助页面关联
  托管 lane 和真实 Codex session，并展示托管窗口最近输出。
- `scan` 会从托管 pane 尾部识别 Codex 是否回到 `›` 输入提示符，
  并输出 `managed_terminal_ready`。
- hook 会把 bell 事件写入 `~/.codex/supervisor/bell_events.jsonl`。
- `scan` 会读取最近事件，并输出 `managed_bell_event_at`。
- `launch` 会在发送给 Codex 的 prompt 末尾追加状态汇报要求。
- 登记表里的 `prompt` 仍保留用户原始文本。
- lane state 默认写入 `~/.codex/supervisor/lane_state.json`。
- 发送 `send_status` 或 `send_continue` 后会记录最近状态和催促次数。
- 冷却期内重复发送会跳过，可用 `--prompt-cooldown 0` 临时关闭。
- 状态请求文本保持单行，避免 Codex TUI 把请求停留在输入区。

状态协议：

```text
SUPERVISOR_STATUS: working|done|blocked|needs_user
SUPERVISOR_SUMMARY: 用一句中文说明当前状态
SUPERVISOR_NEXT: 用一句中文说明建议下一步
```

协议只从 assistant 回复中解析，`SUPERVISOR_STATUS` 必须是四个合法值之一。

状态依据：

- `supervisor_protocol`：被托管 Codex 主动写了 `SUPERVISOR_STATUS`。
- `attention_marker`：最近助手回复命中了确认类文本。
- `stale_timeout`：超过静默阈值没有新事件。
- `recent_event`：最近仍有 Codex 事件。
- `idle_window`：未命中异常规则，也还没超过静默阈值。
- `error_marker`：最近事件命中错误类文本。
- `tmux_bell`：托管 tmux 窗口触发 bell。
- `managed_tmux` / `managed_process`：来自托管会话或进程状态检查。

人类同步观察：

```bash
tmux attach -t isotope-lane-a
```

同一个 tmux session 可以被人类 attach 查看，也可以被 Supervisor
通过 `send` 写入指令。

## 当前边界

- 不接管普通终端窗口；当前控制通道依赖已登记的 tmux 会话。
- `send` 只支持 Supervisor 登记过的 tmux 会话。
- `web` 只监听本机默认地址，不提供认证和远程访问能力。
- `web` 的 `/managed/send` 只接受 `send_status` 和 `send_continue`。
- `web` 的 `/llm-action` 只在手动点击时调用模型，只展示建议；
  解析时会容忍 JSON 前后的说明文字。
- `web` 的 `/events` 只推送 bell 提醒和心跳，不承载任意控制指令。
- 模型建议只会高亮按钮，不会自动点击按钮。
- `/managed/send` 成功发送后会记录 lane state。
- `recommendation` 只表示建议动作，不会自动调用 `send`。
- `advise` 默认只生成命令草案；`--execute` 只允许执行
  `send_status` 和 `send_continue`。
- `--llm-action` 只输出模型建议动作，不自动执行。
- `guide` 只打印命令，不启动 tmux、不调用模型、不发送指令。
- `loop` 是 `supervise --auto-execute --changes-only --bell --interval 30`
  的日常入口。
- `daemon start` 只是把 `loop` 放进后台，并记录 pid（进程号）、
  命令和日志路径。
- `supervise --auto-execute` 可按规则自动执行一个白名单动作。
- `changes-only` 不会阻断自动策略；无变化轮次仍会检查冷却并继续必要发送。
- 未指定 `--name` 的自动轮转会避开冷却中的 lane，
  继续寻找下一个可自动处理窗口。
- `--llm-execute` 可执行 LLM 建议，但动作必须落到可审计白名单上。
- `--execute`、`--auto-execute` 和 `--llm-execute` 不能同时使用。
- bell 只作为弱信号，不直接改变状态，也不自动触发发送。
- `managed_terminal_ready` 表示 Codex 已回到输入态，自动策略会发状态请求。
- bell hook 只写事件文件，不直接发指令。
- 状态协议会影响 `--auto-execute` 的动作选择。
- lane state 只做限频，不替你判断是否应该继续开发。
- 不直接检查 SSH 服务器内部进程。
- 不把完整日志发给 LLM，只发送短摘要和状态字段。

后续继续细化 LLM 决策策略、自动执行边界和前端视图。
