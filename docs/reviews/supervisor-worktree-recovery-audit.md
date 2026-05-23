# Supervisor 工作恢复前状态归属审计

状态：`current recovery plan`

## 结论

`origin/main` 已继续推进；root `main` 目前 behind 3，且 root worktree 里有一组
未提交的 `InProcessServer` runtime 拆分和 projector checkpoint 相关改动。恢复
Supervisor 主线前，不要直接在 root 继续写代码，也不要把这些 root 改动和
Supervisor 分支混合提交。

当前安全顺序：

1. 先保留 root 的 runtime / projector 改动，单独确认它是否要成为下一条重构线。
2. 暂不清理刚刚仍在变化的 worktree；当前没有可直接删除的 clean duplicate
   （干净重复工作树）。
3. 继续保留有未提交改动或独立提交的 worktree，并逐个 rebase / review。
4. 暂不合并 `refactor/supervisor-flat-refactor` 和
   `refactor/supervisor-runner-promotion-split`，因为它们都落后当前 `main`，且会碰到
   Supervisor / docs / state projection 相关文件。

## 审计时间点

审计基线：

- `origin/main`: `89c02a5 fix(capacity): validate selected enum arguments`
- root `main`: `9a4183b feat(supervisor): include state snapshot in loop payload`，behind 3
- 文档收束提交已在该基线内：`73530e4 docs: close old docs cleanup line`

## root worktree

状态：

- branch: `main`
- upstream: `origin/main`
- ahead/behind: behind 3
- dirty files: runtime 拆分和 projector checkpoint 相关，未提交

涉及文件：

- `src/isotope/runtime/in_process.py`
- `src/isotope/platform/state/projector.py`
- `src/isotope/platform/state/projector_checkpoint.py`
- `src/isotope/runtime/in_process_actions.py`
- `src/isotope/runtime/in_process_agent_loop.py`
- `src/isotope/runtime/in_process_approvals.py`
- `src/isotope/runtime/in_process_checkpoints.py`
- `src/isotope/runtime/in_process_snapshots.py`
- `src/isotope/runtime/in_process_workspace.py`
- `tests/isotope/test_in_process_runtime_modularization.py`

判断：这不是旧文档线，也不是当前 Supervisor worktree 审计本身。它看起来是
`InProcessServer` large-file split（大文件拆分）候选，同时夹带小范围 projector
checkpoint 改动。下一步若要处理，应先把它作为独立重构任务验证、提交、迁出或拆开，
不要在 root 上继续叠 Supervisor 改动。

## worktree 归属

| Worktree | Branch | 当前状态 | 处理判断 |
| --- | --- | --- | --- |
| `.worktrees/supervisor-state-command` | `feature/supervisor-state-command` | 跟上 `origin/main`；dirty tests | 保留，先确认测试改动归属 |
| `.worktrees/supervisor-capacity-decision` | `feature/supervisor-capacity-decision` | ahead 1 / behind 2；dirty projector files | 保留，先 rebase / 冲突审计 |
| `.worktrees/worker-event-state-channel` | `codex/worker-event-state-channel` | ahead 4 / behind 1；clean | 保留，platform state / worker event channel 迁移候选 |
| `.worktrees/supervisor-flat-refactor` | `refactor/supervisor-flat-refactor` | ahead 18 / behind 7；clean | 暂不合并，先做 conflict / reuse audit |
| `.worktrees/supervisor-runner-promotion-split` | `refactor/supervisor-runner-promotion-split` | ahead 1 / behind 1；clean | 暂不合并，先确认 promotion split 是否仍有价值 |

## 风险点

- `supervisor-flat-refactor` 与当前 `origin/main` 在 docs、Supervisor parser、
  scheduler、memory views、projector 等文件上差异很大，不能当作简单 fast-forward。
- `supervisor-runner-promotion-split` 虽已变成 ahead 1，但仍需要确认它是否与
  `supervisor-flat-refactor` 或当前 `runner.py` 最新结构重复。
- root runtime 拆分有 1500+ 行移动迹象；如果继续在 root 开发，会让主线和 worktree
  的归属判断再次变复杂。
- root `main` behind 3，不能在未处理 dirty files 前直接 rebase / pull。

## 下一步

默认下一步是 root 改动归属和 main 跟进：

1. 决定 root `InProcessServer` / projector 改动：提交为独立重构、迁出到 worktree、
   拆分，或放弃。
2. 让 root `main` 跟进最新 `origin/main`。
3. 再按顺序处理 capacity / state-command worktree。
4. 最后再看 `worker-event-state-channel`、`supervisor-flat-refactor` 和
   `supervisor-runner-promotion-split`。

每一步都要先 fetch / rebase 到最新 `origin/main`，并避免在 root 上叠加 unrelated
Supervisor 改动。
