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
- `web` 可启动本机页面，展示 `dashboard` 的三组窗口和可读标题。
- `supervise` 可按间隔循环执行扫描、建议、可选 LLM 摘要和显式 send。
- `--prompt-cooldown` 可避免短时间重复催促同一个托管 lane。
- `watch --changes-only` 可持续运行，只在会话状态变化时重新输出。
- `launch` 可启动一个 Codex 进程，并写入托管登记文件。
- `launch --backend tmux` 可在本机 tmux 会话里启动 Codex。
- `adopt` 可把已有 tmux 会话登记成托管 lane。
- `scan/watch` 可显示托管进程的名称、pid 和是否已退出。
- `scan/watch` 可显示托管 tmux 会话是否有 bell（提醒）信号。
- `scan/watch` 可显示 tmux bell hook 记录的最近提醒事件。
- `scan/watch` 可显示托管 Codex 主动汇报的 Supervisor 状态协议。
- `recommendation` 会优先处理 `blocked`、`needs_user`、bell 和 `done`。
- `send` 可向 `launch --backend tmux` 登记的会话发送一行文本并回车。
- 可选 `--llm-summary` 调用已配置 LLM 做中文智能摘要。

## 运行方式

开发态：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner scan
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner dashboard
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner web
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner advise
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner supervise --interval 180 --llm-summary
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner watch --interval 180
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner watch --interval 180 --changes-only
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner launch --name lane-a --cwd /path/to/repo --prompt "继续实现当前任务"
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner launch --backend tmux --tmux-session isotope-lane-a --name lane-a --cwd /path/to/repo --prompt "继续实现当前任务"
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner adopt --name lane-a --cwd /path/to/repo --tmux-session isotope-lane-a
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner send --name lane-a --text "继续"
```

安装后：

```bash
.venv/bin/isotope-supervisor scan
.venv/bin/isotope-supervisor dashboard
.venv/bin/isotope-supervisor web
.venv/bin/isotope-supervisor advise
.venv/bin/isotope-supervisor supervise --interval 180 --llm-summary
.venv/bin/isotope-supervisor watch --interval 180
.venv/bin/isotope-supervisor watch --interval 180 --changes-only
.venv/bin/isotope-supervisor launch --name lane-a --cwd /path/to/repo --prompt "继续实现当前任务"
.venv/bin/isotope-supervisor launch --backend tmux --tmux-session isotope-lane-a --name lane-a --cwd /path/to/repo --prompt "继续实现当前任务"
.venv/bin/isotope-supervisor adopt --name lane-a --cwd /path/to/repo --tmux-session isotope-lane-a
.venv/bin/isotope-supervisor send --name lane-a --text "继续"
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
- JSON 保留 session id、短 hash、Codex 标题、agent 名、状态、
  状态依据、resume 命令、tmux session、bell、摘要和下一步字段。

`web` 是当前本地前端薄入口：

```bash
.venv/bin/isotope-supervisor web --host 127.0.0.1 --port 8765
```

页面默认地址是 `http://127.0.0.1:8765/`。
页面会读取 `/dashboard.json`，并按 `需要看`、`已完成`、`工作中`
三组展示窗口；有 tmux session 的条目会显示 attach 命令。
页面标题优先使用托管名，其次使用 Codex 自带标题、首条用户消息、agent 名和短 hash。
每个窗口会显示“依据”，用来解释当前标签为什么被判成等待用户、停住或工作中。
每个窗口提供 `复制 resume`，会复制完整 `codex resume <session_id>`。
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

`supervise` 是当前的监控小闭环：

```bash
.venv/bin/isotope-supervisor supervise --interval 180 --llm-summary
.venv/bin/isotope-supervisor supervise --interval 180 --llm-summary --execute send_status
.venv/bin/isotope-supervisor supervise --interval 180 --execute send_status --prompt-cooldown 300
.venv/bin/isotope-supervisor supervise --iterations 1 --llm-summary --json
```

每轮会扫描窗口、生成结构化建议、生成命令草案，
可选调用 LLM 生成中文摘要。
只有显式传入 `--execute send_status` 或 `--execute send_continue`
时才会发送指令。

LLM 摘要：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner scan --limit 3 --llm-summary
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner watch --interval 180 --llm-summary
```

如果同时使用 `watch --changes-only --llm-summary`，无变化的轮次不会调用 LLM。

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

托管登记：

- 默认写入 `~/.codex/supervisor/managed_sessions.jsonl`。
- 日志默认写入 `~/.codex/supervisor/logs/`。
- 默认进程模式的启动命令形状为 `codex --cd <cwd> --no-alt-screen <prompt>`。
- tmux 模式会执行 `tmux new-session -d -s <session> -c <cwd> ...`。
- `adopt` 会执行 `tmux has-session -t <session>` 确认会话存在。
- `launch/adopt` 会安装 tmux `alert-bell` hook。
- 当前登记 backend、pid、tmux session、cwd、prompt、启动时间和日志路径。
- `send` 会执行 `tmux send-keys -l <text>`，再发送 `Enter`。
- `scan` 会读取 `#{window_bell_flag}`，并输出 `managed_bell`。
- hook 会把 bell 事件写入 `~/.codex/supervisor/bell_events.jsonl`。
- `scan` 会读取最近事件，并输出 `managed_bell_event_at`。
- `launch` 会在发送给 Codex 的 prompt 末尾追加状态汇报要求。
- 登记表里的 `prompt` 仍保留用户原始文本。
- lane state 默认写入 `~/.codex/supervisor/lane_state.json`。
- 发送 `send_status` 或 `send_continue` 后会记录最近状态和催促次数。
- 冷却期内重复发送会跳过，可用 `--prompt-cooldown 0` 临时关闭。

状态协议：

```text
SUPERVISOR_STATUS: working|done|blocked|needs_user
SUPERVISOR_SUMMARY: 用一句中文说明当前状态
SUPERVISOR_NEXT: 用一句中文说明建议下一步
```

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
- `recommendation` 只表示建议动作，不会自动调用 `send`。
- `advise` 默认只生成命令草案；`--execute` 只允许执行
  `send_status` 和 `send_continue`。
- `supervise` 可循环监控；LLM 决策必须落到白名单动作上。
- 当前的自动执行仍受 `--execute` 白名单限制。
- 后续 LLM 可以参与选择动作，但动作必须落到可审计的白名单能力上。
- bell 只作为弱信号，不直接改变状态，也不自动触发发送。
- bell hook 只写事件文件，不直接发指令。
- 状态协议只增强可观察性，当前不直接触发自动发送。
- lane state 只做限频，不替你判断是否应该继续开发。
- 不直接检查 SSH 服务器内部进程。
- 不把完整日志发给 LLM，只发送短摘要和状态字段。

后续继续细化 LLM 决策策略、自动执行边界和前端视图。
