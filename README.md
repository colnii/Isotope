# Isotope

Isotope 是一个独立的 kernel-first agent runtime 项目，用来验证 canonical event log、policy-gated execution、artifact provenance、projector replay 和 checkpoint-assisted rebuild 等内核边界。

当前状态：`v0.1-demo` 和 `v0.2-demo` developer demo tags 已存在；当前本地 baseline 是 `974 passed`。Track A: HTTP API Minimal Surface、Track C: Artifact Content Read Policy、Track E: Approval Pause / Resume Boundary 和 Track F: External Ingestion 都已 effectively complete / closed for now；Agent / Worker lifecycle、Workspace substrate、Workspace Resource Lifecycle、Retry / Cancel / Supersede、approval-gated tool runner usability spike、approval lookup helper、workspace binding helper、submit action helper、artifact review flow、demo trace mode、source artifact setup helper、artifact provenance helper、external snapshot review second app spike 和 Policy Profile / Action Registry Versioning first slice 已 complete / closed for now；artifact-review first app spike 和 external-snapshot-review second app spike 均已 closed for now。GitHub Release 未发布，详细状态见 [docs/current-status.md](docs/current-status.md)。

`main` 当前 ahead of `v0.2-demo`，主要增量是 Track F external ingestion boundary、Agent / Worker lifecycle first slice、Workspace substrate first slice 和 Retry / Cancel / Supersede stabilization slice；delta 记录见 [docs/post-v0.2-tag-delta.md](docs/post-v0.2-tag-delta.md)。暂不移动 `v0.2-demo` tag，也不发布 GitHub Release。

当前 v0.2 implementation cycle 已建议暂停，进入 cleanup / docs organization / external review mode；Kernel Gap Review 后已新增 Agent / Worker lifecycle、Workspace substrate、Workspace Resource Lifecycle 和 Retry / Cancel / Supersede boundary，且当前 kernel boundary slices 均已 complete / closed for now。

后续 rolling batch mode 由 [docs/agent-task-queue.md](docs/agent-task-queue.md) 管理；默认 session timebox 是 45-60 分钟，agent 每轮应先读 queue，不要自行进入未列出的新 Track 或为了凑时间 invent work。Retry / Cancel / Supersede Runtime Integration helper slice 已 green；当前建议下一步是 closure review，而不是直接实现 scheduler、process kill、real concurrency、plugin marketplace、policy DSL 或 real integration。

