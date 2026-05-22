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
| 用户功能层 | `start-here`、`scan`、`dashboard`、`trace`、`guide`、`up`、`discover`、`web`、`watch`、`advise`、`supervise`、`loop`、`daemon` | `features/supervisor/runner.py` | 面向人类使用的命令入口 |
| 托管控制层 | `launch`、`adopt`、`send`、`archive`、托管登记 | `features/supervisor/registry.py` | 管理 Supervisor 登记的 Codex |
| Worker 审查层 | `worker-review`、`integration-review`、`replan` | `features/supervisor/worker_review.py`、`features/supervisor/integration_review.py`、`features/supervisor/replan.py`、`features/supervisor/runner.py` | 汇总已托管 worker 的 worktree、branch、状态协议、改动、复查提示、合并提示、只读集成分组和下一轮候选 |
| Merge 工单层 | `merge-work-order` builder、merge dispatch | `features/supervisor/merge_work_order.py`、`features/supervisor/merge_dispatch.py`、`features/supervisor/runner.py` | 根据 `integration-review` 生成动态 merge worker 工单，并由 `loop` 在有 `ready_to_integrate` 候选时自动启动专门 merge worker |
| Codex 执行通道 | `resume`、`codex exec resume`、`--last` | `features/supervisor/runner.py`、`features/supervisor/registry.py` | 不依赖 tmux 恢复历史会话并投喂新 prompt |
| 上下文能力层 | `context`、`request_context`、上下文结果记录 | `features/supervisor/context.py`、`features/supervisor/runner.py` | LLM 按需请求检索项目资料，BM25 后端按 query 对文档和代码候选排序，不固定注入全文 |
| Codex 集成层 | 读取 Codex session（会话记录）、索引标题和 agent 元数据 | `features/supervisor/flow.py` | 当前读取本机 `.jsonl`、`session_index.jsonl` 和 SQLite |
| 扫描优化层 | 最近候选、首尾读取和标题兜底 | `features/supervisor/flow.py` | 避免每次页面刷新全量读历史 |
| tmux 集成层 | tmux 启动、buffer/paste 发送和 bell hook | `bell_events.py`、`flow.py`、`registry.py` | 只控制登记过的 tmux 会话 |
| 状态判断层 | 工作中、等待用户、疑似停住、疑似报错 | `features/supervisor/flow.py` | 规则提供候选和证据，不替代 LLM 判断 |
| 状态依据层 | `status_evidence` 说明每个状态标签的来源 | `features/supervisor/flow.py` | 避免只给结论、不说明证据 |
| 建议执行层 | `recommendation`、`command_suggestions`、`--execute` | `flow.py`、`runner.py` | 只允许白名单动作 |
| 模型管理层 | `LLM summary`、`LLM planner` 和 TOML 号池 | `llm_summary.py` | 承担判断、调度和动作选择的 AI 路径 |
| 状态协议层 | `SUPERVISOR_STATUS` 等状态协议 | `flow.py`、`registry.py` | 给被托管 Codex 主动汇报状态 |
| 状态账本层 | lane state（窗口状态）和限频 | `lane_state.py` | 避免重复催促和刷屏 |
| 生命周期观测层 | `trace --json` | `features/supervisor/runner.py` | 只读汇总 goal、worker、decision、merge/repair 和 cleanup 台账 |
| 通知桥接层 | Supervisor event notifications/webhooks | `features/supervisor/notifications.py`、`features/notifications/flow.py` | 把 goal/decision/integration-review 事件派生成低敏通知或外部 POST |
| 本地前端层 | `web`、`/dashboard.json`、`/events`、`/managed/send`、`/llm-action`、`/goal/add`、daemon/watcher 控制接口 | `features/supervisor/web.py` | 本机视图、bell 事件、目标写入、白名单发送、后台循环控制和手动模型建议入口 |

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
- `web` 等待拍板列表可填写答案并提交到 `/decision/answer`，
  只记录 `decision answer` 事件，不开放任意文本发送。
- `dashboard JSON` 和 `web` 会读取通知索引，展示通知列表、未读数量、
  标题、类型和低敏来源摘要；输出层会按 allowlist 再过滤
  `source_ref`，避免把 prompt/log/key 类字段暴露到页面；web 默认折叠
  通知列表，只显示未读/总数和最近摘要，展开后最多显示最近 50 条。
- `web` 会用“运行焦点”把后台循环、需要看的 Codex 窗口、工作中的
  Codex 窗口、当前目标和前三个重点项放到页面顶部，并优先显示当前
  Web 工作区内的 Codex 窗口，先给运行结论。
