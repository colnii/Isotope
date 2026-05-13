# Agent Loop Planner Matrix Friction Review

状态：`spike complete / branch-local`

## 1. Purpose

本文记录 `agent-loop-planner-matrix` fixture matrix spike。它在上一轮 deterministic planner adapter 基础上加入三个 planner fixture，用来区分：

- happy path：当前 public helpers 能执行的 planner decisions。
- blocked deferred path：planner 请求 deferred capability，但这不是 kernel implementation request。
- malformed path：planner 输出未知 symbolic action，runner fail closed 且不追加 partial events。

这个 spike 仍不是 real Agent loop。它不调用真实 LLM，不实现 scheduler，不启动 provider adapter，也不进入 product multi-agent UX。

## 2. Scenario

命令：

```bash
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-matrix
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-matrix --trace
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-matrix --json
```

在 worktree 没有本地 `.venv` 时，可使用主 checkout 的 venv：

```bash
PYTHONPATH=/home/lumber/Github/isotope/.worktrees/app-agent-loop-friction/src \
  /home/lumber/Github/isotope/.venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-matrix --trace
```

## 3. Fixture Matrix

### Happy Path

Fixture id: `happy_path`

Runs the existing deterministic planner adapter path:

1. `create_source_artifact`
2. `submit_worker_handoff`
3. `submit_approval_gated_action`
4. `bind_workspace`
5. `resolve_approval`
6. `verify_replay_checkpoint`

Current result:

- `status=ok`
- `private_append_required=false`
- `kernel_friction=[]`
- replay / checkpoint pass

### Blocked Deferred Capability

Fixture id: `blocked_deferred_capability`

Planner requests `real_llm_plan`. The matrix classifies this as `app_or_product_deferred`, not as a kernel gap.

Current result:

- `status=blocked_deferred`
- `blocked_capability=real_llm_plan`
- `app_deferred_friction` is non-empty
- `kernel_friction=[]`
- no real model prompt / response

### Malformed Symbolic Action

Fixture id: `malformed_symbolic_action`

Planner emits `unknown_symbolic_action`. The runner validates symbolic actions before execution and fails closed.

Current result:

- `status=failed_closed`
- `partial_events_appended=false`
- `kernel_friction=[]`

## 4. Result

Current matrix result:

- `planner_matrix_ok=true`
- `fixture_count=3`
- `kernel_friction_count=0`
- `model_status=not_used`
- `scheduler_status=not_used`
- `provider_status=not_used`
- `network_listener_status=not_used`
- `memory_status=boundary_only`

Interpretation: the current fixture matrix still does not expose a mainline kernel helper gap. The next pressure point is not kernel code; it is whether this branch-local demo logic should become a reusable app-layer runner boundary.

## 5. Next Development Step

Next suggested branch-local step:

`Planner Runner API Boundary Review`

Goal: decide whether the branch-local planner matrix should stay inside `demo.py`, or whether it needs a small reusable app-layer runner module for future spikes. This should begin as docs / review only. Do not extract code unless a later spike actually needs to reuse the runner outside the demo entrypoint.

Stop if this requires real LLM, scheduler, provider adapter, real HTTP server, real worker process, filesystem mutation, public SDK, or product UX decisions.

Only reopen kernel mainline if a future reusable runner review produces non-empty concrete `kernel_friction` with exact files, failing tests, and a narrow helper / boundary / replay / checkpoint / API ergonomics gap.
