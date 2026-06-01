# Agent Loop 分支链闭环审阅

状态：`closed / extract-only complete`

## 1. 结论

`feature/agent-loop-*`、`feature/planner-*`、
`feature/real-planner-*` 这组分支是一条层叠链。
现在不需要逐个合并，也不能整体合并链尾。

主线已经吸收可复用的小接口：

- `get_agent_loop_control(...)`
- `run_agent_loop_step(...)`
- `get_agent_loop_tick_policy(...)`
- `run_agent_loop_planner_step(...)`
- `run_agent_loop_real_planner_contract_step(...)`
- 对应 in-process HTTP facade routes

剩余内容主要是旧 docs 路径、demo trace、重复评审材料和 spike 记录。
这些保留历史参考，不再作为待合并代码。

## 2. 已吸收的能力

`run control`：
产品层可以看 run 当前 phase、阻塞原因、审批状态和 next actions。

`step driver`：
产品层可以显式执行当前允许的一步，不自动循环。

`tick policy`：
产品层可以判断下一 tick 是否继续，支持 tick budget 和 user pause。

`planner adapter`：
只接受符号化 planner output，验证 basis 后交给 step driver。

`real planner contract`：
只接受 raw prompt / raw response 已隔离的 provider-shaped result，
不把真实 provider payload 写进 event 或 checkpoint。

## 3. 不整体合并的原因

- 链尾分支仍使用旧 docs 根目录结构，会覆盖当前 `docs/current` 等新结构。
- 链尾包含旧版 `AGENTS.md` / `README.md` 表述，会冲掉当前中文协作规则。
- 链尾相对当前 main 缺少 terminal、capability runner、LLM route 等后续主线代码。
- demo trace 很多，但不是新的稳定接口。
- real LLM、scheduler、provider execution、product UI 仍不是这组分支的已实现能力。

## 4. 分支处理建议

保留参考：

- `feature/agent-loop-tick-budget-read-model-spike`

可视为已被链尾覆盖：

- `feature/agent-loop-run-control`
- `feature/agent-loop-step-driver`
- `feature/agent-loop-step-driver-restart`
- `feature/planner-step-driver-adapter`
- `feature/planner-step-demo-trace`
- `feature/planner-approval-resume-demo-trace`
- `feature/planner-restart-resume-demo-trace`
- `feature/agent-loop-demo-coverage-review`
- `feature/real-planner-adapter-boundary-review`
- `feature/real-planner-adapter-contract-spike`
- `feature/agent-loop-tick-policy-boundary-review`
- `feature/agent-loop-tick-policy-read-model`
- `feature/agent-loop-tick-policy-demo-trace`
- `feature/agent-loop-tick-budget-pause-contract-review`

无待合并内容：

- `spike/app-agent-loop-friction`

## 5. 后续

如果后面继续做完整 Agent loop 产品，应新开应用层分支，
从真实产品目标出发设计 UI / provider / scheduler / trace。
不要继续从旧 spike 分支整块搬代码。
