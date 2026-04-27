# Isotope

Isotope 是一个独立的 kernel-first agent runtime 项目。当前仓库用于沉淀最小 kernel slice：file event log、action chain、policy grants、artifact provenance、structured ResourceRef、projector replay、RunState rebuild、event/ref validation、event store hardening、approval boundary、action lifecycle hardening、artifact persistence、retrieval authorization、workspace binding、policy validation、action compiler validation、server facade input validation、success path executor event ownership、failure path executor event ownership 和 run completion invariants。

当前代码来自 `x-agent` 中的 Isotope staging snapshot。`x-agent` 不是 Isotope 的 canonical repo，后续 Isotope 的设计和实现应以本仓库为准。

## Current Status

当前状态入口是 [docs/current-status.md](docs/current-status.md)。

Checkpoint ownership 边界见 [docs/checkpoint-ownership-v0.1.md](docs/checkpoint-ownership-v0.1.md)；checkpoint 仍是 deferred capability，不是第二事实源。

当前测试命令：

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel -q
```

当前预期：`172 passed`。

当前 deferred 边界：real LLM、`ActionTypeRegistry`、memory write、external ingestion / `ImportedSnapshot`、checkpoint implementation、SSE、auth、multi-agent concurrency、real HTTP API。

## Current Slice

当前 slice 只验证最小闭环：

- compact intent 编译为 `ActionProposal` 后才能进入 policy。
- executor 只能使用 `PolicyDecision.grants`。
- file event log 使用 JSONL append-only。
- artifact 带 execution provenance。
- artifact identity 使用 structured `ResourceRef`。
- projector 只从 canonical events 重建 `RunState`。
- in-process server facade 只暴露当前 slice 的同步调用入口，不包含 real HTTP。
- event envelope 和 `ResourceRef` 有当前 v0 slice 的最小输入合法性保护。
- file event log 保持 append order replay、同 run 内 duplicate event protection、malformed JSON fail-fast。
- pending approval 会写入 `approval.requested` 并由 projector 从 event log 投影。
- projector 对 action lifecycle ordering 做最小 validation，非法转换 fail fast。
- artifact 使用 run-scoped file-backed persistence，fresh `ArtifactStore` 可读 metadata/content，malformed artifact file fail fast。
- retrieval 只支持 summary by structured `ResourceRef`，必须有 summary grant，且不会读取 artifact content。
- workspace binding 只接受 `PolicyDecision.grants` 中的 `shared_ro`，Executor 不回退到 requested capabilities。
- policy 会校验 proposal 输入和 decision outcome/grants 最小形状，denied decision 不授予有效能力。
- `ActionCompiler` 会校验 malformed `intent` / `runtime_context`、runtime identity、`action`、`tool`、`requested_tools`、`workspace_mode` 和 `budget.seconds`，valid minimal intent 仍编译为 canonical `ActionProposal`。
- `InProcessServer` / server facade 会校验 client request，invalid request 走受控 `ValueError`，不 append action lifecycle events，也不创建 artifact；`get_run_state` 仍允许 fresh process 从已有 event log rebuild。
- success path 的 `action.started`、`artifact.created`、`action.completed` 由 `Executor.execute(...)` append；artifact side effect 发生在 `action.started` 之后，server facade 不重复写这些 executor-owned events，只保留 `run.completed` 等 run-level 收口。
- failure path 的 `action.failed` 由 `Executor.execute(...)` append，并沿用同一个 execution id；failed execution 不写 `artifact.created` / `action.completed` / `run.completed`，server facade 不重复写 failure events。
- `RunProjector` 会校验 `run.completed` invariants：必须已有 completed execution，不能覆盖 running / failed / pending approval 状态，且 run completed 后不能再出现 action/artifact lifecycle events；projector 仍只消费 canonical events。

以下能力仍然 deferred：real LLM、`ActionTypeRegistry`、memory write、external ingestion、checkpoint implementation、SSE、auth、multi-agent concurrency、real HTTP API。

## Verify

```bash
python -m venv .venv
.venv/bin/python -m pip install -U pip pytest
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel -q
```