- `dashboard JSON` 和 `web` 会输出“当前批次”，把仍活跃的
  `active_goals` 与当前托管 worker 从历史 done/stale session 中分离。
- `web` 会用“Worker 详情”集中展示当前 worker 的身份、工作区、
  worktree、branch、状态依据、下一步、状态协议和最近输出。
- `web` 会用“Supervisor 控制台”直接启动/停止 daemon 后台循环和
  watcher 看门进程，并复用页面刷新展示最新状态。
- `web` 会用“目标队列”展示 active goals，并通过 `/goal/add`
  写入新的 Supervisor 目标，默认 cwd 是 Web server 当前工作区。
- `web` 会通过 `/goal/plan` 复用现有 AI goal planner，把自然语言目标
  先转成可审阅预览；页面可编辑目标和并行批次顺序，再由“写入规划目标”
  批量进入目标队列；写入复用编辑后的 candidates，不再二次调用 LLM。
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
- process worker 如果进程已退出且最后明确汇报过 `SUPERVISOR_STATUS: working`，
  或检测到非零退出 / 显式 `--max-run-minutes` 超时，`loop` 会按同名 lane
  的 `worker_retry_count` 最多自动重启 2 次；每次重启仍走
  `launch_managed_codex` 登记表和现有 worker model 配置。
- `worker-review` 是已完成 worker 的收集/审查入口，会读取托管登记、
  process log 状态协议、cwd/worktree 是否存在、当前 branch、`git status`
  和 `git diff --stat` 摘要，并输出建议验证命令、复查提示
  （reviewer prompt）、可复制 `codex exec -C ...` 复查命令与
  主控/人工合并提示；同时输出 `next_decision`，区分合并候选、
  继续拆任务、缺失 worktree 和可归档项，并把这些决策投影成结构化
  `automation_candidates`，供后续主循环读取；它只做高可信汇总，
  不自动合并、不删除 worktree 或分支。
- `integration-review` 是 managed worker 集成前只读分组入口，会读取
  branch、worker HEAD、base commit、`main` 是否已包含 worker HEAD、
  worktree 是否干净和 `merge-tree --write-tree` 冲突结果，输出
  `ready_to_integrate`、`already_integrated`、`needs_review` 和
  `conflict_risk`；默认只看未归档、已汇报 done 且 worktree 仍存在的
  worker，显式传 `--include-unfinished` 才纳入未完成历史，
  `--include-missing-worktrees` 才纳入缺失 worktree 历史；它不执行
  merge、push、delete 或归档。
- `delete_worktree` 是受控清理动作，可由 LLM planner 显式输出，也可通过
  `cleanup delete-worktree` 手动触发；两者都必须带
  `confirm_delete_worktree=true`，runner 会重新确认对应 managed worker 已
  `done`、登记表最后状态已 `archived`、当前 integration review 已是
  `already_integrated`，且目标目录是 repo 内
  `.worktrees/supervisor/<worker>`，才执行 `git worktree remove`。
- 普通 done worker 不再由 `loop` 自动归档或删除 worktree；
  它们留给显式 `cleanup list/archive` 或后续 merge worker 流程处理。
- `loop` 只会对 merge worker 及其已集成 source worker 做受限自动归档：
  merge worker 本身汇报
  `SUPERVISOR_STATUS=done`，且它工单里的候选 worker 已全部进入
  `integration-review.already_integrated` 时，才归档 source worker 和
  merge worker 的 managed 记录、关联 merge goal，并写入低敏通知；随后只
  对本轮刚归档的 source/merge worktree 尝试 `delete_worktree` 清理。
  它不删除来源分支、不删除 merge worker 分支，不顺手清理其他历史
  worktree。
- `replan` CLI 会读取 `worker-review` 的 `automation_candidates`、当前
  active goals，以及 `integration-review` 的 `ready_to_integrate`、
  `already_integrated`、`needs_review`、`conflict_risk` 分组，生成下一轮
  只读建议和可交给动态 Codex worker 复查的合并候选；输出可用 plain 或
  `--json`，不自动合并、不自动归档、不删除 worktree 或分支。
- `merge-work-order` builder 会把 `integration-review` 的
  `ready_to_integrate` 候选渲染成给动态 Codex merge worker 的任务单：
  包含目标 base ref、merge candidates、excluded workers、diff review、
  cherry-pick、组合测试、push/CI watch、CI 失败诊断、30 分钟 watch
  timeout、CI 通过后的 `done` 汇报和 cleanup 归档交接。它只生成工单文本，
  不执行 merge、不 push、不删除分支或 worktree，也不 force push、不 rebase
  已共享分支、不重写历史。
