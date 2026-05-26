# Isotope 当前状态

状态：`主线收束 / Supervisor 产品化推进中`

本文件只记录当前事实和入口。历史状态正文已移到
[status-history](../archive/current/status-history.md)。

## 当前判断

Isotope 是 local-first（本地优先）的 AI engineering workbench（AI 工程工作台），
不是单纯 kernel（内核）项目。当前主线围绕 Codex Supervisor、受控 worker
启动、证据收集、可恢复开发流程和本机 Web dashboard 推进。

项目方向由产品目标决定：先做出可展示、可持续扩展的 AI 应用，再把底层边界
逐步稳定下来。

## 当前分支状态

- `main` 是主线。
- 多 AI 并行开发必须使用独立 worktree。
- 临时分支合并后要清理 worktree、本地分支和远端临时分支。
- 旧暂停分支的可用代码已进入主线；剩余内容只保留历史参考价值。

## 当前重点

1. 保持 `docs/current/` 短入口化，历史流水放入 `docs/archive/current/`。
2. 继续让 Supervisor 成为可日常使用的管理层，而不是只读诊断工具。
3. Supervisor 新能力先查
   [能力地图](./supervisor-capability-map.md) 和
   [架构迁移表](./supervisor-architecture-migration-table.md)，避免重复造轮子。
4. AI agent 功能默认 AI-first；规则、白名单、冷却和工作区边界是 guardrail
   （护栏），不能替代模型主路径。
5. `features/supervisor/state/projection.py` 已提供只读低敏 Supervisor state
   projection（状态投影），统一读取 active goals、decision、lane failure、
   worker events 和 notifications；dashboard/web/daemon 已接入该读模型，
   worker event payload 已经通过平台 schema 过滤成低敏 summary，loop payload
   已带只读 snapshot，`isotope-supervisor state` 可直接查看，后续入口接入前不要
   重复拼散表。
6. `FileFlow` 文件摘要和 `TaskFlow` 结果摘要读取已通过 platform
   `ResourceRef` + artifact record 校验并刷新本地 index，避免盲信
   `files/index.json` / `tasks/index.json`。
7. `ProjectFlow` 关联、读取和列出 task/file 链接时复用 `TaskFlow.get_task()`
   和 `FileFlow.get_file()` 校验目标可读，避免传播不可解析的本地关联 ID。
8. HTTP artifact summary endpoint 已通过 platform artifact record 返回低敏摘要，
   不再由 HTTP 层直接拼 `artifact.created` event payload。
