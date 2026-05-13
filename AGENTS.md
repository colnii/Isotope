# AGENTS

## Repo Boundary

- `/home/lumber/Github/isotope` is the dedicated Isotope repo.
- Treat `/home/lumber/Github/isotope` as the default working directory for Isotope mainline tasks.
- `x-agent` is not the canonical repo for Isotope.
- Do not import `x_agent.*`.
- Do not modify `/home/lumber/Github/x-agent` unless the user explicitly asks.
- Keep source under `src/isotope_kernel/` and tests under `tests/isotope_kernel/`.

## Workflow

- Read [docs/current-status.md](docs/current-status.md) before starting a new Isotope task.
- For queued mainline work, also read [docs/v0.2-roadmap.md](docs/v0.2-roadmap.md) and [docs/agent-task-queue.md](docs/agent-task-queue.md), then follow Rolling Batch Mode, the Current Batch, and Stop Conditions.
- Follow TDD for implementation work: write red tests first, keep them uncommitted, then implement the smallest green slice and commit after verification.
- For docs-only tasks, do not modify `src/`, `tests/`, `.github/`, or `pyproject.toml`.
- After behavior changes, sync `README.md`, `AGENTS.md`, and affected docs/status files in the same task.
- After any scoped Isotope task that leaves intended file changes, verify, commit, and push to the current upstream branch unless the user explicitly asks to pause or keep changes uncommitted.
- Keep project history linear: prefer fast-forward / rebase workflows, avoid merge commits on `main`, and do not force-push shared branches unless the user explicitly requests it.
- Keep detailed status, deferred capability lists, and design boundaries in `docs/`; keep README and AGENTS short.
- Verify `/home/lumber/Github/x-agent` stays untouched on every scoped Isotope task.
- Do not change tags or publish GitHub Releases unless explicitly requested.

## Current Phase

