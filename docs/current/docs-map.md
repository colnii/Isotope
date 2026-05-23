# 当前文档地图

状态：`当前入口`

## 快速入口

1. [README](../../README.md)：项目目标和快速开始。
2. [AGENTS](../../AGENTS.md)：AI 协作、验证、提交和 worktree 规则。
3. [docs 总入口](../README.md)：`docs/` 各目录职责。
4. [当前状态](./status.md)：主线真实状态。
5. [任务队列](agent-task-queue.md)：当前可执行任务。
6. [术语索引](./terminology.md)：英文定位词和中文解释。

## 当前事实

`docs/` 已完成第一轮分层，根目录没有 Markdown 残留。
当前入口集中在 `docs/current/`，历史材料不再和当前规则并列。`docs/README.md`
现在是顶层导航入口，本文件继续作为“当前事实怎么读”的地图。

行为优先级：

1. `AGENTS.md` 和 `README.md` 定义项目目标和 AI 协作规则。
2. `docs/current/status.md` 记录当前事实。
3. `architecture/`、`features/`、`reviews/` 是参考材料。

当产品需求和边界文档冲突时，先按产品目标和 `AGENTS.md` 执行。
边界文档只能提供 guardrail（护栏），不能把 AI 功能降级成规则脚本、
preflight（预检查）、diagnostic（诊断）或 not_enabled（未启用）路径。

仍要注意：

- `archive/` 和部分评审文档会保留旧说法，只用于追溯。
- `architecture/` 和 `features/` 里仍可能有早期命名，需要按需更新。
- 目录结构迁移已完成 demo / release 的第一批；旧路径 stub 已在稳定后删除。
  后续迁移仍处于暂停状态，不要默认继续移动 track、checkpoint、memory、
  kernel 或 status 文档。
- 最新目录命名讨论见 [目录结构最新说明](./目录结构最新说明.md)，其中
  `assistant` 泛化命名已被降级为兼容历史词。

## 当前层级

当前文档层级：

- `current/`：当前事实和近期计划。
- `architecture/`：架构边界参考，不替代产品需求。
- `features/`：功能设计和验收材料，不自动代表当前方向。
- `reviews/`：评审、复盘、分支审计，只作为决策背景。
- `archive/`：过期但仍需追溯的材料。

术语索引保留英文定位词，并补中文解释、所在层级和主要文件。

## 按任务找文档

| 你要做的事 | 先看 |
| --- | --- |
| 判断项目当前状态 | [status](./status.md) |
| 找下一步任务 | [agent-task-queue](./agent-task-queue.md) |
| 查英文术语和中文解释 | [terminology](./terminology.md) |
| 调整应用目录 | [application-structure-plan](./application-structure-plan.md)、[目录结构最新说明](./目录结构最新说明.md) |
| 查导入迁移或兼容代理 | [import-map](./import-map.md)、[compat-proxy-audit](./compat-proxy-audit.md) |
| 做 Supervisor 相关工作 | [codex-supervisor-readonly](./codex-supervisor-readonly.md)、[supervisor-command-reference](./supervisor-command-reference.md)、[supervisor-capability-map](./supervisor-capability-map.md)、[supervisor-capability-details](./supervisor-capability-details.md)、[supervisor-architecture-migration-table](./supervisor-architecture-migration-table.md) |
| 查旧任务/旧状态全文 | [agent-task-history](../archive/current/agent-task-history.md)、[status-history](../archive/current/status-history.md) |
| 查早期 v0.1 旧计划 | [archived plans](../archive/plans/) |
| 看文档迁移边界 | [docs-migration-plan](../reviews/docs-migration-plan.md)、[old-docs-closure-audit](../reviews/old-docs-closure-audit.md) |
| 看第三批长文拆分准备 | [current-docs-refactor-plan](../reviews/current-docs-refactor-plan.md) |
| 查旧分支/当前 worktree 清理证据 | [branch-cleanup](../reviews/branch-cleanup-2026-05-15.md)、[supervisor-worktree-recovery-audit](../reviews/supervisor-worktree-recovery-audit.md) |
| 查已归档的 current 来源材料 | [archive/current](../archive/current/) |

## 废止入口

以下材料不再作为 AI 行为规则：

- 旧分支暂停规则文档。
- 旧等待检查点文档。
- 旧的长篇路线图和批处理队列规则。

它们只保留历史参考价值。

## 后续审阅原则

- 人类要能快速看懂。
- AI 要能快速找到当前规则。
- 过期文档不能和当前规则并列。
- 删除前先判断是否有历史追溯价值。
- 移动文件后集中修复入口链接。
