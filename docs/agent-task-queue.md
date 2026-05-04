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
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario external-snapshot-review
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario external-snapshot-review --trace
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario external-snapshot-review --json

rg -n '(^|\s)(from|import) x_agent\b' src/isotope_kernel tests/isotope_kernel || true

git -C /home/lumber/Github/x-agent status --short \
  src/x_agent src/isotope_kernel tests/isotope_kernel docs/isotope

git diff -- src tests .github pyproject.toml
git status --short
```

当前 baseline：`974 passed`。

## 6. Current Batch

Batch name: `Event Schema Registry / Compatibility Boundary`

Timebox: `45-60 min`

Status: `complete`

Goal: define the minimal event schema compatibility contract as a docs-only artifact.

Tasks:

1. Create `docs/event-schema-registry-compatibility-boundary-v0.2.md`: complete.
2. Clarify current implicit contract (single envelope version, version rejection, known-event validation, digest binding): complete.
3. Recommend first red tests for future evolution: complete.
4. Keep docs-only; no src/test/pyproject changes.
5. Queue update: complete; next suggested batch set to red tests only.

Evidence:

- Boundary doc: `docs/event-schema-registry-compatibility-boundary-v0.2.md`.
- Documents hard contract: registered event schemas, distinct envelope/schema versions, unknown event fail-closed target, unsupported schema version fail-closed target, append-only compatibility, checkpoint separation, and no migration framework.
- Records current implementation truth: known-event validation exists, but unknown event type fail-closed is a next red-test target, not an already complete guarantee.
- References existing design notes without implementing anything.
- No code changes; `974 passed` baseline unaffected.

## 7. Next Suggested Batch

Batch name: `Event Schema Registry / Compatibility Red Tests`

Status: `ready_red_only`

Possible tasks:

1. Add `tests/isotope_kernel/test_event_schema_registry_boundary.py`.
2. Add `tests/isotope_kernel/test_event_schema_version_compatibility.py`.
3. Cover registered known event schemas, unknown event fail-closed, unsupported `event_schema_version` fail-closed, legacy/current missing-schema compatibility mapping, envelope/schema version separation, checkpoint separation, and controlled validation errors.
4. Keep red phase only; do not implement registry unless a later batch explicitly says green.
5. Keep JSON Schema, protobuf, migration framework, plugin marketplace, remote registry, real integrations, product UI, and event-store semantic changes out of scope.

Alternative if user chooses pause/review:

- `External Review Package Refresh`

Or if deeper kernel work is desired:

- `Session / Run Lifecycle Boundary`


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
