# Deferred Docs Placement Review

状态：`decision recorded / no move`

本文记录 track、checkpoint 和 memory 文档是否迁移到专门目录的放置判断。

## 结论

继续暂停 track、checkpoint 和 memory 文档迁移。本批不创建 `docs/tracks/`、
`docs/checkpoint/` 或 `docs/memory/`，也不移动相关文件。

## 原因

- `docs/reviews/docs-migration-plan.md` 已明确 Phase 1 closed / paused，
  后续不默认移动 track、checkpoint、memory、kernel、status entrypoint 或 roadmap。
- Track 文档包含 HTTP API、artifact content、approval pause/resume、
  external ingestion 等当前仍被 README、AGENTS、status、roadmap 和 review 文档引用的
  high-risk entrypoints（高风险入口）。
- checkpoint 文档是一组边界，不是单个旧文件；其中
  `checkpoint-ownership-v0.1.md` 已被 migration plan 标为 high risk。
- memory 文档虽然数量少，但 `memory-v0.1-scope-freeze.md` 仍是 current memory
  scope reference（当前 memory 范围参考），不能混入低风险归档整理。
- 三类目录如果同时打开，会把旧文档整理扩展成大规模目录迁移；如果拆开迁移，
  又需要为每类单独做 stub、链接审计和验证。

## 后续条件

只有满足以下条件时，才重新打开其中一类迁移：

- 明确选择单一类别：track、checkpoint 或 memory，不能三类混在同一批。
- 先写对应 placement review（放置评审），说明保留、迁移或拆分的判断。
- 同提交修复 README、AGENTS、current docs、roadmap、reviews、archive 和所有本地链接。
- 高风险旧路径需要 stub（兼容占位）或明确跳转策略。
- 文档迁移不能和代码实现、测试重构或 Supervisor 产品改动混在一起。

## 当前动作

- 不移动文件。
- 保持 `docs/architecture/` 承担 active boundary reference（活跃边界参考）职责。
- 保持 `docs/reviews/docs-migration-plan.md` 为迁移控制文档。
- 将本 review 加入 `docs/reviews/README.md`，作为后续 track/checkpoint/memory
  批次的判断依据。
