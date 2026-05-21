# Codex Supervisor 监控与托管

状态：`第二版小切片 / LLM 管理层 + 本机监控 + 显式控制通道`

能力登记和后续拆分边界见
[Codex Supervisor 能力地图](./supervisor-capability-map.md)。

## 目标

Codex Supervisor 是后续 Isotope 的核心管理层。
目标不是把它做成纯规则脚本，也不是把 LLM 当成旁路摘要按钮。
LLM 应作为判断、调度和下一步建议的主路径之一，
规则、事件、冷却和白名单执行只提供工程护栏。

当前它能观察、启动和轻量管理本机多个 Codex 进程。
现阶段仍以读取、汇报和受控发送为主。
新增或打磨 Supervisor 产品功能时，必须先说明用户入口如何触发
真实 LLM 路径，以及模型输出如何进入 CLI/API/UI 的可用结果。
除非用户明确要求诊断，不得只交付规则分类、只读报告或预检查。

它解决的问题是：

- 不用反复问每个 Codex “下一步”。
- 快速看到哪些窗口在工作、等待用户、疑似停住或疑似报错。
- 用 LLM 和工程信号共同判断下一步，而不是只靠文本规则。

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
- `web` 等待拍板列表可填写答案并提交到 `/decision/answer`；
  该接口只写入拍板答案账本，不直接向托管 Codex 发送任意文本。
- `web` 会连接 `/events` 事件流；托管 tmux 响铃后会立刻刷新页面，
  不必等 5 秒轮询。
- `guide` 会按当前参数打印可复制的启动、接管、日常 loop 和观察命令。
- `loop` 是日常常驻入口，等价于安全默认的自动监督循环。
- `daemon` 可把日常 `loop` 放到后台运行，并提供 start/status/stop/watchdog。
- `supervise/loop/up/daemon start --goal <目标>` 可把用户目标交给
  LLM planner；没有现成托管窗口时，模型也能选择先查上下文或启动
  新的后台 Codex worker。
- `goal add/list/archive` 可维护持久目标队列；daemon 启动后会由
  `loop` 动态读取活跃目标，不必把目标写死在启动命令里。
- `loop/up/daemon start --goal-low-water N` 可在活跃目标少于 N 个时，
  调用 LLM 根据当前文档补充目标队列；默认 0 表示关闭。
- `--goal-replenish-limit N` 控制单轮最多补多少个目标；
  `--goal-replenish-prompt` 可覆盖补任务时交给模型的高层说明。
- 同名 worker 汇报 `SUPERVISOR_STATUS: done` 时，`loop` 会自动归档
  对应目标；汇报 `blocked/needs_user` 时只记录状态，不删除目标。
- `blocked/needs_user` 会继续作为活跃目标进入 LLM planner 输入，
  让模型根据上下文选择继续查询、启动 worker、发起拍板或继续观察。
- 若阻塞目标满足拍板门槛，LLM 可用 `goal_id` 生成目标级
  decision request，dashboard 和 web 会把它当作稳定“等待拍板”项展示。
- 用户通过 `decision answer` 记录答案后，下一轮 LLM planner 会读取
  `recent_decision_answers`，并可据此继续启动或恢复 worker。
- `goal list` 和 `daemon status` 会直接展示活跃目标最近状态、
  摘要和下一步。
- `daemon watcher` 可启动 watcher（周期看门进程），定期触发 watchdog。
- `supervise` 可按间隔循环执行扫描、建议、可选 LLM 摘要和显式 send。
- `advise/supervise --name <lane>` 可只针对一个托管 lane 生成建议或执行动作。
- `advise/supervise --llm-action` 可让 LLM 在白名单里选择建议动作，
  但不会自动执行。
- `advise/supervise --llm-execute` 可执行 LLM 选择的白名单 send 动作；
  `monitor` 只记录跳过。
- `--prompt-cooldown` 可避免短时间重复催促同一个托管 lane。
- 活跃目标已有同名 worker 运行时，LLM 输入会带 `worker_status`；
  候选动作会过滤同名 `launch_session`，白名单校验也会拒绝重复启动并转为 `monitor`，
  避免常驻 loop 重复启动同一个任务。
- process worker 如果异常退出且最后明确汇报过 `SUPERVISOR_STATUS: working`，
  `loop` 会最多自动重启 2 次，并把 `worker_retry_count` 写入 lane state。
