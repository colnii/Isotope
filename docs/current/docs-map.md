# 当前文档地图

状态：`当前入口`

## 先读这些

1. [README](../../README.md)：项目目标和快速开始。
2. [AGENTS](../../AGENTS.md)：AI 协作规则。
3. [当前状态](./status.md)：本轮整备的真实状态。
4. [任务队列](agent-task-queue.md)：接下来做什么。
5. [术语索引](./terminology.md)：英文定位词和中文解释。

## 当前事实

`docs/` 已完成第一轮分层，根目录没有 Markdown 残留。
当前入口集中在 `docs/current/`，历史材料不再和当前规则并列。

仍要注意：

- `archive/` 和部分评审文档会保留旧说法，只用于追溯。
- `architecture/` 和 `features/` 里仍可能有早期命名，需要按需更新。
- 目录结构迁移还没有执行，新结构先看迁移方案。
- 最新目录命名讨论见 [目录结构最新说明](./目录结构最新说明.md)，其中
  `assistant` 泛化命名已被降级为兼容历史词。

## 当前层级

当前文档层级：

- `current/`：当前事实和近期计划。
- `architecture/`：仍有效的架构设计。
- `features/`：功能设计和验收材料。
- `reviews/`：评审、复盘、分支审计。
- `archive/`：过期但仍需追溯的材料。

术语索引保留英文定位词，并补中文解释、所在层级和主要文件。

## 目录入口

- 当前事实：[current/](./)
- 架构设计：[architecture/](../architecture/)
- 产品能力：[features/](../features/)
- 评审记录：[reviews/](../reviews/)
- 历史归档：[archive/](../archive/)
- 应用目录迁移：[application-structure-plan](./application-structure-plan.md)
- 目录结构最新说明：[目录结构最新说明](./目录结构最新说明.md)
- 目录结构逻辑补充：[重新梳理目录结构逻辑](./重新梳理目录结构逻辑.md)
- 命名与目录审计：[naming-and-structure-review](./naming-and-structure-review.md)
- Codex Supervisor 只读版：[codex-supervisor-readonly](./codex-supervisor-readonly.md)
- Codex Supervisor 能力地图：[supervisor-capability-map](./supervisor-capability-map.md)
- ChatGPT 审查：[chatgpt审查](./chatgpt审查.md)
- 导入路径迁移表：[import-map](./import-map.md)
- 兼容代理审计：[compat-proxy-audit](./compat-proxy-audit.md)
- 分支初审：[branch-audit-initial-2026-05-15](../reviews/branch-audit-initial-2026-05-15.md)
- 分支审计刷新：[branch-audit-refresh-2026-05-15](../reviews/branch-audit-refresh-2026-05-15.md)
- 终端分支深审：[controlled-terminal-exec-deep-review-2026-05-15](../reviews/controlled-terminal-exec-deep-review-2026-05-15.md)
- Agent loop tick policy：[agent-loop-tick-policy-boundary-v0.2](../architecture/agent-loop-tick-policy-boundary-v0.2.md)
- Agent loop planner adapter：[agent-loop-planner-adapter-boundary-v0.2](../architecture/agent-loop-planner-adapter-boundary-v0.2.md)
- Agent loop 分支闭环：[agent-loop-chain-closure-2026-05-15](../reviews/agent-loop-chain-closure-2026-05-15.md)
- 分支清理记录：[branch-cleanup-2026-05-15](../reviews/branch-cleanup-2026-05-15.md)

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
