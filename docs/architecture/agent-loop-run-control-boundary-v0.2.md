# Agent Loop Run Control Boundary v0.2

状态：`first slice complete / closed for now`

## 1. Plain Summary

这一片不是完整 Agent loop 产品。

它补的是一个 app-layer 需要的“控制看板”：给定一个 `run_id`，app 可以问 Isotope 当前 run 在哪里、是否卡在审批、下一步用户或 app 可以做什么，以及哪些大能力还没实现。

## 2. What Was Added

- `InProcessServer.get_agent_loop_control(run_id)`
- `GET /runs/{run_id}/agent-loop-control` in the in-process `HttpApiApp`
- 一个 summary-only read model，包含：
  - `phase`
  - `waiting_on`
  - `next_actions`
  - `progress`
  - `approvals`
  - `blocked_reason_codes`
  - `deferred_capabilities`

## 3. Why It Matters

之前 app 可以读完整 run state，也可以扫 events，但这对产品层太原始。

现在产品层可以直接拿到一份更像“驾驶舱”的结果：

- 新 run：`phase=ready`，可以继续创建 source artifact、交给 worker、或提交需要审批的动作。
- 等审批：`phase=awaiting_approval`，明确显示 pending approval 和可执行的 `get_approval` / `resolve_approval`。
- 已完成：`phase=completed`，没有下一步动作。

## 4. Hard Boundaries

- 这是 read-only helper，不追加 canonical events。
- 不返回 artifact full content、raw tool text、prompt 或 model response。
- 不扫描 public `get_events(...)` 来拼产品状态；它复用 projected `RunState`。
- HTTP 入口仍是 in-process facade，不是 real listening HTTP server。
- 不实现 real LLM provider、scheduler、real worker runtime、memory query engine、UI、auth 或 notification。

## 5. Current Tests

- `tests/isotope_kernel/test_agent_loop_run_control.py`
- `tests/isotope_kernel/test_http_api_agent_loop_control.py`
- HTTP route inventory coverage in `tests/isotope_kernel/test_http_api_route_inventory.py`
- Minimal HTTP surface coverage in `tests/isotope_kernel/test_http_api_boundary.py`

## 6. Next Development Direction

下一步如果继续走完整产品级 Agent loop，不应马上接 real LLM。

更稳的下一步是做 `Product Agent Loop Step Driver`：让 app 在拿到 `next_actions` 后，可以通过一个很小的受控入口触发“执行下一步”，先仍然用 deterministic / fake planner，确认暂停、审批、失败和继续执行这些产品动作都顺。
