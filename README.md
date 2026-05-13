# Isotope

Isotope 是一个独立的 agent runtime 项目；当前采用 kernel-first 开发顺序，先验证 canonical event log、policy-gated execution、artifact provenance、projector replay 和 checkpoint-assisted rebuild 等底座能力。Kernel-first 不等于 kernel-only：后续 Isotope 仍面向 LLM 自动规划、Agent loop、worker、调度和产品层体验。

当前状态：`v0.1-demo` 和 `v0.2-demo` developer demo tags 已存在；当前 branch-local baseline 是 `1084 passed`，pre-branch mainline baseline 是 `1064 passed`。Track A: HTTP API Minimal Surface、Track C: Artifact Content Read Policy、Track E: Approval Pause / Resume Boundary 和 Track F: External Ingestion 都已 effectively complete / closed for now；Agent / Worker lifecycle、Delegation Decision Read Model、Workspace substrate、Workspace Resource Lifecycle helper、Retry / Cancel / Supersede、approval-gated tool runner usability spike、approval lookup helper、workspace binding helper、submit action helper、artifact review flow、demo trace mode、source artifact setup helper、artifact provenance helper、Derived Artifact Basis Refs、Restart Write Helper Run Context、Restart Approval Resolution Context、Restart Create Run Session Context、external snapshot review second app spike、Policy Profile / Action Registry Versioning first slice、Policy Constructor Surface、Event Schema Registry / Compatibility first slice、Tool Protocol first slice、Tool Invocation Runtime Wiring、Session / Run Lifecycle first slice 和 Error Taxonomy first slice 已 complete / closed for now；artifact-review first app spike、external-snapshot-review second app spike、agent-loop-friction branch-local spike、agent-loop-planner-friction branch-local spike、agent-loop-planner-matrix branch-local spike、planner runner API boundary review、planner matrix fixture expansion review、agent-loop-planner-restart-pause branch-local spike 和 agent-loop branch closure review 均已 closed for now。GitHub Release 未发布，详细状态见 [docs/current-status.md](docs/current-status.md)。

`main` 当前 ahead of `v0.2-demo`，主要增量是 Track F external ingestion boundary、Agent / Worker lifecycle first slice、Workspace substrate first slice 和 Retry / Cancel / Supersede stabilization slice；delta 记录见 [docs/post-v0.2-tag-delta.md](docs/post-v0.2-tag-delta.md)。暂不移动 `v0.2-demo` tag，也不发布 GitHub Release。

当前 v0.2 implementation cycle 已建议暂停，进入 cleanup / docs organization / external review mode；Kernel Gap Review 后已新增 Agent / Worker lifecycle、Workspace substrate、Workspace Resource Lifecycle 和 Retry / Cancel / Supersede boundary，且当前 kernel boundary slices 均已 complete / closed for now。

