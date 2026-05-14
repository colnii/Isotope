# Agent Loop Branch Handoff Checkpoint

状态：`current / branch-local handoff`

## 1. Plain Summary

这条分支现在适合交给人 review，或者保留下来等真实 app 使用。

它已经证明三件事：

- 小型 Agent loop 可以只用公开 helper 跑完，不需要 private append。
- fake planner 可以只输出 symbolic decisions，由 runner 执行。
- planner output 可以先过 validator，再执行；坏输出不会留下半截 event 或 artifact。

它还没有证明完整产品级 Agent loop 已完成。

## 2. Runnable Entry Points

```bash
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario agent-loop-friction --trace
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario agent-loop-planner-friction --trace
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario agent-loop-planner-matrix --trace
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario agent-loop-planner-restart-pause --trace
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario agent-loop-planner-io-validator --trace
PYTHONPATH=src .venv/bin/python -m isotope.demo --scenario agent-loop-planner-validated-runner --trace
```

## 3. What Reviewers Should Check

Review should focus on whether the boundary feels right:

- Is validator-before-runner clear enough?
- Are symbolic planner decisions narrow enough?
- Are bad outputs rejected early enough?
- Does the demo accidentally imply real LLM / product Agent loop is done?
- Is there any concrete app-layer friction that should become a core helper?

## 4. What Should Not Happen Next

Do not continue by inventing another fake Agent loop scenario.

Do not add:

- real LLM provider
- scheduler
- real HTTP server
- real worker process
- memory query engine
- filesystem mutation
- public SDK
- product UX

Those need real app pressure or reviewer feedback first.

## 5. Recommended Next Move

Recommended next move:

- keep this branch as the Agent loop proof branch, or
- open a PR for review, or
- merge if the goal is to keep these branch-local demos in mainline.

Plain meaning: the technical spike has reached a natural stop. The next useful input should come from a real user-facing app attempt or reviewer comments.
