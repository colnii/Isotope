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

- `v0.1-demo` developer demo is accepted; baseline is `682 passed`.
- Track D: Demo / Docs Polish is effectively complete / closed for now.
- Current Track A design doc: [docs/http-api-minimal-surface-v0.2.md](docs/http-api-minimal-surface-v0.2.md).
- Track A has in-process `HttpApiApp` / `create_http_app(...)`, request validation / no-side-effect error boundary, response contract, demo smoke, duplicate-submit idempotency boundary, route inventory, and deferred route contract; it is effectively complete / closed for now and is not a real listening HTTP server.
- Current Track C design doc: [docs/artifact-content-read-policy-v0.2.md](docs/artifact-content-read-policy-v0.2.md).
- Track C: Artifact Content Read Policy is effectively complete / closed for now: retrieval requires structured `ResourceRef`, grants, caller context, and purpose; HTTP full-content route has an explicit enablement guard but still returns `501 not_enabled`.
- Current Track E boundary doc: [docs/approval-pause-resume-boundary-v0.2.md](docs/approval-pause-resume-boundary-v0.2.md). Next default work is approval resolution / HTTP approval red tests.
- Real server boundary design only if Track A is explicitly reopened; artifact content HTTP route implementation only if Track C is explicitly reopened.
- Optional docs polish can continue later, but it should not block v0.2 implementation.

## Common Verification

```bash
cd /home/lumber/Github/isotope

PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel -q

PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo

PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --json

rg -n '(^|\s)(from|import) x_agent\b' src/isotope_kernel tests/isotope_kernel || true

git -C /home/lumber/Github/x-agent status --short \
  src/x_agent src/isotope_kernel tests/isotope_kernel docs/isotope

git diff -- src tests .github pyproject.toml

git status --short
```

## Docs Entrypoints

- Current status: [docs/current-status.md](docs/current-status.md)
- Demo walkthrough: [docs/demo-walkthrough-v0.1.md](docs/demo-walkthrough-v0.1.md)
- Demo architecture: [docs/demo-architecture-v0.1.md](docs/demo-architecture-v0.1.md)
- v0.1 demo acceptance: [docs/v0.1-demo-acceptance.md](docs/v0.1-demo-acceptance.md)
- v0.2 roadmap: [docs/v0.2-roadmap.md](docs/v0.2-roadmap.md)
- v0.2 next-track selection: [docs/v0.2-next-track-selection.md](docs/v0.2-next-track-selection.md)
- v0.2 mid-cycle review: [docs/v0.2-mid-cycle-review.md](docs/v0.2-mid-cycle-review.md)
- Approval pause / resume boundary: [docs/approval-pause-resume-boundary-v0.2.md](docs/approval-pause-resume-boundary-v0.2.md)
- Docs inventory: [docs/docs-inventory.md](docs/docs-inventory.md)
- Artifact content read policy: [docs/artifact-content-read-policy-v0.2.md](docs/artifact-content-read-policy-v0.2.md)
- HTTP API minimal surface: [docs/http-api-minimal-surface-v0.2.md](docs/http-api-minimal-surface-v0.2.md)