- `v0.1-demo` and `v0.2-demo` developer demo tags exist; current branch-local baseline on this worktree is `1079 passed` using the main checkout venv; pre-branch mainline baseline was `1064 passed` when using the local `DYLD_LIBRARY_PATH` workaround documented in `/Users/infoxmde/openclaw-ops/state/isotope/local_env_note.md`.
- Track D: Demo / Docs Polish is effectively complete / closed for now.
- Current Track A design doc: [docs/http-api-minimal-surface-v0.2.md](docs/http-api-minimal-surface-v0.2.md).
- Track A has in-process `HttpApiApp` / `create_http_app(...)`, request validation / no-side-effect error boundary, response contract, demo smoke, duplicate-submit idempotency boundary, route inventory, and deferred route contract; it is effectively complete / closed for now and is not a real listening HTTP server.
- Current Track C design doc: [docs/artifact-content-read-policy-v0.2.md](docs/artifact-content-read-policy-v0.2.md).
- Track C: Artifact Content Read Policy is effectively complete / closed for now: retrieval requires structured `ResourceRef`, grants, caller context, and purpose; HTTP full-content route has an explicit enablement guard but still returns `501 not_enabled`.
- Track E: Approval Pause / Resume Boundary is effectively complete / closed for now. Approval resolution plus run-state / HTTP read-model green slices are complete; UI / auth / notification / scheduler / complex DSL remain deferred.
- v0.2 demo readiness is documented in [docs/demo/v0.2-demo-readiness.md](docs/demo/v0.2-demo-readiness.md).
- v0.2 demo scenario is implemented and documented in [docs/demo/v0.2-demo-scenario.md](docs/demo/v0.2-demo-scenario.md): `--scenario v0.2` visibly exercises Track A / C / E without real HTTP server, network listener, memory storage/query, or HTTP full-content route.
- Demo trace mode is implemented for `--scenario v0.2 --trace`, `--scenario approval-tool-runner --trace`, `--scenario artifact-review --trace`, `--scenario external-snapshot-review --trace`, `--scenario agent-loop-friction --trace`, `--scenario agent-loop-planner-friction --trace`, and `--scenario agent-loop-planner-matrix --trace`; it is human-readable only, keeps `--json` compatible, and does not expose artifact full content.
- v0.2 developer demo acceptance is documented in [docs/demo/v0.2-demo-acceptance.md](docs/demo/v0.2-demo-acceptance.md); `v0.2-demo` is already tagged, but no GitHub Release has been published.
- Post-tag delta is documented in [docs/post-v0.2-tag-delta.md](docs/post-v0.2-tag-delta.md): current `main` is ahead of `v0.2-demo` with Track F external ingestion boundary work, Agent / Worker lifecycle first slice, Workspace substrate first slice, and Retry / Cancel / Supersede stabilization slice; do not move the tag or create `v0.2.1-demo` unless explicitly requested.
- Track F: External Ingestion is effectively complete / closed for now at boundary / read-model / checkpoint scope: `ingestion.py`, `ImportedSnapshot`, `InProcessServer.import_external_snapshot(...)`, and `snapshot.imported` projection into checkpointable `RunState.external_observations`; provider adapters, webhooks, and public ingestion API remain deferred.
- v0.2 cycle closure is documented in [docs/v0.2-cycle-closure-review.md](docs/v0.2-cycle-closure-review.md). Default next mode is cleanup / docs organization / external review, not more runtime implementation.
- Kernel Gap Review is documented in [docs/kernel-gap-review-v0.2.md](docs/kernel-gap-review-v0.2.md). Agent / Worker lifecycle boundary is now documented in [docs/agent-worker-lifecycle-boundary-v0.2.md](docs/agent-worker-lifecycle-boundary-v0.2.md), and the first slice is complete: `RunState.agents` / `RunState.workers`, delegation policy gate, checkpoint support, no real concurrency. Delegation Decision Read Model slice is also complete: `RunState.delegations` projects delegation proposal / decision / worker linkage, including denied worker handoff audit, for app-layer audit without raw event scans. Workspace substrate first slice is complete and documented in [docs/workspace-substrate-boundary-v0.2.md](docs/workspace-substrate-boundary-v0.2.md): `RunState.workspaces`, canonical `workspace.bound`, grants-bound `shared_ro` binding, replay, and checkpoint support; no container / git worktree / remote executor. Workspace resource lifecycle helper slice is complete / closed for now and documented in [docs/workspace-resource-lifecycle-boundary-v0.2.md](docs/workspace-resource-lifecycle-boundary-v0.2.md) plus [docs/workspace-resource-lifecycle-closure-review.md](docs/workspace-resource-lifecycle-closure-review.md): `InProcessServer.create_workspace_lease(...)`, `capture_workspace_artifact(...)`, and `release_workspace(...)` append existing canonical `workspace.lease_created`, `workspace.artifact_captured`, and `workspace.released` events so app shells do not use private `_append(...)`; still no real filesystem / container / git worktree / remote executor. Retry / Cancel / Supersede stabilization slice is complete and documented in [docs/retry-cancel-supersede-boundary-v0.2.md](docs/retry-cancel-supersede-boundary-v0.2.md): action lifecycle read models, basis linkage hardening, replay, and checkpoint support; no scheduler / process kill / real concurrency. Do not jump straight to real HTTP server, real LLM, memory query/promotion, provider adapter, or domain packs.
- Derived Artifact Basis Refs slice is complete / closed for now: `InProcessServer.create_source_artifact(...)` accepts optional structured `basis_refs` / `source_refs`, validates them as same-run artifact `ResourceRef` values, stores them in `artifact.created` summary provenance, and projects them through replay / checkpoint / `get_artifact_record(...)` without exposing artifact full content; no real worker runtime, fan-in helper, scheduler, filesystem, container, git worktree, real HTTP, provider, public SDK, tag, or release.
- Restart Write Helper Run Context slice is complete / closed for now: restarted `InProcessServer(root, checkpoint_store=...)` can continue selected public write helpers on existing non-terminal runs by recovering minimal `run.created` / `agent.created` / `thread.created` context from canonical events; post-restart `create_source_artifact(...)` returns the current execution's new artifact ref and preserves structured `basis_refs` / `source_refs`; terminal runs still fail closed with no side effects, and no real worker runtime / scheduler / process supervisor is implemented.
- Restart Approval Resolution Context slice is complete / closed for now: restarted `InProcessServer(root, checkpoint_store=...)` can resolve pending approvals when `approval.requested` carries persisted proposal / decision metadata plus a private payload handle; raw tool text does not enter canonical events / read model / checkpoint, malformed resolution still appends no partial events, and no real HTTP / scheduler / UI / auth / notification / product approval workflow is implemented.
- Restart Create Run Session Context slice is complete / closed for now: restarted `InProcessServer(root, checkpoint_store=...)` can create follow-up runs for event-backed sessions recovered from canonical `session.created` / `run.created` state, so app shells do not need private `_sessions` rebuilds after restart; still no product session workflow, run graph, scheduler, real worker runtime, HTTP, provider, filesystem, container, or git worktree.
- Policy Constructor Surface slice is complete / closed for now: `InProcessServer(..., registry=..., policy_profile_id=..., policy_version=...)` wires explicit policy metadata into the same shared registry path used by `ActionCompiler` / `PolicyEngine` / `Executor`, so `action.decided` and `RunState.actions[*].policy_basis` preserve custom policy basis through replay and checkpoint without replacing `api.policy`; arbitrary `PolicyEngine` injection, policy DSL, remote registry loading, product policy UI, public SDK, real HTTP, and provider adapter remain deferred.
- Docs migration planning is documented in [docs/docs-migration-plan.md](docs/docs-migration-plan.md). Phase 1 is closed / paused after `docs/release/` and `docs/demo/` migrations; do not move more docs files unless a task explicitly asks for migration execution.
- Mainline batch automation is documented in [docs/agent-task-queue.md](docs/agent-task-queue.md). It uses rolling batch mode with a 45-60 min session timebox. Approval lookup, workspace binding, submit action helper, artifact review flow, source artifact setup helper, artifact provenance helper, Derived Artifact Basis Refs, Tool Invocation Runtime Wiring, Restart Write Helper Run Context, Restart Approval Resolution Context, Restart Create Run Session Context, and Policy Constructor Surface are complete; artifact-review first app spike, external-snapshot-review second app spike, agent-loop-friction branch-local spike, agent-loop-planner-friction branch-local spike, agent-loop-planner-matrix branch-local spike, planner runner API boundary review, planner matrix fixture expansion review, app spike coverage review, Kernel Gap Review Refresh, Workspace Resource Lifecycle helper slice, Policy Profile / Action Registry Versioning first slice, Retry / Cancel / Supersede Runtime Integration first slice, Event Schema Registry / Compatibility first slice, External Review Package Refresh, Post External Review Checkpoint, Tool Protocol Boundary docs-only review, Tool Protocol first slice closure, Session / Run Lifecycle first slice, Error Taxonomy Boundary, Error Taxonomy first slice closure, Worker Handoff Error Taxonomy slice, Delegation Decision Read Model slice, and Denied Worker Handoff Audit slice are complete / closed for now; next suggested mode is optional branch-local `Planner Restart Pause Fixture Spike`, application-layer friction intake, or external review feedback intake.
- Kernel mainline maintenance mode is documented in [docs/kernel-mainline-maintenance-mode.md](docs/kernel-mainline-maintenance-mode.md). Mainline is now conservative / stability-first: do not proactively expand kernel features; let application-layer prototype work on the aggressive branch or external review feedback produce concrete friction before reopening kernel batches.
- Mainline idle checkpoint is documented in [docs/mainline-idle-checkpoint.md](docs/mainline-idle-checkpoint.md). Default next action is to wait for app-layer friction / external review feedback, or run periodic verification only.
- Public / internal docs boundary is documented in [docs/public-internal-docs-boundary.md](docs/public-internal-docs-boundary.md). `docs/concepts/` may remain in mainline as concept / application-pressure material, but it is not implementation truth and should not be treated as public product docs without a future audit.
- Real server boundary design only if Track A is explicitly reopened; artifact content HTTP route implementation only if Track C is explicitly reopened.
- Optional docs polish can continue later, but it should not block v0.2 implementation.

