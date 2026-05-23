# Agent Loop Tick Policy Boundary v0.2

状态：`first slice complete`

## 1. 结论

这一片不是自动 Agent loop。

它只给应用层一张“下一 tick 是否继续”的只读决策表：

- 当前 run 是否还能继续。
- 如果不能继续，原因是什么。
- 是否需要人类处理。
- 还有多少 tick budget（步数预算）。
- 用户是否主动暂停。

## 2. 已加入

- `InProcessServer.get_agent_loop_tick_policy(...)`
- `GET /runs/{run_id}/agent-loop-tick-policy`
- `build_agent_loop_tick_policy(...)`
- `python -m isotope.demo --scenario agent-loop-tick-policy-trace --trace`
  用 deterministic demo 展示 continue / pause / budget exhausted / approval /
  completed 的 handoff。

它复用 `get_agent_loop_control(run_id)` 的结果，不维护第二套状态。

## 3. 行为

`phase=ready` 且有 `next_actions` 时：

- `should_continue=true`
- `max_next_tick_kind=planner_step`

等待审批时：

- `should_continue=false`
- `must_stop_reason=awaiting_approval`
- `requires_human=true`

预算耗尽或用户暂停时：

- `must_stop_reason=tick_budget_exhausted`
- 或 `must_stop_reason=user_paused`

## 4. 边界

- 不执行 step。
- 不自动循环。
- 不调用 LLM provider。
- 不创建 event、artifact、checkpoint。
- 不返回 artifact full content、prompt、model response 或 raw content。
- HTTP 入口仍是 in-process facade，不是 hosted API。

## 5. 验证

- `tests/isotope/test_agent_loop_tick_policy.py`
- `tests/isotope/test_agent_loop_tick_policy_demo_scenario.py`
- `tests/isotope/test_http_api_agent_loop_tick_policy.py`
- `tests/isotope/test_http_api_boundary.py`
- `tests/isotope/test_http_api_route_inventory.py`

## 6. 后续方向

下一步不应直接接 real LLM。

更合适的是先用 `agent-loop-tick-policy-trace` 作为产品 handoff，
再决定是否把某个 Supervisor 受控入口接到 agent-loop-driven execution。
