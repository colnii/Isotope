# Agent 任务队列

状态：`当前入口 / 短队列`

本文件只保留当前可执行任务。

## 当前事实

- Isotope 是 AI 应用软件，不是单纯内核项目。
- Supervisor 是当前主线最活跃的产品能力。
- 功能默认 AI-first，guardrail 是护栏不是替代品。

## 已完成

- 第三批已经完成 current 长文拆分：
  [当前状态](./status.md)、本文件、
  [Codex Supervisor 监控与托管](./codex-supervisor-guide.md) 和
  [Supervisor 命令参考](./supervisor-command-reference.md) 都保留为短入口。
- 归档原因：历史流水、命令大全和详细能力表会干扰当前接手判断，所以移到
  [agent-task-history](../archive/current/agent-task-history.md)、
  [status-history](../archive/current/status-history.md)、
  [supervisor-command-reference](./supervisor-command-reference.md)。
- 旧 v0.1 implementation / coding plans 已移到
  [archived plans](../archive/plans/)。归档原因：它们是早期最小闭环和编码拆解，
  已被后续实现、目录重组和 Supervisor 产品路径替代；当前边界以
  `docs/current/` 入口为准。
- `docs/archive/` 根目录旧文档已经补充归档原因和保留边界：
  [docs inventory pre reorg](../archive/docs-inventory-pre-reorg.md) 是迁移记录，
  [kernel one pager](../archive/kernel-one-pager.md) 和
  [kernel decision log](../archive/kernel-decision-log.md) 是 historical kernel
  reference（历史 kernel 参考），[kernel mainline maintenance mode](../archive/kernel-mainline-maintenance-mode.md)
  是 obsolete rule（废止规则）。
- `docs/reviews/` 已补分类索引：migration 控制、branch audit / old-code
  intake、v0.2 阶段复盘、kernel gap / closure 背景和 app spike 压力测试分开读。
- kernel archive placement 已记录：
  [kernel-one-pager](../archive/kernel-one-pager.md) 和
  [kernel-decision-log](../archive/kernel-decision-log.md) 留在 archive；
  原因见
  [kernel archive placement review](../archive/reviews/kernel-archive-placement-review.md)。
- status docs placement 已记录：[当前状态](./status.md)、`v0.2-roadmap`、
  v0.2 closure、tag delta 和 docs inventory 继续按现有入口组织；原因见
  [status docs placement review](../archive/reviews/status-docs-placement-review.md)。
- track / checkpoint / memory placement 已记录：这三类目录迁移维持现有归档位置；
  原因见 archive reviews 中的 docs placement review。
- 旧文档整理收束审计已完成：旧文档线可以停止，下一步回 Supervisor 前先做
  工作区、冲突和分支归属审计；原因见
  [old docs closure audit](../archive/reviews/old-docs-closure-audit.md)。
- Supervisor 工作恢复前状态归属审计已刷新：root `main` 已跟上 `origin/main`，
  runtime / projector 拆分、state command 和 worker event state migration 已进入主线，
  剩余 worktree 需要逐条处理；原因见
  [supervisor worktree recovery audit](../archive/reviews/supervisor-worktree-recovery-audit.md)。
- Agent loop 单 tick driver 已补齐：`run_agent_loop_tick(...)` 和
  `POST /runs/{run_id}/agent-loop-tick` 会先看 tick policy，允许继续时只执行
  一个已解析的 planner-selected step，再返回执行后的 tick policy；真实 LLM 和
  多轮推进由 provider planner / finite-step runner 接管。
- Agent loop finite-step goal runner 已补第一片：`run_agent_loop_until_stop(...)`
  会在单 tick driver 外做有限步 `while`，每轮重新读取 tick policy、调用外部
  planner callable、再执行一个 tick；它复用现有 tick policy / planner adapter /
  step driver，并把终止条件交给 tick policy 统一控制。
