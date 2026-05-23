# Architecture 文档

状态：`reference`

这里保存架构边界、contract（契约）、schema（结构定义）和 guardrail（护栏）。
这些文档帮助判断实现是否越界，但不替代产品目标和当前状态。

## 阅读顺序

1. 先读 [当前状态](../current/status.md) 和 [文档地图](../current/docs-map.md)。
2. 再按当前任务查对应 boundary（边界）文档。
3. 如果旧 boundary 和当前产品目标冲突，先按 `AGENTS.md` 和 `docs/current/`
   的当前事实执行，再把差异写回相关文档。

## 当前规则

- `v0.2` 和早期 `v0.1` 文档可能保留历史命名。
- boundary 文档只提供工程约束，不能把 AI 功能降级成 disabled stub
  （禁用占位）、diagnostic-only（只诊断）或纯规则脚本。
- 移动 architecture 文档前先看
  [docs migration plan](../reviews/docs-migration-plan.md)，当前默认不继续迁移
  kernel、checkpoint、memory 或 track 文档。
