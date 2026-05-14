# Agent Loop Planner Adapter Friction Review

状态：`spike complete / branch-local`

## 1. Purpose

本文记录 `agent-loop-planner-friction` deterministic planner-adapter spike。它是 `agent-loop-friction` 的下一步：在同一套 public kernel helpers 前面放一个 tiny planner adapter，让 planner 产出 symbolic decisions（符号化决策），再由 app-layer runner 执行这些决策。

这个 spike 仍不是 real Agent loop。它不调用真实 LLM，不实现 scheduler，不启动 provider adapter，也不进入 product multi-agent UX。它只验证：如果未来应用层 planner 决定下一步动作，当前 kernel public surface 是否会马上卡住。

## 2. Scenario

命令：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario agent-loop-planner-friction
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario agent-loop-planner-friction --trace
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario agent-loop-planner-friction --json
```

在 worktree 没有本地 `.venv` 时，可使用主 checkout 的 venv：

```bash
PYTHONPATH=/home/lumber/Github/isotope/.worktrees/app-agent-loop-friction/src \
  /home/lumber/Github/isotope/.venv/bin/python -m isotope.demo --scenario agent-loop-planner-friction --trace
```

Planner adapter 当前是 deterministic fixture：

1. observe run status and available public helpers。
2. select `create_source_artifact`。
3. select `submit_worker_handoff`。
4. select `submit_approval_gated_action`。
5. select `bind_workspace`。
6. select `resolve_approval`。
7. select `verify_replay_checkpoint`。

Runner 只执行这些 symbolic decisions，不让 planner 直接写 canonical events。

## 3. Result

当前结果：

- `planner_adapter_friction_ok=true`
- `planner_adapter_status=deterministic_fixture`
- `planner_decision_count=6`
- `agent_loop_friction_ok=true`
- `private_append_required=false`
- `kernel_friction=[]`
- replay / checkpoint pass
- no model prompt / model response in JSON
- no artifact full content in plain / trace / JSON output
- `model_status=not_used`
- `scheduler_status=not_used`
- `provider_status=not_used`
- `network_listener_status=not_used`
- `memory_status=boundary_only`

Interpretation: a tiny app-layer planner adapter can drive the current deterministic loop through public helpers without exposing a new kernel helper gap.

## 4. Boundaries

This spike deliberately does not implement:

- real LLM planning loop
- autonomous scheduler
- provider adapter
- real HTTP server / network listener
- real worker runtime / process spawn / concurrency
- public SDK
- product multi-agent UX
- memory query / memory storage
- filesystem workspace mutation
- direct planner writes to canonical events

It also does not change event-store append-only semantics or executor grants semantics.

## 5. Next Development Step

Next suggested branch-local step:

`Planner Fixture Matrix Friction Spike`

Goal: keep the same deterministic planner adapter, but add a tiny fixture matrix with at least:

1. happy path: current planner decisions produce `kernel_friction=[]`。
2. blocked path: planner requests a deferred capability such as `real_llm_plan` or `memory_query` and the app-layer runner reports it as app/product-deferred friction, not a kernel implementation request。
3. malformed path: planner emits an unknown symbolic action and the runner fails closed without appending partial events。

Stop if this requires real LLM, scheduler, provider adapter, real HTTP server, real worker process, filesystem mutation, public SDK, or product UX decisions.

Only reopen kernel mainline if the matrix produces non-empty concrete `kernel_friction` with exact files, failing tests, and a narrow helper / boundary / replay / checkpoint / API ergonomics gap.
