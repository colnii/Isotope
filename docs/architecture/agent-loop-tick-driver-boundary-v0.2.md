# Agent Loop Tick Driver Boundary v0.2

状态：`first slice complete`

## 1. 结论

这一片补齐的是单 tick driver（单步循环驱动器），不是后台自动循环。

它把已有的三块串起来：

1. `get_agent_loop_tick_policy(...)` 先判断本轮能不能继续。
2. `run_agent_loop_planner_step(...)` 执行一个已解析的 symbolic planner decision。
3. 再读取一次 tick policy，给调用方返回执行后的继续/停止状态。

## 2. 已加入

- `src/isotope/agents/loop/tick.py::run_agent_loop_tick(...)`
- `InProcessServer.run_agent_loop_tick(...)`
- `POST /runs/{run_id}/agent-loop-tick`
- `python -m isotope.demo --scenario agent-loop-tick-driver-trace --trace`
  展示 `before_policy -> planner_result -> after_policy` 的人类可读 handoff。
- Supervisor `call_capacity` action 会复用同一个 `planner_output` contract，
  通过 `run_agent_loop_tick(...)` 执行一次 `call_capability`，并返回
  `tick_result` 供上层 handoff 查看。
- `python -m isotope.demo --scenario supervisor-capacity-handoff-trace --trace`
  展示 `Supervisor action -> planner_output_summary -> tick_result ->
  persisted policy` 的可读链路。
- `isotope-supervisor capacity plan --execute-agent-loop` 的 plain 输出会打印
  低敏 planner selected step、tick status、tick stop reason 和 artifact ref。
- `isotope-supervisor capacity plan --json --execute-agent-loop` 会返回同一组
  `agent_loop_summary` 低敏字段。
- `call_capacity` 执行动作会把同源 `agent_loop_summary` 写入低敏
  capacity memory record，不保存 raw `tick_result`。
- Dashboard / web 的 multi-worker payload 会从 capacity memory record 读取
  `agent_loop_summary`，只展示 tick / step / artifact 摘要，不直接读取原始
  `tick_result` 深层结构。
- Multi-worker payload 的 `supervised_execution` 会聚合最近 capacity run，
  作为更完整 supervised execution view 的低敏读取入口。
- `python -m isotope.demo --scenario supervisor-capacity-dashboard-smoke --trace`
  会执行 fixture `call_capacity`、读取 capacity memory record、刷新
  dashboard/web multi-worker payload，并确认三段复用同一组低敏
  `agent_loop_summary`。
- Dashboard plain view 会优先从
  `multi_worker.supervised_execution.recent_capacity_runs` 打印最近 capacity 的
  tick / step / artifact 摘要，不读取或展开 raw `tick_result`。
- Web 运行焦点区也直接读取 `multi_worker.supervised_execution`，只显示最近
  supervised capacity run 的低敏 tick / step / artifact 摘要。

HTTP body 只接受：

- `planner_output`
- `tick_budget`
- `user_pause`

## 3. 行为

如果 tick policy 显示可以继续：

- `planner_output` 必须是 object。
- driver 只执行一个 planner-selected step。
- 返回 `tick_status=executed`、`before_policy`、`planner_result` 和
  `after_policy`。
- 如果传入 `tick_budget`，执行后 `ticks_used` 加 1。

如果 tick policy 显示不能继续：

- 不要求 `planner_output`。
- 不执行 planner step。
- 不创建 event 或 artifact。
- 返回 `tick_status=stopped` 和 `stop_reason`。

## 4. 边界

- 不调用真实 LLM provider。
- 不自动多轮循环。
- 不接 scheduler 或 real worker runtime。
- 不绕过 planner adapter 的 basis 校验和 raw payload 隔离。
- Supervisor handoff 只允许已由 capacity decision 标记为
  `can_execute_agent_loop=true` 的 `call_capacity` 进入这一条路径。
- HTTP 入口仍是 in-process facade，不是 hosted API。

## 5. 验证

- `tests/unit/agents/loop/test_agent_loop_tick_driver.py`
- `tests/unit/interfaces/http/test_http_api_agent_loop_tick_driver.py`
- `tests/e2e/test_agent_loop_tick_driver_demo_scenario.py`
- `tests/e2e/test_supervisor_capacity_handoff_demo_scenario.py`
- `tests/e2e/test_supervisor_capacity_dashboard_smoke_demo_scenario.py`
- `tests/unit/agents/loop/test_agent_loop_planner_step_adapter.py`
- `tests/unit/agents/loop/test_agent_loop_tick_policy.py`
- `tests/unit/features/supervisor/test_supervisor_capacity_path.py`
- `tests/unit/interfaces/http/test_http_api_boundary.py`
- `tests/unit/interfaces/http/test_http_api_route_inventory.py`
