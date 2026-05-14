# Agent Loop Step Driver Boundary v0.2

状态：`first slice complete / closed for now`

## 1. Plain Summary

上一片 `Agent Loop Run Control` 让 app 能看到“下一步可以做什么”。

这一片补的是一个很小的“执行一步”按钮：app 可以通过一个受控入口，让 Isotope 执行当前 run 允许的一个 Agent loop step。

它不是自动驾驶，也不是完整 Agent loop 产品。它更像手动挡：系统告诉你可选动作，app 明确选择其中一个，内核只执行这一小步。

## 2. What Was Added

- `InProcessServer.run_agent_loop_step(run_id, request)`
- `POST /runs/{run_id}/agent-loop-step` in the in-process `HttpApiApp`
- 当前支持的 step：
  - `create_source_artifact`
  - `submit_worker_handoff`
  - `submit_approval_gated_action`
  - `get_approval`
  - `resolve_approval`

## 3. Behavior

Step driver 会先读取 `get_agent_loop_control(run_id)`，只允许执行当前 `next_actions` 里出现的 step。

如果 run 还在 `ready`：

- 可以创建 source artifact。
- 可以提交 approval-gated action，让 run 进入 `awaiting_approval`。
- 可以提交 worker handoff，只要 app 提供已有 artifact `ResourceRef` 和 delegation intent。

如果 run 正在 `awaiting_approval`：

- 可以读取 pending approval。
- 可以 resolve approval，让原 action 继续完成或被拒绝。

## 4. Hard Boundaries

- 每次只执行一个 step。
- 不做 scheduler，不自动循环。
- 不接 real LLM provider，不读取 prompt / model response。
- 不实现 real worker runtime、process spawn、container、git worktree 或 remote executor。
- 不实现 memory query engine、product UI、auth、notification 或 real listening HTTP server。
- 不允许执行不在当前 `next_actions` 里的 step；这种请求在写入 event 前 fail closed。
- HTTP 入口仍是 in-process facade，不是 hosted API。

## 5. Current Tests

- `tests/isotope/test_agent_loop_step_driver.py`
- `tests/isotope/test_http_api_agent_loop_step_driver.py`
- HTTP route inventory coverage in `tests/isotope/test_http_api_route_inventory.py`
- Minimal HTTP surface coverage in `tests/isotope/test_http_api_boundary.py`

## 6. Next Development Direction

`Agent Loop Tick Policy` first slice 已完成，见
[agent-loop-tick-policy-boundary-v0.2](./agent-loop-tick-policy-boundary-v0.2.md)。

下一步继续审 agent-loop 链尾的 planner adapter / real planner contract。

白话说：现在同一进程里能看控制状态、点下一步、判断下一 tick 是否继续；
后面再决定要不要接规划器输出，而不是直接上 real LLM 自动循环。
