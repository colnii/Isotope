# Isotope Current Status

本文是当前仓库的状态入口。后续 agent 开始新任务前应先读这里，再决定是否需要查阅更细的 spec / architecture / implementation plan。

## Repo Status

- `isotope` 是独立的 kernel-first agent runtime 项目。
- 当前代码已经从 `x-agent` staging snapshot 迁移到 `/home/lumber/Github/isotope`。
- `x-agent` 不是 Isotope 的 canonical repo；后续 Isotope 实现不应回到 `x-agent` 扩展。
- 最新 implementation commit：`3d0e4a78e749b307d1333f86c2fdd269cf168fe0`。

## Implemented Slice

当前已实现并由 tests 覆盖的最小 slice：

- file event log
- action chain
- `PolicyDecision.grants` enforcement
- artifact provenance
- structured `ResourceRef`
- projector replay
- `RunState` rebuild
- in-process server facade
- denied / failed / pending boundary
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
- `Executor.execute(...)` appends `action.failed` with the same execution id after started execution fails
- failed execution does not append `artifact.created` / `action.completed` / `run.completed`
- server facade does not duplicate executor-owned failure events
- checkpoint ownership design note 已落文档
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

## Tests

当前验证命令：

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel -q
```

当前预期结果：

```text
218 passed
```

Import boundary check:

```bash
rg -n '(^|\s)(from|import) x_agent\b' src/isotope_kernel tests/isotope_kernel || true
```

当前预期：无输出。

## Deferred

以下能力明确 deferred，不能在没有 design/doc patch 和 red tests 前直接实现：

- real LLM
- `ActionTypeRegistry`
- memory write
- external ingestion / `ImportedSnapshot`
- checkpoint-assisted recovery
- Projector checkpoint integration
- CheckpointService
- checkpoint migration / version negotiation / integrity hash
- SSE
- auth
- multi-agent concurrency
- real HTTP API

## Forbidden

当前禁止：

- import `x_agent.*`
- 复制 `x-agent` assessment pipeline
- 把 v0 implementation shape 当成永久 protocol

## Suggested Next Step

下一步建议优先做：

- checkpoint-assisted projector rebuild design patch
- checkpoint-assisted projector rebuild red tests

不要直接进入 real LLM / memory / ingestion。
