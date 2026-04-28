# Isotope

Isotope 是一个独立的 kernel-first agent runtime 项目。当前仓库用于沉淀最小 kernel slice：file event log、action chain、policy grants、artifact provenance、structured ResourceRef、projector replay、RunState rebuild、event/ref validation、event store hardening、approval boundary、action lifecycle hardening、artifact persistence、retrieval authorization、workspace binding、policy validation、action compiler validation、server facade input validation、success/failure path executor event ownership、run completion invariants、checkpoint storage boundary、projector event payload validation、checkpoint-assisted projector rebuild、projector-owned checkpoint creation、checkpoint state schema validation、projector-owned checkpoint save boundary、checkpoint prefix consistency、checkpoint integrity/hash validation 和 event prefix digest validation。

当前代码来自 `x-agent` 中的 Isotope staging snapshot。`x-agent` 不是 Isotope 的 canonical repo，后续 Isotope 的设计和实现应以本仓库为准。

## Current Status

当前状态入口是 [docs/current-status.md](docs/current-status.md)。

Checkpoint ownership 边界见 [docs/checkpoint-ownership-v0.1.md](docs/checkpoint-ownership-v0.1.md)；checkpoint integrity/hash 边界见 [docs/checkpoint-integrity-v0.1.md](docs/checkpoint-integrity-v0.1.md)；event prefix digest 边界见 [docs/event-prefix-digest-v0.1.md](docs/event-prefix-digest-v0.1.md)；checkpoint retention / compaction 边界见 [docs/checkpoint-retention-compaction-v0.1.md](docs/checkpoint-retention-compaction-v0.1.md)；server-facing checkpoint 边界见 [docs/server-checkpoint-boundary-v0.1.md](docs/server-checkpoint-boundary-v0.1.md)；checkpoint save trigger 边界见 [docs/checkpoint-save-trigger-v0.1.md](docs/checkpoint-save-trigger-v0.1.md)。当前实现了 opaque checkpoint storage、最小 checkpoint-assisted projector rebuild、projector-owned checkpoint creation、checkpoint state schema validation、projector-owned checkpoint save boundary、checkpoint prefix consistency hardening、checkpoint integrity/hash validation、event prefix digest validation 和 latest-only checkpoint storage boundary hardening，checkpoint 仍不是第二事实源。broader retention / compaction 仍 deferred。

