# Current Docs Refactor Plan

状态：`third batch prepared`

本文准备第三批文档重构，只定范围和验收，不在本批拆长文。

## 目标

让 `docs/current/` 继续承担“当前事实入口”，把历史流水、命令大全和详细能力表
拆到更合适的位置。第三批不改变产品实现，不迁移 architecture / feature
boundary 文档。

## 候选长文

| 文件 | 当前问题 | 建议拆分 |
| --- | --- | --- |
| `docs/current/agent-task-queue.md` | 约 1400 行，历史批次和当前 next step 混在一起。 | 保留短 `agent-task-queue.md`；历史批次移到 `docs/archive/current/agent-task-history.md` 或 `docs/reviews/agent-task-history-*.md`。 |
| `docs/current/codex-supervisor-readonly.md` | 约 800 行，quick start、命令说明、smoke 示例和历史标记混在一起。 | 保留 quick start；命令参考移到 `docs/current/supervisor-command-reference.md`；历史 smoke 移到 archive。 |
| `docs/current/supervisor-capability-map.md` | 约 700 行，能力索引和细节表混在一起。 | 保留能力索引；详细能力登记拆到 `docs/current/supervisor-capability-details.md`。 |
| `docs/current/status.md` | 当前事实和大量历史流水并列。 | 保留当前事实和最近状态；历史流水转入 review 或 archive。 |

## 第三批边界

- 不移动 `docs/architecture/` 里的 kernel、checkpoint、memory、track 文档。
- 不删除仍被 README、AGENTS、status 或 roadmap 直接引用的入口。
- 每次只拆一个长文，先改入口，再移动历史内容，最后修链接。
- 拆分后原路径必须保留短入口，不留下空 stub。

## 建议顺序

1. 拆 `agent-task-queue.md`：收益最大，风险最低。
2. 拆 `codex-supervisor-readonly.md`：保留 quick start，降低新读者负担。
3. 拆 `supervisor-capability-map.md`：把索引和详细登记分开。
4. 最后整理 `status.md`：等前三个入口稳定后再收缩状态页。

## 验证

第三批每个小提交至少运行：

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
