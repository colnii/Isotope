# Checkpoint Ownership v0.1

状态：draft

本文定义 checkpoint ownership（检查点归属）和边界。当前实现只覆盖 opaque checkpoint storage、最小 checkpoint-assisted projector rebuild、projector-owned checkpoint creation、checkpoint state schema validation、projector-owned checkpoint save boundary、checkpoint prefix consistency hardening、checkpoint integrity/hash validation、event prefix digest validation、checkpoint candidate fallback、checkpoint projector version boundary hardening 和最小 event envelope version boundary；checkpoint schema 仍是 v0 candidate。

## Purpose

Checkpoint 的目的，是在不改变事实来源的前提下，加速 replay / recovery / inspection。

本设计要防止一个长期风险：checkpoint 被误用成第二事实源，绕过 canonical event log、event validation 或 projector validation。

## Decision

v0.1 决定：

- canonical event log 仍然是唯一 source of truth。
- checkpoint 只是 derived object（派生对象），只能从 canonical events 和 projector 输出得到。
- checkpoint 可以丢弃、重建、迁移；checkpoint 丢失不能影响事实正确性。
- v0.1 采用 `Projector-owned checkpoint`。
- Projector 负责产出 checkpoint。
- `FileCheckpointStore` 或后续 storage layer 只负责保存/读取 checkpoint blob。
- checkpoint storage 不解释 checkpoint 语义。
- v0.1 暂不新增独立 Checkpoint Service。
- checkpoint schema 是 v0 candidate，不是永久协议。
- checkpoint v0.1 当前已 frozen for current kernel slice；scope freeze 见 `checkpoint-v0.1-scope-freeze.md`。
- checkpoint integrity/hash 的边界见 `checkpoint-integrity-v0.1.md`。
- checkpoint save trigger 的边界见 `checkpoint-save-trigger-v0.1.md`。
- event prefix digest 的边界见 `event-prefix-digest-v0.1.md`。
- event envelope versioning 的边界见 `event-envelope-versioning-v0.1.md`。
- event envelope schema registry 的边界见 `event-envelope-schema-registry-v0.1.md`。
- checkpoint retention / compaction 的边界见 `checkpoint-retention-compaction-v0.1.md`。
- checkpoint history / old-checkpoint fallback 的边界见 `checkpoint-history-fallback-v0.1.md`。
- checkpoint history index / retention policy 的边界见 `checkpoint-history-index-retention-v0.1.md`。
- checkpoint history save 的边界见 `checkpoint-history-save-boundary-v0.1.md`。
- checkpoint migration / version negotiation 的边界见 `checkpoint-migration-versioning-v0.1.md`。
- checkpoint schema version fields 的边界见 `checkpoint-schema-version-fields-v0.1.md`。

## Hard Boundaries

- checkpoint 不能取代 canonical event log。
- checkpoint 不能修正 event log。
- checkpoint 不能让 projector 跳过 canonical event validation。
- checkpoint 不能包含 external raw input。
- checkpoint 不参与 external ingestion。
- checkpoint 不接收 raw `ImportedSnapshot` 或 provider payload；当前 checkpoint state 可以包含由 canonical `snapshot.imported` event 投影出的 `external_observations` read model。
- checkpoint 不能改变 `RunState` / `SessionState` 的事实来源边界。
- 如果 checkpoint 与 event log 冲突，以 event log replay 为准。

## v0.1 Ownership Model

v0.1 ownership 分工：

- `RunProjector`：解释 canonical events，产出 projected state，执行 checkpoint-assisted rebuild，并负责生成 projector-owned checkpoint blob。
- `FileCheckpointStore` / future storage layer：只保存和读取 opaque checkpoint blob，不解释 checkpoint 字段含义。
- `InProcessServer` / future server API：当前 read path 已可选调用 projector-owned checkpoint-assisted rebuild，internal-only `save_checkpoint_for_run(...)` 已可调用 projector-owned latest checkpoint save boundary，internal-only `save_checkpoint_history_for_run(...)` 已可调用 projector-owned history checkpoint save boundary；server 不能直接把 checkpoint 当成 state source。public checkpoint API 和 scheduling 仍 deferred；server-facing 边界见 `server-checkpoint-boundary-v0.1.md`。
- future checkpoint storage：只是一种 storage concern，不是新的 truth layer。

