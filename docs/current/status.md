# Isotope 当前状态

状态：`主线已收束 / 应用目录收束中`

## 当前判断

Isotope 是 AI 应用软件，不是单纯内核项目。

过去的开发过度强调底座、谨慎和边界，导致产品功能推进偏慢。
此前暂停过所有功能分支，现已完成分支审计、代码抽取和分支清理。

当前所在分支只表示代码位置，不代表项目方向。
项目方向由产品目标决定：秋招前搭出可展示、可继续扩展的 AI 应用。

## 当前分支状态

- 本地只保留 `main`。
- 远端只保留 `origin/main`。
- 旧暂停分支中的可用代码已抽入主线。
- 旧分支剩余内容只保留在历史提交中，不再作为待迁移代码。
- 后续功能应从 `main` 新开分支或新 worktree。

## 当前优先级

1. 保持当前 `main` 干净。
2. 后续功能从明确产品目标出发新开分支。
3. 目录结构设计另行讨论；当前继续把 `core` 薄主流程接到真实功能层。
4. 继续避免把产品功能降级成诊断或半成品。
5. AI agent 功能默认 AI-first，规则、白名单和边界文档只做护栏。
6. `assistant` 不再作为新目录叙事，旧路径入口已删除。
7. 活跃 demo 输出使用 `app_friction` 描述应用摩擦，不再传播旧的底座摩擦字段。
8. agent loop 活跃实现已迁入 `src/isotope/agents/loop/`。
9. 兼容代理迁移需同步维护 `docs/current/import-map.md`，并写明计划删除节点。
10. `core` 当前薄包 `InProcessServer`，已有 conversation（对话）、
   task（任务）和 turn（回合）状态，不承载 agent loop 内部实现。
11. `features/tasks` 已有薄入口、低敏摘要索引、`isotope-task`
    CLI 和 tasks API，当前提供任务创建、读取和列表。
12. `features/files` 已有薄入口，当前可把文本保存成
    artifact-backed file summary，已接入 `isotope-file` 和 `/files`
    HTTP facade。
13. `features/projects` 已有薄入口，当前可创建项目摘要、关联
    task/file id、读取关联 task/file 低敏组合摘要，也可一条命令创建
    或复用 project workspace 组合视图，并通过 `isotope-project`、
    `/projects`、`POST /projects/workspace` 和
    `POST /projects/{project_id}/workspace` 调用。
14. `features/search` 已有薄入口，当前可统一搜索 project/task/file
    低敏摘要，支持类型过滤和结果数量限制，并通过 `isotope-search`
    和 `POST /search` 调用。
15. `features/workbench` 已有薄入口，当前可聚合 projects/tasks/files
    低敏摘要、可选 search 结果、空状态和最近更新时间，并通过
    `isotope-workbench`、`GET /workbench`、`POST /workbench` 和
    `isotope-demo --scenario workbench --trace` 调用。
16. `features/ask` 已有第一片 Workbench Ask（工作台问答），
    可把工作台低敏摘要交给注入的 LLM provider 回答一个自然语言问题；
    通用问题没有命中搜索时，会退回使用当前 project/task/file 摘要作为
    上下文候选；已接入 `POST /workbench/ask`，也可通过 `isotope-ask` 和
    `isotope-demo --scenario workbench-ask --trace` 调用。
17. `apps/api` 已有薄后端入口，当前提供 ASGI 兼容 `ApiApp`、
    `create_api_app(...)` 和 `isotope-api routes`，真实路由仍复用
    `interfaces/http.py`；ASGI 请求已支持 query string（查询参数）转 body、
    JSON 响应头和稳定 invalid JSON 错误。