- LLM 自动 `launch_session` 会优先创建 `.worktrees/supervisor/...`
  下的独立 git worktree，再在隔离工作区启动 worker。
- `watch --changes-only` 可持续运行，只在会话状态变化时重新输出。
- `watch --bell` 可在本轮建议需要人看时输出终端 bell（提醒音）。
- `launch` 可启动一个 Codex 进程，并写入托管登记文件。
- `launch --backend tmux` 可在本机 tmux 会话里启动 Codex。
- `launch/resume --codex-model <model> --codex-config key=value` 可覆盖
  后台 Codex worker 的模型和配置。
- `worker-review` 会对已汇报 `done` 的 process worker 运行
  `PYTHONPATH=src .venv/bin/python -m pytest tests/isotope -q`，并在输出和
  `automation_candidates` 里记录 `test_passed`、`test_exit_code` 和
  `test_output_tail`；worktree 缺失时标记为 skipped。
- `integration-review` 可只读扫描 managed worker 的 branch、worker HEAD、
  `main` 包含关系、pytest gate、merge conflict 风险和候选 worktree
  的 lint/test 结果，输出
  `ready_to_integrate`、`already_integrated`、`needs_review`、
  `conflict_risk` 四组，不执行 merge/push/delete；默认只看未归档且已
  汇报 done 且 worktree 仍存在的 worker，排查历史噪音时再加
  `--include-unfinished` 或 `--include-missing-worktrees`；
  pytest gate 或 validation 失败的 worker 会留在 `needs_review` 并输出摘要。
- `replan` 可读取 `worker-review`、活跃目标和 `integration-review`
  分组，生成下一轮只读建议、复查合并候选和候选摘要；它只产出建议，
  不自动 merge、不归档、不删除分支或 worktree。
- `merge-work-order` 当前是工单 builder（生成器）能力：根据
  `integration-review` 的 `ready_to_integrate` 结果渲染给动态 Codex
  merge worker 的任务单，写明 diff review、cherry-pick、组合测试、
  push/CI watch、CI 失败诊断、30 分钟 watch timeout、CI 通过后的 `done`
  汇报和 cleanup 归档交接；builder 本身不执行合并、不删除来源分支或
  worktree、不 force push、不 rebase 已共享分支、不重写历史。
- merge dispatch（合并派发）已接入 `loop`：Supervisor 在确认
  `ready_to_integrate` 候选后，会通过现有 `launch_session` 路径自动启动
  专门 merge worker，并把 `merge-work-order` 交给它执行；runner 本身仍不
  直接 merge、push、删除来源分支或改写历史。
  普通 worker 的通用工单仍禁止主动 push；merge worker 的通用工单会放行
  “只推送当前合并分支用于 CI watch”，避免和 `merge-work-order` 冲突。
- loop cleanup（收尾清理）当前只对 merge worker 做受限自动归档：merge
  worker 汇报 `done`，且候选已进入 `already_integrated` 后，归档托管记录
  和关联 goal；普通 done worker 留给显式 cleanup 或后续专门清理工单。
- `supervise/loop/daemon start --worker-codex-model <model>
  --worker-codex-config key=value` 可把同类覆盖传给 LLM 自动启动或恢复的
  worker，避免写代码任务继承未知的本机默认配置。
- `supervise/loop/daemon start` 默认给写代码 worker 使用 `gpt-5.5`
  和 `model_reasoning_effort="high"`。
- `guide` 默认会把 `gpt-5.5` 和
  `model_reasoning_effort="high"` 写进生成的 `loop/daemon` 命令；
  可用 `guide --worker-codex-model` 和 `guide --worker-codex-config`
  改成低成本或其他 worker 配置。
- `adopt` 可把已有 tmux 会话登记成托管 lane。
- `up` 是日常一键入口：如果后台 daemon 未运行就启动，随后显示
  daemon 状态和最近活动。
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

日常使用闭环优先按这条路径走：

0. 第一次试用：
   `isotope-supervisor start-here --goal "继续推进当前项目目标"`。
   它不会启动任务，只打印一组最短试用命令：启动后台、打开页面、
   查看状态、停止后台，以及应该反馈给开发者的观察点。
1. 启动或唤起 Supervisor：
   `isotope-supervisor up --goal "继续推进当前项目目标"`。
   `up` 会在后台 daemon 未运行时启动日常 `loop`，然后打印后台状态、
   最近 LLM 动作、执行结果、worker 状态和活跃目标。
   带 `--goal` 时会先把目标写入持久目标队列，后台 `loop` 动态读取；
   目标完成后由队列生命周期负责记录状态和归档，避免常驻进程反复执行同一显式目标。