9. Agent loop 已有单 tick driver：`run_agent_loop_tick(...)` 会先读取
   tick policy，允许继续时只执行一个已解析的 planner-selected step，再返回
   执行后的 tick policy；`agent-loop-tick-driver-trace` demo 已能输出
   `before_policy -> planner_result -> after_policy` 的人类可读 handoff。
   Supervisor 的 `call_capacity` 已通过现有 `planner_output` contract 接入这个
   driver；`supervisor-capacity-handoff-trace` demo 可展示
   `Supervisor action -> planner_output_summary -> tick_result -> persisted policy`。
   `isotope-supervisor capacity plan` 的 plain 输出也会显示低敏 planner / tick
   / artifact handoff summary；JSON payload 同步暴露
   `agent_loop_summary`；`call_capacity` 执行动作会把同源 summary 写入
   capacity memory record。Dashboard / web 的 multi-worker read model 已从该
   record 复用这些字段展示最近能力调用摘要，不读取 raw tick payload。
   `supervisor-capacity-dashboard-smoke` demo 已用 fixture 覆盖执行、落盘和
   dashboard read model 三段同源摘要；multi-worker payload 也已补
   `supervised_execution` 聚合视图，dashboard plain view 会直接读取该聚合视图
   显示 capacity worker 数、agent-loop capacity 调用数和最近 run 摘要；
   `worker-manager` plain 输出也会展开同一份 supervised capacity run 摘要；
   Web 运行焦点区会显示最近 supervised capacity run 的低敏摘要。
   `run_agent_loop_until_stop(...)` 已在单 tick driver 外补第一层 bounded goal
   runner（有界目标 runner）：每轮复用 tick policy 和 planner step，受
   `max_ticks`、user pause、approval 和 completed/failed 状态限制；它仍不调用
   真实 LLM，也不默认打开 Supervisor 自动长循环。Agent loop 已补第一层
   agent-to-agent conversation arbiter（智能体间对话仲裁器）contract：
   `AgentConversationMessage` 表达单个 agent 的候选发言，`arbitrate_agent_conversation_turn(...)`
   负责按 interrupt / priority / state_lock / max visible messages 做确定性筛选，
   支持沉默、延迟和状态锁冲突防护；它是低敏同步仲裁壳，不是实时 streaming
   群聊、真实 LLM 发言或跨进程 event bus。
   `supervisor.worker_review` 已注册为 capability runner 的只读能力，
   `isotope-capability list/search/plan/run` 能发现、预检和运行它；执行时复用
   现有 `worker-review` lightweight 路径，只返回低敏 worker 决策摘要，
   不自动合并、不清理 worktree 或分支。
   `supervisor.integration_review` 也已注册为同一路径的只读 capability；
   默认复用现有 `integration-review`，但关闭 pytest gate 和候选 lint/test
   validation，只返回 ready/already/needs/conflict 等低敏分组摘要，不执行
   merge、push、archive 或 cleanup。
   `memory.query` 也已注册为只读 capability：执行时复用现有
   `LocalMemoryQueryService`，要求 `root/query/run_id`，通过 caller audit 和
   memory query grant 读取 summary / refs / provenance，`controlled_expand`
   仅返回 deferred metadata，不读取 full content。capacity path 的
   `agent_loop_summary` / plain 输出只提升 status、result_count 和
   content_policy 等低敏 recall 元数据，不提升 raw memory 内容。
   `memory.promotion` 已补 proposal boundary（提案边界）第一片：
   `build_memory_promotion_proposal(...)` 只从 structured artifact metadata 或
   accepted external observation metadata 生成待批准的 `write_memory`
   `ActionProposal`，拒绝 raw text / raw content 直接进入长期 memory；它不写
   memory store、不追加 canonical event，也不是完整 promotion policy。
   `screen.report` 已注册为只读 capability：执行时复用现有 screen artifact
   report，要求 `root/run_id`，只返回 observe/control plan 低敏摘要，不读取
   screenshot 正文、不执行输入、不改变窗口；capacity agent-loop 执行后，
   JSON summary 会带 screen report status、observe/control status、
   screenshot availability 和 interference 低敏结论。
   `research.search` 已注册为 capability runner / capacity 可选能力：执行时复用
   现有 `ResearchFlow` 和 provider registry，要求 `root/query`，但当前 capability
   只允许 deterministic `fake` provider，不打开 Tavily 网络、不委托 Codex；capacity
   agent-loop summary 只提升 status、provider、source_count 和 artifact_count，
   不返回 report 正文或 raw transcript。
10. Screen observe/control 已有 policy-gated（策略门控）第一片：
    `screen_observe` / `screen_control` 走 registry、policy、executor 和 artifact
    边界，Windows backend 仅用于手动 smoke；observe/control 已支持命令级
    target allowlist（目标白名单）和 reusable allowlist file（可复用白名单文件），
    `--allowlist-file` 只注入 target allowlist，不绕过 execute approval gate；
    `--allowlist-profile` 可从 profile 目录解析命名 allowlist，同样不绕过
    approval gate；
    `allowlist validate` 可离线检查 allowlist 格式并只输出低敏计数；
    `allowlist template` 可打印可编辑 JSON 骨架；
    deterministic first-match（确定性首个匹配）
    metadata，execute 控制遇到多窗口匹配时默认拒绝 first-match 点击；当前不是
    默认自动 GUI agent。窗口最小化或截图不可用时 observe 会降级为
    `metadata_only`，并通过 `screen_diagnostic` 返回
    `restore_window_requires_approval` 恢复建议；`isotope-screen inspect/report`
    可读取单个 screen artifact 或生成 run 级低敏 observe 摘要，不展开截图正文；
    `control-restore` 可生成恢复窗口 dry-run plan，真实恢复仍必须显式批准；
    report 也会总结 control plan 的 action 类型、approval 需求和是否干扰屏幕；
    `isotope-supervisor screen report/inspect` 复用同一套 screen artifact report。
