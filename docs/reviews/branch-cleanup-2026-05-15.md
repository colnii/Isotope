# 分支清理记录：2026-05-15

状态：`完成`

## 1. 结论

暂停分支中的可复用代码已按小切片抽入 `main`。
剩余分支主要保留旧 docs、demo trace、spike 记录或已被主线覆盖的代码。

本次已删除这些本地和远端分支：

- `codex/spike-aggressive-dev`
- `feature/controlled-terminal-exec`
- `feature/agent-loop-*`
- `feature/planner-*`
- `feature/real-planner-*`
- `spike/aggressive-dev`
- `spike/app-agent-loop-friction`

同时删除本地迁移分支：

- `feature/app-terminal-exec-migration`
- `backup/feature-controlled-terminal-exec-pre-rebase-20260513-004746`

## 2. 删除原因

- 正经代码已抽入主线。
- 旧分支会覆盖当前中文协作规则和新 docs 层级。
- 剩余大文件不适合整体合并。
- demo trace / pressure tests 不再是待迁移代码。

## 3. 当前分支状态

当前本地和远端只保留：

- `main`

后续若继续做应用层功能，应从 `main` 新开分支或新 worktree。
