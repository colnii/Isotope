# 当前入口

状态：`当前入口`

这里放当前事实、近期计划和面向 AI 的最新入口。
旧分支清理已经完成，当前工作是应用目录收束，不是继续迁移旧分支。

建议阅读顺序：

1. [当前状态](./status.md)
2. [文档地图](./docs-map.md)
3. [任务队列](./agent-task-queue.md)
4. [术语索引](./terminology.md)
5. [应用目录迁移方案](./application-structure-plan.md)

如果只是想知道 `docs/` 每个目录放什么，先看 [docs 总入口](../README.md)。

旧目录清单已移到 `docs/archive/docs-inventory-pre-reorg.md`。
它只保留历史追溯价值，不再作为当前文档地图。
目录讨论原文、外部审查原文和一次性目录快照已移到 `docs/archive/current/`，
只保留追溯价值。
任务历史和旧状态全文也已移到 `docs/archive/current/`，当前入口只保留短摘要。

## 当前入口边界

- `status.md` 记录主线事实，不是完整 changelog。
- `agent-task-queue.md` 记录当前可执行任务；历史批次看 archive。
- `codex-supervisor-readonly.md` 是 quick start；完整命令看
  `supervisor-command-reference.md`。
- `supervisor-operations-runbook.md` 记录夜间 smoke、`supervise`、LLM summary
  和托管登记等长流程。
- `supervisor-capability-map.md` 是能力索引；详细登记看
  `supervisor-capability-details.md`。
- `docs-map.md` 是导航，不替代具体设计文档。
- `application-structure-plan.md`、`import-map.md` 和 `compat-proxy-audit.md`
  服务于目录/导入收束，不代表所有产品方向。
