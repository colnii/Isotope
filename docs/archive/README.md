# Archive 文档

状态：`historical reference`

这里保存已经退出当前入口的材料。归档不等于删除价值：这些文档仍可用于追溯设计
来源、历史对比和迁移前清单，但不能当作当前实现计划。

## 主要入口

- [Concepts](concepts/)：早期概念设计、应用层设想和参考项目对比。
- [Former current docs](current/)：曾放在 `docs/current/` 的讨论原文、
  外部审查和一次性快照；已不再作为当前执行入口。
- [Archived plans](plans/)：早期 v0.1 implementation / coding plans；
  这些计划已经被后续实现和目录重组替代。
- [Release archive](release/)：旧 release draft。
- [Docs inventory pre reorg](docs-inventory-pre-reorg.md)：文档重组前清单。
- [Kernel one pager](kernel-one-pager.md)：早期 kernel 概览。
- [Kernel decision log](kernel-decision-log.md)：早期 kernel 决策记录。

## 根目录旧文档

这些文件暂时留在 `docs/archive/` 根目录，不是因为它们仍是当前入口，而是因为
引用范围和迁移风险不同。后续要移动时应单独成批，同提交修链接。

| 文件 | 类型 | 留在根目录的原因 | 当前替代入口 |
| --- | --- | --- | --- |
| [docs-inventory-pre-reorg](docs-inventory-pre-reorg.md) | migration record（迁移记录） | `docs-migration-plan` 和 dry run 仍引用它作为迁移前清单。 | [docs-map](../current/docs-map.md)、[docs migration plan](../reviews/docs-migration-plan.md) |
| [kernel-mainline-maintenance-mode](kernel-mainline-maintenance-mode.md) | obsolete rule（废止规则） | 已在 archive；保留是为了解释“底座保守维护”规则为什么不再适用。 | [AGENTS](../../AGENTS.md)、[current status](../current/status.md) |
| [kernel-one-pager](kernel-one-pager.md) | historical kernel reference（历史 kernel 参考） | 迁移计划标为 medium risk kernel batch；先补归档原因，不和本批旧文档清理混动。 | [current status](../current/status.md)、[architecture README](../architecture/) |
| [kernel-decision-log](kernel-decision-log.md) | historical kernel reference（历史 kernel 参考） | 迁移计划标为 medium risk kernel batch；后续若移动，应随 kernel 文档一起处理。 | [current status](../current/status.md)、[architecture README](../architecture/) |

## 使用规则

- 当前事实以 [`../current/status.md`](../current/status.md) 为准。
- archive 文档里的旧命名和旧路径只作历史线索。
- 如果 archive 内容重新变成当前需求，先在 `docs/current/` 或对应目录写清新入口，
  不要直接把旧文档恢复成当前规则。