- Agent loop provider planner tick 已补第一片：
  `run_agent_loop_provider_planner_tick(...)` 用注入 provider 生成 JSON planner
  decision，解析成现有 `planner_output`，再走
  `run_agent_loop_real_planner_contract_step(...)` /
  `run_agent_loop_planner_step(...)` 执行；测试只用 deterministic test provider，不接真实网络，
  raw prompt/messages/raw response 不出 provider/planner 边界。每个 planner tick
  现在会默认注入 `default_context.memory`，复用 agent-loop memory query 的
  summary / refs / provenance / quality preview；这是 runtime 构造上下文，
  event 写入和 full content materialization 走各自授权路径。`default_context.memory` 现在通过通用
  hybrid retrieval helper 查询结构化 `MemoryRecord` preview 字段；通用
  `rag.index` 负责本地 deterministic dense 索引装配，memory 只做
  `MemoryRecord` 到 `RetrievalDocument` 的适配。默认未配置 dense backend
  时继续走 BM25，显式 `dense_retrieval={"backend":"local"}` 会启用本地
  dense smoke 闭环，外部 LanceDB 后端仍是后续接入目标。`controlled_expand` 仍然是唯一
  读取 `MemoryRecord.content` 的授权路径。当前实现用当前 run goal 查询当前
  run memory 和同一 session 内显式晋升的 session memory；其他对话、跨
  session/global recall、超长上下文自动整理晋升和自动 promotion policy 仍是
  后续任务。
- Agent loop agent-to-agent conversation arbiter 已补第一片：
  `AgentConversationMessage` 表达单个 agent 的候选发言，
  `arbitrate_agent_conversation_turn(...)` 按 interrupt、priority、state lock
  和可见消息上限做确定性筛选；它支持沉默、延迟和状态锁冲突防护，但仍不是
  实时 streaming 群聊、真实 LLM 发言或跨进程 event bus。
- `agent-loop-tick-driver-trace` demo 已补齐人类可读 handoff，展示
  `before_policy -> planner_result -> after_policy`，并覆盖 budget / user pause
  停止时不产生 side effect。
- Supervisor `call_capacity` handoff 已接入单 tick driver：capacity action 会
  构造现有 `planner_output`，经 `run_agent_loop_tick(...)` 执行一次
  `call_capability`，结果里保留 `tick_result` 和结构化
  `planner_output`。
- `supervisor-capacity-handoff-trace` demo 已补齐人类可读链路，展示
  `Supervisor action -> planner_output -> tick_result -> persisted policy`；
  它使用 fixture provider，不要求真实 LLM 配置。
- `isotope-supervisor capacity plan` 的 plain 输出已补齐结构化 handoff summary，
  会显示 planner selected step、tick status、tick stop reason 和 artifact ref。
- `isotope-supervisor capacity plan` 的 JSON payload 已补齐
  `agent_loop_summary` helper，复用 plain 输出同一组结构化字段；测试覆盖
  JSON summary 和 no raw payload 边界。
- Dashboard / web 的 multi-worker read model 已消费 capacity memory record 里的
  `agent_loop_summary`，展示最近能力调用的 tick / step / artifact 结构化摘要，
  原始 `tick_result` / `step_result` 留在执行产物路径。
- `call_capacity` 执行动作的返回 payload 已带同源 `agent_loop_summary`，
  并写入 summary capacity memory record；raw `tick_result` 留在执行产物路径。
- `supervisor-capacity-dashboard-smoke` demo 已补齐执行到 dashboard 的
  fixture smoke：执行 `call_capacity`、读取 capacity memory record、刷新
  multi-worker read model，并确认三段使用同一组结构化 `agent_loop_summary`。
- Dashboard plain view（终端可读视图）已展示 multi-worker capacity summary：
  总能力调用数、worker、capacity id、tick / step / artifact 摘要都复用
  capacity memory record 的结构化 `agent_loop_summary`。
- Multi-worker payload 已补 `supervised_execution` 聚合视图：按 worker 聚合
  最近 capacity run，复用同一份 `agent_loop_summary`，给后续受监督执行视图
  一个稳定读取入口。
- `worker-manager` plain 输出已展开 `supervised_execution` 的最近 capacity
  run：worker、capacity id、tick、step、artifact 和结构化 summary 可直接在
  CLI 里检查。
- Dashboard plain view 已直接读取 `multi_worker.supervised_execution`，展示
  capacity worker 数、agent-loop capacity 调用数和最近 run 摘要；旧 worker
  summary 只作为缺少聚合视图时的 fallback。
- Web 运行焦点区已直接读取 `multi_worker.supervised_execution`，展示最近
  supervised capacity run 的 worker、capacity id、tick、step 和 artifact
  结构化摘要。
- `supervisor.worker_review` 已进入 capability runner：`isotope-capability`
  可 search/plan/run，运行时复用既有 lightweight `worker-review`，只返回结构化
  决策摘要，合并和 worktree / branch 清理由专门流程处理。
