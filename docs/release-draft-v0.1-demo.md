# Release Draft: v0.1-demo

## Title

v0.1-demo: Isotope Kernel Developer Demo

## Summary

This is the first developer-demo checkpoint for Isotope. It demonstrates a minimal kernel execution loop with canonical events, policy-gated execution, artifact provenance, replay, checkpoint-assisted rebuild, and memory boundary read models.

This is not a production runtime.

## Tag

- Tag: `v0.1-demo`
- Commit: `b3d4e328e74378bec2fb524deb85233df5a5d4eb`

This document is a GitHub Release draft only. No GitHub Release has been published from it.

## What Works

- Minimal in-process demo entrypoint:
  - `python -m isotope_kernel.demo`
  - `python -m isotope_kernel.demo --json`
- Session / run creation.
- Deterministic action path.
- Action compiler, policy engine, executor.
- `PolicyDecision.grants` enforcement.
- Artifact creation with execution provenance.
- Canonical event log.
- `RunState` projection.
- Event-log replay.
- Checkpoint-assisted rebuild.
- Memory boundary status: `boundary_only`.
- Editable install smoke.
- GitHub Actions smoke CI.

## Verification

- Local tests: `568 passed`
- Demo plain text: `run_status: completed`, `checkpoint_ok: true`, `memory_status: boundary_only`
- Demo JSON: valid JSON, `run_status: completed`
- CI: GitHub Actions smoke passed
- No `x_agent.*` imports

## Install And Run

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/python -m pytest tests/isotope_kernel -q
.venv/bin/python -m isotope_kernel.demo
.venv/bin/python -m isotope_kernel.demo --json
```

## Explicit Non-Goals

- Real LLM integration.
- HTTP server.
- UI.
- Real durable memory storage.
- Real memory query engine.
- External ingestion.
- Plugin system.
- Multi-user auth.
- Production release packaging.

## Notes

The memory subsystem in this demo is boundary-only. It validates structured memory records, canonical memory events, supersession, replay, and checkpoint behavior, but it does not implement real memory storage or query.

The tag is the acceptance anchor. `main` may contain later docs/status updates after the tag; those updates do not change the demo runtime represented by `v0.1-demo`.
