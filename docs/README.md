# Isotope 文档入口

状态：`当前导航入口`

这里是 `docs/` 的总入口。它只负责告诉读者先读什么、各目录放什么、
哪些材料已经归档；当前产品和实现事实仍以 `docs/current/` 为准。

## 先读什么

1. [当前状态](current/status.md)：主线真实状态和当前优先级。
2. [当前文档地图](current/docs-map.md)：按读者路径找材料。
3. [任务队列](current/agent-task-queue.md)：已完成批次和下一步。
4. [术语索引](current/terminology.md)：英文定位词和中文解释。
5. [协作规则](../AGENTS.md)：AI 协作、验证、提交和 worktree 规则。

## 目录职责

| 目录 | 用途 | 当前性 |
| --- | --- | --- |
| [`current/`](current/) | 当前事实、近期计划、活跃入口 | 最高 |
| [`architecture/`](architecture/) | 架构边界、contract（契约）和 guardrail（护栏） | 参考 |
| [`features/`](features/) | 功能设计、demo、验收和 friction review（摩擦评审） | 参考 |
| [`reviews/`](reviews/) | 审查、复盘、迁移计划和分支审计 | 背景 |
| [`archive/`](archive/) | 过期设计、概念材料和旧清单 | 追溯 |

## 清理规则

- `docs/reviews/docs-migration-plan.md` 当前状态是 `phase 1 closed / paused`。
  不要把 track、checkpoint、memory、kernel 或 status 文档当作默认下一批迁移。
- 已移动过的 demo / release 文档曾保留旧路径 compatibility stub（兼容占位文件）；
  稳定一轮并完成链接审计后，低风险 stub 已删除。新增链接应直接指向真实文件。
- 清理文档时优先更新入口和索引；真正移动文件要单独成批，且同一提交修复链接。
- 删除前先判断是否还有历史追溯价值；不能因为内容旧就直接删。

## 常用验证

文档-only 改动至少运行：

```bash
git diff --check
rg -n "\]\((?!https?://)[^)]+\.md\)" README.md AGENTS.md docs
```

如果移动了文件，再按 [迁移计划](reviews/docs-migration-plan.md) 的验证清单执行。
