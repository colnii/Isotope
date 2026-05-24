# Former Current Docs

状态：`archive index`

这里保存曾经放在 `docs/current/` 的来源材料。它们不是因为没价值而移走，
而是因为相关结论已经吸收到当前入口文档，继续放在 `current/` 会让读者把
历史语境误当成今天的执行规则。

## 文件

- [chatgpt审查](chatgpt审查.md)：外部审查原文；当前结论以
  `docs/current/naming-and-structure-review.md`、`import-map.md` 和
  `compat-proxy-audit.md` 为准。
- [目录结构精简说明](目录结构精简说明.md)：2026-05-23 的一次性精简目录快照；
  当前结构以 `docs/current/目录结构最新说明.md` 和实际 `git ls-files` 为准。
- [目录结构完整快照 2026-05-24](目录结构完整快照-2026-05-24.md)：曾在
  current 维护的逐文件 tracked 清单；因篇幅长、更新频率高、容易滞后和产生
  rebase 冲突，已降级为归档快照。当前结构职责以
  `docs/current/目录结构最新说明.md` 为准，真实文件列表以
  `git -c core.quotePath=false ls-files` 为准。
- [重新梳理目录结构逻辑](重新梳理目录结构逻辑.md)：目录结构讨论原文；
  当前规则以 `docs/current/application-structure-plan.md` 和
  `docs/current/naming-and-structure-review.md` 为准。
- [agent-task-history](agent-task-history.md)：旧任务队列完整历史；当前任务以
  `docs/current/agent-task-queue.md` 为准。
- [status-history](status-history.md)：旧状态页完整历史；当前事实以
  `docs/current/status.md` 为准。

## 使用规则

- 可以引用这些文件解释“为什么当时这样想”。
- 不要把这些文件当作当前开发队列或目录规则。
- 如果这里的内容重新成为当前需求，先写入 `docs/current/` 的短入口或对应
  review，再进入实现。