2. 持续监督：
   `isotope-supervisor loop --interval 180` 适合前台常驻；
   `isotope-supervisor daemon start --interval 30` 适合后台常驻；
   `isotope-supervisor daemon status` 用来看后台 loop 是否还活着。
3. 追加目标：
   `isotope-supervisor goal add --cwd /path/to/repo "目标文本"`。
   目标会进入 `~/.codex/supervisor/goals.jsonl`，后续 `loop` 会动态读取，
   不必重启 daemon。
4. 查看状态：
   `isotope-supervisor check` 一次汇总 daemon、watcher、活跃目标、
   integration-review 和 cleanup 候选，适合早上看 overnight 结果；
   `isotope-supervisor goal list` 看活跃目标的最近状态、摘要和下一步；
   `isotope-supervisor dashboard` 看当前窗口分组；
   `isotope-supervisor web --host 127.0.0.1 --port 8765` 打开本机页面。
5. 提交拍板答案：
   先用 `isotope-supervisor decision list` 查看等待拍板项；
   再用
   `isotope-supervisor decision answer --request-id <request-id> --answer "你的答案"`
   记录答案。该命令只写拍板答案账本，下一轮 LLM planner 会读取
   `recent_decision_answers` 后继续判断。
6. 归档目标：
   worker 汇报 `SUPERVISOR_STATUS: done` 时，同名目标会自动归档；
   需要手动结束时，用
   `isotope-supervisor goal archive --goal-id <goal-id>`；可选
   `--status done|blocked|needs_user`、`--summary` 和 `--next-step`
   会写入 goal archive 事件，便于后续审计完成状态和下一步。
   旧托管 lane 仍用 `isotope-supervisor archive --name <lane>` 归档。

开发态：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner scan
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner dashboard
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner guide --cwd /path/to/repo --name lane-a
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner up
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner up --goal "继续推进 Supervisor 可用入口"
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner goal add --cwd /path/to/repo "继续推进 Supervisor 可用入口"
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner goal plan "拆解当前 Supervisor 高层目标" --cwd /path/to/repo --write
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner goal list
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner web
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner advise
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner supervise --interval 180 --llm-summary
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner daemon start --interval 30
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner daemon start --interval 30 --goal "持续跟进当前项目目标"
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner daemon start --interval 30 --goal-low-water 3 --goal-replenish-limit 3
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner daemon status
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner daemon watchdog
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner daemon watcher start --interval 60
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner daemon watcher status
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner daemon watcher stop
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner daemon stop
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner watch --interval 180
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner watch --interval 180 --changes-only
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner launch --name lane-a --cwd /path/to/repo --prompt "继续实现当前任务"
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner launch --backend tmux --tmux-session isotope-lane-a --name lane-a --cwd /path/to/repo --prompt "继续实现当前任务"
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner integration-review --json
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner replan --json
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner adopt --name lane-a --cwd /path/to/repo --tmux-session isotope-lane-a
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner send --name lane-a --text "继续"
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner archive --name lane-a
```

安装后：

```bash
.venv/bin/isotope-supervisor scan
.venv/bin/isotope-supervisor dashboard
.venv/bin/isotope-supervisor guide --cwd /path/to/repo --name lane-a
.venv/bin/isotope-supervisor up
.venv/bin/isotope-supervisor up --goal "继续推进 Supervisor 可用入口"
.venv/bin/isotope-supervisor goal add --cwd /path/to/repo "继续推进 Supervisor 可用入口"
.venv/bin/isotope-supervisor goal plan "拆解当前 Supervisor 高层目标" --cwd /path/to/repo --write
.venv/bin/isotope-supervisor goal list
.venv/bin/isotope-supervisor check
.venv/bin/isotope-supervisor overnight-check --json
.venv/bin/isotope-supervisor web
.venv/bin/isotope-supervisor advise
.venv/bin/isotope-supervisor supervise --interval 180 --llm-summary
.venv/bin/isotope-supervisor daemon start --interval 30
.venv/bin/isotope-supervisor daemon start --interval 30 --goal "持续跟进当前项目目标"
.venv/bin/isotope-supervisor daemon start --interval 30 --goal-low-water 3 --goal-replenish-limit 3
.venv/bin/isotope-supervisor daemon status
.venv/bin/isotope-supervisor daemon watchdog
.venv/bin/isotope-supervisor daemon watcher start --interval 60
.venv/bin/isotope-supervisor daemon watcher status
.venv/bin/isotope-supervisor daemon watcher stop
.venv/bin/isotope-supervisor daemon stop
.venv/bin/isotope-supervisor watch --interval 180
.venv/bin/isotope-supervisor watch --interval 180 --changes-only
.venv/bin/isotope-supervisor launch --name lane-a --cwd /path/to/repo --prompt "继续实现当前任务"
.venv/bin/isotope-supervisor launch --backend tmux --tmux-session isotope-lane-a --name lane-a --cwd /path/to/repo --prompt "继续实现当前任务"
.venv/bin/isotope-supervisor integration-review --json
.venv/bin/isotope-supervisor replan --json
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
如果当前没有托管进程、可旁观 tmux lane 或可恢复会话，会直接返回
`monitor`，不调用 LLM。
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
如果没有托管进程、可旁观 tmux lane 或可恢复会话，会直接回退成
`monitor`，避免无目标时请求模型或报 `target_name` 错误。

