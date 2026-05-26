# Agent 任务队列

状态：`当前入口 / 短队列`

本文件只保留当前可执行任务。历史批次已经移到
[agent-task-history](../archive/current/agent-task-history.md)。

## 当前事实

- Isotope 是 AI 应用软件，不是单纯内核项目。
- `docs/current/` 只放当前入口；历史流水、外部审查原文和一次性快照放入
  `docs/archive/current/`。
- Supervisor 是当前主线最活跃的产品能力；新增能力先查
  [Supervisor 能力地图](./supervisor-capability-map.md) 和
  [Supervisor 架构迁移表](./supervisor-architecture-migration-table.md)。
- 文档迁移仍保持收窄：不默认移动 `architecture/` 里的 kernel、
  checkpoint、memory 或 track 文档。

## 已完成

- 第三批已经完成 current 长文拆分：
  [当前状态](./status.md)、本文件、
  [Codex Supervisor 监控与托管](./codex-supervisor-readonly.md) 和
  [Supervisor 能力地图](./supervisor-capability-map.md) 都保留为短入口。
- 归档原因：历史流水、命令大全和详细能力表会干扰当前接手判断，所以移到
  [agent-task-history](../archive/current/agent-task-history.md)、
  [status-history](../archive/current/status-history.md)、
  [supervisor-command-reference](./supervisor-command-reference.md) 和
  [supervisor-capability-details](./supervisor-capability-details.md)。
- 旧 v0.1 implementation / coding plans 已移到
  [archived plans](../archive/plans/)。归档原因：它们是早期最小闭环和编码拆解，
  已被后续实现、目录重组和 Supervisor 产品路径替代，不应继续放在
  `architecture/` 里当当前边界读。
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
  [kernel-decision-log](../archive/kernel-decision-log.md) 暂不单独迁入
  `docs/kernel/`；原因见
  [kernel archive placement review](../reviews/kernel-archive-placement-review.md)。
- status docs placement 已记录：暂不创建 `docs/status/`，不移动
  [当前状态](./status.md)、`v0.2-roadmap`、v0.2 closure、tag delta 或
  docs inventory；原因见
  [status docs placement review](../reviews/status-docs-placement-review.md)。
- track / checkpoint / memory placement 已记录：继续暂停这三类目录迁移；原因见
  [deferred docs placement review](../reviews/deferred-docs-placement-review.md)。
- 旧文档整理收束审计已完成：旧文档线可以停止，下一步回 Supervisor 前先做
  工作区、冲突和分支归属审计；原因见
  [old docs closure audit](../reviews/old-docs-closure-audit.md)。
- Supervisor 工作恢复前状态归属审计已刷新：root `main` 已跟上 `origin/main`，
  runtime / projector 拆分、state command 和 worker event state migration 已进入主线，
  剩余 worktree 需要逐条处理；原因见
  [supervisor worktree recovery audit](../reviews/supervisor-worktree-recovery-audit.md)。
- Agent loop 单 tick driver 已补齐：`run_agent_loop_tick(...)` 和
  `POST /runs/{run_id}/agent-loop-tick` 会先看 tick policy，允许继续时只执行
  一个已解析的 planner-selected step，再返回执行后的 tick policy；它仍不接
  真实 LLM，不自动多轮循环。
- `agent-loop-tick-driver-trace` demo 已补齐人类可读 handoff，展示
  `before_policy -> planner_result -> after_policy`，并覆盖 budget / user pause
  停止时不产生 side effect。
- Supervisor `call_capacity` handoff 已接入单 tick driver：capacity action 会
  构造现有 `planner_output`，经 `run_agent_loop_tick(...)` 执行一次
  `call_capability`，结果里保留 `tick_result` 和低敏
  `planner_output_summary`。
- `supervisor-capacity-handoff-trace` demo 已补齐人类可读链路，展示
  `Supervisor action -> planner_output_summary -> tick_result -> persisted policy`；
  它使用 fixture provider，不要求真实 LLM 配置。
- `isotope-supervisor capacity plan` 的 plain 输出已补齐低敏 handoff summary，
  会显示 planner selected step、tick status、tick stop reason 和 artifact ref。
- `isotope-supervisor capacity plan` 的 JSON payload 已补齐
  `agent_loop_summary` helper，复用 plain 输出同一组低敏字段；测试覆盖
  JSON summary 和 no raw payload 边界。
- Dashboard / web 的 multi-worker read model 已消费 capacity memory record 里的
  `agent_loop_summary`，展示最近能力调用的 tick / step / artifact 低敏摘要，
  不读取原始 `tick_result` / `step_result`。
