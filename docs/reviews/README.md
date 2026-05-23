# Reviews 文档

状态：`decision background`

这里保存审查、复盘、迁移计划、分支审计和阶段闭环记录。它们用于追溯为什么做过
某个决定，不是当前实现队列本身。

## 主要入口

- [Docs migration plan](docs-migration-plan.md)：文档迁移计划；当前
  `phase 1 closed / paused`。
- [Docs migration phase 1 dry run](docs-migration-phase-1-dry-run.md)：第一轮迁移演练记录。
- [Current docs refactor plan](current-docs-refactor-plan.md)：第三批长文拆分记录和后续边界。
- [Branch cleanup](branch-cleanup-2026-05-15.md)：旧分支清理记录。
- [External review package v0.2](external-review-package-v0.2.md)：外部审查材料。
- [v0.2 cycle closure review](v0.2-cycle-closure-review.md)：v0.2 周期闭环。

## 使用规则

- 要查当前事实，先回到 [`../current/`](../current/)。
- 要移动文档，先读 `docs-migration-plan.md`，不要从单个 review 推断下一批迁移。
- review 可以作为证据来源，但不能覆盖 `AGENTS.md`、`README.md` 和
  `docs/current/status.md` 的当前规则。
