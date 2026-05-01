# Isotope

Isotope 是一个独立的 kernel-first agent runtime 项目，用来验证 canonical event log、policy-gated execution、artifact provenance、projector replay 和 checkpoint-assisted rebuild 等内核边界。

当前状态：`v0.1-demo` developer demo 已完成并打 tag；当前本地 baseline 是 `619 passed`。Track A: HTTP API Minimal Surface 已有 in-process boundary、request validation、response contract 和 demo smoke，详细状态见 [docs/current-status.md](docs/current-status.md)。

## Quick Start

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/python -m pytest tests/isotope_kernel -q
.venv/bin/python -m isotope_kernel.demo
.venv/bin/python -m isotope_kernel.demo --json
```

## What Works

- Deterministic v0.1 demo entrypoint: `python -m isotope_kernel.demo`.
- Session / run creation through the in-process kernel path.
- `ActionCompiler -> PolicyEngine -> Executor` action chain with `PolicyDecision.grants` enforcement.
- Artifact creation with execution provenance and structured refs.
- Canonical event log, `RunProjector` read model, event replay, and checkpoint-assisted rebuild.
- Memory boundary/read-model/checkpoint contracts with `memory_status: boundary_only`.
- Minimal in-process `HttpApiApp` / `create_http_app(...)` boundary for session/run/input/state/events/artifact summary, with request validation and response contract tests.
- Editable install smoke and GitHub Actions smoke CI.

## What Does Not Work Yet

- Real LLM integration.
- Real listening HTTP server / hosted API.
- UI.
- Real durable memory storage or query engine.
- External ingestion / `ImportedSnapshot`.
- Plugin system or dynamic tool loading.
- Production release packaging.

## Docs

- Current status: [docs/current-status.md](docs/current-status.md)
- Demo walkthrough: [docs/demo-walkthrough-v0.1.md](docs/demo-walkthrough-v0.1.md)
- Demo architecture: [docs/demo-architecture-v0.1.md](docs/demo-architecture-v0.1.md)
- v0.1 demo acceptance: [docs/v0.1-demo-acceptance.md](docs/v0.1-demo-acceptance.md)
- v0.2 roadmap: [docs/v0.2-roadmap.md](docs/v0.2-roadmap.md)
- HTTP API minimal surface: [docs/http-api-minimal-surface-v0.2.md](docs/http-api-minimal-surface-v0.2.md)

## CI

GitHub Actions runs a minimal smoke workflow on push / pull request: editable install with `.[test]`, full `tests/isotope_kernel`, and demo plain / JSON smoke. It is not a release, coverage, lint matrix, or real integration pipeline.
