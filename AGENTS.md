# AGENTS

## Repo Boundary

- `/home/lumber/Github/isotope` is the dedicated Isotope repo.
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
- Keep detailed status, deferred capability lists, and design boundaries in `docs/`; keep README and AGENTS short.
- Verify `/home/lumber/Github/x-agent` stays untouched on every scoped Isotope task.
- Do not change tags or publish GitHub Releases unless explicitly requested.

## Current Phase

- `v0.1-demo` and `v0.2-demo` developer demo tags exist; baseline is `913 passed`.
- Track D: Demo / Docs Polish is effectively complete / closed for now.
- Current Track A design doc: [docs/http-api-minimal-surface-v0.2.md](docs/http-api-minimal-surface-v0.2.md).
- Track A has in-process `HttpApiApp` / `create_http_app(...)`, request validation / no-side-effect error boundary, response contract, demo smoke, duplicate-submit idempotency boundary, route inventory, and deferred route contract; it is effectively complete / closed for now and is not a real listening HTTP server.
- Current Track C design doc: [docs/artifact-content-read-policy-v0.2.md](docs/artifact-content-read-policy-v0.2.md).
- Track C: Artifact Content Read Policy is effectively complete / closed for now: retrieval requires structured `ResourceRef`, grants, caller context, and purpose; HTTP full-content route has an explicit enablement guard but still returns `501 not_enabled`.
- Track E: Approval Pause / Resume Boundary is effectively complete / closed for now. Approval resolution plus run-state / HTTP read-model green slices are complete; UI / auth / notification / scheduler / complex DSL remain deferred.
- v0.2 demo readiness is documented in [docs/demo/v0.2-demo-readiness.md](docs/demo/v0.2-demo-readiness.md).
- v0.2 demo scenario is implemented and documented in [docs/demo/v0.2-demo-scenario.md](docs/demo/v0.2-demo-scenario.md): `--scenario v0.2` visibly exercises Track A / C / E without real HTTP server, network listener, memory storage/query, or HTTP full-content route.
- Demo trace mode is implemented for `--scenario v0.2 --trace`, `--scenario approval-tool-runner --trace`, `--scenario artifact-review --trace`, and `--scenario external-snapshot-review --trace`; it is human-readable only, keeps `--json` compatible, and does not expose artifact full content.
- v0.2 developer demo acceptance is documented in [docs/demo/v0.2-demo-acceptance.md](docs/demo/v0.2-demo-acceptance.md); `v0.2-demo` is already tagged, but no GitHub Release has been published.
- Post-tag delta is documented in [docs/post-v0.2-tag-delta.md](docs/post-v0.2-tag-delta.md): current `main` is ahead of `v0.2-demo` with Track F external ingestion boundary work, Agent / Worker lifecycle first slice, Workspace substrate first slice, and Retry / Cancel / Supersede stabilization slice; do not move the tag or create `v0.2.1-demo` unless explicitly requested.
- Track F: External Ingestion is effectively complete / closed for now at boundary / read-model / checkpoint scope: `ingestion.py`, `ImportedSnapshot`, and `snapshot.imported` projection into checkpointable `RunState.external_observations`; provider adapters, webhooks, and public ingestion API remain deferred.
- v0.2 cycle closure is documented in [docs/v0.2-cycle-closure-review.md](docs/v0.2-cycle-closure-review.md). Default next mode is cleanup / docs organization / external review, not more runtime implementation.
- Kernel Gap Review is documented in [docs/kernel-gap-review-v0.2.md](docs/kernel-gap-review-v0.2.md). Agent / Worker lifecycle boundary is now documented in [docs/agent-worker-lifecycle-boundary-v0.2.md](docs/agent-worker-lifecycle-boundary-v0.2.md), and the first slice is complete: `RunState.agents` / `RunState.workers`, delegation policy gate, checkpoint support, no real concurrency. Workspace substrate first slice is complete and documented in [docs/workspace-substrate-boundary-v0.2.md](docs/workspace-substrate-boundary-v0.2.md): `RunState.workspaces`, canonical `workspace.bound`, grants-bound `shared_ro` binding, replay, and checkpoint support; no container / git worktree / remote executor. Retry / Cancel / Supersede stabilization slice is complete and documented in [docs/retry-cancel-supersede-boundary-v0.2.md](docs/retry-cancel-supersede-boundary-v0.2.md): action lifecycle read models, basis linkage hardening, replay, and checkpoint support; no scheduler / process kill / real concurrency. Do not jump straight to real HTTP server, real LLM, memory query/promotion, provider adapter, or domain packs.
- Docs migration planning is documented in [docs/docs-migration-plan.md](docs/docs-migration-plan.md). Phase 1 is closed / paused after `docs/release/` and `docs/demo/` migrations; do not move more docs files unless a task explicitly asks for migration execution.
- Mainline batch automation is documented in [docs/agent-task-queue.md](docs/agent-task-queue.md). It uses rolling batch mode with a 45-60 min session timebox. Approval lookup, workspace binding, submit action helper, artifact review flow, source artifact setup helper, artifact provenance helper, and external snapshot review slices are complete; artifact-review first app spike, external-snapshot-review second app spike, app spike coverage review, Kernel Gap Review Refresh, and Workspace Resource Lifecycle Boundary are closed for now; next suggested batch is Workspace Resource Lifecycle Red Tests.
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

rg -n '(^|\s)(from|import) x_agent\b' src/isotope_kernel tests/isotope_kernel || true

git -C /home/lumber/Github/x-agent status --short \
  src/x_agent src/isotope_kernel tests/isotope_kernel docs/isotope

git diff -- src tests .github pyproject.toml

git status --short
```

## Docs Entrypoints

- Current status: [docs/current-status.md](docs/current-status.md)
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
- Retry / Cancel / Supersede boundary: [docs/retry-cancel-supersede-boundary-v0.2.md](docs/retry-cancel-supersede-boundary-v0.2.md)
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