`up` 是日常推荐入口：

```bash
.venv/bin/isotope-supervisor up
.venv/bin/isotope-supervisor up --json
.venv/bin/isotope-supervisor up --no-auto-adopt
```

它会在后台 daemon 未运行时启动日常 `loop`，并立即显示 daemon 状态、
最近 LLM 动作、最近执行结果和最近 worker 状态。
如果上一轮已经启动了同名后台 worker，后续 loop 会先复用运行中的
登记记录，不会反复开新进程。
当 LLM 要启动新 worker 且目标 cwd 属于 git 仓库时，会从当前 `HEAD`
创建 `supervisor/<name>-<suffix>` 分支和 `.worktrees/supervisor/...`
工作区；如果目标 cwd 是仓库子目录，会进入隔离 worktree 里的对应子目录。
非 git 工作区不会强制隔离；git worktree 创建失败时本轮会跳过启动，
避免退回共享工作区造成文件抢写。

`guide` 是命令说明入口，会生成一组可复制命令：

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
4. `daemon start --interval 30` 后台常驻监控；
   默认写代码 worker 是 `gpt-5.5` + `model_reasoning_effort="high"`。
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
.venv/bin/isotope-supervisor daemon start --interval 30 --max-fanout-launches 2
.venv/bin/isotope-supervisor daemon start --interval 30 --worker-codex-model gpt-5.4-mini --worker-codex-config 'model_reasoning_effort="low"'
.venv/bin/isotope-supervisor daemon status
.venv/bin/isotope-supervisor daemon watchdog
.venv/bin/isotope-supervisor daemon watcher start --interval 60
.venv/bin/isotope-supervisor daemon watcher status
.venv/bin/isotope-supervisor daemon watcher stop
.venv/bin/isotope-supervisor daemon stop
```

它会启动一个后台 `loop` 进程，把状态写到
`~/.codex/supervisor/daemon.json`，日志写到
`~/.codex/supervisor/logs/daemon.log`。
`daemon start --max-fanout-launches N` 会把同轮 fanout 自动启动上限传给
后台 `loop`；`--goal-low-water N` 和 `--goal-replenish-limit N`
会把低水位补任务阈值和单轮补充上限传给后台 `loop`。
这些参数都会随原始命令写入 `daemon.json`；
`daemon status` 会检查本机进程是否还活着，并汇总最近 LLM 动作、
最近执行结果、最近 worker 模型/配置和 worker 状态；
`daemon watchdog` 会检查后台 `loop`，如果进程异常退出，
就按 `daemon.json` 里记录的原始命令重新拉起；
`daemon watcher start` 会再启动一个后台 watcher（周期看门进程），
定期执行 `watchdog`，状态写到 `~/.codex/supervisor/watcher.json`，
日志写到 `~/.codex/supervisor/logs/watcher.log`；
`daemon stop` 发送 `SIGTERM`（终止信号）并把状态标成 `stopped`。
这一步还不是系统级开机自启动；如果机器重启，仍需要重新启动 watcher。

### 过夜长跑流程

睡觉前推荐按“目标入队 -> 唤起后台 -> 看门保活”的顺序启动：

```bash
.venv/bin/isotope-supervisor goal add --cwd /path/to/repo "过夜要推进的目标"
.venv/bin/isotope-supervisor up
.venv/bin/isotope-supervisor daemon start --interval 30
.venv/bin/isotope-supervisor daemon watcher start --interval 60
```

如果只想用一条命令临时追加目标，也可以用：

```bash
.venv/bin/isotope-supervisor up --goal "过夜要推进的目标"
```

`goal add` 只是把目标写入持久队列；`up` 会在 daemon 未运行时启动后台
`loop` 并立刻打印最近状态；`daemon start` 适合显式确认后台常驻参数；
`daemon watcher start` 会周期触发 watchdog，后台 loop 异常退出时按记录命令
重启。当前自动化可以根据活跃目标启动写代码 worker，也可以在
`integration-review` 出现 `ready_to_integrate` 候选后启动 merge worker；
但它仍然不是无人值守发布系统，早上必须人工看 CI、merge conflict
（合并冲突）和 `blocked/needs_user` 状态。

早上先用这些只读命令收口：

```bash
.venv/bin/isotope-supervisor daemon status
.venv/bin/isotope-supervisor daemon watcher status
.venv/bin/isotope-supervisor goal list
.venv/bin/isotope-supervisor integration-review
.venv/bin/isotope-supervisor cleanup list
```

`daemon status` 看后台 loop 是否还活着、最近 LLM 动作和 worker 状态；
`goal list` 看目标是否完成、阻塞或等待拍板；`integration-review` 看哪些
worker 已经可审、已合入或有冲突风险；`cleanup list` 只列出可归档的完成项。
如果看到 CI 失败、冲突风险、`blocked` 或 `needs_user`，先处理这些证据，
再决定是否继续 `goal add`、重跑 daemon，或让 merge worker 继续。

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
.venv/bin/python -m pytest tests/isotope -q
python -m isotope.demo
python -m isotope.demo --json

.venv/bin/isotope-supervisor daemon watchdog --codex-home "$SMOKE_HOME"
.venv/bin/isotope-supervisor daemon watcher start --codex-home "$SMOKE_HOME" --interval 60
.venv/bin/isotope-supervisor daemon watcher status --codex-home "$SMOKE_HOME"
```

