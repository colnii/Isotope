# Supervisor operations runbook

状态：`长流程运行手册 / 从命令参考拆出`

本文从 [Supervisor 命令参考](./supervisor-command-reference.md) 拆出，保留真实 daemon
夜间 smoke、`supervise` 小闭环、LLM summary、托管登记和状态协议等长流程说明。
拆分原因是这些内容篇幅长、更新频率低，独立成文档可以降低
`supervisor-command-reference.md` 的 rebase 冲突面。

## 夜间 smoke 验收清单

这组清单用于真实 daemon（后台守护进程）验收，不是单元测试替代品。
运行前先确认当前仓库没有未保存改动，Codex CLI 已登录，且本轮允许
后台 worker 创建 `.worktrees/supervisor/...` 工作区。建议用独立
`--codex-home` 保存 smoke 账本，避免污染日常 Supervisor 记录：

```bash
export ISO_ROOT=/home/lumber/Github/isotope
export SMOKE_HOME="$ISO_ROOT/.tmp/supervisor-night-smoke-codex-home"

cd "$ISO_ROOT"
git status --short --branch
mkdir -p "$SMOKE_HOME"
.venv/bin/isotope-supervisor daemon stop --codex-home "$SMOKE_HOME" || true
.venv/bin/isotope-supervisor daemon watcher stop --codex-home "$SMOKE_HOME" || true
```

第一段确认 daemon 能用真实 LLM planner 启动多批 worker，并触发
fanout（同轮多目标派发）：

```bash
.venv/bin/isotope-supervisor goal add \
  --codex-home "$SMOKE_HOME" \
  --cwd "$ISO_ROOT" \
  --target-name night-smoke-a \
  "只改 docs/current/codex-supervisor-readonly.md，补一行 night smoke A 标记后提交。"

.venv/bin/isotope-supervisor goal add \
  --codex-home "$SMOKE_HOME" \
  --cwd "$ISO_ROOT" \
  --target-name night-smoke-b \
  "只改 docs/current/codex-supervisor-readonly.md，补一行 night smoke B 标记后提交。"

.venv/bin/isotope-supervisor daemon start \
  --codex-home "$SMOKE_HOME" \
  --interval 60 \
  --max-fanout-launches 2 \
  --worker-profile light \
  --worker-codex-model gpt-5.4-mini \
  --worker-codex-config 'model_reasoning_effort="low"' \
  --no-auto-adopt
```

通过标准：

- `daemon status --codex-home "$SMOKE_HOME"` 显示后台 loop 正在运行。
- `goal list --codex-home "$SMOKE_HOME"` 能看到两个活跃目标及其最近状态。
- `rg "fanout_launch_sessions|night-smoke-a|night-smoke-b" "$SMOKE_HOME/supervisor/logs/daemon.log"`
  能看到同轮 fanout 计划或两条 worker 启动记录。
- `$ISO_ROOT/.worktrees/supervisor/` 下出现两个独立 worker 工作区；
  任何 worker 都不得直接在 `ISO_ROOT` 主工作区抢写。

第二段确认目标生命周期、merge dispatch（合并派发）和 cleanup（收尾归档）：

```bash
.venv/bin/isotope-supervisor goal list --codex-home "$SMOKE_HOME"
.venv/bin/isotope-supervisor integration-review --codex-home "$SMOKE_HOME" --json
.venv/bin/isotope-supervisor merge-work-order --codex-home "$SMOKE_HOME" --json
.venv/bin/isotope-supervisor loop --codex-home "$SMOKE_HOME" --iterations 1 --json
.venv/bin/isotope-supervisor cleanup list --codex-home "$SMOKE_HOME"
```

通过标准：

- worker 完成后会输出 `SUPERVISOR_STATUS: done`，同名 goal 被自动归档；
  若输出 `blocked` 或 `needs_user`，goal 必须继续留在活跃队列。
- `integration-review` 把已完成、分支干净、无冲突且 lint/test 通过的
  worker 放进 `ready_to_integrate`；冲突、未完成或测试失败的 worker
  不得进入该组。
- `merge-work-order` 能渲染给 merge worker 的任务单；随后
  `loop --iterations 1 --json` 在存在 `ready_to_integrate` 候选时应出现
  `merge_dispatch`，并启动名为 `supervisor-merge-dispatch` 的受控 worker。
- `cleanup list` 只列出已完成目标、已完成托管 worker 或可读通知；
  `cleanup archive --all --codex-home "$SMOKE_HOME"` 只追加归档事件，
  不手删账本、不删除源码分支、不删除 worktree。
- `loop --iterations 1 --json` 对 `already_integrated` 且位于
  `.worktrees/supervisor/...` 的已归档 worker 可自动执行
  `git worktree remove`；仍在 `Working ... esc to interrupt` 的 lane
  不会被归档或删除。

第三段确认 CI 和 watchdog（看门进程）：

```bash
.venv/bin/python -m pytest tests -q
python -m isotope.demo
python -m isotope.demo --json

.venv/bin/isotope-supervisor daemon watchdog --codex-home "$SMOKE_HOME"
.venv/bin/isotope-supervisor daemon watcher start --codex-home "$SMOKE_HOME" --interval 60
.venv/bin/isotope-supervisor daemon watcher status --codex-home "$SMOKE_HOME"
```

通过标准：

- 本机测试与 demo smoke 通过；远端 CI 只在本轮允许 push 或已有 PR 时检查
  GitHub Actions 的 `CI / smoke (3.13 self-hosted)`。该 workflow 需要一个在线的
  Linux x64 self-hosted runner，并带 `isotope-ci` 标签；云端额度紧张时不要依赖
  GitHub-hosted runner 自动触发。
- `.github/workflows/ci-cloud.yml` 是手动备用的 GitHub-hosted smoke，只能在
  `workflow_dispatch` 下按需运行，不能作为 push / PR 默认 gate。
- `daemon watchdog` 对仍存活的 daemon 返回 `alive`，不会重复拉起；
  手动停止或异常退出后再次执行，应按 `daemon.json` 的原始命令重启，
  并保留 `--max-fanout-launches` 等启动参数。
- `daemon watcher status` 显示 watcher 正在运行，`watcher.log` 中能看到
  周期 watchdog 结果。

收尾必须显式执行：

```bash
.venv/bin/isotope-supervisor cleanup list --codex-home "$SMOKE_HOME"
.venv/bin/isotope-supervisor cleanup archive --all --codex-home "$SMOKE_HOME"
.venv/bin/isotope-supervisor daemon watcher stop --codex-home "$SMOKE_HOME"
.venv/bin/isotope-supervisor daemon stop --codex-home "$SMOKE_HOME"
git worktree list
git status --short --branch
```

若 smoke 过程中生成了验收专用分支或 worktree，先确认对应提交已经进入
merge worker 或已明确废弃，再由人类维护者删除；Supervisor 的 cleanup
只负责归档自己的账本，不负责清理 Git 历史。

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
显式传入 `--max-run-minutes <分钟>` 时，超时的同名 lane 会被拦截；
默认 0 表示不启用时间限制。
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