- merge dispatch 已接入 `loop`：读取 `integration-review` 产出的
  `ready_to_integrate` 候选，调用 `merge-work-order` builder 生成工单，
  再通过现有 `launch_session` 路径启动专门 merge worker。
- LLM planner 会看到仍在运行的 process 托管记录作为候选目标，避免状态面板
  误报“只有 tmux 才可控”；已完成的后台 worker 转入
  `worker-review`/`cleanup`，不再被常驻 `loop` 反复催促。
- `launch_session` 会写入 lane state 并遵守 `--prompt-cooldown`，
  发现同名后台 process worker 仍在运行时会跳过，避免长跑时对同一个
  `target_name` 反复启动后台 Codex。
- process worker 非零退出或显式 `--max-run-minutes` 超时会把失败原因
  写入 lane state（含 `timeout`/`exit_code`、stderr 摘要和托管记录 id），
  并自动重试 2 次；重试仍失败后会生成 `worker_retry_failed` 拍板请求，
  daemon status 和 dashboard 会展示失败状态，避免同名目标无限重启。
- LLM 自动 `launch_session` 默认把 git 仓库任务放进
  `.worktrees/supervisor/...` 独立工作区；子目录任务会进入隔离
  worktree 里的对应子目录。非 git 工作区不强制隔离，git worktree
  创建失败时跳过启动，避免退回共享工作区抢文件。
- `launch/resume` 可用 `--codex-model`、`--codex-config` 覆盖
  Codex worker 配置；`supervise/loop/daemon start` 可用
  `--worker-profile`、`--worker-codex-model`、`--worker-codex-config` 把配置传给
  LLM 自动启动或恢复的后台 worker。
- `supervise/loop/daemon start` 默认给写代码 worker 使用 `gpt-5.5`
  和 `model_reasoning_effort="high"`；`guide` 会生成同样默认值的
  日常 `loop/daemon` 命令。
- `worker_profile` 目前有 `coding` 和 `light`：`coding` 保持
  `gpt-5.5 high` 写代码默认，`light` 用于只读检查、状态汇报和 smoke，
  默认降到 `model_reasoning_effort="low"`。
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
- `supervise/loop/up/daemon start --goal <目标>` 会把用户目标交给
  LLM planner；没有现成托管窗口时，模型仍可基于该目标选择
  `request_context` 或 `launch_session`，启动新的后台 Codex worker。
- `goal add/list/archive` 是持久目标队列入口；`goal add "目标文本"`
  支持一句话直接入队；`goal archive --goal-id <goal-id>` 可附带
  `--status`、`--summary`、`--next-step`，把最终状态、完成摘要和下一步
  写入 goal archive 事件；`goal plan "高层目标"` 是显式
  AI-first 目标规划入口，读取 `docs/current/status.md`、
  `docs/current/agent-task-queue.md` 和
  `docs/current/supervisor-capability-map.md` 后，围绕用户高层目标
  让 LLM 生成候选目标；`--limit` 表示建议首批并发上限，
  不再截断完整规划结果；当高层目标覆盖完整功能板块时，同时输出
  可审阅的计划摘要、阶段/批次、并行建议、停止条件和验收条件。
  默认只预览，只有传 `--write` 才写入 `supervisor/goals.jsonl`；
  goal planner 会从 JSON、TOML 软语法输出中用本地解析器提取可用 goals；
  中文条目等非结构化输出再交给 LLM 修复成 goals JSON，并忽略后续非 goal JSON 片段。
  日常 `loop` 没有显式 `--goal` 时会读取最早活跃目标，
  并保持 daemon 启动命令不绑定某一个队列目标。
- `loop/up/daemon start --goal-low-water N` 是低水位补任务入口：
  当活跃目标少于 N 个且当前 loop 没有指定单 lane 或显式目标时，
  Supervisor 会调用同一个 goal planner 读取当前文档并写入新 goals；
  `--goal-replenish-limit` 控制单轮补充上限，
  `--goal-replenish-prompt` 可覆盖默认规划说明。
