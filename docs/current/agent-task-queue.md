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

## 当前批次

### 1. 收尾：current 长文拆分验收

目标：

- 确认 [当前状态](./status.md)、本文件、
  [Codex Supervisor 监控与托管](./codex-supervisor-readonly.md) 和
  [Supervisor 能力地图](./supervisor-capability-map.md) 都是短入口。
- 确认长文详情已移到：
  [agent-task-history](../archive/current/agent-task-history.md)、
  [status-history](../archive/current/status-history.md)、
  [supervisor-command-reference](./supervisor-command-reference.md)、
  [supervisor-capability-details](./supervisor-capability-details.md)。
- 跑 Markdown link check 和 `git diff --check`。

验收：

- `git diff --check` 通过。
- Markdown 本地链接解析通过。
- `docs/current/` 的四个入口不再承担历史流水正文。

### 2. Supervisor flat refactor 复核

目标：

- 复核当前已有的 `refactor/supervisor-flat-refactor` worktree 是否还需要合并。
- 对照 `src/isotope/features/supervisor/runner.py` 和
  `src/isotope/features/supervisor/commands/`，确认 runner 是否继续变薄。
- 若该分支已合并，按 `AGENTS.md` 清理 worktree、本地分支和远端临时分支。

验收：

- `git worktree list` 能解释每个剩余 worktree 的用途。
- 若执行合并，至少跑相关 Supervisor 测试或说明阻塞原因。

### 3. Supervisor 产品可用性小批次

目标：

- 从用户最常用路径出发，继续打磨 `start-here`、`up`、`web`、`check`、
  `worker-review` 和 `integration-review`。
- 每个小批次都要说明用户入口、复用的 helper、验证命令和失败回退。
- 不把 AI 路径降级成只读诊断；LLM planner（规划器）仍应处在主路径之一。

候选：

- 让 `check` 输出更适合作为早上接手的摘要。
- 让 `worker-review` 更清楚地区分“可合并”“需复查”“只剩归档”。
- 让 `web` 的受控操作文案和状态分组更适合扫读。

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
