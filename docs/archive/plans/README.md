# Archived Plans

状态：`historical plans`

这里保存已经退出当前执行入口的旧计划文档。它们仍可用于追溯早期
vertical slice（纵向切片）怎么拆，但不能当作当前 architecture boundary
（架构边界）或任务队列。

## 文件

- [Implementation Plan v0.1](implementation-plan-v0.1.md)：早期 v0.1
  最小闭环计划；当前实现状态以 `docs/current/status.md` 和相关 boundary 文档为准。
- [Coding Plan v0.1](coding-plan-v0.1.md)：早期 v0.1 编码拆解；
  归档原因是目录、模块和测试布局已经被后续实现与重构替代。

## 使用规则

- 查当前任务，先读 `docs/current/agent-task-queue.md`。
- 查当前架构边界，先读 `docs/architecture/README.md` 和对应 boundary 文档。
- 如果这里的旧计划重新变成需求，先写一份新的 current/review 入口，再进入实现。
