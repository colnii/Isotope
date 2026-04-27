# AGENTS

## Repo Boundary

- `isotope` 是独立的 kernel-first agent runtime 项目。
- 当前代码来自 `x-agent` staging snapshot，但 `x-agent` 不是 canonical repo。
- 不得 import `x_agent.*`，也不要复制 `src/x_agent/`、assessment pipeline、sample grading assets、runs 或 benchmark artifacts。

## Development Rules

- 每次开始新任务前，先读 `docs/current-status.md`。
- 继续使用 TDD：先写 red tests，确认失败，再写最小实现。
- 使用 `src layout`：源码在 `src/isotope_kernel/`，测试在 `tests/isotope_kernel/`。
- 不要把 v0 implementation shape 误写成永久协议。
- 保持 hard contracts 优先：action chain、policy grants、append-only canonical event log、projector-only replay、RunState rebuild、artifact provenance、ResourceRef。
- 任何 deferred 能力必须先写 design/doc patch 和 red tests，不能直接实现。

## Current Slice

当前 slice 只覆盖：

- file event log
- action chain
- `PolicyDecision.grants`
- artifact provenance
- structured `ResourceRef`
- projector replay
- `RunState` rebuild
- in-process server facade
- event envelope validation
- `ResourceRef` validation
- event ordering preservation
- duplicate event protection
- malformed event log fail-fast
- approval requested event boundary
- pending approval projection
- action lifecycle ordering validation
- illegal lifecycle transition fail-fast
- file-backed artifact persistence
- fresh `ArtifactStore` metadata/content read
- malformed artifact file fail-fast

## Deferred

以下能力仍然 deferred，不要在没有新计划和 red tests 前实现：

- real LLM
- memory write
- external ingestion
- checkpoint
- SSE
- multi-agent concurrency
- real HTTP API

## Verification

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel -q
```
