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
5. `assistant` 不再作为新目录叙事，旧路径入口已删除。
6. 活跃 demo 输出使用 `app_friction` 描述应用摩擦，不再传播旧的底座摩擦字段。
7. agent loop 活跃实现已迁入 `src/isotope/agents/loop/`。
8. 兼容代理迁移需同步维护 `docs/current/import-map.md`，并写明计划删除节点。
9. `core` 当前薄包 `InProcessServer`，已有 conversation（对话）、
   task（任务）和 turn（回合）状态，不承载 agent loop 内部实现。
10. `features/tasks` 已有薄入口、低敏摘要索引、`isotope-task`
    CLI 和 tasks API，当前提供任务创建、读取和列表。
11. `features/files` 已有薄入口，当前可把文本保存成
    artifact-backed file summary，已接入 `isotope-file` 和 `/files`
    HTTP facade。
12. `features/projects` 已有薄入口，当前可创建项目摘要、关联
    task/file id、读取关联 task/file 低敏组合摘要，也可一条命令创建
    或复用 project workspace 组合视图，并通过 `isotope-project`、
    `/projects`、`POST /projects/workspace` 和
    `POST /projects/{project_id}/workspace` 调用。
13. `features/search` 已有薄入口，当前可统一搜索 project/task/file
    低敏摘要，支持类型过滤和结果数量限制，并通过 `isotope-search`
    和 `POST /search` 调用。
14. `features/workbench` 已有薄入口，当前可聚合 projects/tasks/files
    低敏摘要、可选 search 结果、空状态和最近更新时间，并通过
    `isotope-workbench`、`GET /workbench`、`POST /workbench` 和
    `isotope-demo --scenario workbench --trace` 调用。
15. `apps/api` 已有薄后端入口，当前提供 ASGI 兼容 `ApiApp`、
    `create_api_app(...)` 和 `isotope-api routes`，真实路由仍复用
    `interfaces/http.py`；ASGI 请求已支持 query string（查询参数）转 body、
    JSON 响应头和稳定 invalid JSON 错误。
16. `features/supervisor` 已有 Codex Supervisor 监控与托管启动，
    可从本机 `~/.codex/sessions` 读取多个 Codex 会话，判断工作中、
    等待用户、疑似停住、疑似报错和空闲，并通过 `isotope-supervisor`
    输出中文汇报；`watch --changes-only` 可只在变化时再次输出；
    `launch` 可启动 Codex 并写入本机托管登记；`launch --backend tmux`
    可在本机 tmux 会话中启动 Codex；`adopt` 可把已有 tmux 会话
    登记成托管 lane；`--llm-summary` 可通过本机
    TOML 号池做智能摘要；`--llm-action` 可让 LLM 只在白名单里
    选择 `monitor`、`send_status` 或 `send_continue`；`scan --json` 包含结构化建议；
    `advise` 可单独输出建议和命令草案，并可显式执行 send 类草案；
    `dashboard` 可按需要看、已完成和工作中分组输出；
    `web` 可启动本机页面并复用 `/dashboard.json` 展示三组窗口；
    dashboard 和 web 已显示 SQLite 标题、索引标题、首条用户消息标题、
    agent 元数据和短 hash，并可复制完整 `codex resume <session_id>`；
    dashboard 会把同一工作目录下的托管 tmux lane 和最近真实 Codex
    session 合并成一个可控卡片；
    web 已可分别复制 attach、状态请求和继续命令，并可通过
    `/managed/send` 执行 `send_status` 和 `send_continue` 两个白名单动作；
    web 已可通过手动“模型建议”按钮调用 `/llm-action`，展示 LLM
    在白名单里选择的建议动作，但不自动发送；没有可控托管 tmux lane
    时会直接回退为 `monitor`，不调用 LLM；有建议目标时会高亮对应按钮，
    但仍需人类手动点击；
    scan 已改为最近候选和大文件首尾读取，降低页面刷新延迟；
    scan、dashboard 和 web 已输出 `status_evidence` 状态依据，
    说明当前标签来自状态协议、文本规则、超时、bell 或托管检查；
    `supervise` 可循环执行扫描、建议、可选 LLM 摘要和显式 send；
    `send` 可向托管 tmux 会话发送一行指令；`scan` 已能把托管
    tmux 会话的 bell（提醒）信号写入 plain、JSON 和 LLM 摘要输入；
    `launch/adopt` 会安装 tmux `alert-bell` hook，把 bell 事件写入
    `~/.codex/supervisor/bell_events.jsonl`。
    `launch` 会给托管 Codex 注入 `SUPERVISOR_STATUS` 状态协议要求，
    `scan` 会从 `.jsonl` 解析状态、摘要和下一步字段；lane state
    会记录最近状态、最近催促时间和催促次数，避免短时间重复发送；
    `blocked`、`done`、`needs_user` 和 bell 事件已接入结构化建议。
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
- 需要收窄范围时，先向用户说明并对齐。

## 当前验证

常用检查：

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope -q
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario v0.2 --trace
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario workbench --trace
PYTHONPATH=src .venv/bin/python -m isotope.apps.api routes --root /tmp/isotope-api --json
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner scan --limit 3
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner dashboard --limit 3
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner web --print-url
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner scan --limit 3 --json
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner advise
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner supervise --iterations 1 --llm-summary --json
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner adopt --name lane-a --cwd /path/to/repo --tmux-session isotope-lane-a
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner send --name lane-a --text "继续"
.venv/bin/isotope-demo --scenario v0.2 --trace
git status --short
```

CI smoke 当前使用 Python `3.12` / `3.13` / `3.14` matrix。

是否运行完整测试，由具体任务风险决定。
