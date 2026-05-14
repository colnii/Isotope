# Planner Validated Runner Spike Review

状态：`complete / branch-local runnable spike`

## 1. Plain Summary

这一步把“门卫”和“小 runner”接起来了。

白话说：

- fake planner output 先过 validator。
- 通过后，小 runner 才按 symbolic decisions 跑一小步。
- 不通过时，runner 不执行，event 和 artifact 都不多写。

结论：**现在已经证明：先检查 AI planner 输出，再执行，是可跑通的。**

## 2. What Changed

新增 demo scenario：

```bash
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario agent-loop-planner-validated-runner
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario agent-loop-planner-validated-runner --trace
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario agent-loop-planner-validated-runner --json
```

新增测试：

- `tests/isotope/test_agent_loop_planner_validated_runner_spike.py`

## 3. What It Proves

Valid path:

- validator accepts valid symbolic planner output
- runner creates source artifact
- runner submits worker handoff
- runner pauses on approval
- runner binds workspace
- runner resolves approval
- replay / checkpoint still match

Invalid path:

- validator rejects overpowered planner output
- runner does not execute it
- no partial event is appended
- no artifact is created

## 4. Boundary

This still does not add:

- real LLM provider call
- prompt template
- model selection
- scheduler
- real HTTP server
- real worker process
- memory query engine
- filesystem mutation
- public SDK
- product UX

## 5. Next Development Step

Next suggested mode:

Pause artificial branch-local Agent loop expansion.

Plain meaning: this branch has now proved the fake planner path, the validator path, and the validator-before-runner path. The next useful signal should come from real app-layer friction or external review, not another made-up demo case.
