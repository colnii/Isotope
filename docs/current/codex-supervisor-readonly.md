# Codex Supervisor 监控与托管

状态：`第二版小切片 / 本机监控 + 结构化建议 + tmux 控制通道`

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
- `advise` 可只输出当前建议和一条可复制命令草案。
- `watch --changes-only` 可持续运行，只在会话状态变化时重新输出。
- `launch` 可启动一个 Codex 进程，并写入托管登记文件。
- `launch --backend tmux` 可在本机 tmux 会话里启动 Codex。
- `scan/watch` 可显示托管进程的名称、pid 和是否已退出。
- `send` 可向 `launch --backend tmux` 登记的会话发送一行文本并回车。
- 可选 `--llm-summary` 调用已配置 LLM 做中文智能摘要。

## 运行方式

开发态：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner scan
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner advise
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner watch --interval 180
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner watch --interval 180 --changes-only
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner launch --name lane-a --cwd /path/to/repo --prompt "继续实现当前任务"
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner launch --backend tmux --tmux-session isotope-lane-a --name lane-a --cwd /path/to/repo --prompt "继续实现当前任务"
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner send --name lane-a --text "继续"
```

安装后：

```bash
.venv/bin/isotope-supervisor scan
.venv/bin/isotope-supervisor advise
.venv/bin/isotope-supervisor watch --interval 180
.venv/bin/isotope-supervisor watch --interval 180 --changes-only
.venv/bin/isotope-supervisor launch --name lane-a --cwd /path/to/repo --prompt "继续实现当前任务"
.venv/bin/isotope-supervisor launch --backend tmux --tmux-session isotope-lane-a --name lane-a --cwd /path/to/repo --prompt "继续实现当前任务"
.venv/bin/isotope-supervisor send --name lane-a --text "继续"
```

调试 JSON：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner scan --json
```

`scan --json` 里的 `recommendation` 当前只表达建议动作：

- `review_user_prompt`：先看等待用户确认的窗口。
- `inspect_error`：先看疑似报错的窗口。
- `inspect_stale`：检查长时间没新事件的窗口。
- `monitor`：当前无需明显介入。

`advise` 是更短的建议面板：

```bash
.venv/bin/isotope-supervisor advise
.venv/bin/isotope-supervisor advise --json
```

它只输出建议、动作、优先级和命令草案。
命令草案需要人复制执行，不会被自动运行。

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
- 当前登记 backend、pid、tmux session、cwd、prompt、启动时间和日志路径。
- `send` 会执行 `tmux send-keys -l <text>`，再发送 `Enter`。

## 当前边界

- 不接管普通终端窗口；`launch` 启动的是托管 Codex 进程或 tmux 会话。
- `send` 只支持 Supervisor 自己登记的 tmux 会话，不接管手动打开的窗口。
- `recommendation` 只表示建议动作，不会自动调用 `send`。
- `advise` 只生成命令草案，不会执行命令。
- 当前不会自己连续追问或自动续跑；发指令仍由用户或后续策略触发。
- 不直接检查 SSH 服务器内部进程。
- 不把完整日志发给 LLM，只发送短摘要和状态字段。

后续再把 `scan/watch`、LLM 摘要和 `send` 串成半自动流程，
让 Supervisor 能先判断状态，再建议或发送“继续 / 总结 / 暂停”等指令。