不新增独立 `CheckpointService`，除非后续 TDD 证明 projector/storage 边界无法承载最小实现。

## Checkpoint Contents

v0.1 checkpoint 至少应绑定：

- `run_id`
- `projector_version`
- `basis_event_id` 或等价的 last applied event cursor
- projected state snapshot，包括 `approvals` read model、`memory_records` read model 的 summary / refs / provenance / supersession metadata，以及 `external_observations` read model 的 quality / provenance / freshness / basis refs / conflict metadata
- `created_at`

这些字段是当前推荐 shape，用于 future TDD 的测试方向，不是永久协议。

checkpoint 不应包含：

- external raw input
- provider raw response
- tool raw stderr/stdout 全量内容
- memory full content / artifact content / raw content
- 未经 event log 或 artifact/provenance 边界管理的大内容
- 用于修正 event log 的 patch

## Recovery Flow

checkpoint-assisted rebuild 的 v0.1 流程应是：

1. 读取 checkpoint。
2. 校验 checkpoint 的 `run_id`、`projector_version` 和 basis cursor。
3. 如果 checkpoint version 不兼容，丢弃 checkpoint，从 canonical event log 重新投影。
4. 如果 checkpoint 可用，从 checkpoint 的 basis cursor 之后继续 replay canonical event log。
5. replay 过程中仍执行 canonical event validation 和 projector lifecycle validation。
6. 输出 materialized `RunState` / `SessionState`。

checkpoint 只缩短 replay 距离，不改变 replay 语义。

## Invalid Uses

以下用法明确无效：

- 直接从 checkpoint 写回或覆盖 event log。
- 用 checkpoint 接收 external ingestion、raw `ImportedSnapshot` 或 provider payload。
- 在 event log 缺失时，用 checkpoint 假装事实完整。
- 因 checkpoint 存在而跳过 malformed event log fail-fast。
- 在 checkpoint version 不兼容时继续恢复。
- 让 EventStore 根据 checkpoint 内容决定业务状态。
- 把 checkpoint schema 当成长期 protocol 扩散到外部 API。

## Deferred

当前仍不实现：

- automatic checkpoint scheduling
- `save_checkpoint(...)` semantic change / automatic history persistence
- checkpoint history index
- checkpoint GC
- checkpoint retention policy
- checkpoint migration implementation
- checkpoint version negotiation implementation
- checkpoint migrator registry
- schema registry
- checkpoint schema registry
- state schema registry
- integrity schema registry
- event envelope schema registry
- event envelope registry lookup
- event schema registry
- payload schema registry
- event migration
- signature / MAC / key management
- partial checkpoint
- SessionState checkpoint
- public checkpoint API / HTTP exposure
- checkpoint inspection API
- external ingestion integration

## Implementation Notes For Future TDD

已覆盖的最小行为：

