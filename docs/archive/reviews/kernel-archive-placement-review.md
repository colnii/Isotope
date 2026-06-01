# Kernel Archive Placement Review

状态：`decision recorded / no move`

本文记录 `docs/archive/kernel-one-pager.md` 和
`docs/archive/kernel-decision-log.md` 的放置判断。

## 结论

暂不把这两个文件迁到 `docs/kernel/`。它们继续留在 `docs/archive/` 根目录，
并保持 historical kernel reference（历史 kernel 参考）定位。

## 原因

- `docs/reviews/docs-migration-plan.md` 把它们标成 medium-risk kernel batch，
  不是低风险旧文档清理。
- 真实 kernel 批次不只包含这两个文件，还会牵动
  `do../architecture/kernel-v0.1/kernel-spec-v0.1.md`、
  `do../architecture/kernel-v0.1/kernel-architecture-v0.1.md`、
  `do../architecture/kernel-v0.1/kernel-living-spec.md`、
  `docs/architecture/commitment-levels.md` 和 event/action registry 文档。
- 单独创建 `docs/kernel/` 并只放两个 archive 文件，会让读者误以为这些早期
  kernel 叙事重新成为当前事实入口。
- 当前产品主线是 Supervisor 和应用可用性；current truth（当前事实）仍应从
  `docs/current/status.md`、`docs/current/docs-map.md` 和
  `docs/architecture/README.md` 进入。

## 后续条件

只有满足以下条件时，才重新打开 kernel 目录迁移：

- 明确决定要建立 `docs/kernel/` 作为长期目录。
- 同批处理 kernel spec、kernel architecture、kernel living spec、
  commitment levels、action/event registry 和这两个 archive kernel references。
- 同提交修复 README、AGENTS、current docs、migration plan 和所有本地链接。
- 为旧路径保留风险说明或 stub（兼容占位），直到链接稳定。

## 当前动作

- 不移动文件。
- 保留 `docs/archive/README.md` 中的 historical kernel reference 说明。
- 将本 review 加入 `docs/reviews/README.md`，作为后续 kernel 批次的判断依据。
