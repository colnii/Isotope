# Isotope

Isotope 是一个独立的 kernel-first agent runtime 项目，用来验证 canonical event log、policy-gated execution、artifact provenance、projector replay 和 checkpoint-assisted rebuild 等内核边界。

当前状态：`v0.1-demo` 和 `v0.2-demo` developer demo tags 已存在；当前本地 baseline 是 `765 passed`。Track A: HTTP API Minimal Surface、Track C: Artifact Content Read Policy、Track E: Approval Pause / Resume Boundary 和 Track F: External Ingestion 都已 effectively complete / closed for now；GitHub Release 未发布，详细状态见 [docs/current-status.md](docs/current-status.md)。

`main` 当前 ahead of `v0.2-demo`，主要增量是 Track F external ingestion boundary；delta 记录见 [docs/post-v0.2-tag-delta.md](docs/post-v0.2-tag-delta.md)。暂不移动 `v0.2-demo` tag，也不发布 GitHub Release。

当前 v0.2 implementation cycle 已建议暂停，进入 cleanup / docs organization / external review mode；见 [docs/v0.2-cycle-closure-review.md](docs/v0.2-cycle-closure-review.md)。

## Quick Start

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/python -m pytest tests/isotope_kernel -q
.venv/bin/python -m isotope_kernel.demo
.venv/bin/python -m isotope_kernel.demo --json
.venv/bin/python -m isotope_kernel.demo --scenario v0.2
.venv/bin/python -m isotope_kernel.demo --scenario v0.2 --json
```

## What Works

- Deterministic v0.1 demo entrypoint: `python -m isotope_kernel.demo`.
- Explicit v0.2 demo scenario: `python -m isotope_kernel.demo --scenario v0.2`, covering the in-process HTTP facade, approval pause / resume, controlled artifact content policy, checkpoint, and memory `boundary_only` status.
- Session / run creation through the in-process kernel path.
- `ActionCompiler -> PolicyEngine -> Executor` action chain with `PolicyDecision.grants` enforcement.
- Artifact creation with execution provenance and structured refs.
- Controlled artifact content retrieval boundary through structured `ResourceRef`, explicit grants, caller context, and purpose; HTTP full-content route remains deferred / not enabled.
- Canonical event log, `RunProjector` read model, event replay, and checkpoint-assisted rebuild.
- Memory boundary/read-model/checkpoint contracts with `memory_status: boundary_only`.
- Minimal in-process `HttpApiApp` / `create_http_app(...)` boundary for session/run/input/state/events/artifact summary, with request validation, response contract, idempotency, route inventory, and deferred route contract tests.
- Minimal approval resolution / read model boundary: approved resumes through existing executor path with original `PolicyDecision.grants`; denied does not execute; pending / approved / denied approval state is replayable and checkpointable.
- External ingestion boundary: `ImportedSnapshot` can be accepted through canonical `snapshot.imported` into checkpointable `RunState.external_observations` without overriding native state; conflicts are explicit, provider adapters and HTTP ingestion remain not enabled.
- Editable install smoke and GitHub Actions smoke CI.

## What Does Not Work Yet

- Real LLM integration.
- Real listening HTTP server / hosted API.
- UI.
- Real durable memory storage or query engine.
- Real provider adapters, external callbacks / webhooks, and external ingestion HTTP API.
- Plugin system or dynamic tool loading.
- Production release packaging.

## Docs

- Current status: [docs/current-status.md](docs/current-status.md)
- Demo walkthrough: [docs/demo/demo-walkthrough-v0.1.md](docs/demo/demo-walkthrough-v0.1.md)
- Demo architecture: [docs/demo/demo-architecture-v0.1.md](docs/demo/demo-architecture-v0.1.md)
- v0.1 demo acceptance: [docs/v0.1-demo-acceptance.md](docs/v0.1-demo-acceptance.md)
- v0.2 demo acceptance: [docs/v0.2-demo-acceptance.md](docs/v0.2-demo-acceptance.md)
- v0.2 roadmap: [docs/v0.2-roadmap.md](docs/v0.2-roadmap.md)
- Track F external ingestion boundary: [docs/external-ingestion-boundary-v0.2.md](docs/external-ingestion-boundary-v0.2.md)
- Post v0.2 tag delta: [docs/post-v0.2-tag-delta.md](docs/post-v0.2-tag-delta.md)
- v0.2 cycle closure review: [docs/v0.2-cycle-closure-review.md](docs/v0.2-cycle-closure-review.md)
- Docs migration plan: [docs/docs-migration-plan.md](docs/docs-migration-plan.md)
- v0.2 demo readiness: [docs/v0.2-demo-readiness.md](docs/v0.2-demo-readiness.md)
- v0.2 demo scenario: [docs/v0.2-demo-scenario.md](docs/v0.2-demo-scenario.md)
- v0.2 next-track selection: [docs/v0.2-next-track-selection.md](docs/v0.2-next-track-selection.md)
- v0.2 mid-cycle review: [docs/v0.2-mid-cycle-review.md](docs/v0.2-mid-cycle-review.md)
- Approval pause / resume boundary: [docs/approval-pause-resume-boundary-v0.2.md](docs/approval-pause-resume-boundary-v0.2.md)
- Docs inventory: [docs/docs-inventory.md](docs/docs-inventory.md)
- Artifact content read policy: [docs/artifact-content-read-policy-v0.2.md](docs/artifact-content-read-policy-v0.2.md)
- HTTP API minimal surface: [docs/http-api-minimal-surface-v0.2.md](docs/http-api-minimal-surface-v0.2.md)

## CI

GitHub Actions runs a minimal smoke workflow on push / pull request: editable install with `.[test]`, full `tests/isotope_kernel`, and demo plain / JSON smoke. It is not a release, coverage, lint matrix, or real integration pipeline.
