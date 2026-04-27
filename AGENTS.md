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
- 不得直接实现 checkpoint-assisted recovery / Projector checkpoint integration；checkpoint 相关实现必须遵守 `docs/checkpoint-ownership-v0.1.md`，并先写 red tests。

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
- retrieval authorization validation
- summary-only retrieval boundary
- retrieval content-read prevention
- workspace grants validation
- shared_ro-only workspace binding
- executor uses decision workspace grants only
- policy proposal validation
- policy decision outcome validation
- denied decision no-effective-grants validation
- required grants shape validation
- action compiler input validation
- runtime identity validation from runtime context
- valid minimal intent to canonical `ActionProposal`
- server facade input validation
- malformed client input controlled `ValueError`
- invalid server request no action lifecycle event side effects
- invalid server request no artifact side effects
- fresh `RunState` rebuild remains event-log based
- success path executor event ownership
- `Executor.execute(...)` appends `action.started` before artifact side effect
- `Executor.execute(...)` appends `artifact.created` and `action.completed`
- server facade does not duplicate executor-owned success events
- server facade remains responsible for run-level completion such as `run.completed`
- failure path executor event ownership
- `Executor.execute(...)` appends `action.failed` with the same execution id
- failed execution does not append `artifact.created` / `action.completed` / `run.completed`
- server facade does not duplicate executor-owned failure events
- projector / run completion invariant hardening
- `run.completed` requires a completed execution
- `run.completed` cannot override running / failed / pending approval state
- `run.completed` closes later action/artifact lifecycle events
- projector remains canonical-event-only for run completion state
- checkpoint storage boundary
- `FileCheckpointStore` run-scoped opaque blob save/load
- checkpoint required fields: `run_id`, `projector_version`, `basis_event_id`, `state`, `created_at`
- checkpoint `run_id` must match target run
- checkpoint rejects external raw input / provider response / imported snapshot
- missing checkpoint returns `None`
- malformed checkpoint file fail-fast
- checkpoint store does not modify event log
- projector event payload validation hardening
- `PolicyDecision.modified` enters execution lifecycle like `approved`
- malformed projector event payload fail-fast with controlled `ValueError`
- projector validates action decided/started/completed/failed payloads
- projector validates artifact created payload and rejects projected content
- projector validates approval requested payload
- projector remains canonical-event-only and does not read artifact store / executor state / server memory / checkpoint

## Deferred

以下能力仍然 deferred，不要在没有新计划和 red tests 前实现：

- real LLM
- ActionTypeRegistry
- memory write
- external ingestion
- checkpoint-assisted recovery
- Projector checkpoint integration
- CheckpointService
- checkpoint migration / version negotiation / integrity hash
- SSE
- auth
- multi-agent concurrency
- real HTTP API

## Verification

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel -q
```
