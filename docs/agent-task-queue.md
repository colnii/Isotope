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
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario approval-tool-runner
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario approval-tool-runner --json

rg -n '(^|\s)(from|import) x_agent\b' src/isotope_kernel tests/isotope_kernel || true

git -C /home/lumber/Github/x-agent status --short \
  src/x_agent src/isotope_kernel tests/isotope_kernel docs/isotope

git diff -- src tests .github pyproject.toml
git status --short
```

当前 baseline：`842 passed`。

## 6. Current Batch

Batch name: `Approval-Gated Tool Runner Spike`

Timebox: `45-60 min`

Status: `complete`

Goal: implement the confirmed `approval-gated tool runner` usability pressure test spike as a deterministic in-process scenario.

Constraints:

- deterministic
- in-process
- no real LLM
- no real HTTP server
- no external provider
- no real filesystem mutation
- use existing artifact / `write_artifact_tool` path
- exercise approval pause / resume
- exercise workspace binding read model
- produce artifact / `ResourceRef` handoff
- verify replay and checkpoint
- expose whether the kernel API feels awkward

### Task 1: Red tests for spike CLI / in-process scenario

Status: `complete`

Scope:

- add spike-specific tests
- verify red against missing scenario
- do not stop after red unless a stop condition fires

Evidence:

- Added `tests/isotope_kernel/test_usability_spike_approval_tool_runner.py`.
- Added `tests/isotope_kernel/test_usability_spike_approval_tool_runner_read_model.py`.
- Red result: `10 failed, 1 passed`, failing because `approval-tool-runner` scenario was unsupported.

### Task 2: Green implementation for minimal spike

Status: `complete`

Scope:

- implement the smallest deterministic scenario
- prefer `src/isotope_kernel/demo.py`
- keep kernel core changes minimal
- do not introduce real network / LLM / provider / filesystem mutation

Evidence:

- Implemented `python -m isotope_kernel.demo --scenario approval-tool-runner`.
- Implemented `python -m isotope_kernel.demo --scenario approval-tool-runner --json`.
- Targeted tests: `11 passed`.
- Full regression: `842 passed`.
- Implementation changed `src/isotope_kernel/demo.py` only; no real HTTP server / LLM / provider / filesystem mutation.

### Task 3: Docs/status sync

Status: `complete`

Scope:

- update `docs/usability-pressure-test-plan-v0.2.md`
- update `docs/current-status.md`
- update `docs/v0.2-roadmap.md`
- update `docs/agent-task-queue.md`
- README / AGENTS only if needed

Evidence:

- Updated status docs for `842 passed` and first-slice completion.

### Task 4: Spike closure review

Status: `complete`

Scope:

- confirm the spike is first slice complete or record remaining gaps
- docs-only unless a bug is found

Closure:

- `approval-gated tool runner` first slice is complete.
- It exercises approval pause / resume, workspace binding read model, artifact / `ResourceRef` handoff, replay, checkpoint, and in-process HTTP facade.
- Exposed API friction: approval-gated input uses `server.submit_tool_request(...)`, workspace binding requires explicit `workspace.bound`, and `approval_id` lookup scans events.

### Task 5: Update queue with next suggested batch

Status: `complete`

Scope:

- write the next suggested batch
- do not start it in this session

Evidence:

- Next Suggested Batch set to API friction review.

### Task 6: Stop for user review

Status: `complete`

Scope:

- report verification, commit, push, and current status
- do not continue to the next batch

## 7. Next Suggested Batch

Batch name: `Approval Tool Runner API Friction Review`

Status: `ready_after_user_review`

Possible shape:

- docs-only review of API awkwardness exposed by the spike
- decide whether approval-gated input needs a first-class facade
- decide whether workspace binding needs a server-level helper instead of direct event append
- decide whether approval lookup needs a read helper
- no implementation until user confirms

## 8. Completed Batch Log

### Approval-Gated Tool Runner Spike

Status: `complete`

Evidence:

- Red result: `10 failed, 1 passed`.
- Targeted green result: `11 passed`.
- Full regression: `842 passed`.
- New scenario: `python -m isotope_kernel.demo --scenario approval-tool-runner`.
- New JSON scenario: `python -m isotope_kernel.demo --scenario approval-tool-runner --json`.
- No real HTTP server / LLM / provider / filesystem mutation / container / process spawn / dependency.
- Stop reason: batch completed; wait for user review before starting API friction follow-up.

### Kernel Usability Pressure Test Planning

Status: `complete`

Evidence:

- Added `docs/usability-pressure-test-plan-v0.2.md`.
- Compared file summarizer, artifact review flow, approval-gated tool runner, and research assistant mini flow.
- Technical recommendation: `approval-gated tool runner`.
- Stop reason: selecting the spike requires product / user judgment, so no red tests were started.
- User later confirmed `approval-gated tool runner` as the selected spike.

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
