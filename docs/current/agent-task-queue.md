# Agent 任务队列

状态：`项目整备`

## 当前原则

- 所有功能分支已暂停。
- 先做文档和协作规则整备。
- 不继续功能开发。
- 不合并、不删除、不重写分支。
- 不把当前分支定义成项目方向。

## 当前批次：协作入口清理

目标：让 AI 先读到正确的项目目标和工作方式。

范围：

- `AGENTS.md`
- `README.md`
- `docs/current/status.md`
- `docs/current/docs-map.md`
- `docs/current/agent-task-queue.md`
- 旧暂停规则文档的废止说明

完成标准：

- `AGENTS.md` 少于 100 行。
- 中文为主。
- 不再把 Isotope 描述成单纯内核项目。
- 不再要求所有工作围绕底座保守扩展。
- 不再把真实产品能力默认降级成诊断或预检查。
- 不再出现旧项目迁移来源叙述。

## 当前批次：文档与目录结构整理

状态：`已完成`

目标：把 `docs/` 分出清楚层级，建立真实术语索引，
并设计去 `kernel` 化的应用目录结构。

已采用层级：

- `docs/current/`
- `docs/architecture/`
- `docs/features/`
- `docs/reviews/`
- `docs/archive/`

已完成：

- 修复入口链接。
- 补充术语索引。
- 写应用目录迁移方案。
- 检查 `docs/` 根目录没有 Markdown 残留。
- 检查仓库内 Markdown 相对链接没有断链。

术语整理要求：

- 从代码、文档和用户常用表达中抽取术语。
- 英文术语保留，方便搜索对应代码。
- 每个术语补中文解释、所在层级和主要文件。
- 重点解释用户未必熟悉、但会影响判断的术语。
- 不只整理 `AGENTS.md` 里列出的临时术语。

目录结构整理要求：

- 不把 `isotope_kernel` 当成长期包名。
- 参考 AI 应用常见结构设计新目录。
- 候选层级包括 `apps/`、`src/core/`、`src/models/`。
- 候选层级包括 `src/agents/`、`src/rag/`、`src/features/`。
- 先出迁移方案，再移动代码。

## 下一批次：分支审计

状态：`初审完成`

目标：先看清每个暂停分支的真实状态，不急着合并。

初审文档：[branch-audit-initial-2026-05-15](../reviews/branch-audit-initial-2026-05-15.md)

刷新文档：[branch-audit-refresh-2026-05-15](../reviews/branch-audit-refresh-2026-05-15.md)

每个分支需要输出：

- 分支目标。
- 和当前分支的差异。
- 可直接合并的正经代码。
- 半成品或实验代码。
- 建议：继续、合并、归档、废弃。

下一步深审：

- 优先看 `feature/controlled-terminal-exec`。
- 只抽取可复用应用能力，不整体合并旧包名结构。
- 深审前先固定当前文档整备结果，避免后续 rebase/迁移时混杂。

深审已完成：[controlled-terminal-exec-deep-review-2026-05-15](../reviews/controlled-terminal-exec-deep-review-2026-05-15.md)

下一步迁移：

- 从 `feature/controlled-terminal-exec` 抽取终端执行层。
- 新代码放入应用化目录，不沿用 `isotope_kernel` 长期命名。
- 先做最小可测切片，再考虑 LLM provider 和产品聊天入口。

当前分支顺序：

1. 收敛 `feature/app-terminal-exec-migration`。
2. 深审 `codex/spike-aggressive-dev`。
3. 再看 agent-loop 链尾分支。

迁移进展：

- 已开分支 `feature/app-terminal-exec-migration`。
- 已新增 `src/agents/tools/terminal.py`。
- 已新增 `src/agents/executor/terminal_backend.py`。
- 已新增 `tests/agents/` 下的终端执行层测试。
- 已把旧 `src/isotope_kernel/terminal*.py` 入口改成短期兼容层。

## 验证

文档批次至少检查：

```bash
git diff --check
wc -l AGENTS.md
```

文档搬迁后额外检查：

```bash
find docs -maxdepth 1 -type f -name '*.md' -print
```

代码未改时，不必运行完整测试。