18. `features/supervisor` 已有 Codex Supervisor 监控与托管启动，
    可从本机 `~/.codex/sessions` 读取多个 Codex 会话，判断工作中、
    等待用户、疑似停住、疑似报错和空闲，并通过 `isotope-supervisor`
    输出中文汇报；`watch --changes-only` 可只在变化时再次输出；
    `watch --bell` 可在建议目标变化时输出终端 bell，
    不会因静默秒数增长而按固定 interval 重复响；
    `launch` 可启动 Codex 并写入本机托管登记，默认 process 后端使用
    `codex exec -C <cwd> --skip-git-repo-check <prompt>`，避免无 TTY
    后台进程报 `stdin is not a terminal`；`launch --backend tmux`
    可在本机 tmux 会话中启动交互式 Codex；process 后端会读取
    托管 log 尾部，从 `SUPERVISOR_STATUS/SUMMARY/NEXT` 解析完成状态，
    dashboard 可把已退出但明确 `done` 的后台任务归入“已完成”，
    但已退出进程不会因日志残留 `working` 被误判为仍在工作；
    `resume` 可通过
    `codex exec resume <session> <prompt>` 或 `--last` 恢复历史会话，
    会带 `--skip-git-repo-check` 以兼容历史会话落在非仓库父目录的情况，
    并登记成后台托管进程；`discover` 可只读列出现有
    tmux 会话并生成接管命令，也可用 `--adopt-first` 或
    `--adopt-index <编号>` 直接接管候选；`adopt` 可把已有 tmux 会话登记成托管 lane；
    `archive` 可归档旧托管记录，让它不再进入
    活跃 dashboard、建议和自动发送；`--llm-summary` 可通过本机
    TOML 号池做智能摘要；`--llm-action` 会让 LLM planner（规划器）
    在受控动作里选择 `monitor`、`send_status`、`send_continue`
    `resume_session`、`launch_session`、`request_context` 或 `ask_user`；
    `advise`、`supervise` 和 `loop` 默认只把当前工作区内的会话作为
    LLM/action 候选，避免误恢复其他项目或父目录会话；可用
    `--workspace-root <path>` 指定范围，或用 `--all-workspaces` 显式放开；
    `launch_session` 允许 LLM 自己生成发给新 Codex 的目标，
    执行时会包成 A 层 `work order` prompt，写明 goal、cwd、
    scope、budget hint、完成条件和停等用户条件；这只是提示边界，
    不是 Supervisor 强制预算控制；`request_context` 是按需上下文检索能力，
    当前使用 `rg` 优先、Python 关键词扫描兜底，不是 BM25，
    也不是每轮固定塞文档全文；
    `scan --json` 包含结构化建议；
    `ask_user` 只有在 Codex 明确提出拍板请求、LLM 无法根据用户
    既有指示判断、并且上下文检索结果缺失/过时/冲突时才允许；
    CLI 和 web 的模型建议会读取最近 context 结果，合法 `ask_user`
    会显示“等待拍板”、问题和上下文状态；`--llm-execute` 执行
    合法 `ask_user` 时会写入
    `~/.codex/supervisor/decision_requests.jsonl`，dashboard 和 web
    会读取成稳定拍板列表；`decision list` 可查看活跃拍板项，
    `decision archive --request-id <id>` 可把已处理项移出活跃列表；
    `--llm-execute` 可执行 LLM 选择的 send、resume、launch 或
    context 动作；当 LLM 选择 `request_context` 时，Supervisor 会在同轮
    检索后再让 LLM 选择一个后续动作；已完成会话不再作为
    `resume_session` 候选，但其 cwd 仍可供 `launch_session` 和
    `request_context` 使用；LLM 重规划时会看到已检索过的
    context history，避免重复请求同一个 cwd/query；
    `resume_session` 也受 `--prompt-cooldown` 约束，避免短时间重复恢复
    同一历史会话；如果目标 session 所在 cwd 已有后台 process worker
    仍在运行，`resume_session` 会跳过，避免同一个隔离工作区被重复驱动；
    `launch_session` 同样受 `--prompt-cooldown` 约束，
    且发现同名后台 process worker 仍在运行时会跳过，避免 LLM
    长跑时反复启动同名后台任务；LLM 自动 `launch_session`
    会优先创建 `.worktrees/supervisor/...` 独立 git worktree，
    在隔离工作区启动 worker，子目录任务会保留相对路径；
    非 git 工作区不强制隔离，git worktree 创建失败则跳过启动，
    不退回共享工作区；B 层预算控制已落地
    `--max-continue-count`、`--max-context-requests` 和
    `--max-run-minutes`；前者用 lane state 记录
    `continue_count`，达到显式阈值后拦截继续推进请求；后者限制
    每轮可执行的上下文检索次数；时间预算按托管登记的 `started_at`
    判断同名 lane 是否超时，超时后拦截自动或 LLM 继续推进；
    三者默认值都是 0，表示不启用限制，避免阻碍长期托管任务；
    `launch/resume` 支持 `--codex-model` 和可重复的
    `--codex-config key=value`，`supervise/loop/daemon start`
    支持 `--worker-codex-model` 和可重复的 `--worker-codex-config`，
    用于把模型、`model_reasoning_effort` 等 Codex 配置传给后台 worker，
    避免自动托管无意识继承未知的本机默认配置；
    `supervise/loop/daemon start` 默认给写代码 worker 使用
    `gpt-5.5` 和 `model_reasoning_effort="high"`；
    `guide` 会生成同样默认值的 `loop/daemon` 命令，
    用户仍可用参数降配或覆盖；
    已有多 lane loop 回归测试覆盖默认宽松预算下连续推进不同
    托管窗口，并有显式时间预算回归覆盖超时 lane 不再继续推进；
    模型动作返回非 JSON、非法目标或模型池空响应时会降级为
    可见 `monitor`，不让 loop 直接退出；OpenAI-compatible provider
    遇到 `finish_reason=length` 且只有 `reasoning_content`、无正文时，
    会重试一次并关闭 thinking，避免 reasoning token 吃完整个输出预算；
    Supervisor LLM 默认输出上限为 2048 tokens，降低动作 JSON 被截断
    导致误降级为 `monitor` 的概率；
    `scan` 会记录真实 Codex session JSONL 的 `source_size_bytes`，
    LLM planner 会看到 `resume_context_hint`，当历史文件较大时优先考虑
    `request_context` 或 `launch_session`，避免无意识恢复高成本长历史；
    开启 LLM 动作时，JSON 里的主 `command_suggestion` 会跟随
    `llm_action.command_suggestion`，旧规则建议保留在
    `rule_command_suggestion` 里，避免前端把旧规则建议误当主动作；
    `monitor` 只记录跳过；
    `advise` 可单独输出建议和命令草案，并可显式执行 send 类草案；
    `up` 是日常一键入口，会在 daemon 未运行时启动后台 loop，
    并显示最近 LLM 动作、执行结果和 worker 状态；
    `guide` 可生成一组可复制的启动、接管、日常 loop 和观察命令，
    作为真实使用入口；`loop` 是日常常驻入口，默认由 LLM planner
    选择并执行受控动作，process 后台托管是主线；
    `daemon start` 生成的后台 loop 使用 Python `-u` 非缓冲输出，
    确保自动动作和监控状态能及时写入 `daemon.log`；
    `daemon status` 会聚合最近 LLM 动作、执行结果、worker
    模型/配置和 worker 状态，不必手动 tail 日志判断是否在工作；
    自动发现并接管未登记的 Codex tmux 窗口只作为可旁观兼容通道；
    `--rule-execute` 可切回旧规则自动策略；
    `changes-only` 只减少输出，不会阻断 LLM planner 在无变化轮次继续判断；
    `daemon start/status/stop/watchdog` 可把日常 `loop` 放到后台运行，
    状态写入 `~/.codex/supervisor/daemon.json`，日志写入
    `~/.codex/supervisor/logs/daemon.log`；`watchdog` 可按状态文件
    检查后台 `loop`，异常退出时用原命令重新拉起；
    `daemon watcher start/status/stop` 可启动 watcher（周期看门进程），
    定期触发 `watchdog`，状态写入 `~/.codex/supervisor/watcher.json`；
    `advise/supervise --name <lane>` 可把建议、显式执行和自动执行
    收窄到指定托管 lane，名字不存在时不会退回到其他窗口；
    `dashboard` 可按需要看、已完成和工作中分组输出；
    dashboard/web 和 `supervise` plain 视图默认隐藏已退出的托管
    tmux lane，`scan --json` 仍保留已退出记录；已归档记录会从
    活跃扫描中折叠掉；
    `web` 可启动本机页面并复用 `/dashboard.json` 展示三组窗口；
    dashboard 和 web 已显示 SQLite 标题、索引标题、首条用户消息标题、
    agent 元数据和短 hash，并可复制完整 `codex resume <session_id>`；
    dashboard 会把托管 tmux lane 和最近真实 Codex session 合并成一个
    可控卡片；关联不再只依赖 cwd，而是全局候选打分，优先用
    launch 登记的原始 prompt、只读 tmux pane 文本、session id、
    Codex 标题和用户消息匹配，并一对一分配；
    session id 只是弱证据，管理窗口讨论别人 id 时不会抢走对应 session；
    同一 tmux lane 内执行 `/new` 后，会优先使用新 Codex banner
    和 `Thread renamed to ...` 之后的活跃终端片段，避免继续黏住旧 session；
    终端输出很长时，最近输出会保留新 Codex 窗口锚点和最新尾部，
    防止旧 resume 行再次抢占绑定；
    通用状态请求和否定语境里的旧标题不再作为强匹配，
    防止 `test` 这类新窗口被旧 session 重新抢走；
    超时且没有状态协议的 session 只要仍被当前 tmux pane 明确命中，
    也可作为关联候选；若没有正分匹配，不再硬连旧 session；
    web 会显示 `linked_match` 绑定依据、分数和命中来源；
    有状态协议的超时 session 仍可作为关联候选；若真实 session 有状态协议，
    dashboard 分组和 web 状态汇报会优先使用真实 session；
    web 卡片会单独展示“卡片来源”，区分普通历史会话和托管 tmux 窗口；
    web 托管卡片会展示 bell 是否收到、bell hook 安装状态、
    终端是否已回到可输入状态、关联 session 和最近输出，
    最近输出保留尾部行并默认滚到底部，让人类直接看到
    Supervisor 看到的托管窗口收尾文本；用户手动上翻后，
    自动刷新会保留最近输出滚动位置；
    web 已可分别复制 attach、状态请求和继续命令，并可通过
    `/managed/send` 执行 `send_status` 和 `send_continue` 两个白名单动作；
    两个动作都会要求托管 Codex 按状态协议汇报；
    web 已可通过手动“模型建议”按钮调用 `/llm-action`，展示 LLM
    在受控动作里选择的建议，模型输出带解释时会尽量提取动作 JSON，
    但不自动发送；没有任何可控 Supervisor 目标
    时会直接回退为 `monitor`，不调用 LLM；有建议目标时会高亮对应按钮，
    但仍需人类手动点击；
    scan 已改为最近候选和大文件首尾读取，降低页面刷新延迟；
    scan、dashboard 和 web 已输出 `status_evidence` 状态依据，
    说明当前标签来自状态协议、文本规则、超时、bell 或托管检查；
    `supervise` 可循环执行扫描、建议、可选 LLM 摘要和显式 send；
    `loop` 复用 `supervise` 引擎，并固定为日常 LLM 监督默认值；
    无变化轮次仍会让 LLM planner 判断本轮是否要执行动作；
    `supervise --auto-execute` 已有第一版规则自动策略：
    `done` 默认续跑，终端可输入、`stale` 或 bell 时询问状态，
    `blocked/needs_user/error` 只提醒；如果 `SUPERVISOR_NEXT`
    明确写出可结束、可归档、等待归档或无需继续，自动策略只监控不续跑；
    未指定 `--name` 时会扫描所有活跃托管 lane，优先推进可自动处理的
    窗口，不会被第一个仍在运行的窗口挡住；
    自动轮转会避开仍在 `--prompt-cooldown` 冷却期内的 lane，
    继续寻找下一个可自动处理窗口；显式 `--name` 仍保留冷却跳过提示；
    `loop --rule-execute` 可显式使用规则自动策略；
    即使报告指纹不变，规则模式也会继续检查冷却和发送；
    终端明确显示 `Working ... esc to interrupt` 时，
    自动策略会优先相信当前窗口仍在工作，不被同目录旧 `done` session 误导；
    `supervise --bell` 可和自动执行合用，只按本轮托管 lane 的自动处理
    结果判断是否需要人看，不被无关历史窗口误触发；
    自动发送 `send_status/send_continue` 已处理的状态不会响；
    `send` 可向托管 tmux 会话发送一行指令；`scan` 已能把托管
    tmux 会话的 bell（提醒）信号写入 plain、JSON 和 LLM 摘要输入；
    tmux 发送会用 `set-buffer + paste-buffer + 短暂等待 + C-m`，
    避免状态请求停在 Codex 输入区；
    `launch/adopt` 会安装 tmux `alert-bell` hook，把 bell 事件写入
    `~/.codex/supervisor/bell_events.jsonl`；`repair-hooks` 可给旧托管
    tmux 记录补装 hook，web 启动时也会自动做一次补装。
    手动 tmux 内启动 Codex 后，`adopt -> loop -> archive`
    已通过真实闭环验收；`discover` 已能在没有 tmux server 时返回空列表，
    有候选窗口时给出可复制的接管命令，或按候选直接接管；
    `loop` 已能在启动后自动发现并接管候选，不需要人先手动 adopt；
    `launch` 会给托管 Codex 注入 `SUPERVISOR_STATUS` 状态协议要求，
    `scan` 会从 assistant 回复解析状态、摘要和下一步字段，并校验
    状态合法值；scan 顶层状态、统计计数和 dashboard 展示都会优先采用
    合法状态协议，避免已完成窗口继续显示成疑似停住；lane state
    会记录最近状态、最近催促时间和催促次数，避免短时间重复发送；
    `blocked`、`done`、`needs_user` 和 bell 事件已接入结构化建议。
    `supervise` plain 视图复用 dashboard 当前分组，再输出托管自动化
    是否可用；没有托管 process 或可旁观 tmux lane 时，
    会明确提示并优先给出 process `launch` 命令形状；
    已退出或已归档的旧托管 tmux lane 不再参与建议和自动发送；
    运行中且终端未回到可输入态的 lane 不会仅因缺少状态协议就被催促。
    真实 `done -> send_continue -> 第二阶段状态协议` 闭环已通过烟测；
    多窗口烟测已验证：一个 lane 仍在工作时，另一个已完成 lane
    可被自动选择并继续推进；
    连续循环烟测已验证：一个 lane 进入冷却期后，其他可推进 lane
    不会被它挡住；
    无变化连续循环已验证：`changes-only` 不再让 LLM planner 停摆；
    真实 guide/loop 验收发现并修正旧 `done` session 误导新工作窗口的问题；
    手动窗口接管验收已验证：已有 tmux Codex 窗口可被接管、
    监督、识别完成状态并归档；接管前可用 `discover` 查找候选；
    web 已新增 `/events` 事件流，tmux bell 写入事件文件后会推动前端
    立即刷新 dashboard，不必等 5 秒轮询。
    能力登记见 `docs/current/supervisor-capability-map.md`。