当前测试命令：

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel -q
```

当前预期：`333 passed`。

当前 deferred 边界：real LLM、`ActionTypeRegistry`、memory write、external ingestion / `ImportedSnapshot`、public checkpoint API / HTTP endpoint、automatic checkpoint scheduling、CheckpointService、signature / MAC / key management、checkpoint history、checkpoint GC、checkpoint retention policy、old checkpoint fallback、checkpoint inspection API、checkpoint migration / version negotiation、event log compaction、SSE、auth、multi-agent concurrency、real HTTP API。`InProcessServer` read path 已可选使用 checkpoint-assisted rebuild；internal-only manual save trigger 已实现，但 server 仍不接收或解释 checkpoint state。

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
- `FileCheckpointStore` 只做 run-scoped opaque checkpoint blob 存取和最小边界校验，不解释 projected state 业务语义，不修改 event log。
- `RunProjector` 会对 action / artifact / approval event payload 做最小字段校验，malformed payload 受控 `ValueError` fail fast；`modified` decision 和 `approved` 一样允许进入 execution lifecycle，projector 仍不读取 artifact store / executor state / server memory / checkpoint。
- `RunProjector.rebuild_with_checkpoint(...)` 支持最小 checkpoint-assisted rebuild：无 checkpoint 或 version 不兼容时回落完整 replay；checkpoint 可用时从 basis state 继续 replay 后续 canonical events，且仍验证完整 event log，不能隐藏 malformed / lifecycle-invalid events。
- `RunProjector.create_checkpoint(...)` 支持 projector-owned checkpoint creation：checkpoint 由 canonical events 经 `project(...)` 生成，包含最小 projected state，拒绝 empty / malformed / lifecycle-invalid event stream，不写 checkpoint store，创建出的 checkpoint 可交由 `FileCheckpointStore` 保存并用于 assisted rebuild。
- `RunProjector.rebuild_with_checkpoint(...)` 只在 checkpoint projector version 兼容时校验 checkpoint state schema：state 必须包含最小 projected state 字段、run/status/action/artifact shape 合法，artifact entry 不得包含 content；不兼容 version 仍回落 full rebuild，`FileCheckpointStore` 仍不解释 projected state。
- `RunProjector.save_checkpoint(...)` 支持 projector-owned checkpoint save boundary：从 `event_store.list_events(run_id)` 读取 canonical events，经 `create_checkpoint(...)` 生成 checkpoint，再调用 `checkpoint_store.save_checkpoint(...)` 保存；空日志或 invalid event stream fail-fast 且不写 checkpoint，不修改 event log，不读取 artifact store / executor state / server memory。
- `RunProjector.rebuild_with_checkpoint(...)` 会比较 checkpoint state 与 `basis_event_id` 对应的 event-log prefix projection；只有一致时才从 checkpoint 继续 replay，不一致时 fallback full rebuild，且 fallback 仍执行完整 event validation；`FileCheckpointStore` 仍保持 opaque。
- `RunProjector.create_checkpoint(...)` 会生成 checkpoint `integrity`，使用 `sha256` 和 deterministic canonical JSON 计算 `checkpoint_hash`；`rebuild_with_checkpoint(...)` 遇到 hash mismatch 只让 checkpoint 失效并 fallback full rebuild，hash match 后仍执行 state schema validation、prefix consistency validation 和 event/lifecycle validation；legacy checkpoint 无 hash 时继续走现有 validation path，`FileCheckpointStore` 仍只保存 opaque blob。
- `RunProjector.create_checkpoint(...)` 会在 checkpoint `integrity` 中生成最小 event prefix digest metadata：`event_digest_algorithm: "sha256"`、`event_prefix_digest`、`event_digest_basis_event_id`、`event_digest_event_count`；digest 输入使用 deterministic JSON / UTF-8，覆盖 run 内第一条 event 到 `basis_event_id` 的 canonical event representation，event append order 和 prefix payload 改动都会影响 digest；`rebuild_with_checkpoint(...)` 遇到 digest mismatch 会让 checkpoint invalid 并 fallback full rebuild，digest match 后仍执行 state schema validation、prefix consistency validation 和 suffix replay，legacy checkpoint 无 event prefix digest 时继续走兼容路径；`FileCheckpointStore` 仍保持 opaque，`InProcessServer` 没有 digest-specific 行为。
- `InProcessServer.get_run_state(...)` 已可选使用 checkpoint-assisted rebuild：constructor 支持 optional `checkpoint_store`；没有 checkpoint store 时仍走 full event log rebuild，有 checkpoint store 时调用 projector-owned `RunProjector.rebuild_with_checkpoint(...)`；server 不直接解释 checkpoint state，checkpoint missing / invalid / mismatch / incompatible 时 fallback full rebuild，lifecycle-invalid event log 仍 fail-fast。
- `InProcessServer.save_checkpoint_for_run(run_id)` 已实现为 internal-only manual trigger：没有 checkpoint store 时返回 `not_enabled`，有 checkpoint store 时只调用 projector-owned `RunProjector.save_checkpoint(...)`；返回最小 metadata，不返回 checkpoint state，不修改 event log，不读取 artifact content / executor state / server memory；`create_checkpoint(...)` 仍返回 `not_enabled`。
- checkpoint retention / compaction 已有 design note；latest-only checkpoint storage boundary hardening 已实现：checkpoint path 仍是 `runs/{run_id}/checkpoints/latest.json`，同一 run 第二次保存会替换 `latest.json`，不创建 checkpoint history 文件；invalid replacement 不会覆盖已有 valid latest checkpoint；replacement 不修改 event log，也不创建 / 删除 / 重写 `events.jsonl`；`checkpoint_path` / `save_checkpoint` / `load_latest_checkpoint` 都会校验 run_id path segment。broader retention / compaction 仍 deferred，`FileCheckpointStore` 仍保持 opaque，不解释 checkpoint business state。

以下能力仍然 deferred：real LLM、`ActionTypeRegistry`、memory write、external ingestion、public checkpoint API / HTTP endpoint、automatic checkpoint scheduling、CheckpointService、signature / MAC / key management、checkpoint history、checkpoint GC、checkpoint retention policy、old checkpoint fallback、checkpoint inspection API、checkpoint migration / version negotiation、event log compaction、SSE、auth、multi-agent concurrency、real HTTP API。

## Verify

```bash
python -m venv .venv
.venv/bin/python -m pip install -U pip pytest
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel -q
```