- `loop` 会把同名 worker 的 `SUPERVISOR_STATUS` 写回目标队列；
  `done` 自动归档，`blocked/needs_user` 只记录状态并等待后续处理。
  当同一轮 fanout worker 全部汇报 `done` 时，`loop --json` 会输出
  `fanout_status.status=completed` 和每个 worker 的摘要；当 fanout 中任一
  worker 汇报 `blocked/needs_user` 时，`fanout_status.status=paused`，
  本轮不再继续 fanout 扩展，并依赖 goal status notification 提醒用户。
- `blocked/needs_user` 活跃目标会带着 `last_status`、摘要和下一步进入
  LLM planner 的 `active_goals` 输入；模型不能默认停住，应重新选择
  `request_context`、`launch_session`、`ask_user` 或 `monitor`。缺少上下文
  时 prompt 会额外提供 `blocked_context_priority`，要求先考虑
  `request_context`，检索后仍无法判断且满足拍板 gate 时才 `ask_user`。
- 存在 `active_goals` 时，LLM prompt 和动作校验都会使用收窄后的
  目标相关 command suggestions，旧普通 session 的 `resume_session`
  不能绕过校验抢走新目标。
- 目标级 `ask_user` 可用 `goal_id` 写入 decision request；这解决了
  队列目标已阻塞但没有普通 Codex session 可恢复时的拍板记录问题。
- goal 状态回写、decision request/answer 和通过 `integration-review` 的
  done worker 会尽力生成低敏通知或 webhook；notification index 损坏、
  本地写入失败或外部 POST 失败都不能破坏原 goal/decision 账本。
- `loop/up/daemon start --decision-timeout <秒>` 会扫描活跃 decision
  request；超过阈值时写入 lane state、生成
  `supervisor_decision_timeout` 低敏通知，并在本轮 payload 输出
  `decision_timeout_alerts`；同一个 request 不重复提醒，answer/archive
  会清理对应 timeout 状态。
- `cleanup list/archive` 会列出可归档的 done goal、done managed worker
  和未读 done 通知；归档不删除 Codex 历史，tmux worker 会读取当前
  pane 文本，避免用旧 log 误归档仍在工作的窗口。
- `trace --json` 是只读生命周期观测入口，会把 active goals、managed
  workers、decision requests、merge/repair worker 和 archived workers
  聚合成一个阶段化 payload，方便排查长跑链路停在目标、执行、拍板、
  合并修复还是清理。
- `start-here` 是第一次试用入口，只打印“启动后台、打开页面、看状态、
  反馈观察点、停止后台”的最短路径，不展开高级命令清单。
- `loop --json` 每轮也会带 `lifecycle_trace`，读取本轮执行后的同一套
  台账摘要，让 daemon 日志直接留下长跑链路证据；刚启动 worker 且没有
  拍板或清理项时，`next_attention.kind` 会显示 `wait_workers`，避免把
  “等待 worker 完成”误写成继续拆目标。
- `goal list` 和 `daemon status` 会合并活跃目标的最近状态、
  摘要和下一步，便于直接看阻塞原因。
- `daemon start/status/stop` 可把 `loop` 放到后台常驻，记录
  pid（进程号）、命令、状态文件和日志路径。
- `daemon start` 的后台 loop 使用 Python `-u` 非缓冲输出，避免
  自动动作已经发生但 `daemon.log` 仍为空。
- `daemon start --max-fanout-launches N` 会把同轮 fanout 自动启动上限
  透传给后台 `loop`；watchdog 重启时仍复用状态文件里的原始命令。
- `loop/up/daemon start --merge-dispatch-execute --auto-merge-promote`
  会启用合并后半段自动化：启动 merge-dispatch、合回 main，
  并在 merge worker 阻塞时启动同 worktree 的 `merge_repair`。
- `daemon start` 会把低水位补任务参数透传给后台 `loop`，
  watchdog 重启时继续复用同一低水位策略。
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
- 本机目标队列事件文件 `goals.jsonl`，保存目标添加、状态和归档事件。
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
- `context` 支持按 query 检索当前工作区资料，当前会基于文档和代码文件
  构建 BM25 候选索引，并会为 `docs/current/status.md`、
  `supervisor-capability-map.md`、`docs-map.md` 和 Supervisor 关键代码入口
  补充项目上下文锚点，把结果记录给后续 LLM planner 使用；结果会带
  `source_group` 和更清晰的 `match_reason`，让 `docs/current` 与
  `src/isotope/features/supervisor` 命中不再只是散乱关键词。
- `--llm-execute` 执行 `request_context` 后会在同一轮把检索结果交回
  LLM planner，再执行一次后续受控动作；同轮只允许一次上下文检索，避免循环。
