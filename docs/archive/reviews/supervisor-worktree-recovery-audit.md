# Supervisor 工作恢复前状态归属审计

状态：`current recovery plan`

## 结论

`origin/main` 已继续推进；root `main` 已跟上并保持 clean。此前 root 里的
`InProcessServer` runtime 拆分和 projector checkpoint 改动已经作为独立提交进入
`main`。

恢复 Supervisor 主线前，不要再在 root 叠加新改动；继续用 worktree 逐条处理剩余
Supervisor / capacity / state 分支。

当前安全顺序：

1. root `main` 只作为同步基线，不继续叠新改动。
2. 保留仍有独立提交或活跃 dirty state 的 worktree，并逐个 rebase / review。
3. 对 clean 且等同 `origin/main` 的 worktree，先确认是否有活跃窗口再清理；不要在
   状态快速变化时批量删除。
4. 暂不合并 `refactor/supervisor-flat-refactor` 和
   `refactor/supervisor-runner-promotion-split`，因为它们都落后当前 `main`，且会碰到
   Supervisor / docs / state projection 相关文件。

## 审计时间点

审计基线：

- `origin/main`: `3d92810 fix(state): preserve projector datetime hook`
- root `main`: `3d92810 fix(state): preserve projector datetime hook`
- 文档收束提交已在该基线内：`73530e4 docs: close old docs cleanup line`

## root worktree

状态：

- branch: `main`
- upstream: `origin/main`
- ahead/behind: clean relative to upstream
- dirty files: none

刚进入主线的 runtime split 涉及：

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

判断：root runtime 归属已经解决。下一步不要回到 root 继续改；应从最新
`origin/main` 开 worktree 或使用已有 worktree，逐条处理剩余分支。

## worktree 归属

| Worktree | Branch | 当前状态 | 处理判断 |
| --- | --- | --- | --- |
| `.worktrees/http-api-boundary-split` | `refactor/http-api-boundary-split` | behind 4；clean | 可清理候选；其 commit 已在 `origin/main` 历史内 |
| `.worktrees/supervisor-capacity-decision` | `feature/supervisor-capacity-decision` | tracks `origin/feature/supervisor-capacity-decision`；clean | 保留，按分支自己的 upstream 处理 |
| `.worktrees/supervisor-flat-refactor` | detached worktree；branch `refactor/supervisor-flat-refactor` still exists | branch ahead 18 / behind 7 | 暂不合并，先恢复 worktree branch 绑定或重新建干净审计 worktree |

## 风险点

- `supervisor-flat-refactor` 与当前 `origin/main` 在 docs、Supervisor parser、
  scheduler、memory views、projector 等文件上差异很大，不能当作简单 fast-forward。
- promotion split 已进入 `origin/main`，不要再从旧 runner-promotion worktree 回退它。
- runtime split 已进入 `main`，后续如果继续拆 runtime，必须新开独立 worktree。
- `supervisor-flat-refactor` 当前 worktree 是 detached HEAD；处理前先确认 worktree
  和 branch 的关系，避免在错误 HEAD 上继续。
- clean duplicate 可能是刚完成的活跃窗口；清理前先确认没有未同步输出或正在运行的
  agent。

## 下一步

默认下一步是小分支处理：

1. 先确认是否可以清理 clean duplicate：`http-api-boundary-split`。
2. 处理 `supervisor-capacity-decision`，需要先 rebase 到最新 `origin/main`。
3. 最后再看 `supervisor-flat-refactor`。

每一步都要先 fetch / rebase 到最新 `origin/main`，并避免在 root 上叠加 unrelated
Supervisor 改动。
