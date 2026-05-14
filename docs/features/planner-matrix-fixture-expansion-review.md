# Planner Matrix Fixture Expansion Review

状态：`review complete / docs-only / branch-local`

## 1. Purpose

本文只回答一个问题：`agent-loop-planner-matrix` 之后，要不要继续加新的 planner fixture（测试场景）。

结论：**默认先暂停扩展。** 如果用户还想要一个 runnable spike，下一条最值得做的是 **restart after planner pause**。

这一步不实现代码，不扩大 mainline，也不把 planner runner 抽成新 module。

## 2. Candidate Fixtures

### Approval Denial Path

价值：能证明 planner 触发 approval 后，如果审批被拒绝，runner 不会继续执行后续 action。

判断：有用，但不是最优先。approval deny 在现有 approval boundary 中已经有较多覆盖；继续加它更像补 demo completeness，不太可能暴露新的 app friction。

### Worker Handoff Denial Path

价值：能证明 planner 请求 worker handoff 后，如果 policy 拒绝，app-layer audit 仍能看到 denied decision。

判断：有用，但当前 `submit_worker_handoff(...)` denied path 和 Delegation Decision Read Model 已经收口。继续加它更像复核已有 helper，不太像新的压力点。

### Restart After Planner Pause

价值：最接近真实 Agent loop。真实系统常会先计划、暂停等人批、进程重启，然后再恢复执行。这个 fixture 可以检查 app-layer runner 是否只靠 public helpers / event-backed state 继续走，而不是依赖 process-local memory。

判断：**如果继续做 runnable spike，选这个。** 它能同时压力 approval pause / resume、restart context、checkpoint-assisted rebuild 和 planner runner 状态边界，但仍不需要 real LLM、scheduler、real worker process 或 real HTTP server。

### Memory Query Deferred Path

价值：能再次确认 memory query 仍是 deferred capability，不应被偷偷实现成 core feature。

判断：暂不优先。当前 matrix 已有 `real_llm_plan` blocked deferred capability；再加 memory query 主要是边界说明价值，runnable 价值有限。

## 3. Decision

Do not expand the matrix by default.

If the branch-local track continues, add exactly one fixture:

`restart after planner pause`

That fixture should remain demo-local and should only report whether public helpers are enough after restart. It must not introduce:

- real LLM planning
- scheduler
- provider adapter
- real HTTP server
- real worker process
- filesystem mutation
- memory query engine
- public SDK
- product multi-agent UX

## 4. Stop Conditions

Stop instead of implementing if the next slice requires:

- changing core append-only event semantics
- changing executor grants semantics
- extracting `agent_loop` / `orchestration` / `planner_runner` before a second non-demo caller exists
- treating memory query as mandatory loop stage
- product decisions about UX, identity, scheduling, or planner policy

## 5. Next Development Step

Next suggested branch-local batch:

`Planner Restart Pause Fixture Spike`

Goal: add one deterministic fixture showing a planner pauses at approval, the process restarts, and the loop resumes through public helpers / event-backed state.

Default alternative: pause this branch-local agent-loop track and wait for real application-layer friction or external review feedback.