11. Web research 已有 shared Research flow（共享研究流程）和可用测试入口：
    `isotope-research search/list/inspect/providers/promote` 与
    `isotope-supervisor research search/list/inspect/providers/promote` 都复用同一套
    `ResearchFlow`、artifact store、provider registry 和 plain/json 输出边界。
    provider registry 当前列出 `fake`、`codex`、`tavily`、`searxng`、`browser`；
    `fake`、`codex` 与 `tavily` implemented；Tavily 默认仍是 preflight（预检），
    只有显式传 `--tavily-enable-network` 才会请求 `https://api.tavily.com/search`。
    key 可来自 `--tavily-api-key`、`TAVILY_API_KEY` 或 git-ignored 的
    `src/isotope/features/research/research_tavily.toml`。缺 key 或未打开网络开关
    都会复用 `ResearchFlow` 写 `research.provider_trace`，不落成功 report；真实
    Tavily 响应会归一化为 source-backed `research.raw_transcript` 与
    `research.report`。SearXNG / browser 仍 fail closed（失败关闭，创建 flow 前报错）。
    成功结果写
    `research.raw_transcript` 与 `research.report`；provider 失败只写
    `research.provider_trace`，并保留 retry attempt、Codex event/error
    diagnostics（诊断）供 `inspect` 查看。当前 durable ingestion（持久摄取）
    路径是 `search/fetch -> research.* artifact / provenance -> retrieval ->
    optional memory promotion`；`promote` 只允许 `research.report` artifact metadata
    生成 `write_memory` proposal，不写 memory、不读取 raw transcript。Codex delegated
    provider 已有小预算 retry；SearXNG / browser crawler 的真实接入仍是后续
    provider layering（提供方分层）工作，不要另造绕开 artifact/provenance 的搜索系统。
12. 代码结构继续以 `src/isotope/` 为 Python 主包，不新增 `packages/`、
   `aios` 或 kernel 主叙事。

## 当前入口

- [README](../../README.md)：项目目标和快速开始。
- [文档总入口](../README.md)：`docs/` 目录职责。
- [文档地图](./docs-map.md)：按任务找文档。
- [任务队列](./agent-task-queue.md)：当前可执行任务。
- [Supervisor 监控与托管](./codex-supervisor-readonly.md)：Supervisor 快速入口。
- [Supervisor 命令参考](./supervisor-command-reference.md)：命令索引和边界。
- [Supervisor operations runbook](./supervisor-operations-runbook.md)：夜间 smoke 和长流程验收。
- [Supervisor 能力地图](./supervisor-capability-map.md)：能力索引。
- [Supervisor 能力详情](./supervisor-capability-details.md)：详细能力登记。

## 常用验证

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests -q
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario workbench --trace
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario workbench-ask --trace
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner scan --limit 3
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner dashboard --limit 3
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner state --json
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner check
PYTHONPATH=src .venv/bin/python -m isotope.features.research.runner search --root /tmp/isotope-research --query "agent memory retrieval" --provider fake
PYTHONPATH=src .venv/bin/python -m isotope.features.research.runner providers
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner research list --root /tmp/isotope-research
```

文档-only 改动至少跑 `git diff --check` 和 Markdown link check。
