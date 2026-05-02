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
- 默认 batch timebox 是 45-60 min。
- 每个 batch 应包含 3-5 个连续小任务，形成一个 work package。
- 按 Current Batch 顺序执行任务，不要因为单个小任务完成就停下来等待用户。
- 每个 implementation task 默认遵守 red -> green -> docs/status sync。
- docs-only task 不得改 `src/`、`tests/`、`.github/` 或 `pyproject.toml`。
- red-only task 只写 failing tests，不实现，不提交，除非 queue 明确要求继续 green。
- 每完成一个小任务，可以在本文件记录 status / evidence，但继续执行同一 batch 的后续任务。
- 只有遇到 stop condition，或整个 batch 完成，才停下来汇报。
- 每个 batch 完成后，必须跑完整验证、docs/status sync、commit + push、更新 next suggested batch，然后停给用户 review。
- 不要自行进入未列出的新 Track。
- 如果 queue 与用户最新明确指令冲突，以用户最新明确指令为准，并同步 queue。

## 3. Stop Conditions

遇到以下情况必须停止并汇报，不继续：

- full regression 出现非本批失败
- red tests 意外全绿且无法说明是已有覆盖
- 需要新增依赖
- 需要修改 `/home/lumber/Github/x-agent`
- 需要创建或修改 tag
- 需要发布 GitHub Release
- 需要重写已 closed 的 kernel contract
- 需要实现 real HTTP server / real LLM / provider adapter / memory query engine
- 需要修改 event store append-only 语义
- 需要进入 real concurrency / process spawn / container / git worktree
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

当前 baseline：`820 passed`。

## 5. Current Batch

Batch name: `Retry / Cancel / Supersede Stabilization`

Timebox: 45-60 min

Status: `ready`

Goal: stabilize the first Retry / Cancel / Supersede slice as one 45-60 minute work package, then stop for user review.

### Task 1: Retry / Cancel / Supersede closure review

Status: `ready`

Scope:

- review recent implementation
- confirm current boundary can be marked first slice complete
- docs-only unless bug found

### Task 2: Retry / Cancel / Supersede malformed event hardening

Status: `ready`

Scope:

- red -> green
- add tests for malformed retry / cancel / supersede payloads
- ensure controlled `ValueError`
- ensure no partial read model mutation

### Task 3: Retry / Cancel / Supersede checkpoint/replay hardening

Status: `ready`

Scope:

- red -> green if needed
- ensure retry / cancel / supersede read-model fields replay and checkpoint-assisted rebuild consistently
- if already covered, document evidence and skip implementation

### Task 4: Docs/status sync

Status: `ready`

Scope:

- update `docs/retry-cancel-supersede-boundary-v0.2.md`
- update `docs/current-status.md`
- update `docs/v0.2-roadmap.md`
- update `docs/agent-task-queue.md`
- update README / AGENTS only if needed

### Task 5: Stop for user review

Status: `ready`

Scope:

- do not start next batch
- report results and next suggested batch

## 6. Next Suggested Batch

Batch name: `Kernel Usability Pressure Test Planning`

Possible tasks:

- docs-only pressure test boundary
- define first tiny app spike candidate
- decide whether Agent / Workspace / RCS are sufficient to begin

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