## Common Verification

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

rg -n '(^|\s)(from|import) x_agent\b' src/isotope_kernel tests/isotope_kernel || true

git -C /home/lumber/Github/x-agent status --short \
  src/x_agent src/isotope_kernel tests/isotope_kernel docs/isotope

git diff -- src tests .github pyproject.toml

git status --short
```

## Docs Entrypoints

- Current status: [docs/current-status.md](docs/current-status.md)
- Current docs map: [docs/current-docs-map.md](docs/current-docs-map.md)
- Agent task queue: [docs/agent-task-queue.md](docs/agent-task-queue.md)
- Demo walkthrough: [docs/demo/demo-walkthrough-v0.1.md](docs/demo/demo-walkthrough-v0.1.md)
- Demo architecture: [docs/demo/demo-architecture-v0.1.md](docs/demo/demo-architecture-v0.1.md)
- v0.1 demo acceptance: [docs/demo/v0.1-demo-acceptance.md](docs/demo/v0.1-demo-acceptance.md)
- v0.2 demo acceptance: [docs/demo/v0.2-demo-acceptance.md](docs/demo/v0.2-demo-acceptance.md)
- v0.2 roadmap: [docs/v0.2-roadmap.md](docs/v0.2-roadmap.md)
- External ingestion boundary: [docs/external-ingestion-boundary-v0.2.md](docs/external-ingestion-boundary-v0.2.md)
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
- Retry / Cancel / Supersede boundary: [docs/retry-cancel-supersede-boundary-v0.2.md](docs/retry-cancel-supersede-boundary-v0.2.md)
- Retry / Cancel / Supersede runtime integration boundary: [docs/retry-cancel-supersede-runtime-integration-boundary-v0.2.md](docs/retry-cancel-supersede-runtime-integration-boundary-v0.2.md)
- Retry / Cancel / Supersede runtime closure review: [docs/retry-cancel-supersede-runtime-closure-review.md](docs/retry-cancel-supersede-runtime-closure-review.md)
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
- Public / internal docs boundary: [docs/public-internal-docs-boundary.md](docs/public-internal-docs-boundary.md)
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