- `supervisor.goal_plan` 已进入 capability runner / capacity path：
  `isotope-capability` 可 search/plan/run；dashboard 的“规划目标”入口也走同一个
  `supervisor.goal_plan` capability。默认只返回规划候选，只有显式 `write=true`
  才写入 `goals.jsonl`。
- Web research 当前入口已闭环：`isotope-research search/list/inspect` 和
  `isotope-supervisor research search/list/inspect` 复用同一套 Research flow、
  `research.*` artifact 和 provenance 边界；成功 report、失败 trace、list
  和 inspect 都已有 CLI / Supervisor 测试。后续不要另开孤立搜索系统，先复用
  这些 artifact-backed entrypoints。
- `research.search` 已进入 capability runner / capacity path：`isotope-capability`
  可 search/plan/run，运行时复用现有 `ResearchFlow`；模型只提供 query，
  capacity path 注入 root，provider / gate / network 策略由 runtime policy
  内部决定；经 capacity agent loop 执行后，`agent_loop_summary` / plain 输出只显示 status、provider、
  source_count 和 artifact_count，report 正文和 raw transcript 走 artifact inspect。
- `research.recall` 已进入 capability runner / capacity path：`isotope-capability`
  可 search/plan/run，运行时只扫描 existing `research.report` artifact 的
  preview metadata，复用 `rag.index` / hybrid retrieval，可显式传
  `dense_retrieval={"backend":"local"}` 启用本地 dense smoke；结果只返回
  summary、ref、source_refs 和 provenance，report 正文仍走 artifact inspect /
  expand。capacity plain 输出和 desktop capacity card 已能显示 recall status、
  report count、retrieval backend / dense status，以及可读的 report preview 列表。
- `research.promote` 已进入 capability runner / capacity path：`isotope-capability`
  可 search/plan/run，运行时复用 existing research promote payload builder 和
  `memory.promotion` proposal boundary；它只从 `research.report` metadata 和
  quality gate 生成 `write_memory` proposal summary，memory 写入走 approval，
  proposal payload content 走 proposal inspect。
- `supervisor.integration_review` 已进入同一 capability runner：默认复用既有
  `integration-review`，关闭 test gate 和候选 validation，只返回
  ready/already/needs/conflict 等结构化分组摘要，merge / push / archive /
  cleanup 交给后续显式流程。
- `memory.query` 已进入 capability runner：`isotope-capability` 可
  search/plan/run，运行时复用 `LocalMemoryQueryService` 和 `FileMemoryStore`，
  通过 memory query grant / caller audit 返回 summary / refs / provenance；
  `controlled_expand` 有 expand grant 和正预算时会物化 matched
  `MemoryRecord.content` 的 budgeted `materialized_text`；source artifact full
  content 走 artifact inspect / expansion 路径。
- `memory.recall` 是面向 Supervisor / desktop chat 的应用层记忆召回能力：
  它从当前 `state_root` 的 `memory/*.json` 搜索 summary / refs / provenance preview，
  模型只提供面向产品的 recall 输入，raw memory content 走 controlled expand。
  `memory.query` 保留为需要显式 `run_id` 的 agent-loop 内部精确查询能力。
- `memory.promotion` 已有 proposal path：将 structured artifact metadata
  或 accepted external observation metadata 整理为待批准的
  `write_memory` `ActionProposal`；raw text / raw content 留在 artifact / observation
  展开路径，helper 产出 proposal；store 写入、event append 和 promotion policy
  由外层流程负责。
- `memory.promotion.preview` 已进入 capability runner：`isotope-capability` 可
  search/plan/run，运行时复用 `memory.promotion` proposal boundary，只返回结构化
  proposal preview，memory 写入和 event append 走 approval/action 路径。
- approval-gated durable memory write 第一片已打开：默认 runtime 能编译
  `write_memory` action，但必须显式 approval；批准后写入 `FileMemoryStore`
  并追加结构化 `memory.record_created` canonical event。
- Agent loop run -> session promotion 已补第一片：`promote_run_memory` 只能把
  当前 run 内已有的 structured run memory 晋升为同一 session 的 session memory，
  并复用 `write_memory` action / policy / execution / event 链；`record_turn_memory`
  负责 run 级记录，session memory 写入走 promotion 路径。自动长上下文整理、
  跨 session/global promotion 和 source artifact full-content expand 仍在后续任务。
