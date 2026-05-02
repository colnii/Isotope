# Agent Task Queue

状态：`active`

## 1. Purpose

本文是后续主线 AI 的 task queue（任务队列）。目标是把接下来 45-60 分钟的工作拆成有 stop conditions（停止条件）的 bounded batch（有界批次），减少用户每 3-10 分钟手动传下一步指令的需要。

它不是授权 agent 自行开新方向。未列入 Current Batch 的 track、feature、tag、release 或 repo migration 不得自动开始。

## 2. Operating Rules

- 每轮开始先读：
  - `docs/current-status.md`
  - `docs/v0.2-roadmap.md`
  - `docs/agent-task-queue.md`
- 按 Current Batch 顺序执行任务。
- 每个 implementation task 默认遵守 red -> green -> docs/status sync。
- docs-only task 不得改 `src/`、`tests/`、`.github/` 或 `pyproject.toml`。
- red-only task 只写 failing tests，不实现，不提交，除非 queue 明确要求继续 green。
- 每完成一个任务，更新本文件的 task status。
- 每个 batch 完成后，写清 next suggested batch。
- 不要自行进入未列出的新 Track。
- 如果 queue 与用户最新明确指令冲突，以用户最新明确指令为准，并同步 queue。

## 3. Stop Conditions

遇到以下情况必须停止并汇报，不继续：

- full regression 出现非本批失败
- red tests 意外全绿
- 需要新增依赖
- 需要修改 `/home/lumber/Github/x-agent`
- 需要创建或修改 tag
- 需要发布 GitHub Release
- 需要重写已 closed 的 kernel contract
- 需要实现 real HTTP server / real LLM / provider adapter / memory query engine
- 需要修改 event store append-only 语义
- docs/code 状态冲突且无法确定 source of truth
- 用户明确要求暂停

## 4. Verification Baseline

每个 batch 至少跑：

```bash
cd /home/lumber/Github/isotope

PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel -q

PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --json
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario v0.2
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario v0.2 --json

rg -n '(^|\s)(from|import) x_agent\b' src/isotope_kernel tests/isotope_kernel || true

git -C /home/lumber/Github/x-agent status --short \
  src/x_agent src/isotope_kernel tests/isotope_kernel docs/isotope

git diff -- src tests .github pyproject.toml
git status --short
```

当前 baseline：`806 passed`。

## 5. Current Batch

Batch name: `Retry / Cancel / Supersede Boundary Planning`

Timebox: 45-60 min

Status: `ready`

Goal: define the action lifecycle boundary for retry / cancel / supersede without opening implementation.

### Task 1: Retry / Cancel / Supersede Boundary docs-only

Status: `ready`

Scope:

- 新增 `docs/retry-cancel-supersede-boundary-v0.2.md`
- 不写实现
- 不新增测试
- 说明 action lifecycle 里 retry / cancel / supersede 的最小 kernel 边界

Expected contents:

- why this boundary is next after Workspace Substrate first slice
- current implemented lifecycle facts
- retry / cancel / supersede definitions
- canonical event candidates
- projector / checkpoint expectations
- approval / worker / workspace interaction risks
- explicit non-goals
- first red tests recommendation

Completion requirement:

- docs/status synced
- no `src/` / `tests/` / `.github/` / `pyproject.toml` changes
- verification baseline passes
- queue updated before commit

### Task 2: Retry / Cancel / Supersede red tests only

Status: `blocked until Task 1 complete`

Scope:

- 新增 suggested tests:
  - `tests/isotope_kernel/test_action_retry_boundary.py`
  - `tests/isotope_kernel/test_action_cancel_boundary.py`
  - `tests/isotope_kernel/test_action_supersede_boundary.py`
- only red phase
- no implementation
- no docs expansion beyond status / queue update

Expected red focus:

- retry must not mutate prior action state directly
- retry must preserve lineage to original proposal / execution
- cancel must append canonical event and stop later execution where allowed
- supersede must link old and replacement proposal
- cancelled / superseded actions must remain replayable
- checkpoint-assisted rebuild must preserve lifecycle read model
- retry / cancel / supersede cannot bypass policy grants

Stop rule:

- If these tests are unexpectedly green, stop and report.
- Do not start green phase in this batch.

### Task 3: Stop For User Review

Status: `blocked until Task 2 complete`

Scope:

- Do not enter green phase.
- Report red results and expected failure points.
- Recommend the next batch.
- Update this queue with Current Batch status.

## 6. Next Suggested Batch

If the user confirms after reviewing red results, the next batch should be:

Batch name: `Retry / Cancel / Supersede Green Slice`

Likely scope:

- implement minimal lifecycle projection
- keep event store append-only
- keep executor grants semantics unchanged
- update checkpoint expected fields only if new read-model fields enter `RunState`
- docs/status sync after green

Do not start this next batch without explicit user confirmation or an updated queue that marks it as Current Batch.

## 7. Maintenance

When a task completes:

- change its status from `ready` / `in_progress` to `complete`
- add a short evidence note with tests / demo / commit hash if committed
- update Current Batch status when all tasks are complete
- write the next suggested batch without starting it

When a stop condition triggers:

- leave the incomplete task status as `blocked`
- record the stop reason
- do not continue with later tasks
