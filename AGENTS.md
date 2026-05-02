# AGENTS

## Repo Boundary

- `/home/lumber/Github/isotope` is the dedicated Isotope repo.
- `x-agent` is not the canonical repo for Isotope.
- Do not import `x_agent.*`.
- Do not modify `/home/lumber/Github/x-agent` unless the user explicitly asks.
- Keep source under `src/isotope_kernel/` and tests under `tests/isotope_kernel/`.

## Workflow

- Read [docs/current-status.md](docs/current-status.md) before starting a new Isotope task.
- Follow TDD for implementation work: write red tests first, keep them uncommitted, then implement the smallest green slice and commit after verification.
- For docs-only tasks, do not modify `src/`, `tests/`, `.github/`, or `pyproject.toml`.
- After behavior changes, sync `README.md`, `AGENTS.md`, and affected docs/status files in the same task.
- Keep detailed status, deferred capability lists, and design boundaries in `docs/`; keep README and AGENTS short.
- Verify `/home/lumber/Github/x-agent` stays untouched on every scoped Isotope task.
- Do not change tags or publish GitHub Releases unless explicitly requested.

## Current Phase

- `v0.1-demo` and `v0.2-demo` developer demo tags exist; baseline is `765 passed`.
- Track D: Demo / Docs Polish is effectively complete / closed for now.
- Current Track A design doc: [docs/http-api-minimal-surface-v0.2.md](docs/http-api-minimal-surface-v0.2.md).
- Track A has in-process `HttpApiApp` / `create_http_app(...)`, request validation / no-side-effect error boundary, response contract, demo smoke, duplicate-submit idempotency boundary, route inventory, and deferred route contract; it is effectively complete / closed for now and is not a real listening HTTP server.
- Current Track C design doc: [docs/artifact-content-read-policy-v0.2.md](docs/artifact-content-read-policy-v0.2.md).
- Track C: Artifact Content Read Policy is effectively complete / closed for now: retrieval requires structured `ResourceRef`, grants, caller context, and purpose; HTTP full-content route has an explicit enablement guard but still returns `501 not_enabled`.
- Track E: Approval Pause / Resume Boundary is effectively complete / closed for now. Approval resolution plus run-state / HTTP read-model green slices are complete; UI / auth / notification / scheduler / complex DSL remain deferred.
- v0.2 demo readiness is documented in [docs/demo/v0.2-demo-readiness.md](docs/demo/v0.2-demo-readiness.md).
- v0.2 demo scenario is implemented and documented in [docs/demo/v0.2-demo-scenario.md](docs/demo/v0.2-demo-scenario.md): `--scenario v0.2` visibly exercises Track A / C / E without real HTTP server, network listener, memory storage/query, or HTTP full-content route.
- v0.2 developer demo acceptance is documented in [docs/demo/v0.2-demo-acceptance.md](docs/demo/v0.2-demo-acceptance.md); `v0.2-demo` is already tagged, but no GitHub Release has been published.
- Post-tag delta is documented in [docs/post-v0.2-tag-delta.md](docs/post-v0.2-tag-delta.md): current `main` is ahead of `v0.2-demo` with Track F external ingestion boundary work; do not move the tag or create `v0.2.1-demo` unless explicitly requested.
- Track F: External Ingestion is effectively complete / closed for now at boundary / read-model / checkpoint scope: `ingestion.py`, `ImportedSnapshot`, and `snapshot.imported` projection into checkpointable `RunState.external_observations`; provider adapters, webhooks, and public ingestion API remain deferred.
- v0.2 cycle closure is documented in [docs/v0.2-cycle-closure-review.md](docs/v0.2-cycle-closure-review.md). Default next mode is cleanup / docs organization / external review, not more runtime implementation.
- Kernel Gap Review is documented in [docs/kernel-gap-review-v0.2.md](docs/kernel-gap-review-v0.2.md). Default next design target is Agent / worker lifecycle, then Workspace substrate; do not jump straight to real HTTP server, real LLM, memory query/promotion, provider adapter, or domain packs.
- Docs migration planning is documented in [docs/docs-migration-plan.md](docs/docs-migration-plan.md). Phase 1 is closed / paused after `docs/release/` and `docs/demo/` migrations; do not move more docs files unless a task explicitly asks for migration execution.
- Real server boundary design only if Track A is explicitly reopened; artifact content HTTP route implementation only if Track C is explicitly reopened.
- Optional docs polish can continue later, but it should not block v0.2 implementation.

## Common Verification

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

## Docs Entrypoints

- Current status: [docs/current-status.md](docs/current-status.md)
- Demo walkthrough: [docs/demo/demo-walkthrough-v0.1.md](docs/demo/demo-walkthrough-v0.1.md)
- Demo architecture: [docs/demo/demo-architecture-v0.1.md](docs/demo/demo-architecture-v0.1.md)
- v0.1 demo acceptance: [docs/demo/v0.1-demo-acceptance.md](docs/demo/v0.1-demo-acceptance.md)
- v0.2 demo acceptance: [docs/demo/v0.2-demo-acceptance.md](docs/demo/v0.2-demo-acceptance.md)
- v0.2 roadmap: [docs/v0.2-roadmap.md](docs/v0.2-roadmap.md)
- External ingestion boundary: [docs/external-ingestion-boundary-v0.2.md](docs/external-ingestion-boundary-v0.2.md)
- Post v0.2 tag delta: [docs/post-v0.2-tag-delta.md](docs/post-v0.2-tag-delta.md)
- v0.2 cycle closure review: [docs/v0.2-cycle-closure-review.md](docs/v0.2-cycle-closure-review.md)
- Kernel gap review: [docs/kernel-gap-review-v0.2.md](docs/kernel-gap-review-v0.2.md)
- Docs migration plan: [docs/docs-migration-plan.md](docs/docs-migration-plan.md)
- v0.2 demo readiness: [docs/demo/v0.2-demo-readiness.md](docs/demo/v0.2-demo-readiness.md)
- v0.2 demo scenario: [docs/demo/v0.2-demo-scenario.md](docs/demo/v0.2-demo-scenario.md)
- v0.2 next-track selection: [docs/v0.2-next-track-selection.md](docs/v0.2-next-track-selection.md)
- v0.2 mid-cycle review: [docs/v0.2-mid-cycle-review.md](docs/v0.2-mid-cycle-review.md)
- Approval pause / resume boundary: [docs/approval-pause-resume-boundary-v0.2.md](docs/approval-pause-resume-boundary-v0.2.md)
- Docs inventory: [docs/docs-inventory.md](docs/docs-inventory.md)
- Artifact content read policy: [docs/artifact-content-read-policy-v0.2.md](docs/artifact-content-read-policy-v0.2.md)
- HTTP API minimal surface: [docs/http-api-minimal-surface-v0.2.md](docs/http-api-minimal-surface-v0.2.md)