- 已完成会话不再作为 `resume_session` 候选，避免 LLM 把旧验收窗口反复唤醒；
  但其工作目录仍可用于 `launch_session` 和 `request_context`。
- `resume_session` 会写入 lane state，并受 `--prompt-cooldown` 和
  `--max-continue-count` 约束；如果目标 session 所在 cwd 已有
  后台 process worker 仍在运行，会跳过恢复，避免同一个工作区被
  多个后台 Codex 重复驱动；已删除 worktree 或不存在 cwd 不再作为
  resume/context/launch 的正常候选，LLM 误选时只记录 skipped；
  LLM 临时空响应、非 JSON、worker 启动失败、resume/context 检索失败
  和 merge dispatch 派发失败会写入 `supervisor/failure_events.jsonl`；
  同一 lane 同类失败超过 `--max-failure-retries`（默认 3）后，
  会自动生成 `ask_user` 拍板请求并复用低敏通知桥接层。
- `delete_worktree` 是 deny-by-default（默认拒绝）的受控动作：LLM 只能
  对已知且 cwd 已缺失的 worker 表达清理意图；执行层固定 skipped，
  不自动删除目录、分支或登记。
- `ask_user` 是拍板请求动作，可绑定普通 session 或持久 `goal_id`，
  必须同时满足：Codex 明确请求拍板、
  LLM 无法从用户既有指示判断、上下文检索缺失/过时/冲突。
- `advise --llm-action` 和 web `/llm-action` 会读取最近 context
  结果；合法 `ask_user` 会显示“等待拍板”、问题和 `context_status`。
- `--llm-execute` 执行合法 `ask_user` 时会写入
  `supervisor/decision_requests.jsonl`；dashboard 和 web 会读取成
  稳定拍板列表；同一 `session_id` 和问题已有活跃请求时会复用旧项，
  不重复追加和通知。
- `decision list` 可查看活跃拍板项；`decision answer --request-id <id>
  --answer <答案>` 会写入用户答案并移出活跃拍板项，后续 LLM planner
  会收到 `recent_decision_answers`；web 可通过 `/decision/answer`
  执行同一受控记录；`decision archive --request-id <id>`
  只用于无需继续的项。
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
- LLM 或显式执行 `send_status/send_continue` 前，会在执行层检查
  托管 tmux pane 是否仍显示 `Working ... esc to interrupt`；
  若仍在工作则跳过发送，避免打断正在输出的交互式 Codex。
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
- 显式 `--goal` 会作为用户目标进入 `launch_session` 和
  `request_context` 候选，不要求用户先手动创建 tmux 或历史会话。
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
`--max-run-minutes`、worker 自动重启上限 `--max-worker-retry-count`，
以及失败重试护栏 `--max-failure-retries`：
`--max-continue-count` 用 lane state 记录 `continue_count`，
限制同一 lane 同一状态下的继续推进；`--max-context-requests`
限制同一 supervise/loop 轮次里 `request_context` 的执行次数；
`--max-run-minutes` 按托管登记的
`started_at` 判断同名 lane 是否已超时，超时后纳入 worker 自动重启路径；
`--max-worker-retry-count` 默认 2，耗尽后生成 `worker_retry_failed` 拍板请求；
`--max-failure-retries` 默认 3，超过后生成 `needs_user` 类拍板请求。
`--max-continue-count`、`--max-context-requests` 和 `--max-run-minutes`
默认值都是 0，表示不启用限制；只有显式传入正数阈值时才会拦截，
避免阻碍需要长时间运行的任务。`--max-worker-retry-count` 默认开启，
用于减少需要人工手动重启 worker 的场景。
当前回归测试已覆盖默认宽松预算下，多 lane loop 连续推进不同
托管窗口。

当前 A 层字段：

- `goal`：本次要完成什么。
- `cwd`：执行所在工作区。
- `allowed_scope`：允许改哪些目录或模块。
- `forbidden_scope`：明确不碰什么。
- `budget_hint`：写给 worker 的时间、轮次和上下文请求提醒。
- `done_conditions`：什么证据算完成。
- `completion_template`：写清 `done`、`needs_user`、`blocked`
  的使用条件，并要求 summary 带验证证据、提交哈希和剩余风险；
  这里只描述 status value，不写会被日志解析器误判的状态示例行。
- `integration_review_marker`：要求 worker 保持 worktree 干净，并把最终
  commit 写进 summary；base 分支包含该 commit 或等价补丁后，
  `integration-review` 会归入 `already_integrated`。