- Supervisor `worktree-audit` 已补第一片：开工前可读取
  `git worktree list --porcelain`，按 branch/path 主题词提示可能重复开发的
  worktree 候选；现在还会读取每个 worktree 的 `git status --porcelain=v1`，
  报告多个 dirty worktree 是否修改了同一个文件。删除、合并和任务收敛走后续
  显式流程；它给人类做协调判断。

## 下一批任务

### 1. clean duplicate worktree 清理确认

目标：

- 先跑 `isotope-supervisor worktree-audit --repo-root .`，确认当前是否有重复开发候选。
- 先确认 `refactor/http-api-boundary-split` 是否只是 clean duplicate。
- 如果没有，清理对应 worktree 和本地分支。
- 保留仍有 ahead 提交的 worktree，先做归属确认。

验收：

- 清理前后都重新检查 `git worktree list`、`git branch --list` 和
  `git status --short --branch`。
- 有未推提交或未提交改动的 worktree 先保留并确认归属。

### 2. 小分支合并准备

目标：

- `supervisor-capacity-decision` 需要单独确认是否 ready。
- 先确认它们是否重复、互补或需要合并成同一条小批次。

验收：

- 能给出先合哪一个、怎么验证、哪些测试必须跑。
- 不和 root runtime 拆分或 flat refactor 混提交。

### 3. Capability 路由已接上

状态：

- LLM planner / capacity path 已复用 `supervisor.goal_plan`、
  `supervisor.worker_review` 和 `supervisor.integration_review` 的 capability id。
- `build_supervisor_capacity_plan(...)` 会从 `CapabilityRunner` 取得可提供给
  LLM 的 manifest；这两个 Supervisor review capability 缺 `state_root` 时也会
  以 missing-inputs 状态暴露给 planner 补参。
- `loop/supervise --capacity-decisions` 会把当前 Supervisor state root 作为
  `state_root` 和 `root` capacity input default 注入，让 LLM 直接拿到本机
  Supervisor 状态根 / memory store 路径；模型显式给出的 argument 仍优先于
  default。
- 选中并补齐输入后仍复用 `capacity_graph` /
  `CapabilityRunner.plan_capability_run(...)` / agent loop `call_capability`
  路径，不新增私有 `worker-review` 或 `integration-review` 执行分支。
- `memory.query` 已接入同一 capability runner；capacity path 会给它补
  `root` default，但 `query/run_id` 仍必须来自目标或模型参数，避免把 recall
  变成每轮自动步骤。通过 agent loop 执行后，`agent_loop_summary` 和 plain
  输出会显示 `agent_loop_memory_query_status`、`result_count` 和
  `content_policy` 这类结构化 recall 元数据；query results、source refs、
  provenance 和 raw content 走 recall result / expand 路径。
- `research.search` 已接入同一 capability runner；capacity path 会给它补
  `root` default，模型只需要提供 `query`；provider / gate / network 策略
  不进入模型可见 input contract。
- `research.recall` 已接入同一 capability runner；capacity path 会给它补
  `root` default，模型只需要提供 `query`，可选 `run_id/limit/dense_retrieval`；
  它检索 artifact preview，不走 inspect/promote 的正文路径，也不返回 report 正文。
  现在已有低敏 `agent_loop_research_recall_*` projection 和 desktop preview
  展示；planner/prompt 自动优先选择 recall 仍是后续 slice。
- `research.promote` 已接入同一 capability runner；capacity path 会给它补
  `root` default，但 `run_id/artifact_id/agent_id/thread_id` 仍必须来自目标或
  模型参数。metadata 齐备时生成 `write_memory` proposal，memory 写入交给
  approval / action 路径。

后续：

- 只在真实 capacity run 发现缺口时补测试或 UI 摘要，不继续凭空扩展。

### 4. Supervisor 大分支暂缓

目标：

- `refactor/supervisor-flat-refactor` 先按最新 `origin/main` 做 conflict / reuse
  audit，再决定合并路径。
- promotion split 和 worker event state migration 已进入主线，不要从旧 worktree 回退。

验收：

- 任何大分支 rebase 前先列出同名/同职责现有模块和冲突文件。
- 不让旧分支回退已经进入 `origin/main` 的 docs、capacity 或 agent-loop 变更。

### 5. 文档维护边界

规则：