## 文档策略

- 入口文档要短、中文、可执行。
- 历史文档只在有追溯价值时保留。
- 已过期的暂停规则不再作为 AI 行为依据。
- 文档结构要兼顾 AI 检索和人类审阅。
- 术语和目录命名要从 AI 应用角度重新整理。
- 历史归档里的旧说法不代表当前方向。
- Supervisor 新能力要同步登记到能力地图，避免重复实现。

## 开发策略

- 速度和质量都重要。
- 测试用于保护交付，不用于拖慢交付。
- 真实产品功能不能被自动降级成诊断或预检查。
- AI 相关产品功能必须交付真实 AI 主流程，规则只能作为工程护栏。
- 需要收窄范围时，先向用户说明并对齐。

## 当前验证

常用检查：

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope -q
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario v0.2 --trace
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario workbench --trace
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario workbench-ask --trace
PYTHONPATH=src .venv/bin/python -m isotope.features.ask.runner ask --root /tmp/isotope-ask --question "下一步做什么？" --mock-answer "先整理一个可展示任务。"
PYTHONPATH=src .venv/bin/python -m isotope.apps.api routes --root /tmp/isotope-api --json
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner scan --limit 3
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner dashboard --limit 3
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner guide --cwd /path/to/repo --name lane-a
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner up
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner resume --cwd /path/to/repo --name lane-a --session-id <session-id> --prompt "继续推进当前任务"
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner resume --cwd /path/to/repo --name latest --last --prompt "请汇报当前状态"
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner discover --cwd /path/to/repo
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner discover --cwd /path/to/repo --adopt-first
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner web --print-url
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner scan --limit 3 --json
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner advise
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner supervise --iterations 1 --llm-summary --json
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner loop --interval 30
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner loop --interval 30 --no-auto-adopt
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner daemon start --interval 30
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner daemon status
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner daemon watchdog
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner daemon watcher start --interval 60
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner daemon watcher status
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner daemon watcher stop
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner daemon stop
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner adopt --name lane-a --cwd /path/to/repo --tmux-session isotope-lane-a
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner send --name lane-a --text "继续"
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner archive --name lane-a
.venv/bin/isotope-demo --scenario v0.2 --trace
git status --short
```

CI smoke 当前使用 Python `3.13` / `3.14` matrix。

是否运行完整测试，由具体任务风险决定。