- `ask_user_conditions`：只有哪些情况能停下来问用户。
- `report_protocol`：最后按 `SUPERVISOR_STATUS/SUMMARY/NEXT` 汇报。

## Merge Worker 交接边界

动态合并 worker 分成四个职责，不要混在一个入口里：

- `integration-review`：只读扫描 managed worker，按
  `ready_to_integrate`、`already_integrated`、`needs_review` 和
  `conflict_risk` 分组；它负责回答“哪些 worker 看起来能进合并复查”，
  不执行 merge/push/delete。
- `replan`：读取 worker 审查、活跃目标和集成分组，生成下一轮建议和
  merge candidates；它负责回答“下一轮应该复查哪些候选”，不自动合并、
  不归档、不删除分支。
- `merge-work-order`：把 ready 候选渲染成专门给 merge worker 的工单；
  它负责回答“merge worker 应按什么步骤复查、cherry-pick、测试和
  watch CI”，但 builder 本身不碰 git 状态。
- merge dispatch：已接入 `loop` 的派发层；它负责在候选明确时自动启动
  merge worker，并把 `merge-work-order` 交给 worker。

当前阶段的安全线：Supervisor 可以自动启动 merge worker；当 merge worker
的验证分支 CI 成功且它汇报 `done` 后，runner 可受控 fast-forward `main`、
push `main` 并等待 main CI；除此之外 runner 不直接
cherry-pick、删除 worker 分支或来源历史。唯一允许的删除动作是
`delete_worktree`：只清理已完成、已归档、已集成的
`.worktrees/supervisor/<worker>`，不 force push，不 rebase 已共享分支，
不重写远端历史。
`launch_session` 的通用工单默认禁止主动 push；merge dispatch worker
例外，只允许按 `merge-work-order` 推送当前合并分支用于 CI watch。

merge worker 成功合入后的交接边界也要分清：

- merge worker 可在工单范围内完成 diff review、cherry-pick、组合测试、
  推送验证分支和 CI watch；只有验证分支 CI 明确通过并能给出提交哈希、
  CI run id 和 conclusion 时，才能汇报 `SUPERVISOR_STATUS: done`。
  CI 失败或超过 30 分钟未结束时必须汇报 `blocked`，并保留 merge worktree
  供后续复查。
- `loop` 会在主工作区看到 done merge worker 后，确认验证分支 CI 为
  `success`，再要求当前工作区位于干净的 `main`，执行 `git merge --ff-only`
  到 merge worker 提交、`git push origin main`，并等待 main CI 成功；
  promotion 结果会写入 `merge_promotions`。验证分支 CI、main 工作区、
  fast-forward、push 或 main CI 任一 gate 失败时，会写入
  `merge_promotion_failed` 拍板请求，并在请求的 gate 中保留失败原因、
  分支、worker commit 和 CI payload。用户回答“放弃/不再/abandon/drop”
  后，`loop` 会把该 merge worker 标记为 `skipped_by_decision`，
  不再重复查 CI 或重复生成同一拍板请求；用户回答“修复/fix/repair”后，
  `loop` 会在独立 worktree 启动 `worker_role=merge_repair` 的 repair
  worker；该 repair worker 汇报 done 后，后续 loop 会带上
  `repair_completed` 证据并重新走 promotion gate；promotion 成功后会
  归档对应 repair worker 的 managed 记录；用户回答“重试/retry”后，
  后续 loop 也会重新走 promotion gate。
- `cleanup list/archive/delete-worktree` 是生命周期清理入口；`list` 会展示
  可归档项和可删除 worktree 候选，`archive` 只把已完成的 goal、managed
  worker 或通知标记为已处理，`delete-worktree` 复用 `delete_worktree`
  护栏删除已归档且已集成的 Supervisor worktree。它不删除 Codex 历史、
  不删除 git branch。
- 当前自动边界到“派发 merge worker”、“验证分支成功后 fast-forward main
  并 watch main CI”、“集成后归档 source/merge worker”和“清理本轮刚归档且
  已集成的 source/merge worktree”为止；
  普通 ready/already-integrated worker 不由 `loop` 自动归档或删除；
  删除 worktree 仍必须走显式 cleanup/delete-worktree 护栏或后续专门清理工单。
- `git worktree remove` 仍属于受控清理动作：需要先确认来源工作已被目标分支包含、
  没有未提交改动、没有活跃 managed record 仍在运行，再由 loop cleanup 或显式
  `delete_worktree` 执行。