- 新文档能从 [docs-map](./docs-map.md) 找到。
- 长历史、一次性快照和外部审查原文继续进入 archive 或 reviews。
- 后续新增 Supervisor 命令时，同步更新 quick start 和 command reference。
- 后续新增 Supervisor 能力时，先更新能力索引，再更新能力详情。
- `docs/current/` 保持当前入口，不重新塞入长历史流水。
- 旧文档线默认停止；除非用户明确指定单一类别，不继续移动 track、checkpoint、
  memory、kernel 或 status 文档。

### 6. Web research provider layering 下一小片

目标：

- 在现有 `ResearchFlow` / `research.*` artifact / Supervisor proxy 入口上继续做，
  不另造新搜索路径。
- Provider registry / selection design（提供方注册与选择设计）第一片已完成：
  `isotope-research providers` 与 `isotope-supervisor research providers` 都能列出
  `codex`、`tavily`、`searxng`、`browser`；`codex` / `tavily`
  implemented，SearXNG / browser 仍走 provider trace；这些路径统一经过
  `ResearchFlow` 和 artifact/provenance 边界。
- Tavily provider 的配置读取小片已完成：key 可来自显式
  `--tavily-api-key`、`TAVILY_API_KEY` 或 git-ignored 的
  `src/isotope/features/research/research_tavily.toml`；配置或网络参数缺失时会写入
  `research.provider_trace`。
- Tavily provider 的真实 API execution 小片已完成：必须显式
  `--tavily-enable-network`，并把 Tavily `/search` 响应归一化为 source-backed
  `research.raw_transcript` / `research.report`，source 会带结构化
  `source_kind` / `source_authority` 分类字段。
- Tavily live smoke 已跑通：真实 `tavily` provider 返回 `research.raw_transcript`
  / `research.report`，usage 记录在 provenance，artifact 未泄露 key。
- Research memory promotion 接入片已完成：`isotope-research promote` 与
  `isotope-supervisor research promote` 复用 `memory.promotion` proposal boundary，
  从 `research.report` artifact metadata 与结构化 report quality gate 生成
  `write_memory` proposal；quality gate 会统计 high-authority 和 unknown
  sources，低质量 report 返回 review-required reasons；raw transcript 走 inspect，
  memory 写入走 approval/action 路径。
- Memory promotion preview capability 已完成：`memory.promotion.preview` 可作为
  其他系统接入 promotion boundary 的统一入口，避免直接散落 import helper。
- Durable memory write 第一片已完成：approved `write_memory` action 会持久化
  structured `MemoryRecord`，并让 projector 通过 `memory.record_created` 结构化事件
  读取 summary / refs / provenance。
- Codex delegated provider 保持可信 fallback，Tavily 作为普通 API provider 候选，
  SearXNG 保持可选 self-hosted / fallback，browser/crawler 只做最低层 fetch
  fallback。
- durable memory promotion policy 仍需继续收口：当前只能从 structured
  source-backed artifact / observation 生成 proposal 或 approved `write_memory`
  action；raw web text 先进入 artifact / observation，再进入 proposal 或 action。

验收：

- 新 provider 或 provider registry 必须复用 `ResearchProvider`、`ResearchFlowResult.to_dict()`、
  `research.provider_trace` 和 `isotope-research` / `isotope-supervisor research`
  入口。
- provider failure 仍要落 `research.provider_trace`，plain/json 输出继续可 inspect。
- 更新相关 tests 和 current docs，不让 CLI、Supervisor、artifact、memory 边界分离。

## 验证命令

文档-only 批次至少运行：

```bash
git diff --check
python3 - <<'PY'
from pathlib import Path
import re
root = Path.cwd()
link_re = re.compile(r'\[[^\]]+\]\(([^)]+)\)')
missing = []
for path in sorted(root.glob('**/*.md')):
    if '.git' in path.parts or '.worktrees' in path.parts:
        continue
    text = path.read_text(encoding='utf-8')
    for match in link_re.finditer(text):
        target = match.group(1).split('#', 1)[0]
        if not target or '://' in target or target.startswith('mailto:'):
            continue
        resolved = (path.parent / target).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            continue
        if not resolved.exists():
            missing.append(f'{path.relative_to(root)} -> {match.group(1)}')
if missing:
    print('\n'.join(missing))
    raise SystemExit(1)
print('all local markdown links resolve')
PY
```

代码批次按影响范围补跑相关 `pytest`。