- checkpoint 丢失时仍可从 event log 完整 rebuild。
- checkpoint version 不兼容时被丢弃，并从 event log 重新投影。
- checkpoint basis cursor 之后的 events 会继续 replay。
- malformed event log 不会因为 checkpoint 存在而被静默跳过。
- `FileCheckpointStore` 只存取 checkpoint blob，不解释 projector state。
- checkpoint 不包含 external raw input。
- `RunProjector.create_checkpoint(...)` 只通过 canonical events 和 `project(...)` 生成 checkpoint。
- checkpoint creation 不写 checkpoint store。
- checkpoint creation 拒绝 empty events、malformed events 和 lifecycle-invalid events。
- 创建出的 checkpoint 可由 `FileCheckpointStore` 保存，并可用于 `rebuild_with_checkpoint(...)`。
- `RunProjector.rebuild_with_checkpoint(...)` 只在 checkpoint projector version 兼容时校验 checkpoint state schema。
- checkpoint version 不兼容时仍 fallback full rebuild，不因 malformed checkpoint state 失败。
- new checkpoint state 必须是 dict，并包含 `run_id`、`status`、`current_agent`、`actions`、`approvals`、`artifacts`、`memory_records`、`last_event_id`；legacy checkpoint 缺少 `approvals` 或 `memory_records` 仍走兼容路径。
- checkpoint state 的 `run_id`、`last_event_id`、run status、actions/artifacts shape 会在 projector 使用前校验。
- checkpoint artifact entry 不得包含 `content`，且必须包含 `ref`、`artifact_type`、`summary`、`provenance`。
- checkpoint memory record entry 只能包含 summary / refs / provenance / supersession metadata，不得包含 `content`、`full_content`、`artifact_content` 或 `raw_content`。
- checkpoint memory record shape 和 supersession metadata 会在 projector 使用前校验。
- malformed checkpoint state fail-fast，抛受控 `ValueError`。
- `RunProjector.save_checkpoint(...)` 只组合 `event_store.list_events(run_id)`、`create_checkpoint(...)` 和 `checkpoint_store.save_checkpoint(run_id, checkpoint)`。
- save checkpoint 读取 canonical events，生成 projector-owned checkpoint，并交给 checkpoint store 保存。
- save checkpoint 不修改 event log，不读取 artifact store / executor state / server memory。
- empty event log 或 invalid event stream 会 fail-fast，且不写 checkpoint。
- 保存后的 checkpoint 可读回，并可用于 `rebuild_with_checkpoint(...)`，结果与 full rebuild 等价。
- `RunProjector.rebuild_with_checkpoint(...)` 会比较 checkpoint state 与 `basis_event_id` 对应的 event-log prefix projection。
- 只有 checkpoint state 与 prefix projection 一致时，才从 checkpoint 继续 replay basis 之后的 events。
- checkpoint state 的 `status` / `current_agent` / `actions` / `approvals` / `artifacts` / `memory_records` 不一致时，fallback full rebuild。
- checkpoint state 多出不存在的 action 或少了已有 artifact 时，fallback full rebuild。
- checkpoint state 中 memory read model 与 event-log prefix projection 不一致时，fallback full rebuild。
- fallback full rebuild 仍执行完整 event validation，lifecycle-invalid event log 不能被 checkpoint mismatch 隐藏。
- `FileCheckpointStore` 保持 opaque，不负责 consistency check。
- `RunProjector.create_checkpoint(...)` 会生成 `integrity`，使用 `algorithm: sha256` 和 `checkpoint_hash`。
- checkpoint hash 输入使用 deterministic canonical JSON，并排除 `integrity` / `checkpoint_hash` 本身。
- hash mismatch 只让 checkpoint 失效并 fallback full rebuild，不能掩盖 lifecycle-invalid event log。
- legacy checkpoint 无 hash 时仍走现有 validation path。
- hash match 后仍继续执行 checkpoint state schema validation 和 prefix consistency validation。
- `FileCheckpointStore` 仍只保存 opaque checkpoint blob，不解释 hash 或业务 state。
- event prefix digest design note 已落文档。
- `RunProjector.create_checkpoint(...)` 会在 checkpoint `integrity` 中生成 event prefix digest metadata。
- event prefix digest 使用 deterministic JSON / UTF-8，覆盖 run 内从第一条 event 到 `basis_event_id` 的 canonical event representation。
- event append order 和 prefix payload 改动会影响 event prefix digest。
- event prefix digest mismatch 只让 checkpoint 失效并 fallback full rebuild，不能替代 canonical replay、lifecycle validation、checkpoint state schema validation 或 prefix consistency validation。
- digest match 后仍继续执行 checkpoint state schema validation 和 prefix consistency validation。
- legacy checkpoint 无 event prefix digest 仍走兼容路径，suffix events 仍会 replay。
- `FileCheckpointStore` 不解释 digest，`InProcessServer` 没有 digest-specific 行为。
- checkpoint retention / compaction design note 已落文档。
- 当前 checkpoint storage 仍是 latest-only。
- latest-only checkpoint storage boundary hardening 已实现。
- checkpoint path 仍是 `runs/{run_id}/checkpoints/latest.json`。
- 同一 run 第二次保存 checkpoint 会替换 `latest.json`，不创建 history 文件。
- invalid replacement 不会覆盖已有 valid latest checkpoint。
- replacement 不修改 event log，也不创建 / 删除 / 重写 `events.jsonl`。
- `checkpoint_path` / `save_checkpoint` / `load_latest_checkpoint` 都校验 run_id path segment。
- broader retention / compaction 仍 deferred。
- retention / compaction 只能处理 checkpoint blobs，不能删除、重写、压缩或裁剪 canonical event log。
- checkpoint 删除后仍必须能从 canonical event log full rebuild。
- checkpoint history / old-checkpoint fallback boundary 已落文档。
- `FileCheckpointStore.load_checkpoint_candidates(run_id)` 已实现，可按 checkpoint `created_at` newest-to-oldest 读取 run-scoped candidates。
- candidate loading 仍保持 storage opaque，不解释 projector version、integrity、event prefix digest、event envelope version 或 projected state 语义。
- `RunProjector.rebuild_with_checkpoint(...)` 可使用 candidate chain。
- invalid latest checkpoint 后可尝试 older fully valid candidate。
- 每个 candidate 仍必须独立通过 projector-owned validation chain。
- invalid candidate 不能被部分读取或部分采用。
- 所有 candidates 都 invalid 时，fallback full canonical event-log rebuild。
- lifecycle-invalid event log 不能被 older checkpoint fallback 隐藏。
- `save_checkpoint(...)` 仍是 latest-only replacement，不创建 checkpoint history 文件。
- 当前没有 checkpoint history index、retention policy 或 GC。
- checkpoint history index / retention policy design note 已落文档。
- history index 不是 source of truth，不能证明 checkpoint 有效。
- retention / GC 只能作用于 checkpoint blobs 或 future index metadata，不能处理 canonical events。
- corrupt / missing history index 不能让系统跳过 full event-log replay。
- checkpoint history save boundary design note 已落文档。
- `FileCheckpointStore.save_checkpoint_history(run_id, checkpoint)` 已实现为 explicit history candidate save method。
- `RunProjector.save_checkpoint_history(...)` 已实现为显式 projector-owned history save method。
- `InProcessServer.save_checkpoint_history_for_run(...)` 已实现为 internal-only explicit history save trigger。
- server history save trigger 只委托 `RunProjector.save_checkpoint_history(...)`，不直接调用 storage、不返回 checkpoint state、不写 `latest.json`。
- history save 不覆盖 `latest.json`，不修改 event log。
- `FileCheckpointStore` 仍保持 opaque，不解释 checkpoint state / integrity / projector version。
- `save_checkpoint(...)` 仍是 latest-only replacement，不自动保存 history。
- checkpoint v0.1 已足够支撑当前 kernel slice；history index、retention policy、checkpoint GC、automatic scheduling、public checkpoint API 和 `CheckpointService` 暂不继续实现，除非 checkpoint scope 被明确 reopened。
- memory read-model checkpoint boundary 已实现：`RunProjector.create_checkpoint(...)` 会包含 `memory_records`，`RunProjector.rebuild_with_checkpoint(...)` 可从 checkpoint + suffix events 恢复 `memory_records`，并且 event-log replay / checkpoint-assisted replay 都不读取 memory store 或 query service。
- 这只是 checkpoint/read-model boundary，不是 durable memory storage、successful memory write/update 或 memory query engine。
- invalid checkpoint 不能覆盖 latest，也不能进入 history。
- candidate loading 不等于 save path 已经持久化 history。
- latest write / history write failure ordering 必须先有明确策略。
- server 不能直接选择、解释或信任 old checkpoint；仍必须走 projector-owned boundary。
- checkpoint migration / version negotiation design note 已落文档。
- checkpoint schema version fields design note 已落文档。
- 当前 checkpoint 使用 `projector_version`；当前 projector version 是 `run_projector@v1`。
- 当前实现仍以 `projector_version` 作为 checkpoint compatibility 的唯一已实现版本边界。
- `checkpoint_schema_version` / `state_schema_version` / `integrity_schema_version` 目前还没有实现字段。
- checkpoint schema version fields 不能覆盖 `projector_version`，不能让 malformed checkpoint 合法，不能让 checkpoint 成为第二事实源。
- projector version 不兼容时，checkpoint 会失效并 fallback full rebuild。
- malformed `projector_version` 不会被使用；non-string / empty `projector_version` 会让 checkpoint invalid 并 fallback full rebuild。
- incompatible 或 malformed version fallback 不读取 checkpoint state，且不能隐藏 lifecycle-invalid event log。
- valid `projector_version` override 参数仍控制兼容性，但 malformed version 不能因 caller 传同样 malformed 值而被接受。
- future sketch fields 如 `checkpoint_schema_version` / `state_schema_version` 不能 override `projector_version`；event envelope version metadata 也不能 override `projector_version`。
- compatible checkpoint 带 future sketch fields 时仍按当前 validation chain 处理。
- `FileCheckpointStore` 仍保持 opaque，不解释 version 字段。
- checkpoint schema 仍是 v0 candidate，event envelope 仍是 slice-only shape。
- migration / version negotiation 不能修改 canonical event log，不能伪造 state，不能跳过 checkpoint validation chain。
- event envelope versioning design note 已落文档。
- event envelope schema registry design note 已落文档。
- 当前 `CanonicalEvent` envelope 仍是 slice-only implementation shape。
- 当前 event prefix digest 绑定的是当前 slice canonical event representation。
- `CanonicalEvent` 当前有 `event_envelope_version`，默认值是 `canonical_event_slice@v0`。
- legacy event JSON 缺少 `event_envelope_version` 时按当前 slice legacy representation 读取。
- empty / non-string / unknown event envelope version 会被拒绝。
- event prefix digest input 包含 `event_envelope_version`，checkpoint integrity metadata 记录 digest 绑定的 event envelope version。
- checkpoint event envelope version mismatch 只让 checkpoint 失效并 fallback full rebuild，且不能读取 checkpoint state。
- legacy checkpoint 无 event envelope version metadata 仍走兼容路径。
- event envelope versioning 不能重写 canonical event log，不能让 malformed event 变合法。
- 当前没有 event envelope schema registry 或 registry lookup；future registry 不能重写 event log、不能解释 payload、不能让 server / checkpoint store 直接生成 state。
- `InProcessServer.get_run_state(...)` 没有 checkpoint store 时仍走 full event log rebuild，有 checkpoint store 时调用 `RunProjector.rebuild_with_checkpoint(...)`。
- server 不直接读取或解释 checkpoint state，不创建 checkpoint，不写 checkpoint store。
- `create_checkpoint(...)` 仍返回 `not_enabled`。
- checkpoint missing 或所有 candidates invalid 时 fallback full rebuild；lifecycle-invalid event log 仍 fail-fast。
- checkpoint save trigger boundary design note 已落文档。
- internal-only save trigger 已命名为 `save_checkpoint_for_run(...)`。
- save trigger 只能调用 projector-owned `RunProjector.save_checkpoint(...)`，不能读取 artifact content / executor state / server memory 生成 state。
- `create_checkpoint(...)` 不应被复用为 save trigger，除非先有明确 rename/deprecation 设计。
- checkpoint schema 仍被标记为 v0 candidate。

后续实现必须先写 red tests，优先覆盖：

- checkpoint schema version fields boundary red tests。
- event envelope schema registry boundary red tests。
- checkpoint history index / retention boundary red tests only after explicit checkpoint scope reopen。
- automatic history persistence from `save_checkpoint(...)` boundary red tests only after explicit checkpoint scope reopen。
- server history save integration boundary red tests。
- corrupt / missing history index fallback boundary red tests。
- server API 如需使用 checkpoint，只能调用 projector rebuild boundary，不能直接读取 checkpoint 当作 state source。
