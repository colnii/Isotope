# Codex Supervisor 监控与托管

状态：`第二版小切片 / 本机监控 + LLM 摘要 + 显式控制通道`

能力登记和后续拆分边界见
[Codex Supervisor 能力地图](./supervisor-capability-map.md)。

## 目标

Codex Supervisor 用来观察、启动和轻量管理本机多个 Codex 进程。
当前仍以读取和汇报为主，但已能向自己托管的 tmux 会话发送一行指令。

它解决的问题是：

- 不用反复问每个 Codex “下一步”。
- 快速看到哪些窗口在工作、等待用户、疑似停住或疑似报错。
- 先把状态判断和受控发送跑通，再做后续自动续跑。

## 当前能力

- 从 `~/.codex/sessions` 读取本机 Codex 会话记录。
- 识别 session id、工作目录、git 分支和最近消息。
- 按最近事件时间排序，默认展示最近 10 个会话。
- 用规则判断 `工作中`、`等待用户`、`疑似停住`、`疑似报错`、`空闲`。
- 输出中文报告，也支持 JSON。
- JSON 输出包含 `recommendation` 结构化建议，供后续半自动管理复用。
- `advise` 可只输出当前建议和可复制命令草案。
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
```

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

`--llm-summary` 只发送压缩后的会话摘要和结构化建议，
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

人类同步观察：

```bash
tmux attach -t isotope-lane-a
```

同一个 tmux session 可以被人类 attach 查看，也可以被 Supervisor
通过 `send` 写入指令。

## 当前边界

- 不接管普通终端窗口；当前控制通道依赖已登记的 tmux 会话。
- `send` 只支持 Supervisor 登记过的 tmux 会话。
- `recommendation` 只表示建议动作，不会自动调用 `send`。
- `advise` 默认只生成命令草案；`--execute` 只允许执行
  `send_status` 和 `send_continue`。
- `supervise` 可循环监控，但不会让 LLM 自由决定执行任意命令。
- 当前不会自己无限自动续跑；发指令仍受 `--execute` 白名单限制。
- bell 只作为弱信号，不直接改变状态，也不自动触发发送。
- bell hook 只写事件文件，不直接发指令。
- 状态协议只增强可观察性，当前不直接触发自动发送。
- lane state 只做限频，不替你判断是否应该继续开发。
- 不直接检查 SSH 服务器内部进程。
- 不把完整日志发给 LLM，只发送短摘要和状态字段。

后续再细化 LLM 决策策略和自动执行边界。