## Quick Start

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/python -m pytest tests/isotope_kernel -q
.venv/bin/python -m isotope_kernel.demo
.venv/bin/python -m isotope_kernel.demo --json
.venv/bin/python -m isotope_kernel.demo --scenario v0.2
.venv/bin/python -m isotope_kernel.demo --scenario v0.2 --trace
.venv/bin/python -m isotope_kernel.demo --scenario v0.2 --json
.venv/bin/python -m isotope_kernel.demo --scenario approval-tool-runner
.venv/bin/python -m isotope_kernel.demo --scenario approval-tool-runner --trace
.venv/bin/python -m isotope_kernel.demo --scenario approval-tool-runner --json
.venv/bin/python -m isotope_kernel.demo --scenario artifact-review
.venv/bin/python -m isotope_kernel.demo --scenario artifact-review --trace
.venv/bin/python -m isotope_kernel.demo --scenario artifact-review --json
.venv/bin/python -m isotope_kernel.demo --scenario external-snapshot-review
.venv/bin/python -m isotope_kernel.demo --scenario external-snapshot-review --trace
.venv/bin/python -m isotope_kernel.demo --scenario external-snapshot-review --json
```

## What Works

- Deterministic v0.1 demo entrypoint: `python -m isotope_kernel.demo`.
- Explicit v0.2 demo scenario: `python -m isotope_kernel.demo --scenario v0.2`, covering the in-process HTTP facade, approval pause / resume, controlled artifact content policy, checkpoint, and memory `boundary_only` status.
- Approval-gated tool runner usability spike: `python -m isotope_kernel.demo --scenario approval-tool-runner`, covering approval pause / resume, workspace binding read model, artifact / `ResourceRef` handoff, replay, and checkpoint without real HTTP server, real LLM, provider adapter, or filesystem mutation; approval lookup/read helper, workspace binding helper, and `submit_action(...)` now remove the event-scan, manual `workspace.bound`, and raw `submit_tool_request(...)` demo glue.
- Artifact review flow usability spike: `python -m isotope_kernel.demo --scenario artifact-review`, covering artifact summary / `ResourceRef`, controlled retrieval policy, reviewer action chain, review artifact handoff, replay, and checkpoint without real HTTP server, real LLM, provider adapter, semantic retrieval / ranking, or filesystem mutation; HTTP full-content route remains `not_enabled`. `InProcessServer.create_source_artifact(...)` removes private `_append(...)` source setup glue, and `InProcessServer.get_artifact_record(...)` removes source artifact basis-event scan glue from the demo.
- External snapshot review usability spike: `python -m isotope_kernel.demo --scenario external-snapshot-review`, covering `snapshot.imported`, `RunState.external_observations`, conflict diagnostics, native state priority, replay, and checkpoint without real provider adapter, webhook, real HTTP server, real LLM, filesystem mutation, or memory query engine; HTTP `/external-ingestion` remains `not_enabled`. This second app spike is closed for now.
- Demo trace mode: `--trace` is available for `v0.2`, `approval-tool-runner`, `artifact-review`, and `external-snapshot-review` to print human-readable runtime steps; default plain output and `--json` remain compatible, and trace does not expose artifact full content.
- Session / run creation through the in-process kernel path.
- `ActionCompiler -> PolicyEngine -> Executor` action chain with `PolicyDecision.grants` enforcement.
- Artifact creation with execution provenance and structured refs.
- Controlled artifact content retrieval boundary through structured `ResourceRef`, explicit grants, caller context, and purpose; HTTP full-content route remains deferred / not enabled.
- Canonical event log, `RunProjector` read model, event replay, and checkpoint-assisted rebuild.
- Memory boundary/read-model/checkpoint contracts with `memory_status: boundary_only`.
- Minimal in-process `HttpApiApp` / `create_http_app(...)` boundary for session/run/input/state/events/artifact summary, with request validation, response contract, idempotency, route inventory, and deferred route contract tests.
- Minimal approval resolution / read model boundary: approved resumes through existing executor path with original `PolicyDecision.grants`; denied does not execute; pending / approved / denied approval state is replayable and checkpointable.
- External ingestion boundary: `ImportedSnapshot` can be accepted through canonical `snapshot.imported` into checkpointable `RunState.external_observations` without overriding native state; conflicts are explicit, provider adapters and HTTP ingestion remain not enabled.
- Agent / Worker lifecycle first slice: `RunState.agents` / `RunState.workers`, delegation policy gate, worker lifecycle projection, worker action grants boundary, and checkpoint-assisted rebuild.
- Workspace substrate first slice: `RunState.workspaces`, canonical `workspace.bound`, grants-bound `shared_ro` binding, replay, and checkpoint support.
- Workspace resource lifecycle first slice: `workspace.lease_created`, `workspace.released`, and `workspace.artifact_captured` projection / validation in `RunState.workspaces`, with replay and checkpoint support, while keeping no real filesystem / container / git worktree / remote executor; this slice is closed for now.
- Retry / Cancel / Supersede stabilization slice: action lifecycle read models for retries, cancellations, and supersessions with basis linkage hardening, replay, and checkpoint support.
- Policy Profile / Action Registry Versioning first slice: `ActionTypeRegistry.registry_id` / `registry_version`、`ActionProposal` / `action.proposed` registry basis、`PolicyEngine.policy_profile_id` / `policy_version`、`PolicyDecision` / `action.decided` policy basis，以及 projected action summaries 的 basis metadata；不包含 plugin marketplace、remote registry loading、policy DSL 或 migration framework。
- Editable install smoke and GitHub Actions smoke CI.

## What Does Not Work Yet

- Real LLM integration.
- Real listening HTTP server / hosted API.
- UI.
- Real durable memory storage or query engine.
- Real provider adapters, external callbacks / webhooks, and external ingestion HTTP API.
- Plugin system or dynamic tool loading.
- Production release packaging.
- Real worker concurrency / process spawning / remote worker runtime.
- Container / git worktree / remote executor workspace substrate.

## Docs

- Current status: [docs/current-status.md](docs/current-status.md)
- Agent task queue: [docs/agent-task-queue.md](docs/agent-task-queue.md)
- Demo walkthrough: [docs/demo/demo-walkthrough-v0.1.md](docs/demo/demo-walkthrough-v0.1.md)
- Demo architecture: [docs/demo/demo-architecture-v0.1.md](docs/demo/demo-architecture-v0.1.md)
- v0.1 demo acceptance: [docs/demo/v0.1-demo-acceptance.md](docs/demo/v0.1-demo-acceptance.md)
- v0.2 demo acceptance: [docs/demo/v0.2-demo-acceptance.md](docs/demo/v0.2-demo-acceptance.md)
- v0.2 roadmap: [docs/v0.2-roadmap.md](docs/v0.2-roadmap.md)
- Track F external ingestion boundary: [docs/external-ingestion-boundary-v0.2.md](docs/external-ingestion-boundary-v0.2.md)
- Post v0.2 tag delta: [docs/post-v0.2-tag-delta.md](docs/post-v0.2-tag-delta.md)
- v0.2 cycle closure review: [docs/v0.2-cycle-closure-review.md](docs/v0.2-cycle-closure-review.md)
- Kernel gap review: [docs/kernel-gap-review-v0.2.md](docs/kernel-gap-review-v0.2.md)
- Kernel gap refresh: [docs/kernel-gap-review-refresh-v0.2.md](docs/kernel-gap-review-refresh-v0.2.md)
- Agent / Worker lifecycle boundary: [docs/agent-worker-lifecycle-boundary-v0.2.md](docs/agent-worker-lifecycle-boundary-v0.2.md)
- Workspace substrate boundary: [docs/workspace-substrate-boundary-v0.2.md](docs/workspace-substrate-boundary-v0.2.md)
- Workspace resource lifecycle boundary: [docs/workspace-resource-lifecycle-boundary-v0.2.md](docs/workspace-resource-lifecycle-boundary-v0.2.md)
- Workspace resource lifecycle closure review: [docs/workspace-resource-lifecycle-closure-review.md](docs/workspace-resource-lifecycle-closure-review.md)
- Policy profile / action registry versioning boundary: [docs/policy-profile-action-registry-versioning-boundary-v0.2.md](docs/policy-profile-action-registry-versioning-boundary-v0.2.md)
- Policy registry version basis closure review: [docs/policy-registry-version-basis-closure-review.md](docs/policy-registry-version-basis-closure-review.md)
- Workspace binding helper boundary: [docs/workspace-binding-helper-boundary-v0.2.md](docs/workspace-binding-helper-boundary-v0.2.md)
- Retry / Cancel / Supersede boundary: [docs/retry-cancel-supersede-boundary-v0.2.md](docs/retry-cancel-supersede-boundary-v0.2.md)
- Retry / Cancel / Supersede runtime integration boundary: [docs/retry-cancel-supersede-runtime-integration-boundary-v0.2.md](docs/retry-cancel-supersede-runtime-integration-boundary-v0.2.md)
- Usability pressure test plan: [docs/usability-pressure-test-plan-v0.2.md](docs/usability-pressure-test-plan-v0.2.md)
- Usability friction round 1 review: [docs/usability-friction-round-1-review.md](docs/usability-friction-round-1-review.md)
- First app spike readiness: [docs/first-app-spike-readiness.md](docs/first-app-spike-readiness.md)
- Artifact review flow friction review: [docs/artifact-review-flow-friction-review.md](docs/artifact-review-flow-friction-review.md)
- Artifact review flow closure review: [docs/artifact-review-flow-closure-review.md](docs/artifact-review-flow-closure-review.md)
- Second app spike selection: [docs/second-app-spike-selection.md](docs/second-app-spike-selection.md)
- External snapshot review closure review: [docs/external-snapshot-review-closure-review.md](docs/external-snapshot-review-closure-review.md)
- App spike coverage review: [docs/app-spike-coverage-review.md](docs/app-spike-coverage-review.md)
- Source artifact setup helper boundary: [docs/source-artifact-setup-helper-boundary-v0.2.md](docs/source-artifact-setup-helper-boundary-v0.2.md)
- Source artifact helper closure review: [docs/source-artifact-helper-closure-review.md](docs/source-artifact-helper-closure-review.md)
- Artifact review provenance helper boundary: [docs/artifact-review-provenance-helper-boundary-v0.2.md](docs/artifact-review-provenance-helper-boundary-v0.2.md)
- Approval tool runner friction review: [docs/approval-tool-runner-friction-review.md](docs/approval-tool-runner-friction-review.md)
- Submit action helper boundary: [docs/submit-action-helper-boundary-v0.2.md](docs/submit-action-helper-boundary-v0.2.md)
- Docs migration plan: [docs/docs-migration-plan.md](docs/docs-migration-plan.md)
- v0.2 demo readiness: [docs/demo/v0.2-demo-readiness.md](docs/demo/v0.2-demo-readiness.md)
- v0.2 demo scenario: [docs/demo/v0.2-demo-scenario.md](docs/demo/v0.2-demo-scenario.md)
- v0.2 next-track selection: [docs/v0.2-next-track-selection.md](docs/v0.2-next-track-selection.md)
- v0.2 mid-cycle review: [docs/v0.2-mid-cycle-review.md](docs/v0.2-mid-cycle-review.md)
- Approval pause / resume boundary: [docs/approval-pause-resume-boundary-v0.2.md](docs/approval-pause-resume-boundary-v0.2.md)
- Docs inventory: [docs/docs-inventory.md](docs/docs-inventory.md)
- Artifact content read policy: [docs/artifact-content-read-policy-v0.2.md](docs/artifact-content-read-policy-v0.2.md)
- HTTP API minimal surface: [docs/http-api-minimal-surface-v0.2.md](docs/http-api-minimal-surface-v0.2.md)

## CI

GitHub Actions runs a minimal smoke workflow on push / pull request: editable install with `.[test]`, full `tests/isotope_kernel`, and demo plain / JSON smoke. It is not a release, coverage, lint matrix, or real integration pipeline.
