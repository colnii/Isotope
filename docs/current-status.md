# Isotope Current Status

本文是当前仓库的状态入口。后续 agent 开始新任务前应先读这里，再决定是否需要查阅更细的 spec / architecture / implementation plan。

## Repo Status

- `isotope` 是独立的 kernel-first agent runtime 项目。
- 当前代码已经从 `x-agent` staging snapshot 迁移到 `/home/lumber/Github/isotope`。
- `x-agent` 不是 Isotope 的 canonical repo；后续 Isotope 实现不应回到 `x-agent` 扩展。

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

## Tests

当前验证命令：

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel -q
```

当前预期结果：

```text
60 passed
```

Import boundary check:

```bash
rg -n '(^|\s)(from|import) x_agent\b' src/isotope_kernel tests/isotope_kernel || true
```

当前预期：无输出。

## Deferred

以下能力明确 deferred，不能在没有 design/doc patch 和 red tests 前直接实现：

- real LLM
- memory write
- external ingestion / `ImportedSnapshot`
- checkpoint
- SSE
- multi-agent concurrency
- real HTTP API

## Forbidden

当前禁止：

- import `x_agent.*`
- 复制 `x-agent` assessment pipeline
- 把 v0 implementation shape 当成永久 protocol

## Suggested Next Step

下一步建议优先做：

- checkpoint design doc only
- artifact persistence hardening

不要直接进入 real LLM / memory / ingestion。
