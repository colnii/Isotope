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
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario v0.2 --trace
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario v0.2 --json
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario approval-tool-runner
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario approval-tool-runner --trace
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario approval-tool-runner --json
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario artifact-review
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario artifact-review --trace
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario artifact-review --json

rg -n '(^|\s)(from|import) x_agent\b' src/isotope_kernel tests/isotope_kernel || true

git -C /home/lumber/Github/x-agent status --short \
  src/x_agent src/isotope_kernel tests/isotope_kernel docs/isotope

git diff -- src tests .github pyproject.toml
git status --short
```

当前 baseline：`892 passed`。

## 6. Current Batch

Batch name: `Source Artifact Setup Helper`

Timebox: `45-60 min`

Status: `complete`

Goal: remove private source artifact setup glue from the `artifact-review` spike without creating a product artifact upload API.

Tasks:

1. Source Artifact Setup Helper Boundary Docs: complete; added `docs/source-artifact-setup-helper-boundary-v0.2.md`.
2. Red Tests: complete; added `tests/isotope_kernel/test_source_artifact_setup_helper.py`.
3. Green Implementation: complete; added `InProcessServer.create_source_artifact(...)` and updated `artifact-review` demo.
4. Docs / status sync: complete.
5. Queue update: complete; next suggested batch set to `Source Artifact Helper Closure Review`.

Evidence:

- Red targeted result: `9 failed, 11 passed`; failures were expected because `create_source_artifact(...)` did not exist and `artifact-review` still used private `_append(...)` setup glue.
- Targeted green result: `20 passed`.
- Full regression: `892 passed`.
- v0.1 demo plain / JSON: pass.
- v0.2 demo plain / JSON: pass.
- approval-tool-runner demo plain / JSON: pass.
- artifact-review demo plain / JSON / trace: pass.
- Helper behavior: validates request, uses existing compiler / policy / executor path, appends canonical action + artifact events, returns summary / structured `ResourceRef` / provenance, and does not append `run.completed`.
- `artifact-review` demo no longer uses private `server._append(...)` source setup glue.
- HTTP full-content route remains `not_enabled`.
- No real filesystem upload / binary streaming / real HTTP server / real LLM / provider adapter / memory query engine / container / git worktree / process spawn / dependency.

### Previous Batch Snapshot: Artifact Review Flow Friction Review

Batch name: `Artifact Review Flow Friction Review`

Status: `complete`

Evidence:

- Full regression: `876 passed`.
- Review conclusion: `artifact-review` is useful and exposed no kernel correctness bug.
- Main friction: source artifact setup used demo glue and private `server._append(...)` to hand-write canonical source action / artifact lifecycle events.
- Classification: source setup is a facade / helper gap; controlled retrieval verbosity is acceptable v0 shape; review artifact handoff through `submit_action(...)` is acceptable.
- Recommendation: A. source artifact setup helper.
- No code changed; no real HTTP server / real LLM / provider adapter / memory query engine / filesystem mutation / container / git worktree / process spawn / dependency.

### User-Directed Follow-up: Demo Trace Mode

Status: `complete`

Evidence:

- Added `--trace` for `v0.2`, `approval-tool-runner`, and `artifact-review`.
- Red targeted result: `6 failed, 1 passed`; failures were expected because `--trace` was unsupported.
- Targeted green result: `7 passed`.
- Full regression: `883 passed`.
- `--trace` is human-readable only and keeps `--json` compatible.
- Trace output does not expose artifact full content.
- No real HTTP server / real LLM / provider adapter / filesystem mutation / dependency.

### Previous Batch Snapshot: Artifact Review Flow Spike

Batch name: `Artifact Review Flow Spike`

Status: `complete`

Evidence:

- Red result: `10 failed, 1 passed`; failures were expected because `artifact-review` scenario was unsupported.
- Targeted green: `11 passed`.
- Full regression: `876 passed`.
- v0.1 demo plain / JSON: pass.
- v0.2 demo plain / JSON: pass.
- approval-tool-runner demo plain / JSON: pass.
- artifact-review demo plain / JSON: pass.
- Flow uses artifact summary / structured `ResourceRef`, controlled retrieval policy, reviewer action chain, review artifact handoff, replay, and checkpoint.
- HTTP full-content route remains `not_enabled`.
- No real HTTP server / real LLM / provider adapter / filesystem mutation / container / git worktree / process spawn / dependency.

### Previous Batch Snapshot: Usability Friction Round 1 Closure + First App Spike Decision

Batch name: `Usability Friction Round 1 Closure + First App Spike Decision`

Status: `complete`

Evidence:

- Full regression: `865 passed`.
- Selected `artifact review flow` for the next app spike.
- Added `docs/usability-friction-round-1-review.md`.
- Added `docs/first-app-spike-readiness.md`.

### Previous Batch Snapshot: Usability Friction Reduction Package 2

Batch name: `Usability Friction Reduction Package 2`

Status: `complete`

Evidence:

- Added `docs/submit-tool-request-friction-review.md`.
- Added `docs/submit-action-helper-boundary-v0.2.md`.
- Added `tests/isotope_kernel/test_submit_action_helper.py`.
- Added `InProcessServer.submit_action(run_id, intent, requires_approval=False)`.
- Existing `submit_tool_request(...)` remains public / compatible.
- Updated `approval-tool-runner` demo to stop directly calling raw `submit_tool_request(...)`.
- Full regression after package: `865 passed`.

### Previous Batch Snapshot: Usability Friction Reduction Package 1

Batch name: `Usability Friction Reduction Package 1`

Status: `complete`

Evidence:

- Approval lookup helper closure review found no bug.
- Workspace binding helper friction review and boundary docs landed.
- Added `InProcessServer.bind_workspace(...)`.
- Updated `approval-tool-runner` demo to stop hand-writing `workspace.bound` payload.
- Full regression after package: `859 passed`.

### Previous Batch Snapshot: Approval Tool Runner API Friction Review

Batch name: `Approval Tool Runner API Friction Review`

Status: `complete`

Evidence:

- Added `docs/approval-tool-runner-friction-review.md`.
- Classified `server.submit_tool_request(...)` as a facade/helper gap.
- Classified event-scan approval id lookup as a read-model helper gap.
- Classified explicit `workspace.bound` append as a broader workspace/server integration gap.
- Recommended `Approval Lookup Helper Boundary` as the next smallest safe slice.

### Previous Batch Snapshot: Approval-Gated Tool Runner Spike

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
- Exposed API friction at that time: approval-gated input used `server.submit_tool_request(...)`, workspace binding required explicit `workspace.bound`, and `approval_id` lookup scanned events. Later helper slices have resolved approval lookup, workspace binding glue, and server-level submit action glue; remaining friction is HTTP approval-gated input shape.

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

Batch name: `Source Artifact Helper Closure Review`

Status: `ready_docs_only`

Possible tasks:

1. Review `InProcessServer.create_source_artifact(...)`.
2. Confirm `artifact-review` no longer uses private source setup glue.
3. Confirm helper remains deterministic / in-process and does not become product upload API.
4. Confirm no real filesystem upload / binary streaming / real HTTP server / provider adapter / memory query scope leaked in.
5. Docs/status sync and queue update only unless a clear bug is found.

Constraints:

- docs-only by default.
- no real filesystem mutation.
- no real LLM.
- no real HTTP server / provider adapter / memory query engine.
- no event store append-only semantic changes.
- no executor grants semantic changes.

## 8. Completed Batch Log

### Usability Friction Reduction Package 1

Status: `complete`

Evidence:

- Approval lookup helper closure review found no bug; helper remains first slice complete.
- Added `docs/workspace-binding-helper-friction-review.md`.
- Added `docs/workspace-binding-helper-boundary-v0.2.md`.
- Added `tests/isotope_kernel/test_workspace_binding_helper.py`.
- Workspace helper red targeted result: `6 failed`.
- Full with red tests: `6 failed, 853 passed`.
- Targeted green result: `6 passed`.
- Full regression: `859 passed`.
- Added `InProcessServer.bind_workspace(...)`.
- Updated `approval-tool-runner` demo to use helper instead of manual `workspace.bound`.
- No real HTTP server / real LLM / provider adapter / filesystem mutation / container / git worktree / process spawn / new dependency.
- Stop reason: package complete; next approval-gated submission helper boundary needed user confirmation and was later completed in Package 2.

### Usability Friction Reduction Package 2

Status: `complete`

Evidence:

- Added `docs/submit-tool-request-friction-review.md`.
- Added `docs/submit-action-helper-boundary-v0.2.md`.
- Added `tests/isotope_kernel/test_submit_action_helper.py`.
- Red targeted result: `5 failed, 1 passed`.
- Full with red tests: `5 failed, 860 passed`.
- Targeted green result: `6 passed`.
- Full regression: `865 passed`.
- Added `InProcessServer.submit_action(...)`.
- Existing `submit_tool_request(...)` remains compatible.
- Updated `approval-tool-runner` demo to use submit action helper plus existing approval lookup and workspace binding helpers.
- No real HTTP server / real LLM / provider adapter / filesystem mutation / container / git worktree / process spawn / new dependency.
- Stop reason: package complete; next HTTP approval input boundary requires user confirmation.

### Approval Lookup Helper Boundary

Status: `complete`

Evidence:

- Red targeted result: `10 failed, 1 passed`.
- Full with red tests: `10 failed, 843 passed`.
- Targeted green result: `11 passed`.
- Full regression: `853 passed`.
- Added server approval lookup/read helpers.
- Added in-process HTTP approval lookup read helper routes.
- Updated `approval-tool-runner` demo to stop scanning events for `approval_id`.
- No approval resolution semantic change.
- No real server / UI / auth / notification / scheduler / new dependency.
- Stop reason: batch complete; next remaining-friction decision needs user confirmation.

### Approval Tool Runner API Friction Review

Status: `complete`

Evidence:

- Added `docs/approval-tool-runner-friction-review.md`.
- Classified `server.submit_tool_request(...)` as a facade/helper gap.
- Classified event-scan approval id lookup as a read-model helper gap.
- Classified explicit `workspace.bound` append as a broader workspace/server integration gap.
- Recommended `Approval Lookup Helper Boundary` as the next smallest safe slice.
- Stop reason: next helper slice requires user confirmation.

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
