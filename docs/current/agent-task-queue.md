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

## 下一批任务

### 1. 旧文档第三刀：reviews 过期审查分组

目标：

- 盘点 `docs/reviews/` 里的旧 branch audit、closure review、external review
  记录，区分 still-useful decision background（仍有用的决策背景）和 purely
  historical transcript（纯历史流水）。
- 优先更新 `docs/reviews/README.md` 分类，不急着批量移动。
- 若要移动，先选低风险、少引用、已关闭的旧审查记录。

验收：

- `reviews/README.md` 能把旧审查材料按用途找出来。
- 不把 review 里的旧结论提升为当前执行规则。
- `git diff --check` 和 Markdown 本地链接检查通过。

### 2. 旧文档第四刀：kernel 批次是否移动

目标：

- 对照 `docs/reviews/docs-migration-plan.md` 的 medium-risk kernel batch，
  判断 `kernel-one-pager.md` 和 `kernel-decision-log.md` 是否仍留在 archive
  根目录，还是迁到未来 `docs/kernel/`。
- 不和 reviews 分组混在同一提交里。

验收：

- 若移动，必须同提交修链接并保留旧路径风险说明。
- 若不移动，说明延后原因。

### 3. Supervisor 任务暂缓但保留

目标：

- 当前先处理旧文档；Supervisor flat refactor 和产品可用性小批次暂不删除。
- 回到 Supervisor 前，先确认 `git status` 里的代码改动归属，再决定是否合并
  `refactor/supervisor-flat-refactor`。

验收：

- 恢复 Supervisor 工作前，能解释每个剩余 worktree 的用途。
- 任何代码提交都不和旧文档整理混在一起。

### 4. 文档维护边界

规则：

- 新文档能从 [docs-map](./docs-map.md) 找到。
- 长历史、一次性快照和外部审查原文继续进入 archive 或 reviews。
- 后续新增 Supervisor 命令时，同步更新 quick start 和 command reference。
- 后续新增 Supervisor 能力时，先更新能力索引，再更新能力详情。
- `docs/current/` 保持当前入口，不重新塞入长历史流水。

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
