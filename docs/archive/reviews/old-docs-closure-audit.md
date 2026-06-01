# 旧文档整理收束审计

状态：`closed; return to Supervisor prep`

## 结论

旧文档整理线可以停止。下一步不继续移动文档，也不新开 `docs/status/`、
`docs/tracks/`、`docs/checkpoint/`、`docs/memory/` 或 `docs/kernel/`。

默认回到 Supervisor 主线前，先做一次工作区归属审计：确认当前 root worktree、
并行 worktree、未提交改动和冲突分别属于哪条任务线，再决定合并、暂停或清理。

## 审计范围

本次只检查旧文档整理是否已经有足够的入口、归档原因和暂停理由：

- `docs/current/agent-task-queue.md`
- `docs/current/docs-map.md`
- `docs/README.md`
- `docs/archive/README.md`
- `docs/reviews/README.md`
- `docs/reviews/docs-migration-plan.md`
- `docs/reviews/kernel-archive-placement-review.md`
- `docs/reviews/status-docs-placement-review.md`
- `docs/reviews/deferred-docs-placement-review.md`

不检查代码实现，不处理 Supervisor 代码冲突，不移动文件。

## 已满足项

- `docs/current/` 已保持短入口化；历史状态和历史任务正文进入
  `docs/archive/current/`。
- `docs/archive/README.md` 已说明 archive（归档）不是当前事实来源，并解释
  根目录旧文档为何暂留。
- `docs/reviews/README.md` 已把 migration、branch audit、v0.2 closure、
  kernel gap 和 app spike 分开索引。
- `docs/reviews/docs-migration-plan.md` 已标明 `phase 1 closed / paused`，
  并列出未来目录只是候选结构，不是默认迁移动作。
- kernel archive placement、status docs placement、track / checkpoint /
  memory placement 都已有独立 review，且结论都是暂不移动。
- `docs/current/agent-task-queue.md` 已记录归档原因，而不只是列出移动结果。

## 不继续处理的原因

继续做文档迁移的收益已经低于冲突风险：

- track、checkpoint、memory、kernel、status 文档仍有较多 cross-link（交叉链接）
  和当前入口引用，移动会制造大面积链接 churn（变更噪音）。
- 目前真正阻塞主线的是 Supervisor 产品化和并行工作区状态，不是旧文档缺少目录。
- 旧文档已经能通过入口定位；继续重排目录不会明显提高接手效率。

因此旧文档线只保留维护规则：新增文档先接入入口；旧文档重新变成当前需求时，
先写当前入口或 placement review，再考虑移动。

## 下一步

回 Supervisor 前先做：

1. 审计 root worktree 是否仍有 detached HEAD、conflict 或未提交代码改动。
2. 审计现有并行 worktree 的用途和是否已合并。
3. 决定 Supervisor 相关分支的顺序：先恢复/清理工作区，再继续产品化小批次。

如果用户明确要求继续文档线，只能按单一类别重开，例如只处理 track 或只处理
checkpoint，并在同一批里写 placement review、保留必要 stub、修链接和验证。