- `call_capacity` 执行动作的返回 payload 已带同源 `agent_loop_summary`，
  并写入只含 summary 的 capacity memory record，不落 raw `tick_result`。
- `supervisor-capacity-dashboard-smoke` demo 已补齐执行到 dashboard 的
  fixture smoke：执行 `call_capacity`、读取 capacity memory record、刷新
  multi-worker read model，并确认三段使用同一组低敏 `agent_loop_summary`。
- Dashboard plain view（终端可读视图）已展示 multi-worker capacity summary：
  总能力调用数、worker、capacity id、tick / step / artifact 摘要都复用
  capacity memory record 的低敏 `agent_loop_summary`。
- Multi-worker payload 已补 `supervised_execution` 聚合视图：按 worker 聚合
  最近 capacity run，复用同一份 `agent_loop_summary`，给后续受监督执行视图
  一个稳定读取入口。
- `worker-manager` plain 输出已展开 `supervised_execution` 的最近 capacity
  run：worker、capacity id、tick、step、artifact 和低敏 summary 可直接在
  CLI 里检查。
- Dashboard plain view 已直接读取 `multi_worker.supervised_execution`，展示
  capacity worker 数、agent-loop capacity 调用数和最近 run 摘要；旧 worker
  summary 只作为缺少聚合视图时的 fallback。
- Web 运行焦点区已直接读取 `multi_worker.supervised_execution`，展示最近
  supervised capacity run 的 worker、capacity id、tick、step 和 artifact
  低敏摘要。
- `supervisor.worker_review` 已进入 capability runner：`isotope-capability`
  可 search/plan/run，运行时复用既有 lightweight `worker-review`，只返回低敏
  决策摘要，不自动合并、不清理 worktree 或分支。
- Web research 当前入口已闭环：`isotope-research search/list/inspect` 和
  `isotope-supervisor research search/list/inspect` 复用同一套 Research flow、
  `research.*` artifact 和 provenance 边界；成功 report、失败 trace、list
  和 inspect 都已有 CLI / Supervisor 测试。后续不要另开孤立搜索系统，先复用
  这些 artifact-backed entrypoints。
- `supervisor.integration_review` 已进入同一 capability runner：默认复用既有
  `integration-review`，关闭 test gate 和候选 validation，只返回
  ready/already/needs/conflict 等低敏分组摘要，不 merge、不 push、不 archive、
  不 cleanup。

## 下一批任务

### 1. clean duplicate worktree 清理确认

目标：

- 先确认 `refactor/http-api-boundary-split` 是否只是 clean duplicate。
- 如果没有，清理对应 worktree 和本地分支。
- 不清理仍有 ahead 提交的 worktree。

验收：

- 清理前后都重新检查 `git worktree list`、`git branch --list` 和
  `git status --short --branch`。
- 不删除有未推提交或未提交改动的 worktree。

### 2. 小分支合并准备

目标：

- `supervisor-capacity-decision` 需要单独确认是否 ready。
- 先确认它们是否重复、互补或需要合并成同一条小批次。

验收：

- 能给出先合哪一个、怎么验证、哪些测试必须跑。
- 不和 root runtime 拆分或 flat refactor 混提交。

### 3. Capability 路由已接上

状态：

- LLM planner / capacity path 已复用 `supervisor.worker_review` 和
  `supervisor.integration_review` 的 capability id。
- `build_supervisor_capacity_plan(...)` 会从 `CapabilityRunner` 取得可提供给
  LLM 的 manifest；这两个 Supervisor review capability 缺 `codex_home` 时也会
  以 missing-inputs 状态暴露给 planner 补参。
- 选中并补齐输入后仍复用 `capacity_graph` /
  `CapabilityRunner.plan_capability_run(...)` / agent loop `call_capability`
  路径，不新增私有 `worker-review` 或 `integration-review` 执行分支。

后续：

- 只在真实 capacity run 发现缺口时补测试或 UI 摘要，不继续凭空扩展。

### 4. Supervisor 大分支暂缓

目标：

- `refactor/supervisor-flat-refactor` 暂不直接合并；它需要先按最新 `origin/main`
  做 conflict / reuse audit。
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
- 下一步优先做 provider registry / selection design（提供方注册与选择设计）：
  Codex delegated provider 保持可信 fallback，Tavily 作为普通 API provider 候选，
  SearXNG 保持可选 self-hosted / fallback，browser/crawler 只做最低层 fetch
  fallback。
- durable memory promotion 仍保持 deferred：只能从 structured source-backed
  artifact / observation 显式提升，不能从 raw web text 直写。

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