## Runner 接线边界

本节只登记后续接入 `features/supervisor/runner.py` 时的分工。
`runner.py` 当前仍是 Supervisor CLI 入口和受控动作编排层，
不应被扩成新的目标队列、worker registry、LLM provider 或真实代码合并器。

### 现有输入与归属

| 接线点 | 当前归属 | 后续接入边界 |
| --- | --- | --- |
| `current_batch` | dashboard/web read model（读取模型） | 只展示仍活跃的 `active_goals` 和当前托管 worker；不启动 worker、不改目标状态、不替代 cleanup。 |
| `fanout` | `loop` 与 `goal plan --fanout-execute` | 把多个活跃目标或 `parallel_recommendations` 展开成一批受控 `launch_session`；复用 goal queue、managed registry、prompt cooldown 和预算 gate，不另建队列。 |
| `replan` | `_maybe_replan_after_context_request` | 只在同一轮 `request_context` 成功后追加最近上下文，再让 LLM planner 重新选择一次受控动作；不得无限循环，不得绕过 `ask_user` gate。 |
| `merge dispatch` | 已接入 runner loop | 读取 `ready_to_integrate` 候选，生成 `merge-work-order`，再用现有 `launch_session` 路径启动专门 merge worker；登记表写入 `worker_role=merge_dispatch`，runner 本身不得直接 cherry-pick、delete branch 或改写历史。 |

### 建议调用顺序

`current_batch`、低水位补任务、`fanout`、`replan` 接进 runner 时，顺序保持：

1. `scan/report`：先读取 Codex session、managed registry、目标状态和工作区存在性。
2. `low-water goal replenishment`：活跃目标低于显式阈值时，先让 LLM
   根据当前文档补充目标队列。
3. `current_batch`：投影当前仍可推进的目标和 worker，过滤 done、已归档、已删除 worktree。
4. `fanout planning/execution`：如果存在多个可推进目标或 goal plan 的 `parallel_recommendations`，生成受控候选并在并发上限内执行；跳过已有同名运行中 worker 的目标。
5. `merge dispatch`：fanout 不适用且 `integration-review` 给出
   `ready_to_integrate` 候选时，生成 `merge-work-order` 并启动专门
   merge worker；如果当前工作区本身是 `merge_dispatch`、`merge_repair`
   或 cleanup worker，则跳过自动 cleanup、promotion 和新的 merge
   dispatch，避免递归嵌套。
6. `LLM planner`：fanout 和 merge dispatch 都不适用时，在 `active_goals`、recent context、worker review 和白名单命令内选择一个动作。
7. `execute`：只执行通过校验的 `request_context`、`launch_session`、`resume_session`、send 或 `ask_user`。
8. `replan`：只有本轮执行的是成功的 `request_context` 时，才把检索结果加入 prompt，再执行一次 follow-up 动作。
9. `current_batch refresh`：fanout 或 merge dispatch 同轮执行了 `launch_session` 后，
   `loop --json` 会刷新一次 `current_batch`；下一轮 dashboard/web
   继续反映 worker、goal status 或 decision request 的变化。

### 验收命令

