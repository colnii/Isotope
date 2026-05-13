# Agent Task Queue

状态：`active`

Current note: Controlled terminal / provider integration is being merged from `feature/controlled-terminal-exec` on a temporary integration branch. Scope is existing-code integration only: controlled argv-only terminal execution, Codex task route, model-tool bridge, LLM provider route, tool-result loop, product-chat route, and LLM terminal-tool loop. Do not expand into interactive shell, process supervisor, real listening HTTP server, container, git worktree, product shell, or new dependency.

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
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario external-snapshot-review
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario external-snapshot-review --trace
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario external-snapshot-review --json
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario agent-loop-friction
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario agent-loop-friction --trace
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario agent-loop-friction --json
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-friction
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-friction --trace
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-friction --json
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-matrix
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-matrix --trace
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-matrix --json
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-restart-pause
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-restart-pause --trace
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-restart-pause --json

rg -n '(^|\s)(from|import) x_agent\b' src/isotope_kernel tests/isotope_kernel || true

git -C /home/lumber/Github/x-agent status --short \
  src/x_agent src/isotope_kernel tests/isotope_kernel docs/isotope

git diff -- src tests .github pyproject.toml
git status --short
```

当前 integration baseline：`1359 passed, 5 skipped`。Pre-controlled-terminal mainline baseline：`1134 passed`。

## 34. Current Batch

Batch name: `Controlled Terminal / Provider Existing-Code Integration`

Status: `in_progress / verification_passed_on_integration_branch`

Goal: merge existing worthwhile code from `feature/controlled-terminal-exec` into mainline without opening new feature scope.

Tasks:

1. Create temporary integration branch from current `main`: complete.
2. Squash-merge `feature/controlled-terminal-exec` and resolve conflicts with current Agent Loop Run Control / Step Driver status preserved: complete.
3. Verify targeted terminal / provider / agent-loop tests: complete.
4. Verify full regression: complete, `1359 passed, 5 skipped`.
5. Sync README / AGENTS / current status / queue: in progress.

Evidence:

- Added/merged surfaces: controlled `terminal_exec`, Codex task route, model-tool bridge, LLM provider route, LLM tool-result loop, product-chat route, and LLM terminal-tool loop.
- Preserved existing surfaces: Capability Hub Core and Agent Loop Run Control / Step Driver.
- Scope remains bounded: no interactive shell, process supervisor, real listening HTTP server, provider product, workflow engine, container, git worktree, new dependency, tag, or release.

Next suggested mode:

Fast-forward this integration branch to `main` after final boundary checks, then inspect `codex/spike-aggressive-dev` for remaining mergeable existing-code slices.

## Branch-Local Batch: Agent Loop Friction Spike

Branch: `spike/app-agent-loop-friction`

Status: `complete`

Goal: start the AI Agent Orchestration / Agent loop work as an isolated application-layer friction spike, without expanding kernel mainline or implementing real LLM loop / scheduler / provider adapter / real worker runtime.

Tasks:

1. Create isolated worktree: complete, at `.worktrees/app-agent-loop-friction`.
2. Confirm clean baseline: complete, pre-branch `1064 passed`; after adding the spike tests, branch-local full regression is `1079 passed` using the main checkout venv.
3. Write red tests for `agent-loop-friction` scenario: complete, expected failure was unsupported scenario.
4. Implement smallest deterministic in-process scenario in `src/isotope_kernel/demo.py`: complete.
5. Record friction review and next development step: complete, see `docs/agent-loop-friction-review.md`.

Evidence:

- New scenario: `python -m isotope_kernel.demo --scenario agent-loop-friction`.
- Trace / JSON variants are supported.
- Targeted tests: `tests/isotope_kernel/test_agent_loop_friction_spike.py`.
- Current result: `private_append_required=false`, `kernel_friction=[]`.
- No real LLM loop / scheduler / provider adapter / real HTTP server / real worker runtime / process spawn / memory query engine / filesystem mutation.

Next suggested branch-local batch:

`Real App-Layer Planner Adapter Friction Spike`

Status: `complete`

Goal: put a tiny deterministic or fixture-backed planner adapter in front of `agent-loop-friction`, require it to produce the same structured `kernel_friction` report, and stop unless it exposes a concrete non-empty kernel gap.

Tasks:

1. Write red tests for `agent-loop-planner-friction` scenario: complete, expected failure was unsupported scenario.
2. Implement smallest deterministic fixture-backed planner adapter in `src/isotope_kernel/demo.py`: complete.
3. Keep planner output symbolic; runner executes public helpers and planner does not append canonical events directly: complete.
4. Record planner adapter friction review and next development step: complete, see `docs/agent-loop-planner-adapter-friction-review.md`.

Evidence:

- New scenario: `python -m isotope_kernel.demo --scenario agent-loop-planner-friction`.
- Trace / JSON variants are supported.
- Targeted tests: `tests/isotope_kernel/test_agent_loop_planner_adapter_spike.py`.
- Current result: `planner_adapter_status=deterministic_fixture`, `private_append_required=false`, `kernel_friction=[]`.
- No real LLM loop / prompt / response / scheduler / provider adapter / real HTTP server / real worker runtime / process spawn / memory query engine / filesystem mutation.

Next suggested branch-local batch:

`Planner Fixture Matrix Friction Spike`

Status: `complete`

Goal: keep the same deterministic planner adapter, but add a tiny fixture matrix with happy path, blocked deferred path, and malformed symbolic action fail-closed path. The blocked path should report app/product-deferred friction for capabilities such as `real_llm_plan` or `memory_query`, not a kernel implementation request.

Tasks:

1. Write red tests for `agent-loop-planner-matrix` scenario: complete, expected failure was unsupported scenario.
2. Implement happy path fixture by reusing the deterministic planner adapter path: complete.
3. Implement blocked deferred capability fixture that classifies `real_llm_plan` as app / product deferred rather than kernel friction: complete.
4. Implement malformed symbolic action fixture that validates before execution and appends no partial events: complete.
5. Record matrix friction review and next development step: complete, see `docs/agent-loop-planner-matrix-friction-review.md`.

Evidence:

- New scenario: `python -m isotope_kernel.demo --scenario agent-loop-planner-matrix`.
- Trace / JSON variants are supported.
- Targeted tests: `tests/isotope_kernel/test_agent_loop_planner_matrix_spike.py`.
- Current result: `planner_matrix_ok=true`, `fixture_count=3`, `kernel_friction=[]`.
- Blocked `real_llm_plan` is app / product deferred friction, not a kernel implementation request.
- Malformed `unknown_symbolic_action` fails closed with `partial_events_appended=false`.
- No real LLM loop / prompt / response / scheduler / provider adapter / real HTTP server / real worker runtime / process spawn / memory query engine / filesystem mutation.

Next suggested branch-local batch:

`Planner Runner API Boundary Review`

Status: `complete`

Goal: review whether the branch-local matrix runner should remain demo-local or become a small reusable app-layer runner module for future spikes. Start docs-only. Do not extract code unless a later spike actually needs to reuse the runner outside `demo.py`.

Tasks:

1. Review current runner callers and reuse pressure: complete.
2. Decide whether to extract a reusable app-layer runner module: complete; do not extract yet.
3. Record kernel boundary risk of names like `agent_loop`, `orchestration`, or `planner_runner`: complete.
4. Define reopen criteria for future extraction: complete.
5. Record next development step: complete, see `docs/planner-runner-api-boundary-review.md`.

Evidence:

- Review doc: `docs/planner-runner-api-boundary-review.md`.
- Scope: docs-only; no `src/`, `tests`, `.github`, or `pyproject.toml` changes.
- Decision: keep runner demo-local until a second non-demo caller or concrete app-layer friction justifies extraction.
- No new kernel API / app-layer runner module was introduced.

Next suggested branch-local batch:

`Planner Matrix Fixture Expansion Review`

Status: `complete`

Goal: docs-only selection for whether the next fixture should pressure one narrow surface: approval denial path, worker handoff denial path, restart after planner pause, or memory query deferred path. Default recommendation is to pause branch-local agent-loop expansion unless the user wants another runnable spike.

Tasks:

1. Review candidate fixtures: complete.
2. Select whether to continue matrix expansion: complete.
3. Record next suggested branch-local step: complete, see `docs/planner-matrix-fixture-expansion-review.md`.

Evidence:

- Review doc: `docs/planner-matrix-fixture-expansion-review.md`.
- Scope: docs-only; no `src/`, `tests`, `.github`, or `pyproject.toml` changes.
- Decision: do not expand by default; if continuing, choose `restart after planner pause`.
- Rationale: it best pressure-tests app-layer lifecycle after restart without requiring real LLM, scheduler, provider adapter, real HTTP server, real worker process, memory query engine, filesystem mutation, public SDK, or product UX.

Next suggested branch-local batch:

`Planner Restart Pause Fixture Spike`

Status: `complete`

Goal: add one deterministic runnable fixture showing a planner pauses at approval, the process restarts, and the loop resumes through public helpers / event-backed state.

Tasks:

1. Write red tests for `agent-loop-planner-restart-pause`: complete, expected failure was unsupported scenario.
2. Implement the smallest deterministic restart-pause demo path: complete.
3. Keep restart recovery public-helper / event-backed; no private append or process-local approval memory required after restart: complete.
4. Record closure and next development step: complete, see `docs/planner-restart-pause-fixture-review.md`.

Evidence:

- New scenario: `python -m isotope_kernel.demo --scenario agent-loop-planner-restart-pause`.
- Trace / JSON variants are supported.
- Targeted tests: `tests/isotope_kernel/test_agent_loop_planner_restart_pause_spike.py`.
- Current result: `planner_restart_pause_ok=true`, `private_append_required=false`, `kernel_friction=[]`.
- No real LLM / scheduler / provider adapter / real HTTP server / real worker process / memory query engine / filesystem mutation / public SDK / product multi-agent UX.

Next suggested branch-local mode:

Pause Agent loop expansion and wait for real app-layer friction or external review feedback.

Next closure batch:

`Agent Loop Branch Closure Review`

Status: `complete`

Goal: record the branch-level conclusion in plain language so the branch can be kept, reviewed, PR'd, or merged without adding more artificial Agent loop scenarios.

Evidence:

- Closure doc: `docs/agent-loop-branch-closure-review.md`.
- Decision: stop branch-local Agent loop expansion for now.
- Scope clarification: stop expansion does not mean Agent loop product is done; it means this foundation check found no new kernel gap.
- Current integration choice remains a user decision: merge, PR, or keep the branch.

Next design batch:

`Planner Input / Output Contract`

Status: `complete`

Goal: define what a future LLM planner can see, what symbolic decisions it can return, and how invalid / unsafe output fails closed before execution.

Evidence:

- Design doc: `docs/planner-input-output-contract-v0.2.md`.
- Decision: next implementation should be a small planner I/O validator spike, not a real LLM integration.
- Plain meaning: first build the gatekeeper, then connect the AI later.

Next implementation batch:

`Planner I/O Validator Spike`

Status: `complete`

Goal: add a small demo-local gatekeeper that accepts one valid symbolic planner output and rejects malformed / unknown / overpowered / unauthorized full-text output before execution.

Evidence:

- New scenario: `python -m isotope_kernel.demo --scenario agent-loop-planner-io-validator`.
- Trace / JSON variants are supported.
- Targeted tests: `tests/isotope_kernel/test_agent_loop_planner_io_validator_spike.py`.
- Current result: `planner_io_validator_ok=true`, `partial_events_appended=false`, `kernel_friction=[]`.
- No real LLM provider / scheduler / real HTTP server / real worker process / memory query engine / filesystem mutation / public SDK / product UX.

Next suggested branch-local batch:

`Planner Validated Runner Spike`

Plain meaning: connect the gatekeeper to the tiny demo runner, so valid fake planner output can run and bad output remains blocked.

Status: `complete`

Goal: connect the demo-local validator to the tiny runner so valid symbolic planner output executes one deterministic loop, while invalid output is blocked before side effects.

Evidence:

- New scenario: `python -m isotope_kernel.demo --scenario agent-loop-planner-validated-runner`.
- Trace / JSON variants are supported.
- Targeted tests: `tests/isotope_kernel/test_agent_loop_planner_validated_runner_spike.py`.
- Current result: `planner_validated_runner_ok=true`, `valid_plan_executed=true`, `invalid_plan_partial_events_appended=false`, `kernel_friction=[]`.
- No real LLM provider / scheduler / real HTTP server / real worker process / memory query engine / filesystem mutation / public SDK / product UX.

Next suggested branch-local mode:

Pause artificial Agent loop expansion and wait for real app-layer friction or external review feedback.

Handoff checkpoint:

Status: `complete`

Evidence:

- Handoff doc: `docs/agent-loop-branch-handoff-checkpoint.md`.
- Decision: branch is ready for keep / PR / merge decision.
- Next useful input should come from real app-layer friction or external review feedback.

Stop conditions:

- requires real LLM, scheduler, provider adapter, real HTTP server, real worker process, filesystem mutation, public SDK, or product UX decision
- requires changing event-store append-only semantics or executor grants semantics
- requires extracting reusable runner code before a second non-demo caller exists
- produces no new branch-local pressure, in which case pause expansion and wait for real application-layer friction

## Capability Hub Core Batch

Batch name: `Capability Hub Core`

Timebox: `red -> green -> docs/status sync`

Status: `complete / closed for now`

Goal: define and implement the smallest mainline-ready extraction from aggressive Capability Hub without merging the aggressive branch wholesale.

Evidence:

- Boundary doc: `docs/capability-hub-core-boundary-v0.2.md`.
- Source review: `docs/aggressive/mainline-merge-candidate-review-v0.md` on `codex/spike-aggressive-dev`.
- Explicitly excludes 49 aggressive capabilities, diagnostics, self-evolution harness, DeepSeek provider, LLM route, `ask`, `interactive`, workflow engine, and product shell.
- Implementation: `src/isotope_kernel/capability_catalog.py`.
- Tests: `tests/isotope_kernel/test_capability_catalog_core.py` and `tests/isotope_kernel/test_capability_catalog_shelves.py`.
- Verification before rebase: red `19 failed`, green targeted `19 passed`, full regression `1083 passed`.

## Capability Hub Core Next Suggested Batch

Batch name: `Capability Hub Core Merge Readiness Review`

Status: `complete`

Goal: rebase the capability catalog branch onto current `origin/main`, verify it remains a small catalog-only extraction, and decide whether it is safe to merge.

Evidence:

- Review doc: `docs/capability-hub-core-merge-readiness-review.md`.
- Rebased onto current `origin/main`.
- Targeted capability catalog tests: `19 passed`.
- Full regression: `1115 passed`.
- `v0.2 --trace` and `agent-loop-planner-validated-runner --trace` demos passed.
- No capability execution, provider routing, product shell, diagnostics, self-evolution, `ask`, or `interactive`.

Next action: user decision to merge / PR / keep branch.

## 8. Previous Current Batch

Batch name: `Worker Handoff Helper Boundary`

Timebox: `docs-only selection slice`

Status: `complete`

Goal: convert aggressive branch `private_append_worker_handoff` evidence into a bounded mainline helper boundary, without implementing runtime worker behavior.

Tasks:

1. Read incoming review / aggressive evidence for `private_append_worker_handoff`: complete.
2. Classify friction as kernel helper gap rather than app-local glue: complete.
3. Define docs-only boundary and first red tests recommendation: complete.

Evidence:

- Boundary doc: `docs/worker-handoff-helper-boundary-v0.2.md`.
- Aggressive evidence: commit `1950e32`, scenario `worker-handoff-gap`, targeted `tests/isotope_kernel/test_worker_handoff_gap_spike.py` -> `5 passed`.
- No `src/`, `tests/`, `.github`, or `pyproject.toml` changes in this docs-only slice.

## 9. Previous Next Suggested Batch

Batch name: `Worker Handoff Helper Closure Review`

Status: `complete`

Tasks:

1. Review `InProcessServer.submit_worker_handoff(...)` implementation and tests: complete.
2. Confirm the helper closes `private_append_worker_handoff` without widening worker runtime: complete.
3. Confirm no real concurrency / process spawn / remote worker / scheduler / product route was added: complete.
4. Decide whether to mark worker handoff helper first slice closed for now: complete.

Evidence:

- Closure doc: `docs/worker-handoff-helper-closure-review.md`.
- Review result: `aca2e3c` accepted with no blocking finding.
- Full regression with local Mac DYLD workaround: `1019 passed`.
- Caveat: `_derive_worker_handoff_grants(...)` is first-slice local grant derivation, not full delegation policy engine.

## 8. Next Suggested Batch

Batch name: `Aggressive Worker Handoff Follow-up Review`

Status: `complete`

Tasks:

1. Wait for aggressive-dev to update `worker-handoff-gap` to use `submit_worker_handoff(...)`: complete.
2. Confirm `private_append_required` becomes false in the app spike: complete.
3. If new `kernel_friction` appears, classify it as kernel helper gap, app-local glue, docs mismatch, or product decision: complete; no active new `kernel_friction`.
4. Do not start deeper worker runtime without concrete friction: complete.

Evidence:

- Aggressive-dev commit: `c7e0b32`.
- Review result: accepted with no mainline implementation request.
- `worker-handoff-gap --json`: `private_append_required=false`, `kernel_friction=[]`, `resolved_kernel_friction[0].kind=private_append_worker_handoff`.
- `approval-input-gap --json`: `approval_gap_detected=false`, `approval_input_supported=true`, `pending_approvals_after_input=1`.
- Targeted aggressive verification: `19 passed`.

Stop conditions:

- red tests need real concurrency / process spawn / remote worker / container / git worktree / real HTTP / real LLM / provider adapter / public SDK
- red tests require product UX decisions
- red tests require changing event-store append-only semantics or executor grants semantics

## 9. Next Suggested Batch

Batch name: `Application-Layer Friction Intake`

Status: `selection complete`

Goal: keep mainline active but bounded by evidence from aggressive-dev or external review. Do not expand kernel runtime unless a specific app spike produces `kernel_friction` with files, tests, and a narrow helper / boundary / replay / checkpoint / API ergonomics gap.

Selection outcome:

- `docs/worker-handoff-app-spike-selection.md` selects `Worker Handoff App Spike Red Tests` as the next bounded mainline step.
- Rationale: worker handoff app composition remains an open kernel-level pressure surface, and the previous `private_append_worker_handoff` helper friction is now closed by `submit_worker_handoff(...)`.
- Scope: red tests only first; no real worker runtime, scheduler, process spawn, remote worker, container, git worktree, real HTTP, real LLM, provider, public SDK, or product multi-agent UX.
- Follow-up: aggressive-dev `1993521` covered this same pressure point through Capability Hub default capability `worker.handoff.review`; review accepted it with `kernel_friction=[]`, so mainline should not duplicate the red-test batch unless new friction appears.

Allowed next actions:

1. Read aggressive-dev / review evidence for the next concrete pressure point.
2. Classify the reported friction as kernel-level, app-local, docs mismatch, or product decision.
3. If kernel-level and bounded, open a red-test-first mainline slice.
4. If app-local or under-specified, record the reason and wait for sharper evidence.

Stop conditions:

- needs real HTTP server, real LLM, provider/webhook, memory query/storage, real filesystem/container/git worktree, UI/auth/multi-user, plugin marketplace, scheduler/process kill, or tag/release
- needs product/user decision before a kernel contract can be defined
- requires modifying event-store append-only semantics or executor grants semantics

## 10. Next Suggested Batch

Batch name: `Worker Handoff App Spike Red Tests`

Status: `paused; covered by aggressive-dev 1993521`

Goal: write red tests for a deterministic in-process `worker-handoff-app` scenario that composes worker lifecycle, delegation policy, workspace grants, artifact `ResourceRef` result handoff, replay, and checkpoint without opening real worker runtime.

Suggested tests:

1. `tests/isotope_kernel/test_worker_handoff_app_spike.py`
2. `tests/isotope_kernel/test_worker_handoff_app_read_model.py`

Stop conditions:

- requires real concurrency, scheduler, process spawn, remote worker, process kill, container, git worktree, real filesystem mutation, real HTTP server, real LLM, provider adapter, memory query/storage, public SDK, or product UX decision
- requires changing event-store append-only semantics or executor grants semantics

Pause reason:

- Review of aggressive-dev `1993521` confirmed `worker.handoff.review --json` returns `status=ok`, `private_append_required=false`, and `kernel_friction=[]`.
- Starting this red-test batch now would duplicate app-layer coverage instead of responding to active kernel friction.
- Reopen only if a later pressure point reports new files / tests / bounded action and non-empty `kernel_friction`.

## 11. Next Suggested Batch

Batch name: `Application-Layer Friction Intake`

Status: `waiting for new concrete pressure point`

Goal: wait for aggressive-dev or external review to report a distinct bounded `kernel_friction`. If no such friction exists, keep mainline clean and avoid speculative kernel expansion.

Candidate if user explicitly requests kernel-forward docs-only selection:

- `Session / Run Lifecycle Boundary`
- `Error Taxonomy Boundary`

Do not implement either candidate without a separate batch decision.

## 12. Current Batch

Batch name: `Session / Run Lifecycle Boundary`

Status: `complete`

Type: docs-only boundary

Goal: define the minimum kernel contract for session identity, run lifecycle status transitions, terminal-state behavior, replay, and checkpoint without implementing product session workflow.

Evidence:

- Boundary doc: `docs/session-run-lifecycle-boundary-v0.2.md`.
- Scope: docs-only; no `src/`, `tests`, `.github`, or `pyproject.toml` changes.
- Deferred: product session UX, auth, real HTTP server, scheduler, process kill, real concurrency, run graph, and cross-run memory promotion.

## 13. Next Suggested Batch

Batch name: `Session / Run Lifecycle Red Tests`

Status: `complete`

Goal: write red tests for the accepted boundary before any implementation.

Suggested tests:

1. `tests/isotope_kernel/test_session_lifecycle_boundary.py`
2. `tests/isotope_kernel/test_run_lifecycle_boundary.py`

Stop conditions:

- tests require product session UX, auth, real HTTP server, scheduler, process kill, real concurrency, run graph, memory promotion, or dependency changes
- tests require event-store append-only semantic changes
- tests require hidden server-local session state to become replay truth without canonical events

Evidence:

- Added `tests/isotope_kernel/test_session_lifecycle_boundary.py`.
- Added `tests/isotope_kernel/test_run_lifecycle_boundary.py`.
- Review accepted the narrowed red tests around aggressive-dev `terminal_run_partial_mutation`.

## 14. Current Batch

Batch name: `Session / Run Lifecycle Green Slice`

Status: `complete`

Goal: fix terminal ordinary-input partial mutation and add the minimal event-backed session/run lifecycle read path.

Evidence:

- `session.created` is registered as a canonical event and appended by `InProcessServer.create_session()`.
- `InProcessServer.get_session_state(...)` reconstructs session status and run ids from canonical events.
- `RunState` now exposes `session_id`, `goal`, `created_event_id`, and `completed_event_id`; checkpoint-assisted rebuild preserves these fields.
- `submit_input(...)` now rejects terminal runs before appending proposal / decision / execution / artifact / completion events.
- Targeted result: `14 passed`.
- Full non-packaging regression on this Mac mini: `1016 passed, 8 deselected`.
- Full regression including packaging smoke: `1020 passed, 4 errors`; the 4 errors are existing local `test_packaging_smoke.py` ensurepip/temp venv bootstrap errors.

## 15. Next Suggested Batch

Batch name: `Application-Layer Friction Intake`

Status: `complete`

Goal: let aggressive-dev rerun `run.lifecycle.review` against the updated mainline shape; only reopen mainline if it reports a new concrete `kernel_friction`.

Evidence:

- Aggressive-dev `run.lifecycle.review` consumed mainline `664d14b` and returned `kernel_friction=[]`.
- Aggressive-dev `error.taxonomy.review` exposed new accepted `kernel_friction`: `unstructured_kernel_helper_errors`.
- Review accepted the friction and requested an `Error Taxonomy Boundary` before red tests / implementation.

## 16. Current Batch

Batch name: `Error Taxonomy Boundary`

Status: `complete`

Type: docs-only boundary

Goal: define the minimum structured kernel error contract for direct helpers and HTTP facade mapping without product error UX or public SDK.

Evidence:

- Boundary doc: `docs/error-taxonomy-boundary-v0.2.md`.
- Scope: docs-only; no `src/`, `tests`, `.github`, or `pyproject.toml` changes.
- Contract: future `KernelError(ValueError)` should preserve legacy message compatibility while exposing stable `code`, `category`, `retryable`, optional `http_status`, and low-sensitive `details`.
- Deferred: product error UX, public SDK, real HTTP server, provider / webhook, process supervisor, container, git worktree, plugin error registry, tag, and release.

## 17. Next Suggested Batch

Batch name: `Error Taxonomy Red Tests`

Status: `complete`

Goal: write red tests for `KernelError` compatibility and first helper / HTTP mapping paths before implementation.

Suggested tests:

1. `tests/isotope_kernel/test_kernel_error_taxonomy_boundary.py`
2. `tests/isotope_kernel/test_http_error_mapping_boundary.py`

Stop conditions:

- tests require product error UX, public SDK, real HTTP server, provider adapter, process supervisor, container, git worktree, dependency changes, tag, or release
- tests require changing event-store append-only semantics or executor grants semantics
- tests require leaking raw content, provider payloads, or secrets into `details`

Evidence:

- Added `tests/isotope_kernel/test_kernel_error_taxonomy_boundary.py`.
- Added `tests/isotope_kernel/test_http_error_mapping_boundary.py`.
- Targeted red result before implementation: `12 failed`.
- Review accepted the red tests and fixed `run_terminal` category as `conflict`.

## 18. Current Batch

Batch name: `Error Taxonomy Green Slice`

Status: `complete`

Goal: implement the smallest structured kernel error compatibility layer for helper and HTTP mapping paths.

Evidence:

- Added `src/isotope_kernel/errors.py`.
- Implemented `KernelError(ValueError)` preserving `str(exc)` / `args[0]`.
- Added stable attrs: `code`, `category`, `retryable`, `http_status`, `details`.
- Covered terminal run, unknown run/session, invalid request, and `not_enabled` first-slice paths.
- HTTP facade maps structured attrs while preserving top-level `status` envelope compatibility.
- `details` rejects secret/raw-content style keys.
- Targeted result: `12 passed`.
- Full regression with local Mac env workaround: `1036 passed`.
- Demos `artifact-review --trace`, `external-snapshot-review --trace`, and `approval-tool-runner --trace` pass.
- No product error UX / public SDK / real HTTP server / provider / process supervisor / container / git worktree / tag / release.

## 19. Next Suggested Batch

Batch name: `Error Taxonomy Closure Review`

Status: `complete`

Goal: close the structured kernel error first slice after review accepted `4aa094f`.

Evidence:

- Added `docs/error-taxonomy-closure-review.md`.
- Boundary status updated to `first slice complete / closed for now`.
- Confirmed current slice is `KernelError(ValueError)` compatibility + helper / HTTP mapping first paths, not product error UX or public SDK.
- Deferred provider / process / container / git-worktree error surfaces remain closed until concrete `kernel_friction` appears.

## 20. Next Suggested Batch

Batch name: `Worker Handoff Error Taxonomy Slice`

Status: `complete`

Goal: consume accepted aggressive-dev `unstructured_worker_handoff_errors` pressure and add structured taxonomy attrs to worker handoff helper rejection paths without changing append semantics.

Evidence:

- Added `tests/isotope_kernel/test_worker_handoff_error_taxonomy.py`.
- Targeted red before implementation: `4 failed`.
- Implemented structured worker handoff rejection errors for malformed intent, forged grants, unknown artifact ref, and policy denied.
- Policy denial preserves `PermissionError` compatibility while exposing `code=worker_handoff_denied`, `category=policy`, `retryable=False`, `http_status=403`, and `details.reason_codes`.
- Validation / forged grants / unknown artifact use `KernelError(ValueError)` compatibility.
- No partial delegation / worker events on all tested rejection paths.
- Targeted worker handoff result: `13 passed`.
- Error taxonomy regression result: `12 passed`.
- No real worker runtime / scheduler / process spawn / HTTP route / provider / product UX / SDK / tag / release.

## 21. Next Suggested Batch

Batch name: `Application-Layer Friction Intake`

Status: `complete; reopened by accepted delegation decision read-model friction`

Goal: let aggressive-dev consume the structured error contract and rerun `error.taxonomy.review`; only reopen mainline if it reports a new concrete `kernel_friction`.

Evidence:

- Aggressive-dev consumed the structured error contract and later reported `delegation_decision_read_model_missing`.
- Review accepted it as real bounded kernel read-model friction.

## 22. Current Batch

Batch name: `Delegation Decision Read Model Slice`

Status: `complete`

Goal: remove app-layer raw event scans for worker handoff audit by projecting canonical delegation decisions into `RunState`.

Evidence:

- Added `tests/isotope_kernel/test_delegation_decision_read_model.py`.
- Implemented `RunState.delegations` keyed by `delegation_id`.
- Projected `delegation.proposed`, `delegation.decided`, and `worker.created` linkage.
- Read model includes `decision_id`, `outcome`, `reason_codes`, `grants`, `policy_basis`, and `worker_id`.
- Replay and checkpoint-assisted rebuild are covered.
- Targeted result: `3 passed`.
- Focused regression: `35 passed`.
- Full regression with local Mac env workaround: `1043 passed`.
- No event append semantic changes; no denied-delegation append, real worker runtime, scheduler/process spawn, HTTP route, provider, product audit UX, SDK, tag, or release.

## 23. Next Suggested Batch

Batch name: `Application-Layer Friction Intake`

Status: `complete; reopened by accepted workspace lifecycle helper friction`

Goal: let aggressive-dev consume `RunState.delegations` and rerun `worker.handoff.audit.review`; only reopen mainline if it reports a new concrete `kernel_friction`.

Evidence:

- Aggressive-dev consumed `RunState.delegations` in `d562fb7aa383c7b231c512313b1b88193f986d3a`; review confirmed `worker.handoff.audit.review` uses the read model with `event_scan_used=false`, `kernel_friction=[]`, and `mainline_action_requested=none`.
- Aggressive-dev later reported accepted `workspace_lifecycle_helper_missing` from `d9780413e91600af7a46622fe6c759b4b0deadb2`.

## 24. Current Batch

Batch name: `Workspace Lifecycle Helper Slice`

Status: `complete`

Goal: remove app-layer private `_append(...)` glue for existing workspace lifecycle canonical events without opening real workspace substrate.

Evidence:

- Added `tests/isotope_kernel/test_workspace_lifecycle_helper.py`.
- Implemented `InProcessServer.create_workspace_lease(...)`, `capture_workspace_artifact(...)`, and `release_workspace(...)`.
- Helpers append existing canonical `workspace.lease_created`, `workspace.artifact_captured`, and `workspace.released` events after candidate replay validation.
- Helpers return projected workspace summaries and keep replay / checkpoint-assisted rebuild consistent.
- Targeted result: `3 passed`.
- Focused regression: `38 passed`.
- Full regression with local Mac env workaround: `1046 passed`.
- No real filesystem / container / git worktree / remote executor / cleanup scheduler / path-safety engine / product workspace API / tag / release.

## 25. Next Suggested Batch

Batch name: `Application-Layer Friction Intake`

Status: `complete; reopened by accepted derived artifact provenance friction`

Goal: let aggressive-dev consume the workspace lifecycle helper slice and rerun `workspace.lifecycle.review`; only reopen mainline if it reports a new concrete `kernel_friction`.

Evidence:

- Review accepted aggressive-dev `spike/aggressive-dev@0a04542d05cb432dae462ca7d3406da553c58eda` `derived_artifact_basis_refs_missing` as bounded artifact provenance / read-model `kernel_friction`.
- Mainline implemented optional `basis_refs` / `source_refs` support on `InProcessServer.create_source_artifact(...)`.
- Refs are validated as same-run structured artifact `ResourceRef` values, persisted in `artifact.created` summary provenance, and projected through replay / checkpoint / `get_artifact_record(...)`.
- Targeted result: `tests/isotope_kernel/test_artifact_provenance_helper.py` -> `8 passed`.
- Focused regression: artifact provenance / source artifact setup / worker handoff / workspace lifecycle helpers -> `29 passed`.
- Full regression with local Mac env workaround: `1049 passed`.
- No artifact full content exposure, real worker runtime, pipeline/fan-in helper, scheduler/process spawn, container/git worktree, real HTTP server, provider adapter, public SDK, tag, or release.

## 26. Next Suggested Batch

Batch name: `Application-Layer Friction Intake`

Status: `complete; reopened by accepted tool invocation runtime friction`

Goal: let aggressive-dev consume the derived artifact basis refs slice and rerun `worker.handoff.provenance.review`; only reopen mainline if it reports a new concrete `kernel_friction`.

Evidence:

- Aggressive-dev consumed `origin/main@105f7fb214d32767861b5dfe5fa8d23722d386c7` and reported `tool.protocol.runtime.review` friction from `spike/aggressive-dev@134b9d9019910ca7cffbe41d419e5c22e135b523`.
- Review accepted `tool_invocation_runtime_missing` as bounded kernel friction: metadata-registered `app_probe_tool` still fails closed as `unsupported handler for tool app_probe_tool` because `Executor.execute(...)` does not construct/pass `ToolInvocation` to an explicit in-process handler boundary.

## 27. Current Batch

Batch name: `Tool Invocation Runtime Wiring Green Slice`

Status: `complete; pushed`

Goal: pin the narrow executor runtime wiring gap without opening plugin marketplace, remote execution, sandbox/process, public SDK, provider adapter, real HTTP route, or new dependency.

Evidence:

- Added `docs/tool-invocation-runtime-wiring-boundary-v0.2.md`.
- Added red tests in `tests/isotope_kernel/test_tool_invocation_runtime_wiring.py`; initial red result was `2 failed, 1 passed` at `Executor.__init__() got an unexpected keyword argument 'tool_handlers'`.
- Implemented optional `Executor(..., tool_handlers={...})` for explicit deterministic in-process handlers.
- Implemented optional `InProcessServer(..., tool_handlers={...})` and facade forwarding to `Executor`.
- `Executor` now constructs `ToolInvocation` from proposal / decision / execution / effective grants / budget / workspace binding and passes it to the handler.
- Requested capabilities are capped to effective grants before entering `ToolInvocation`; forged requested tools are not passed through.
- Ungranted tool still fails before handler invocation and leaves only `action.started` / `action.failed`.
- Non-artifact `ToolResult.artifact_refs=[]` no longer returns a stale prior `artifact_ref` from the same run.
- Existing `write_artifact_tool` deterministic artifact path remains unchanged.
- Targeted result: `tests/isotope_kernel/test_tool_invocation_runtime_wiring.py` -> `6 passed`.
- Focused regression: tool invocation runtime / tool protocol / tool result event / executor registry / server action registry wiring / submit action helper -> `41 passed`.
- Review passed and mainline pushed `d2a6ae9..d697d5d` to `origin/main`.

## 28. Current Batch

Batch name: `Restart Write Helper Run Context Green Slice`

Status: `complete; pushed`

Goal: pin the restart write-helper run-context gap without opening real worker runtime, scheduler/process supervisor, process spawn, container/git worktree, real HTTP, provider adapter, public SDK, new dependency, tag, or release.

Evidence:

- Review accepted aggressive-dev `spike/aggressive-dev@a27477b1a79606bd1a5323e1f838206b80dae75f` `restart_write_helper_run_context_missing` as bounded `kernel_friction`.
- Added `docs/restart-write-helper-run-context-boundary-v0.2.md`.
- Added red tests in `tests/isotope_kernel/test_restart_write_helper_run_context.py`; initial red result was `3 failed` including `KernelError: unknown run_id` after restart even though `get_run_state(run_id)` can rebuild the same run.
- Implemented event-backed runtime context recovery for selected helpers from `run.created` / `agent.created` / `thread.created` plus projected non-terminal `RunState`.
- `create_source_artifact(...)` and `submit_worker_handoff(...)` can continue writing to an existing non-terminal run after `InProcessServer` restart.
- Terminal run post-restart writes still fail closed without appended events.
- Targeted result: `tests/isotope_kernel/test_restart_write_helper_run_context.py` -> `3 passed`.
- Focused regression: restart write helper / source artifact setup / worker handoff / run lifecycle -> `24 passed`.
- Full regression with local Mac env workaround: `1058 passed`.
- Review passed and mainline pushed `22566db` to `origin/main`.

## 29. Current Batch

Batch name: `Restart Approval Resolution Context Green Slice`

Status: `complete; pushed`

Goal: close accepted `restart_approval_resolution_context_missing` without opening real HTTP, scheduler/process kill, real concurrency, UI/auth/notification/product approval workflow, provider adapter, public SDK, tag, or release.

Evidence:

- Review accepted aggressive-dev `spike/aggressive-dev@db76ac10c4899f7444576a62d27ae348f4bd4d64` `restart_approval_resolution_context_missing` as bounded `kernel_friction`.
- Added red tests in `tests/isotope_kernel/test_approval_run_state_invariants.py`; initial red result was `1 failed, 1 passed`, with restarted `resolve_approval(...)` failing `ValueError: unknown approval` while no partial events were appended.
- Implemented persisted approval `resolution_context` on `approval.requested`, carrying minimal proposal / decision metadata plus a private payload handle for restarted `resolve_approval(...)`.
- Added full-content leak regression: pending approval event payload / run-state / checkpoint must not contain raw tool text.
- Restarted `InProcessServer(root, checkpoint_store=...)` can resolve a pending approval and continue the existing executor path with original grants.
- Malformed restarted resolution still fails closed without appended events.
- Targeted red/green result: restarted approval and leak-regression tests -> `3 passed`.
- Focused regression: approval resolution / approval run-state invariants / approval lookup -> `35 passed`.
- Full regression with local Mac env workaround: `1061 passed`.

## 30. Current Batch

Batch name: `Restart Source Artifact Return Ref Green Slice`

Status: `complete; pushed`

Goal: close accepted aggressive-dev `restart_source_artifact_return_ref_mismatch` without opening real worker runtime, scheduler/process supervisor, process spawn, container/git worktree, real HTTP, provider adapter, public SDK, new dependency, tag, or release.

Evidence:

- Review accepted aggressive-dev `spike/aggressive-dev@8a38df6c3debf5a33b9f40342d4e24e3f9f63abd` `worker.handoff.restart.pipeline.review` as bounded `kernel_friction`.
- Added red coverage to `tests/isotope_kernel/test_restart_write_helper_run_context.py`: after restart, `create_source_artifact(...)` must return the current executor-created artifact ref, not the pre-restart artifact, and must preserve `basis_refs` / `source_refs`.
- Red result: targeted test failed because returned `ResourceRef` was the pre-restart artifact.
- Implemented current-execution lookup via `_completed_artifact_ref(run_id, execution.execution_id)` and `ArtifactStore.get_metadata(...)`, replacing `ArtifactStore.list_artifacts(run_id)[-1]` in `create_source_artifact(...)`.
- Targeted result: `tests/isotope_kernel/test_restart_write_helper_run_context.py::test_source_artifact_helper_can_write_after_server_restart` -> `1 passed`.
- Focused regression: restart write helper / artifact provenance / source artifact setup / worker handoff -> `29 passed`.
- Full regression currently has the known local packaging smoke `ensurepip` errors: `1058 passed, 4 errors`; non-packaging kernel tests were otherwise green.

## 31. Current Batch

Batch name: `Denied Worker Handoff Audit Green Slice`

Status: `complete; pending review`

Goal: close accepted aggressive-dev `denied_worker_handoff_audit_missing` without opening real worker runtime, scheduler/process supervisor, process spawn, container/git worktree, real HTTP, provider adapter, public SDK, new dependency, tag, or release.

Evidence:

- Review accepted aggressive-dev `spike/aggressive-dev@56a8d533d9f96b48f9dad848c6c6dd90ef505615` `worker.handoff.denial.audit.review` as bounded `kernel_friction`.
- Added red coverage to `tests/isotope_kernel/test_worker_handoff_helper.py`: denied `submit_worker_handoff(...)` must still raise structured `KernelPermissionError`, but append canonical `delegation.proposed` + `delegation.decided(outcome=denied)` so `RunState.delegations` can audit the denied decision.
- Updated worker handoff error taxonomy coverage to treat the two delegation audit events as intentional canonical audit, while still requiring no `worker.*` events.
- Implemented denied-path candidate replay and append for delegation audit events before raising `KernelPermissionError`; no worker ids/events are created for denied decisions.
- Targeted denied audit / taxonomy tests -> `2 passed`.
- Focused worker handoff / error taxonomy / delegation read-model tests -> `17 passed`.

## 32. Current Batch

Batch name: `Restart Create Run Session Context Green Slice`

Status: `complete; pending review`

Goal: close accepted aggressive-dev `restart_create_run_session_context_missing` without opening product session workflow, run graph, real worker runtime, scheduler/process supervisor, process spawn, real HTTP, provider adapter, filesystem/container/git worktree, public SDK, new dependency, tag, or release.

Evidence:

- Review accepted aggressive-dev `spike/aggressive-dev@6485feef27ff719fde17c95867dc03b4bb48057e` `worker.handoff.approval.recovery.review` as bounded `kernel_friction`.
- Added red coverage to `tests/isotope_kernel/test_session_lifecycle_boundary.py`: restarted `InProcessServer(root)` must allow `create_run(session_id, ...)` for a session recoverable via `get_session_state(...)`, and the new run must appear in the event-backed session read model.
- Red result: targeted test failed with `KernelError(code=unknown_session)` because session validation only checked process-local `_sessions`.
- Implemented event-backed session validation fallback: `_validate_existing_session_id(...)` now recovers minimal session context through `get_session_state(...)` when `_sessions` is empty after restart.
- Targeted red/green result: restarted create-run session test -> `1 passed`.
- Focused regression: session lifecycle / restart write helper / unknown session taxonomy -> `7 passed`.
- Full regression with local `DYLD_LIBRARY_PATH` workaround: `1064 passed in 7.44s`.

### Previous Batch Snapshot: Worker Handoff Helper Red / Green Slice

Batch name: `Worker Handoff Helper Red / Green Slice`

Status: `complete`

Evidence:

- Added `tests/isotope_kernel/test_worker_handoff_helper.py`.
- Implemented `InProcessServer.submit_worker_handoff(...)`.
- Targeted result: `9 passed`.
- Full regression on this Mac mini: `1015 passed, 4 errors`; 4 errors are known `test_packaging_smoke.py` ensurepip/temp venv bootstrap environment failures.
- No real concurrency / process spawn / remote worker / scheduler / container / git worktree / real HTTP / real LLM / provider adapter / public SDK / new dependency.

## 9. Previous Current Batch

Batch name: `Workspace Binding Demo Glue Cleanup`

Timebox: `small external-review cleanup slice`

Status: `complete`

Goal: accept review feedback that `approval-tool-runner` had an unused stale demo-local workspace append helper.

Tasks:

1. Replace monkeypatch guard with a source-level test that `demo.py` contains no `_append_workspace_binding_event(...)` or private `server._append(...)` workspace glue: complete.
2. Remove the unused `_append_workspace_binding_event(...)` helper from `src/isotope_kernel/demo.py`: complete.
3. Sync workspace helper friction docs / status: complete.

Evidence:

- Updated test path: `tests/isotope_kernel/test_workspace_binding_helper.py`.
- Updated demo path: `src/isotope_kernel/demo.py`.
- Targeted workspace binding helper tests: `6 passed`.
- Approval tool runner trace: passed.
- `git diff -- src tests .github pyproject.toml`: limited to intended demo/test cleanup before commit.
- No kernel feature, provider/webhook/API/real workspace/runtime behavior changed.

## 9. Previous Next Suggested Batch

Batch name: `Application-Layer Friction Intake`

Status: `waiting for concrete app-layer or external-review feedback`

Possible tasks:

1. Read incoming app-layer friction / external review notes.
2. Classify each issue as kernel bug, helper/facade gap, docs mismatch, or app-layer glue.
3. Only open a new kernel red/green batch when friction is concrete and bounded.
4. Keep plugin / remote / sandbox / streaming / public SDK / real HTTP / real LLM / provider / tag-release work out of scope unless explicitly requested.

Alternative if user chooses pause/review:

- stay paused at the current stable external review package

Or if deeper kernel work is explicitly requested:

- `Worker Handoff App Spike Selection`
- `External Review Package Refresh`

### Previous Batch Snapshot: Tool Protocol Green Slice

Batch name: `Tool Protocol Green Slice`

Status: `complete`

Evidence:

- Implemented `src/isotope_kernel/tool_protocol.py`.
- Added:
  - `tests/isotope_kernel/test_tool_protocol_boundary.py`
  - `tests/isotope_kernel/test_tool_result_event_boundary.py`
- Completed artifact event provenance and structured `action.failed` error shape.
- Targeted result: `17 passed`.
- Full regression: `1003 passed`.


### Previous Batch Snapshot: Kernel Mainline Maintenance Check

Batch name: `Kernel Mainline Maintenance Check`

Timebox: `verification / docs-only`

Status: `complete`

Goal: confirm the mainline is in conservative maintenance mode and ready for application-layer friction intake.

Evidence:

- Maintenance mode entry: `docs/kernel-mainline-maintenance-mode.md`.
- Public / internal docs boundary: `docs/public-internal-docs-boundary.md`.
- Full regression baseline remained: `986 passed`.
- Mainline default: do not proactively expand kernel features.

### Previous Batch Snapshot: Post External Review Checkpoint

Batch name: `Post External Review Checkpoint`

Timebox: `45-60 min`

Status: `complete`

Goal: record that the repo is external-review ready and define next-stage options.

Tasks:

1. Add post external review checkpoint doc: complete.
2. Record external review readiness, baseline, passing demos, and no tag/release: complete.
3. Summarize stable-for-review kernel contracts: complete.
4. Summarize not-product / not-overclaimed surfaces: complete.
5. Record next-stage options and default recommendation: complete.
6. Sync README / AGENTS / status / roadmap / inventory: complete.

Evidence:

- External review package: `docs/external-review-package-v0.2.md`.
- Post external review checkpoint: `docs/post-external-review-checkpoint.md`.
- Checkpoint records external review ready status, `986 passed`, passing artifact-review / external-snapshot-review / approval-tool-runner traces, no tag/release, and `main` ahead of `v0.2-demo`.
- Default recommendation: pause kernel expansion briefly and let application-layer work create real friction.
- Full regression remains: `986 passed`.

### Previous Batch Snapshot: Retry / Cancel / Supersede Runtime Integration Green Slice

Batch name: `Retry / Cancel / Supersede Runtime Integration Green Slice`

Status: `complete`

Evidence:

- Implemented:
  - `InProcessServer.request_retry(...)`
  - `InProcessServer.request_cancel(...)`
  - `InProcessServer.request_supersede(...)`
- Targeted green result: `15 passed`.
- Full regression: `974 passed`.
- No scheduler / process kill / real concurrency / product HTTP route / new dependency / executor grants semantic change.

### Previous Batch Snapshot: Retry / Cancel / Supersede Runtime Integration Red Tests

Batch name: `Retry / Cancel / Supersede Runtime Integration Red Tests`

Status: `complete`

Evidence:

- Added:
  - `tests/isotope_kernel/test_retry_runtime_integration_boundary.py`
  - `tests/isotope_kernel/test_cancel_runtime_integration_boundary.py`
  - `tests/isotope_kernel/test_supersede_runtime_integration_boundary.py`
- Targeted red result: `12 failed, 3 passed`.
- Full regression with red tests: `12 failed, 962 passed`.
- Failures were only missing `InProcessServer.request_retry(...)`, `request_cancel(...)`, and `request_supersede(...)` helpers.

### Previous Batch Snapshot: Policy Registry Version Basis Closure Review

Batch name: `Policy Registry Version Basis Closure Review`

Status: `complete`

Evidence:

- Boundary doc: `docs/policy-profile-action-registry-versioning-boundary-v0.2.md`.
- Closure doc: `docs/policy-registry-version-basis-closure-review.md`.
- Targeted tests: `17 passed`.
- Full regression: `959 passed`.
- Test files:
  - `tests/isotope_kernel/test_action_registry_version_basis.py`
  - `tests/isotope_kernel/test_policy_profile_version_basis.py`
- Fixture sync: existing handwritten `action.proposed` / `action.decided` payload fixtures now include default basis metadata; malformed missing-basis tests still fail fast.
- Deferred: plugin marketplace, dynamic plugin loading, remote registry loading, signed registry bundles, policy DSL, product policy UI, multi-tenant policy profile management, and schema migration framework.

### Current Batch Snapshot: Policy Constructor Surface Green Slice

Batch name: `Policy Constructor Surface Green Slice`

Status: `complete; pushed`

Evidence:

- Source friction: review accepted `server_policy_profile_injection_missing` as a bounded kernel ergonomics gap.
- TDD red: `tests/isotope_kernel/test_server_action_registry_wiring.py::test_server_constructor_policy_metadata_flows_to_decision_read_model_replay_and_checkpoint` first failed because `InProcessServer.__init__()` did not accept `policy_profile_id`.
- Green: `InProcessServer(..., registry=..., policy_profile_id=..., policy_version=...)` constructs `PolicyEngine(registry=self.registry, policy_profile_id=..., policy_version=...)`.
- Targeted verification: `tests/isotope_kernel/test_server_action_registry_wiring.py tests/isotope_kernel/test_policy_profile_version_basis.py tests/isotope_kernel/test_action_registry_version_basis.py -q` -> `23 passed`.
- Full regression with local `DYLD_LIBRARY_PATH` workaround: `1062 passed in 7.14s`.
- `git diff --check` clean; strict `x_agent.*` scan no matches.
- Review passed and commit `139a6c4 feat: expose policy profile constructor metadata` was pushed to `origin/main`.
- Boundary: no arbitrary `PolicyEngine` injection, no registry mismatch, no policy DSL, no remote registry loading, no product policy UI, no public SDK, no real HTTP, no provider adapter, no new dependency, no tag/release.

### Previous Batch Snapshot: Workspace Resource Lifecycle Closure Review

Batch name: `Workspace Resource Lifecycle Closure Review`

Status: `complete`

Evidence:

- Closure doc: `docs/workspace-resource-lifecycle-closure-review.md`.
- Full regression: `942 passed`.
- `workspace.lease_created`, `workspace.released`, and `workspace.artifact_captured` are closed at projector/read-model/checkpoint scope.
- Remaining work is deferred: `workspace.release_failed`, path-safety, write / isolated modes, cleanup scheduler, real filesystem substrate, container, git worktree, remote executor, and product workspace file/content API.

### Previous Batch Snapshot: Workspace Resource Lifecycle Green Slice

Batch name: `Workspace Resource Lifecycle Green Slice`

Status: `complete`

Evidence:

- Targeted workspace lifecycle tests: `29 passed`.
- Full regression: `942 passed`.
- artifact-review trace regression: pass.
- external-snapshot-review trace regression: pass.
- Tests: `tests/isotope_kernel/test_workspace_lease_lifecycle_boundary.py` and `tests/isotope_kernel/test_workspace_artifact_capture_boundary.py`.
- Code: `src/isotope_kernel/projector.py`.
- Supported events: `workspace.lease_created`, `workspace.bound`, `workspace.released`, `workspace.artifact_captured`.
- `RunState.workspaces` now includes lease / release / artifact-ref linkage fields and restores via replay / checkpoint-assisted rebuild.
- No real filesystem mutation / container / git worktree / remote executor / cleanup scheduler / dependency.

### Previous Batch Snapshot: Workspace Resource Lifecycle Red Tests

Batch name: `Workspace Resource Lifecycle Red Tests`

Status: `complete`

Evidence:

- Targeted red result: `24 failed, 5 passed`.
- Full regression with red tests: `24 failed, 918 passed`.
- Failures were only from the new workspace lifecycle / capture tests.
- Added:
  - `tests/isotope_kernel/test_workspace_lease_lifecycle_boundary.py`
  - `tests/isotope_kernel/test_workspace_artifact_capture_boundary.py`
- No `src` / docs changes in red-only batch.

### Previous Batch Snapshot: Workspace Resource Lifecycle Boundary

Batch name: `Workspace Resource Lifecycle Boundary`

Status: `complete`

Evidence:

- Full regression: `913 passed`.
- artifact-review trace regression: pass.
- external-snapshot-review trace regression: pass.
- Boundary doc: `docs/workspace-resource-lifecycle-boundary-v0.2.md`.
- Boundary keeps workspace as policy-bound resource, not agent identity.
- Binding and lease are separate.
- Candidate events: `workspace.lease_created`, `workspace.bound`, `workspace.released`, deferred `workspace.release_failed`, optional `workspace.artifact_captured`.
- First red test recommendation: `tests/isotope_kernel/test_workspace_lease_lifecycle_boundary.py` and `tests/isotope_kernel/test_workspace_artifact_capture_boundary.py`.
- No code / tests changed.
- No real filesystem mutation / container / git worktree / remote executor / cleanup scheduler / dependency.

### Previous Batch Snapshot: Kernel Gap Review Refresh

Batch name: `Kernel Gap Review Refresh`

Status: `complete`

Tasks:

1. Review current kernel surfaces against `src/isotope_kernel/`: complete.
2. Compare original kernel gaps against current first-slice coverage: complete.
3. Separate kernel-level gaps from not-now product / integration gaps: complete.
4. Recommend next path among worker handoff, workspace lifecycle, RCS runtime integration, policy/profile versioning, and external review package: complete.
5. Docs / status sync: complete.
6. Queue update: complete; next suggested batch set to `Workspace Resource Lifecycle Boundary`.

Evidence:

- Full regression: `913 passed`.
- artifact-review trace regression: pass.
- external-snapshot-review trace regression: pass.
- approval-tool-runner trace regression: pass.
- Refresh doc: `docs/kernel-gap-review-refresh-v0.2.md`.
- First-slice enough: agent / worker lifecycle, workspace substrate, retry / cancel / supersede, HTTP facade, approval pause / resume, external ingestion boundary, artifact content read policy.
- Still-open kernel gaps: workspace resource lifecycle, policy profile / action registry versioning, retry / cancel / supersede runtime integration, worker handoff app composition, session / run lifecycle, error taxonomy, event schema registry, tool protocol.
- Next recommended path: `Workspace Resource Lifecycle Boundary`.
- No real provider adapter / webhook / real HTTP server / real LLM / filesystem mutation / container / memory query engine / dependency.

### Previous Batch Snapshot: App Spike Coverage Review

Batch name: `App Spike Coverage Review`

Status: `complete`

Evidence:

- Full regression: `913 passed`.
- artifact-review trace regression: pass.
- `python -m isotope_kernel.demo --scenario external-snapshot-review --trace`: pass.
- approval-tool-runner trace regression: pass.
- Coverage review doc: `docs/app-spike-coverage-review.md`.
- First app spike `artifact-review` covers artifact / content policy / provenance / ResourceRef / replay / checkpoint.
- Second app spike `external-snapshot-review` covers ImportedSnapshot / external observations / conflict diagnostics / native state priority / replay / checkpoint.
- Next recommended path was `Kernel Gap Review Refresh`; this has now been completed.
- No real provider adapter / webhook / real HTTP server / real LLM / filesystem mutation / memory query engine / dependency.

### Previous Batch Snapshot: External Snapshot Review Closure Review

Batch name: `External Snapshot Review Closure Review`

Status: `complete`

Evidence:

- Full regression: `913 passed`.
- `python -m isotope_kernel.demo --scenario external-snapshot-review`: pass.
- `python -m isotope_kernel.demo --scenario external-snapshot-review --json`: pass.
- `python -m isotope_kernel.demo --scenario external-snapshot-review --trace`: pass.
- artifact-review trace regression: pass.
- Closure review doc: `docs/external-snapshot-review-closure-review.md`.
- Scenario covers deterministic `ImportedSnapshot` payloads, canonical `snapshot.imported`, `RunState.external_observations`, conflict diagnostics, native state priority, replay, and checkpoint.
- HTTP `/external-ingestion` remains `not_enabled`.
- JSON / trace do not expose raw external content or artifact full content.
- No real provider adapter / webhook / real HTTP server / real LLM / filesystem mutation / memory query engine / dependency.

### Previous Batch Snapshot: External Snapshot Review Green Slice

Batch name: `External Snapshot Review Green Slice`

Status: `complete`

Evidence:

- Targeted green: `15 passed`.
- Full regression: `913 passed`.
- `python -m isotope_kernel.demo --scenario external-snapshot-review`: pass.
- `python -m isotope_kernel.demo --scenario external-snapshot-review --json`: pass.
- `python -m isotope_kernel.demo --scenario external-snapshot-review --trace`: pass.
- artifact-review trace regression: pass.
- Scenario covers deterministic `snapshot.imported`, `RunState.external_observations`, conflict diagnostics, native state priority, replay, and checkpoint.
- HTTP `/external-ingestion` remains `not_enabled`.
- No real provider adapter / webhook / real HTTP server / real LLM / filesystem mutation / memory query engine / dependency.

### Previous Batch Snapshot: Second App Spike Selection

Batch name: `Second App Spike Selection`

Status: `complete`

Evidence:

- Full regression: `898 passed`.
- artifact-review demo plain / JSON / trace: pass.
- approval-tool-runner trace: pass.
- Recommended candidate: `external snapshot review`.
- Reason: it covers `ImportedSnapshot`, `RunState.external_observations`, conflict diagnostics, native state priority, replay, and checkpoint, which were not app-pressure-tested by `approval-tool-runner` or `artifact-review`.
- Not selected now: `approval-gated workspace task` because it overlaps `approval-tool-runner` and combines too many surfaces; `worker handoff task` because it risks multi-agent product drift before real concurrency exists; `memory boundary review` because it risks reopening memory query/storage/promotion.
- No code / tests changed.
- No real provider adapter / webhook / real HTTP server / real LLM / filesystem mutation / memory query engine / dependency.

### Previous Batch Snapshot: Artifact Review Flow Closure Review

Batch name: `Artifact Review Flow Closure Review`

Status: `complete`

Evidence:

- Closure review doc: `docs/artifact-review-flow-closure-review.md`.
- Full regression: `898 passed`.
- artifact-review demo plain / JSON / trace: pass.
- approval-tool-runner trace: pass.
- Source artifact setup uses `InProcessServer.create_source_artifact(...)`, not private `server._append(...)`.
- Review provenance uses `InProcessServer.get_artifact_record(...)`, not demo/client raw event scanning for source basis metadata.
- Flow still covers action chain, policy / grants, artifact summary / structured `ResourceRef` / provenance, controlled content retrieval policy, replay, checkpoint, and disabled HTTP full-content route.
- HTTP full-content route remains `not_enabled`.
- No product artifact review facade / real filesystem upload / binary streaming / real HTTP server / real LLM / provider adapter / memory query engine / container / git worktree / process spawn / dependency.
- Remaining friction is optional polish: explicit controlled retrieval parameters, deterministic review content, and no product artifact review facade.

### Previous Batch Snapshot: Artifact Review Provenance Helper Package

Batch name: `Artifact Review Provenance Helper Package`

Status: `complete`

Evidence:

- Red targeted result: `6 failed, 5 passed`; failures were expected because `get_artifact_record(...)` did not exist and `artifact-review` still scanned raw events for source basis metadata.
- Targeted green result: `11 passed`.
- Full regression: `898 passed`.
- artifact-review demo plain / JSON / trace: pass.
- Helper behavior: accepts structured `ResourceRef` only; returns artifact id / type / summary / ref / provenance / source `artifact.created` basis event metadata; does not return full content; does not append events.
- `artifact-review` demo no longer scans raw events to find the source artifact `artifact.created` basis event.
- HTTP full-content route remains `not_enabled`.
- No product artifact review facade / real filesystem upload / binary streaming / real HTTP server / real LLM / provider adapter / memory query engine / container / git worktree / process spawn / dependency.

### Previous Batch Snapshot: Source Artifact Helper Closure Review

Batch name: `Source Artifact Helper Closure Review`

Status: `complete`

Evidence:

- Full regression: `892 passed`.
- artifact-review demo plain / JSON / trace: pass.
- Helper behavior: validates request, uses existing compiler / policy / executor path, appends canonical action + artifact events, returns summary / structured `ResourceRef` / provenance, and does not append `run.completed`.
- `artifact-review` demo no longer uses private `server._append(...)` source setup glue.
- HTTP full-content route remains `not_enabled`.
- No real filesystem upload / binary streaming / real HTTP server / real LLM / provider adapter / memory query engine / container / git worktree / process spawn / dependency.
- Coverage note: malformed input, provenance, no full content, no `run.completed`, replay / checkpoint, and HTTP route disabled are covered. Helper-specific policy modified / denied tests are not present because this helper exposes no requested capability knobs; generic policy tests cover modified / denied decisions.

### Previous Batch Snapshot: Source Artifact Setup Helper

Batch name: `Source Artifact Setup Helper`

Status: `complete`

Evidence:

- Red targeted result: `9 failed, 11 passed`; failures were expected because `create_source_artifact(...)` did not exist and `artifact-review` still used private `_append(...)` setup glue.
- Targeted green result: `20 passed`.
- Full regression: `892 passed`.
- v0.1 demo plain / JSON: pass.
- v0.2 demo plain / JSON: pass.
- approval-tool-runner demo plain / JSON: pass.
- artifact-review demo plain / JSON / trace: pass.
- Added `InProcessServer.create_source_artifact(...)` and updated `artifact-review` demo.

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

## 10. Completed Batch Log

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

## 11. Maintenance

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
