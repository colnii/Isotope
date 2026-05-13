# Agent Loop Branch Closure Review

状态：`complete / branch-local closure`

## 1. Plain Summary

这条分支已经把 Agent loop 的本地小路跑了一遍：

- Agent 能按公开接口创建输入材料。
- Agent 能把一段工作交给 worker helper。
- Agent 能停下来等人审批。
- 程序重启后，Agent 还能找回待审批事项并继续完成。

结论：**目前没有发现必须改 kernel 主线的缺口。**

## 2. What Was Added

新增四个 demo 场景：

- `agent-loop-friction`
- `agent-loop-planner-friction`
- `agent-loop-planner-matrix`
- `agent-loop-planner-restart-pause`

这些场景都支持 plain output、`--trace` 和 `--json`。

## 3. What This Does Not Mean

这还不是产品级 Agent 系统。

本分支没有实现：

- real LLM
- scheduler
- real HTTP server
- real worker process
- provider adapter
- memory query engine
- filesystem mutation
- public SDK
- product multi-agent UX

## 4. Closure Decision

Branch-local Agent loop expansion should stop here.

Plain meaning: **不要继续凭空造更多测试场景。**  
下一步应该是三选一：

- 合并这条分支。
- 开 PR 给别人 review。
- 先保留这条分支，等真实 app 或 reviewer 反馈新问题。

## 5. Suggested Next Step

Recommended default: keep this branch as an app-layer proof branch until the user decides whether to merge or open a PR.

If continuing development later, only reopen when someone can point to a real problem, such as:

- “真实 app 调这个接口很别扭。”
- “reviewer 认为这里必须变成 kernel helper。”
- “某个公开 helper 不够用，导致 app 必须扫 raw events 或 private append。”
