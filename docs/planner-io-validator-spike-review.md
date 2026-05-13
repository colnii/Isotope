# Planner I/O Validator Spike Review

状态：`complete / branch-local runnable spike`

## 1. Plain Summary

这一步做了一个“门卫”。

它不接真实 AI，也不执行 AI 的决定。它只检查 fake planner output：

- 格式对不对。
- 动作是不是认识。
- 有没有请求未开放能力。
- 有没有想绕过授权读 artifact 全文。

结论：**门卫能拦住明显不该执行的 planner output，并且不会留下半截事件或 artifact。**

## 2. What Changed

新增 demo scenario：

```bash
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-io-validator
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-io-validator --trace
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-io-validator --json
```

新增测试：

- `tests/isotope_kernel/test_agent_loop_planner_io_validator_spike.py`

## 3. What It Checks

Accepted:

- one valid symbolic planner output

Rejected:

- malformed output
- unknown action
- overpowered capability request
- artifact full-text read without grant

Fail-closed result:

- no partial canonical events
- no artifact created
- no worker created
- no approval resolved

## 4. Boundary

This is still demo-local validation. It does not add:

- real LLM provider call
- prompt template
- model selection
- scheduler
- real HTTP server
- real worker process
- memory query engine
- public SDK
- product UX

## 5. Next Development Step

Next suggested branch-local batch:

`Planner Validated Runner Spike`

Plain meaning: connect this “门卫” to the existing tiny demo runner, so valid fake planner output can run, while bad output is blocked before anything happens.

Still do not connect a real model provider yet.
