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
- 每个 implementation task 默认遵守 red -> green -> docs/status sync。
- docs-only task 不得改 `src/`、`tests/`、`.github/` 或 `pyproject.toml`。
- red-only task 只写 failing tests，不实现，不提交，除非 queue 明确要求继续 green。
- 每完成一个小任务，可以在本文件记录 status / evidence，但继续执行同一 batch 的后续任务。
- 不要自行进入未列出的新 Track。
- 如果 queue 与用户最新明确指令冲突，以用户最新明确指令为准，并同步 queue。

## 3. Execution Mode

Rolling batch mode.

Default session timebox: `45-60 min`.

Rules:

- Execute Current Batch first.
- If Current Batch is clean and time remains, continue with Next Suggested Batch.
- Promote Next Suggested Batch to Current Batch only after updating this queue.
- Each batch must finish with verification and commit / push before starting the next.
- Do not stop after every batch unless a stop condition fires.
- Stop when the timebox is near, a stop condition fires, there is no clear next batch, or the next batch requires user decision.
- Do not invent unlisted work just to fill time.
- If selecting a spike requires product / user judgment, stop instead of choosing arbitrarily.

## 4. Stop Conditions

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
- selecting a spike requires product / user judgment
- 用户明确要求暂停

## 5. Verification Baseline

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

当前 baseline：`831 passed`。

## 6. Current Batch

Batch name: `Kernel Usability Pressure Test Planning`

Timebox: part of rolling 45-60 min session

Status: `blocked_for_user_decision`

Goal: define the first usability pressure test boundary and decide whether the current kernel slices are enough to begin a tiny app spike.

### Task 1: Docs-only usability pressure test boundary

Status: `complete`

Scope:

- add `docs/usability-pressure-test-plan-v0.2.md`
- judge what the first tiny app spike should be
- no implementation
- no new tests

Evidence:

- Added `docs/usability-pressure-test-plan-v0.2.md`.
- Current technical recommendation is `approval-gated tool runner`.

### Task 2: Decide first tiny app spike candidate

Status: `blocked_for_user_decision`

Compare:

- file summarizer
- artifact review flow
- approval-gated tool runner
- research assistant mini flow

Scope:

- select one spike that best fits the current kernel
- explain why it fits better than the alternatives
- if product / user judgment is required, stop instead of choosing arbitrarily

Decision:

- `approval-gated tool runner` is the technical recommendation because it exercises HTTP facade, action chain, policy grants, approval pause / resume, workspace binding, artifact handoff, replay, and checkpoint without real network / real LLM.
- This still requires product / user judgment because it frames the first spike as a tool-runner path rather than artifact review, file summarization, or research-assistant behavior.
- Stop condition fired: selecting a spike requires product / user judgment.

### Task 3: Update queue

Status: `complete`

Scope:

- if safe to continue, set Next Suggested Batch to selected spike red tests only
- if user judgment is required, stop
- do not start implementation unless the queue explicitly marks it safe

Evidence:

- Next Suggested Batch remains blocked pending explicit user selection.
- Do not start red tests until the user confirms the spike candidate.

## 7. Next Suggested Batch

Batch name: `Selected Usability Spike Red Tests`

Status: `blocked_pending_user_selection`

Possible shape:

- add spike-specific tests
- red phase only
- no implementation unless Current Batch explicitly marks it safe

Recommended candidate if user confirms: `approval-gated tool runner`.

Do not start this next batch until the user explicitly selects a spike candidate.

## 8. Completed Batch Log

### Kernel Usability Pressure Test Planning

Status: `blocked_for_user_decision`

Evidence:

- Added `docs/usability-pressure-test-plan-v0.2.md`.
- Compared file summarizer, artifact review flow, approval-gated tool runner, and research assistant mini flow.
- Technical recommendation: `approval-gated tool runner`.
- Stop reason: selecting the spike requires product / user judgment, so no red tests were started.

### Retry / Cancel / Supersede Stabilization

Status: `complete`

Evidence:

- Targeted RCS tests: `25 passed`.
- Full regression: `831 passed`.
- Added basis linkage / replacement identity / cancel request ordering / projector reuse hardening.
- Verified retry / cancel / supersede checkpoint-assisted rebuild.
- No scheduler / process kill / tool-level cancellation / real concurrency / new dependency.

## 9. Maintenance

When a task completes:

- change its status from `ready` / `in_progress` to `complete`
- add a short evidence note with tests / demo / commit hash if committed
- update Current Batch status when all tasks are complete
- write or promote the next suggested batch before starting it

When a stop condition triggers:

- leave the incomplete task status as `blocked`
- record the stop reason
- do not continue with later tasks

When rolling forward:

- first update this queue so the promoted batch is visible as Current Batch
- commit / push the completed batch before beginning the promoted batch
- do not invent unlisted work just to fill time
