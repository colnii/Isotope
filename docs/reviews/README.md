# Reviews 文档

状态：`decision background`

这里保存审查、复盘、迁移计划、分支审计和阶段闭环记录。它们用于追溯为什么做过
某个决定，不是当前实现队列本身。

## 主要入口

- [External review package v0.2](external-review-package-v0.2.md)：外部审查材料。
- [Post external review checkpoint](post-external-review-checkpoint.md)：外部审查可交付后的停靠点。
- [v0.2 cycle closure review](v0.2-cycle-closure-review.md)：v0.2 周期闭环。
- [Docs migration plan](docs-migration-plan.md)：文档迁移控制文档；当前
  `phase 1 closed / paused`。
- [Current docs refactor plan](current-docs-refactor-plan.md)：current 长文拆分记录和后续边界。
- [Branch cleanup](branch-cleanup-2026-05-15.md)：旧分支清理记录。

## 分类索引

### 文档迁移和旧文档整理

这些文件控制文档移动、归档和链接风险。移动任何文档前先读这里，不要从单个
review 推断下一批迁移。

- [Docs migration plan](docs-migration-plan.md)：文档迁移计划和暂停边界。
- [Docs migration phase 1 dry run](docs-migration-phase-1-dry-run.md)：第一轮迁移演练记录。
- [Current docs refactor plan](current-docs-refactor-plan.md)：current 长文拆分记录和后续边界。
- [Kernel archive placement review](kernel-archive-placement-review.md)：记录旧 kernel
  参考文档暂不迁入 `docs/kernel/` 的判断。
- [Status docs placement review](status-docs-placement-review.md)：记录暂不创建
  `docs/status/`、不移动 current status / roadmap / v0.2 closure 的判断。
- [Deferred docs placement review](deferred-docs-placement-review.md)：记录 track /
  checkpoint / memory 文档迁移继续暂停的判断。
- [Old docs closure audit](old-docs-closure-audit.md)：旧文档整理线收束结论；
  下一步回 Supervisor 前先审计工作区、冲突和分支归属。

### 分支审计和旧代码 intake

这些文件只说明旧分支、aggressive/dev 分支或历史代码如何被审计、抽取或放弃。
它们不是当前合并授权。

- [Branch audit initial](branch-audit-initial-2026-05-15.md)：旧分支第一次盘点。
- [Branch audit refresh](branch-audit-refresh-2026-05-15.md)：旧分支刷新盘点。
- [Branch cleanup](branch-cleanup-2026-05-15.md)：旧分支清理记录。
- [Agent loop chain closure](agent-loop-chain-closure-2026-05-15.md)：agent-loop 链尾抽取闭环。
- [Controlled terminal exec deep review](controlled-terminal-exec-deep-review-2026-05-15.md)：受控终端执行深审。
- [Aggressive remaining code review](aggressive-remaining-code-review-v0.md)：aggressive 剩余代码首次 intake。
- [Aggressive remaining code intake refresh](aggressive-remaining-code-intake-refresh-v0.md)：CLI slice 后的 intake 刷新。

### v0.2 阶段和外部审查

这些文件解释 v0.2 为什么停在当前边界、tag 后有哪些增量，以及外部 reviewer
应该读什么。

- [v0.2 next track selection](v0.2-next-track-selection.md)：Track C 选择记录。
- [v0.2 mid cycle review](v0.2-mid-cycle-review.md)：v0.2 中段复盘和 Track E 选择。
- [Post v0.2 tag delta](post-v0.2-tag-delta.md)：`v0.2-demo` tag 后主线增量。
- [v0.2 cycle closure review](v0.2-cycle-closure-review.md)：v0.2 周期闭环。
- [External review package v0.2](external-review-package-v0.2.md)：外部审查包。
- [Post external review checkpoint](post-external-review-checkpoint.md)：外部审查 ready checkpoint。
- [Mainline idle checkpoint](mainline-idle-checkpoint.md)：主线 idle / maintenance 停靠点。

### kernel gap、track 和 closure 背景

这些文件记录 kernel gap、deferred surface、checkpoint integration 和已关闭的
runtime slice。它们是决策背景，不直接打开新实现。

- [Kernel gap review v0.2](kernel-gap-review-v0.2.md)：v0.2 kernel gap 初版评审。
- [Kernel gap review refresh](kernel-gap-review-refresh-v0.2.md)：app spike 后的 gap 刷新。
- [Deferred boundary review](deferred-boundary-review-v0.1.md)：deferred surface 排序。
- [Checkpoint history save integration](checkpoint-history-save-integration-v0.1.md)：checkpoint history save 集成边界。
- [Retry/cancel/supersede runtime closure](retry-cancel-supersede-runtime-closure-review.md)：R/C/S runtime first slice closure。

### app spike 和可用性压力测试

这些文件解释 app-shaped pressure test（应用形态压力测试）如何选择、覆盖了什么、
以及为什么某些方向暂缓。

- [First app spike readiness](first-app-spike-readiness.md)：第一个 app spike 准备度。
- [Second app spike selection](second-app-spike-selection.md)：第二个 app spike 选择。
- [App spike coverage review](app-spike-coverage-review.md)：两个 app spike 覆盖面复盘。

## 使用规则

- 要查当前事实，先回到 [`../current/`](../current/)。
- 要移动文档，先读 `docs-migration-plan.md`，不要从单个 review 推断下一批迁移。
- 旧文档整理线已收束；除非用户明确指定单一类别，不继续做默认迁移。
- review 可以作为证据来源，但不能覆盖 `AGENTS.md`、`README.md` 和
  `docs/current/status.md` 的当前规则。
- 旧 branch audit、closure review 和 intake review 只能解释历史判断，不能当作
  “现在可以合并/删除/迁移”的授权。
