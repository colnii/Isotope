# Planner Runner API Boundary Review

状态：`review complete / docs-only / branch-local`

## 1. Purpose

本文评审 `agent-loop-planner-matrix` 中的 branch-local planner runner 是否应该从 `src/isotope_kernel/demo.py` 抽成可复用 app-layer runner module。

结论：**暂不抽取。保持 demo-local。**

原因不是当前代码不能抽，而是还没有第二个真实调用者。现在抽成模块会把一个 branch-local pressure-test helper 误读成 Isotope kernel API 或 product-facing runner surface。

## 2. Current Shape

当前 runner 只存在于 demo scenario：

- `agent-loop-friction`
- `agent-loop-planner-friction`
- `agent-loop-planner-matrix`

它执行的是 deterministic / fixture-backed planner decisions：

- `create_source_artifact`
- `submit_worker_handoff`
- `submit_approval_gated_action`
- `bind_workspace`
- `resolve_approval`
- `verify_replay_checkpoint`

Matrix 还覆盖：

- `happy_path`
- `blocked_deferred_capability`
- `malformed_symbolic_action`

当前结果仍是：

- `kernel_friction=[]`
- `private_append_required=false`
- `real_llm_plan` 被归类为 app / product deferred friction
- unknown symbolic action fail closed

## 3. Decision

Keep the runner demo-local for now.

Do not create a new public or semi-public module such as:

- `src/isotope_kernel/planner_runner.py`
- `src/isotope_kernel/agent_loop.py`
- `src/isotope_kernel/orchestration.py`
- `src/isotope_kernel/planning.py`

Do not add a public SDK, product runner abstraction, real LLM adapter, scheduler, provider adapter, or real worker runtime.

## 4. Why Not Extract Yet

### No Second Caller

The only caller is the demo entrypoint. A reusable module would be speculative until another app-layer spike needs the same runner outside `demo.py`.

### Kernel Boundary Risk

Names like `agent_loop`, `orchestration`, or `planner_runner` would look like committed kernel surfaces. The current work is still an application-layer pressure test, not a kernel contract.

### Product Semantics Are Unsettled

The matrix does not decide product questions:

- how a real planner chooses actions
- whether planning is LLM-backed
- how scheduling / retries / cancellation interact with planning
- how product UX presents blocked deferred capabilities
- how memory query should be exposed to planner context

Those decisions should remain outside kernel mainline until a concrete app spike produces friction.

## 5. Reopen Criteria

Reconsider extraction only if a future branch-local app spike has at least one of these concrete needs:

1. A second non-demo caller must run the same fixture matrix.
2. Test duplication appears across multiple planner / agent-loop spikes.
3. A future app shell needs a stable internal runner boundary to report `kernel_friction`.
4. The demo file becomes hard to maintain because runner logic, fixture definitions, and formatting are blocking clear review.

Even then, extraction should be app-layer / branch-local first. It should not become kernel mainline API unless the extracted runner exposes a concrete kernel gap with failing tests and exact scope.

## 6. Next Development Step

Next suggested branch-local step:

`Planner Matrix Fixture Expansion Review`

Goal: add docs-only selection for whether the next fixture should pressure one narrow surface:

- approval denial path
- worker handoff denial path
- restart after planner pause
- memory query deferred path

Default recommendation: choose **restart after planner pause** only if the user wants another runnable spike; otherwise pause branch-local agent-loop expansion and wait for real application-layer friction.

Stop if the next step requires real LLM, scheduler, provider adapter, real HTTP server, real worker process, filesystem mutation, public SDK, or product UX decisions.