通过标准：

- 本机测试与 demo smoke 通过；远端 CI 只在本轮允许 push 或已有 PR 时检查
  GitHub Actions 的 `CI / smoke (3.13)` 和 `CI / smoke (3.14)`。
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

## 当前边界

- 以下边界是 guardrail（护栏），不是产品目标。
  不得据此把用户要求的 AI 功能降级成规则脚本或诊断工具。
- 不接管普通终端窗口；当前控制通道依赖已登记的 tmux 会话。
- `send` 只支持 Supervisor 登记过的 tmux 会话。
- `web` 只监听本机默认地址，不提供认证和远程访问能力。
- `web` 的 `/managed/send` 只接受 `send_status` 和 `send_continue`。
- `web` 的 `/decision/answer` 只接受 `request_id` 和 `answer`，
  用于记录用户拍板答案。
- `web` 的 `/llm-action` 只在手动点击时调用模型，只展示建议；
  解析时会容忍 JSON 前后的说明文字。
- `web` 的 `/events` 只推送 bell 提醒和心跳，不承载任意控制指令。
- 模型建议只会高亮按钮，不会自动点击按钮。
- `/managed/send` 成功发送后会记录 lane state。
- `recommendation` 只表示建议动作，不会自动调用 `send`。
- `advise` 默认只生成命令草案；`--execute` 只允许执行
  `send_status` 和 `send_continue`。
- `--llm-action` 只输出模型建议动作，不自动执行。
  如果用户要求 AI 自动管理，应另设计真实 LLM 执行闭环，
  不能停在按钮高亮或建议展示。
- `guide` 只打印命令，不启动 tmux、不调用模型、不发送指令。
- `loop` 是 `supervise --auto-execute --changes-only --bell --interval 30`
  的日常入口。
- `daemon start` 只是把 `loop` 放进后台，并记录 pid（进程号）、
  命令和日志路径。
- `daemon watchdog` 只复用状态文件里的原始命令，不重新猜参数。
- `daemon start --max-fanout-launches N`、`--goal-low-water N` 和
  `--goal-replenish-limit N` 会随原始命令保存，watchdog 重启后
  继续使用同一组 fanout / 低水位补任务参数。
- `daemon watcher` 只负责周期触发 watchdog，不直接判断业务状态。
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