最小回归应覆盖三类接线点：

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_codex_supervisor_readonly.py::test_codex_supervisor_dashboard_json_separates_current_batch_from_deleted_worktree_history -q
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_codex_supervisor_readonly.py::test_codex_supervisor_runner_loop_fanout_launches_parallel_active_goals -q
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_codex_supervisor_readonly.py::test_codex_supervisor_runner_daemon_start_passes_max_fanout_launches_to_loop -q
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_codex_supervisor_readonly.py::test_codex_supervisor_runner_loop_suggests_all_active_goals -q
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_codex_supervisor_readonly.py::test_codex_supervisor_runner_supervise_request_context_replans_same_iteration -q
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_codex_supervisor_readonly.py::test_codex_supervisor_runner_loop_replans_blocked_goal_with_llm_context -q
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_supervisor_goal_replenishment.py -q
```

fanout 回归必须覆盖：多个 active goals 中已有同名 running worker 时，只能为剩余目标执行
`launch_session`，并且同轮 `loop` payload 与随后 `dashboard` 的
`current_batch` 都能看见当前 worker；所有 fanout worker 同轮完成时要输出
`fanout_status` 完成摘要；任一 fanout worker 汇报 `blocked/needs_user` 时要
暂停 fanout 扩展并保留通知证据；显式 `goal plan --fanout-execute` 和
低水位补任务返回的 `parallel_recommendations` 都必须复用同一条受控
`launch_session` fanout 路径，且不能直接归档任何目标。

## 后续目标补给设计

目标补给是下一阶段让 Supervisor 真正持续工作到明早的 B 层机制。
它不替代现有 `goal add/plan`、`fanout`、`daemon` 和 worker registry，
而是在每轮 `loop` 开头读取一个用户给定的 `goal seed`（目标种子）和
当前活跃目标水位，决定是否补充新的可执行 goal。

推荐规则：

1. `goal seed` 只保存高层方向、允许范围、禁区、预算提示和验收口径。
   它不是正在执行的 goal，也不能被 worker 直接消费；补给器必须把它
   拆成小目标后写入现有 goal queue。
2. 低水位补充以“可推进 active goals 数量”为判断口径，而不是只看
   `goals.jsonl` 行数。`done`、`blocked`、已归档、同名 worker
   正在执行的目标、明确 `needs_user` 且没有新答案的目标，都不计入
   可补给水位。
3. 同一轮补给必须受最大任务数约束：先用全局 active goal 上限控制
   队列规模，再用 `--max-fanout-launches` 控制同轮启动数。补给可以写入
   多个候选 goal，但不能绕过 fanout 上限一次性启动所有 worker。
4. 补给前要做冲突检查：同名或同 scope worker 正在运行时不重复发放；
   `integration-review` 已标记 `conflict_risk` 的分支不再继续生成同一区域
   写代码任务；存在未处理 merge worker 时，优先等待 merge 结果。
5. 停止条件必须比“还有 seed”优先：CI 红灯、merge conflict、worker
   汇报 `blocked/needs_user` 且需要人类拍板、连续补给没有产生完成结果、
   或达到用户给定时间/任务预算时，补给器只能写 decision request 或
   `monitor`，不得继续扩散新任务。

接线位置应保持保守：补给器只在 `scan/report` 之后、`fanout` 之前运行，
产物仍是普通 active goals；后面的 fanout、merge dispatch、LLM planner
继续复用现有动作白名单和 budget gate。这样下一阶段实现时只需要新增
“何时补目标、补几个、何时停”的决策层，不需要再造目标队列或新 worker
启动通道。

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
- 拍板已处理后，不要手删 JSONL；有答案用 `decision answer`，
  无需继续才用 `decision archive`。
- 不要只展示状态标签而不展示判断依据。
- 不要另写一套 dashboard 数据接口，先复用 `/dashboard.json`。
- 不要把 `/events` 做成控制通道；它只负责提醒前端刷新。
- 不要在页面重复展示同一个托管 Codex 的 lane 视角和 session 视角。
- 不要在 web 里放任意文本发送框；先走白名单动作。
- web 的拍板答案表单只写 `decision_answer`，不向托管 Codex 直接发任意文本。
- 不要让 `/llm-action` 自动调用 `/managed/send`。
- 高亮模型建议不等于执行动作，执行必须由人类点击或显式参数触发。
- 没有可控托管目标时，不要为了动作建议调用 LLM。
- LLM 动作选择必须落到可审计的白名单能力上。
- 不要把 `integration-review`、`replan` 或 `merge-work-order` 的候选结果
  当成自动删除分支、force push、rebase 已共享分支或重写历史的授权；
  worktree 清理必须走 `delete_worktree` 的归档、集成和路径护栏。

## 后续拆分方向

- `features/supervisor/status.py`：后续可下沉状态分类和状态依据生成。
- `features/supervisor/advice.py`：建议、命令草案、自动策略和执行白名单。
- `features/supervisor/protocol.py`：后续可下沉状态协议解析和提示语注入。
- `features/supervisor/tmux_control.py`：后续可下沉 tmux 会话、发送和 bell hook。
- `features/supervisor/lane_state.py`：每个窗口的最近状态、催促次数和限频。
- `integrations/codex/session_reader.py`：后续可把 Codex `.jsonl` 读取下沉。

## 下一步顺序

1. 用真实 daemon 长跑验证 cleanup/current dashboard 在多批任务中的稳定性。
2. 后续再决定是否把通知接到更多 worker 生命周期事件。
3. 再拆分 `runner.py` 中的匹配、建议和 tmux 控制代码。

## 登记规则

新增 Supervisor 能力时，至少同步：

- 本文件。
- [当前状态](./status.md)。
- [任务队列](./agent-task-queue.md)。
- 新术语或新命令还要同步 [术语索引](./terminology.md)。