后续 rolling batch mode 由 [docs/agent-task-queue.md](docs/agent-task-queue.md) 管理；默认 session timebox 是 45-60 分钟，agent 每轮应先读 queue，不要自行进入未列出的新 Track 或为了凑时间 invent work。External Review Package 已刷新，见 [docs/external-review-package-v0.2.md](docs/external-review-package-v0.2.md)；post external review checkpoint 见 [docs/post-external-review-checkpoint.md](docs/post-external-review-checkpoint.md)。当前主线进入 idle / conservative maintenance mode，见 [docs/mainline-idle-checkpoint.md](docs/mainline-idle-checkpoint.md) 和 [docs/kernel-mainline-maintenance-mode.md](docs/kernel-mainline-maintenance-mode.md)：默认短暂停止 kernel expansion，让 application-layer prototype / aggressive branch 先制造真实 friction。文档公开/内部边界见 [docs/public-internal-docs-boundary.md](docs/public-internal-docs-boundary.md)。

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
.venv/bin/python -m isotope_kernel.demo --scenario agent-loop-friction
.venv/bin/python -m isotope_kernel.demo --scenario agent-loop-friction --trace
.venv/bin/python -m isotope_kernel.demo --scenario agent-loop-friction --json
.venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-friction
.venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-friction --trace
.venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-friction --json
.venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-matrix
.venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-matrix --trace
.venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-matrix --json
.venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-restart-pause
.venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-restart-pause --trace
.venv/bin/python -m isotope_kernel.demo --scenario agent-loop-planner-restart-pause --json
```

## What Works

- Deterministic v0.1 demo entrypoint: `python -m isotope_kernel.demo`.
- Explicit v0.2 demo scenario: `python -m isotope_kernel.demo --scenario v0.2`, covering the in-process HTTP facade, approval pause / resume, controlled artifact content policy, checkpoint, and memory `boundary_only` status.
- Approval-gated tool runner usability spike: `python -m isotope_kernel.demo --scenario approval-tool-runner`, covering approval pause / resume, workspace binding read model, artifact / `ResourceRef` handoff, replay, and checkpoint without real HTTP server, real LLM, provider adapter, or filesystem mutation; approval lookup/read helper, workspace binding helper, and `submit_action(...)` now remove the event-scan, manual `workspace.bound`, and raw `submit_tool_request(...)` demo glue.
- Artifact review flow usability spike: `python -m isotope_kernel.demo --scenario artifact-review`, covering artifact summary / `ResourceRef`, controlled retrieval policy, reviewer action chain, review artifact handoff, replay, and checkpoint without real HTTP server, real LLM, provider adapter, semantic retrieval / ranking, or filesystem mutation; HTTP full-content route remains `not_enabled`. `InProcessServer.create_source_artifact(...)` removes private `_append(...)` source setup glue, and `InProcessServer.get_artifact_record(...)` removes source artifact basis-event scan glue from the demo.
- External snapshot review usability spike: `python -m isotope_kernel.demo --scenario external-snapshot-review`, covering `snapshot.imported`, `RunState.external_observations`, conflict diagnostics, native state priority, replay, and checkpoint without real provider adapter, webhook, real HTTP server, real LLM, filesystem mutation, or memory query engine; `InProcessServer.import_external_snapshot(...)` removes private `_append(...)` snapshot setup glue while HTTP `/external-ingestion` remains `not_enabled`. This second app spike is closed for now.
- Agent loop friction spike: `python -m isotope_kernel.demo --scenario agent-loop-friction`, covering a deterministic app-layer loop composition across source artifact setup, worker handoff, approval pause / resume, workspace binding, replay, checkpoint, and a structured `kernel_friction` report; current result is `kernel_friction=[]` and `private_append_required=false`. This is not a real LLM loop, scheduler, provider adapter, real worker runtime, or product multi-agent UX; see [docs/agent-loop-friction-review.md](docs/agent-loop-friction-review.md).
- Agent loop planner adapter friction spike: `python -m isotope_kernel.demo --scenario agent-loop-planner-friction`, covering a deterministic fixture-backed planner adapter that emits symbolic decisions before the same app-layer runner executes source artifact setup, worker handoff, approval pause / resume, workspace binding, replay, checkpoint, and a structured `kernel_friction` report; current result is `kernel_friction=[]` and `private_append_required=false`. This is still not a real LLM loop, scheduler, provider adapter, real worker runtime, or product multi-agent UX; see [docs/agent-loop-planner-adapter-friction-review.md](docs/agent-loop-planner-adapter-friction-review.md).
- Agent loop planner matrix friction spike: `python -m isotope_kernel.demo --scenario agent-loop-planner-matrix`, covering happy path, blocked deferred capability, and malformed symbolic action fail-closed fixtures; current result is `kernel_friction=[]`, while deferred real LLM planning is classified as app/product-deferred, not a kernel request. This is still not a real LLM loop, scheduler, provider adapter, real worker runtime, or product multi-agent UX; see [docs/agent-loop-planner-matrix-friction-review.md](docs/agent-loop-planner-matrix-friction-review.md).
- Planner Runner API Boundary Review: [docs/planner-runner-api-boundary-review.md](docs/planner-runner-api-boundary-review.md) keeps the planner runner demo-local for now. No `agent_loop` / `orchestration` / `planner_runner` kernel module is introduced until a second non-demo caller or concrete app-layer friction justifies extraction.
- Planner Matrix Fixture Expansion Review: [docs/planner-matrix-fixture-expansion-review.md](docs/planner-matrix-fixture-expansion-review.md) says not to expand by default; if one more runnable fixture is needed, choose `restart after planner pause`.
- Agent loop planner restart-pause spike: `python -m isotope_kernel.demo --scenario agent-loop-planner-restart-pause`, covering the realistic path where the loop pauses for approval, the server restarts, and the approval can still be resumed from event-backed state. Current result is `kernel_friction=[]` and `private_append_required=false`; see [docs/planner-restart-pause-fixture-review.md](docs/planner-restart-pause-fixture-review.md).
- Agent loop branch closure review: [docs/agent-loop-branch-closure-review.md](docs/agent-loop-branch-closure-review.md) says to stop adding artificial Agent loop cases and decide whether to merge, PR, or keep the branch for later app/reviewer feedback.
- Scope clarification: Isotope is not limited to kernel work; current Agent loop spikes only prove that the foundation is ready for later real LLM planning / product-layer pressure, not that the full Agent loop product is complete.
- Demo trace mode: `--trace` is available for `v0.2`, `approval-tool-runner`, `artifact-review`, `external-snapshot-review`, `agent-loop-friction`, `agent-loop-planner-friction`, `agent-loop-planner-matrix`, and `agent-loop-planner-restart-pause` to print human-readable runtime steps; default plain output and `--json` remain compatible, and trace does not expose artifact full content.
- Session / run creation through the in-process kernel path.
- Minimal event-backed Session / Run Lifecycle slice: `session.created`, `get_session_state(...)`, restarted `create_run(...)` for event-backed sessions, run lifecycle checkpoint fields, and terminal ordinary-input no-side-effect rejection.
- Error Taxonomy first slice: minimal `KernelError(ValueError)` compatibility layer for helper / HTTP mapping, covering terminal run, unknown run/session, invalid request, `not_enabled`, and worker handoff helper rejection paths without product error UX or public SDK.
- `ActionCompiler -> PolicyEngine -> Executor` action chain with `PolicyDecision.grants` enforcement.
- Artifact creation with execution provenance and structured refs.
- Controlled artifact content retrieval boundary through structured `ResourceRef`, explicit grants, caller context, and purpose; HTTP full-content route remains deferred / not enabled.
- Canonical event log, `RunProjector` read model, event replay, and checkpoint-assisted rebuild.
- Memory boundary/read-model/checkpoint contracts with `memory_status: boundary_only`.
- Minimal in-process `HttpApiApp` / `create_http_app(...)` boundary for session/run/input/state/events/artifact summary, with request validation, response contract, idempotency, route inventory, and deferred route contract tests.
- Minimal approval resolution / read model boundary: approved resumes through existing executor path with original `PolicyDecision.grants`; denied does not execute; pending / approved / denied approval state is replayable and checkpointable; restarted `InProcessServer(root, checkpoint_store=...)` can resolve pending approvals through persisted proposal / decision metadata plus a private payload handle, without putting raw tool text in the canonical event log or checkpoint.
- External ingestion boundary: structured `ImportedSnapshot` can be accepted through `InProcessServer.import_external_snapshot(...)`, which appends canonical `snapshot.imported` into checkpointable `RunState.external_observations` without overriding native state; conflicts are explicit, provider adapters and HTTP ingestion remain not enabled.
- Agent / Worker lifecycle first slice: `RunState.agents` / `RunState.workers`, delegation policy gate, worker lifecycle projection, worker action grants boundary, and checkpoint-assisted rebuild.
- Delegation Decision Read Model slice: `RunState.delegations` projects delegation proposal / decision / worker linkage so app shells can audit `outcome`, `reason_codes`, `grants`, and `policy_basis` without raw event scans.
- Workspace substrate first slice: `RunState.workspaces`, canonical `workspace.bound`, grants-bound `shared_ro` binding, replay, and checkpoint support.
- Workspace resource lifecycle helper slice: `InProcessServer.create_workspace_lease(...)`, `capture_workspace_artifact(...)`, and `release_workspace(...)` append existing canonical workspace lifecycle events so app shells do not use private `_append(...)`; still no real filesystem / container / git worktree / remote executor.
- Restart write helper run context slice: restarted `InProcessServer(root, checkpoint_store=...)` can continue selected public write helpers such as `create_source_artifact(...)` and `submit_worker_handoff(...)` on existing non-terminal runs by recovering minimal context from canonical events; terminal runs still fail closed without side effects.
- Retry / Cancel / Supersede stabilization slice: action lifecycle read models for retries, cancellations, and supersessions with basis linkage hardening, replay, and checkpoint support.
- Policy Profile / Action Registry Versioning first slice: `ActionTypeRegistry.registry_id` / `registry_version`、`ActionProposal` / `action.proposed` registry basis、`PolicyEngine.policy_profile_id` / `policy_version`、`PolicyDecision` / `action.decided` policy basis，以及 projected action summaries 的 basis metadata；`InProcessServer(..., registry=..., policy_profile_id=..., policy_version=...)` wires explicit policy metadata through the same shared registry path；不包含 arbitrary `PolicyEngine` injection、plugin marketplace、remote registry loading、policy DSL 或 migration framework。
- Event Schema Registry / Compatibility first slice: static in-process `EventSchemaRegistry` registers known canonical event types, separates `event_envelope_version` from payload `event_schema_version`, keeps legacy/current missing schema metadata explicit for known events, and makes unknown event types / unsupported schema versions fail closed; this slice is closed for now and does not add JSON Schema, protobuf, Avro, migration framework, plugin registry, or remote registry.
- Tool Protocol and runtime wiring first slices: minimal `ToolInvocation` / `ToolResult` / `ToolError` models, complete artifact event provenance, structured `action.failed` error shape, and optional deterministic in-process `tool_handlers` so `InProcessServer` / `Executor` can pass a grants-capped `ToolInvocation` to registered handlers; this still does not implement plugin marketplace, remote tools, sandboxed process, streaming output, or public SDK.
- Editable install smoke and GitHub Actions smoke CI.

## What Does Not Work Yet

- Real LLM integration.
- Real listening HTTP server / hosted API.
- UI.
- Real durable memory storage or query engine.
- Real provider adapters, external callbacks / webhooks, and external ingestion HTTP API.
- Plugin system or dynamic tool loading.
- Public tool SDK, remote tools, streaming tool output, or sandboxed tool process.
- Production release packaging.
- Real worker concurrency / process spawning / remote worker runtime.
- Container / git worktree / remote executor workspace substrate.

## Docs

- Current status: [docs/current-status.md](docs/current-status.md)
- Current docs map: [docs/current-docs-map.md](docs/current-docs-map.md)
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
- Retry / Cancel / Supersede runtime closure review: [docs/retry-cancel-supersede-runtime-closure-review.md](docs/retry-cancel-supersede-runtime-closure-review.md)
- Usability pressure test plan: [docs/usability-pressure-test-plan-v0.2.md](docs/usability-pressure-test-plan-v0.2.md)
- Usability friction round 1 review: [docs/usability-friction-round-1-review.md](docs/usability-friction-round-1-review.md)
- First app spike readiness: [docs/first-app-spike-readiness.md](docs/first-app-spike-readiness.md)
- Artifact review flow friction review: [docs/artifact-review-flow-friction-review.md](docs/artifact-review-flow-friction-review.md)
- Artifact review flow closure review: [docs/artifact-review-flow-closure-review.md](docs/artifact-review-flow-closure-review.md)
- Second app spike selection: [docs/second-app-spike-selection.md](docs/second-app-spike-selection.md)
- External snapshot review closure review: [docs/external-snapshot-review-closure-review.md](docs/external-snapshot-review-closure-review.md)
- Agent loop friction review: [docs/agent-loop-friction-review.md](docs/agent-loop-friction-review.md)
- Agent loop planner adapter friction review: [docs/agent-loop-planner-adapter-friction-review.md](docs/agent-loop-planner-adapter-friction-review.md)
- Agent loop planner matrix friction review: [docs/agent-loop-planner-matrix-friction-review.md](docs/agent-loop-planner-matrix-friction-review.md)
- Planner runner API boundary review: [docs/planner-runner-api-boundary-review.md](docs/planner-runner-api-boundary-review.md)
- Planner matrix fixture expansion review: [docs/planner-matrix-fixture-expansion-review.md](docs/planner-matrix-fixture-expansion-review.md)
- Planner restart pause fixture review: [docs/planner-restart-pause-fixture-review.md](docs/planner-restart-pause-fixture-review.md)
- Agent loop branch closure review: [docs/agent-loop-branch-closure-review.md](docs/agent-loop-branch-closure-review.md)
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
- Event schema registry / compatibility boundary: [docs/event-schema-registry-compatibility-boundary-v0.2.md](docs/event-schema-registry-compatibility-boundary-v0.2.md)
- Event schema registry closure review: [docs/event-schema-registry-closure-review.md](docs/event-schema-registry-closure-review.md)
- Tool protocol boundary: [docs/tool-protocol-boundary-v0.2.md](docs/tool-protocol-boundary-v0.2.md)
- Tool protocol closure review: [docs/tool-protocol-closure-review.md](docs/tool-protocol-closure-review.md)
- Tool invocation runtime wiring boundary: [docs/tool-invocation-runtime-wiring-boundary-v0.2.md](docs/tool-invocation-runtime-wiring-boundary-v0.2.md)
- Restart write helper run context boundary: [docs/restart-write-helper-run-context-boundary-v0.2.md](docs/restart-write-helper-run-context-boundary-v0.2.md)
- Worker handoff app spike selection: [docs/worker-handoff-app-spike-selection.md](docs/worker-handoff-app-spike-selection.md)
- Session / run lifecycle boundary: [docs/session-run-lifecycle-boundary-v0.2.md](docs/session-run-lifecycle-boundary-v0.2.md)
- Error taxonomy boundary: [docs/error-taxonomy-boundary-v0.2.md](docs/error-taxonomy-boundary-v0.2.md)
- Error taxonomy closure review: [docs/error-taxonomy-closure-review.md](docs/error-taxonomy-closure-review.md)
- External review package: [docs/external-review-package-v0.2.md](docs/external-review-package-v0.2.md)
- Post external review checkpoint: [docs/post-external-review-checkpoint.md](docs/post-external-review-checkpoint.md)
- Mainline idle checkpoint: [docs/mainline-idle-checkpoint.md](docs/mainline-idle-checkpoint.md)
- Kernel mainline maintenance mode: [docs/kernel-mainline-maintenance-mode.md](docs/kernel-mainline-maintenance-mode.md)
- Public / internal docs boundary: [docs/public-internal-docs-boundary.md](docs/public-internal-docs-boundary.md)
- Concept docs: [docs/concepts/README.md](docs/concepts/README.md)
- Docs inventory: [docs/docs-inventory.md](docs/docs-inventory.md)
- Artifact content read policy: [docs/artifact-content-read-policy-v0.2.md](docs/artifact-content-read-policy-v0.2.md)
- HTTP API minimal surface: [docs/http-api-minimal-surface-v0.2.md](docs/http-api-minimal-surface-v0.2.md)

## CI

GitHub Actions runs a minimal smoke workflow on push / pull request: editable install with `.[test]`, full `tests/isotope_kernel`, and demo plain / JSON smoke. It is not a release, coverage, lint matrix, or real integration pipeline.
