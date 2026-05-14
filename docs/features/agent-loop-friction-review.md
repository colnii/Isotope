# Agent Loop Friction Review

状态：`spike complete / branch-local`

## 1. Purpose

本文记录 `agent-loop-friction` deterministic app-layer spike。它回答一个窄问题：在不实现 real LLM planning loop、scheduler、provider adapter、real HTTP server 或 product multi-agent UX 的前提下，现有 public kernel helpers 能否支撑一轮最小代理循环式编排。

这个 spike 不是 Isotope kernel 的完整 Agent loop。它只是应用层压力测试，用来判断下一步是否有 concrete `kernel_friction` 值得带回 mainline。

## 2. Scenario

命令：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario agent-loop-friction
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario agent-loop-friction --trace
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario agent-loop-friction --json
```

在 worktree 没有本地 `.venv` 时，可使用主 checkout 的 venv：

```bash
PYTHONPATH=/home/lumber/Github/isotope/.worktrees/app-agent-loop-friction/src \
  /home/lumber/Github/isotope/.venv/bin/python -m isotope.demo --scenario agent-loop-friction --trace
```

该 scenario 串起以下 deterministic loop steps：

1. create session / run。
2. observe run context。
3. plan deterministic next action。
4. create source artifact through `InProcessServer.create_source_artifact(...)`。
5. hand off worker result through `InProcessServer.submit_worker_handoff(...)`。
6. pause on approval-gated `InProcessServer.submit_action(...)`。
7. bind workspace through `InProcessServer.bind_workspace(...)`。
8. resolve approval and resume execution。
9. verify replay / checkpoint。
10. emit `kernel_friction` report and next development step。

## 3. Result

当前结果：

- `agent_loop_friction_ok=true`
- `private_append_required=false`
- `kernel_friction=[]`
- replay / checkpoint pass
- no artifact full content in plain / trace / JSON output
- `model_status=not_used`
- `scheduler_status=not_used`
- `provider_status=not_used`
- `network_listener_status=not_used`
- `memory_status=boundary_only`

Interpretation: current public helpers are enough for this deterministic in-process composition. This branch did not expose a new kernel helper gap.

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

It also does not change event-store append-only semantics or executor grants semantics.

## 5. Next Development Step

Next suggested branch-local step:

`Real App-Layer Planner Adapter Friction Spike`

Goal: put a tiny planner adapter in front of the same `agent-loop-friction` flow, still deterministic or fixture-backed, and require it to output a structured `kernel_friction` report. The adapter may decide the next symbolic step, but it must not call a real LLM yet.

Stop if the next step requires real LLM, scheduler, provider adapter, real HTTP server, real worker process, filesystem mutation, public SDK, or product UX decisions.

Only reopen kernel mainline if the next spike produces non-empty `kernel_friction` with exact files, failing tests, and a narrow helper / boundary / replay / checkpoint / API ergonomics gap.
