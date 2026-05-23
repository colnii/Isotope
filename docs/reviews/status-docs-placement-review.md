# Status Docs Placement Review

状态：`decision recorded / no move`

本文记录 status 类文档是否迁入 `docs/status/` 的放置判断。

## 结论

暂不创建 `docs/status/`，也不移动 `docs/current/status.md`、
`docs/architecture/v0.2-roadmap.md`、`docs/reviews/v0.2-cycle-closure-review.md`、
`docs/reviews/post-v0.2-tag-delta.md` 或
`docs/archive/docs-inventory-pre-reorg.md`。

## 原因

- `docs/current/status.md` 是当前事实入口，被 README、AGENTS、docs 总入口、
  external review 和多份历史文档直接引用。
- `docs/architecture/v0.2-roadmap.md` 仍承担 roadmap（路线图）和 post-tag
  delta（标签后增量）索引职责；它不是单纯旧状态页。
- `docs/reviews/v0.2-cycle-closure-review.md` 和
  `docs/reviews/post-v0.2-tag-delta.md` 已在 reviews 分类索引中，当前更适合保留
  decision background（决策背景）定位。
- `docs/archive/docs-inventory-pre-reorg.md` 是 migration record（迁移记录），
  migration plan 和 dry run 仍用它做迁移前基线。
- 现在新建 `docs/status/` 会迫使 README、AGENTS、current docs、roadmap、
  reviews 和 archive 链接同批改动，风险超过本轮旧文档整理收益。

## 后续条件

只有满足以下条件时，才重新打开 status 目录迁移：

- 明确决定 `docs/status/` 是长期目录，而不是临时整理位置。
- 同批处理 current status、roadmap、cycle closure、tag delta、docs inventory、
  migration plan 和 dry run 的路径关系。
- 为 `docs/current/status.md` 这种高频入口保留 stub（兼容占位）或其他明确
  跳转策略。
- 同提交修复 README、AGENTS、docs/current、docs/reviews、docs/archive 和所有
  本地 Markdown 链接。

## 当前动作

- 不移动任何 status 类文件。
- 保持 `docs/current/status.md` 为当前事实入口。
- 保持 v0.2 closure / tag delta 在 `docs/reviews/`，由
  `docs/reviews/README.md` 分类索引。
- 保持 `docs/archive/docs-inventory-pre-reorg.md` 在 archive 根目录，继续作为迁移
  前清单。
