# Agent Loop Planner Adapter Boundary v0.2

状态：`first slice complete`

## 1. 结论

这一片不是 real LLM planner。

它只接收已经解析好的 symbolic planner output（符号化规划器输出），
验证 basis（依据）没有过期，再交给 `run_agent_loop_step(...)` 执行当前允许的一步。

## 2. 已加入

- `run_agent_loop_planner_step(...)`
- `run_agent_loop_real_planner_contract_step(...)`
- `POST /runs/{run_id}/agent-loop-planner-step`

其中 real planner contract 只是未来真实 provider 的隔离壳：
它要求 raw prompt / raw response 已经 quarantine（隔离），
只把 `parsed_planner_output` 交给 planner adapter。

## 3. 行为

planner output 必须包含：

- `planner_run_id`
- `basis.run_id`
- `basis.last_event_id`
- `decision.step`
- `decision.request`

如果 `last_event_id` 已过期，直接拒绝。
如果 step 不在当前 `next_actions` 里，直接拒绝。
如果 payload 里出现 raw model text、prompt、full content 等字段，直接拒绝。

## 4. 边界

- 不调用真实 LLM。
- 不读取 prompt / model response。
- 不接受 raw provider payload。
- 不自动循环。
- 不创建第二套 planner 状态。
- 不绕过 `agent_loop_step` 的 allowlist。
- HTTP 入口仍是 in-process facade，不是 hosted API。

## 5. 验证

- `tests/isotope_kernel/test_agent_loop_planner_step_adapter.py`
- `tests/isotope_kernel/test_real_planner_adapter_contract.py`
- `tests/isotope_kernel/test_http_api_agent_loop_planner_step_adapter.py`
- `tests/isotope_kernel/test_http_api_boundary.py`
- `tests/isotope_kernel/test_http_api_route_inventory.py`

## 6. 后续方向

agent-loop 链尾的可复用主线接口已抽完。

后续如果要继续做产品级自动循环，应新开应用层分支，
明确 UI / scheduler / provider / auth / trace 的产品目标，
不要继续在旧 spike 分支上堆 demo。
