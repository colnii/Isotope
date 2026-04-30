# Memory v0.1 Scope Freeze

状态：`accepted for v0.1 demo planning`

## 1. Purpose

本文用于冻结 v0.1 demo 前的 memory 范围，避免把 not-enabled boundary 误读成真实 durable memory system。

当前 memory 线已经足够支撑 kernel slice 的 contract demonstration：structured record shape、provenance、canonical event read model、append-only supersession、event-log replay 和 checkpoint-assisted rebuild。它还不是可用于产品展示的 durable storage / query engine。

## 2. What Is Implemented

当前已实现：

- `MemoryRecord` slice-only implementation shape。
- `NotEnabledMemoryService` write / query boundary。
- `NotEnabledMemoryStore` persistence boundary。
- `NotEnabledMemoryQueryService` query / controlled expand authorization boundary。
- `write_memory` action 可通过 compiler / policy / executor 进入 not-enabled handler boundary。
- `memory.record_created` canonical event read-model boundary。
- `memory.record_superseded` canonical event read-model boundary。
- `RunState.memory_records` 可从 event log replay。
- `RunState.memory_records` 可通过 checkpoint-assisted rebuild 恢复。
- checkpoint schema / prefix consistency 覆盖 memory read model。

这些能力只证明 kernel boundary：memory 只能通过 action chain、authorized execution、canonical event 和 validated checkpoint state 影响 read model。memory store 和 query service 仍不能直接推进 `RunState`。

## 3. What Is Not Implemented

当前没有实现：

- 真实 durable memory storage。
- successful durable memory write。
- real memory query engine。
- controlled expand materialization。
- server public memory write / query / update API。
- memory ranking / exposure policy。
- memory index。
- memory compaction。
- cross-run session memory promotion。

## 4. Hard Boundaries Preserved

- memory store 不能直接推进 `RunState`。
- memory query 不能绕过 retrieval / grants。
- memory update 不能原地修改旧 record，只能 append supersession event。
- checkpoint 不能夹带 full content / artifact content / raw content。
- projector 只消费 canonical events / validated checkpoint state，不读取 memory store 或 query service。

## 5. Demo Implication

v0.1 demo 可以展示 memory boundaries 和 read model，但不要把 memory 当作已完成产品能力展示。

demo entrypoint 已实现，见 `docs/demo-entrypoint-v0.1.md`。该 demo 把 memory 输出标记为 `boundary_only`，避免误解为 storage/query product capability。

推荐 demo wording：

> Memory support in v0.1 demonstrates the kernel contract for durable memory: structured records, provenance, append-only events, supersession, replay, and checkpointing. Actual storage/query engines remain deferred.

## 6. Deferred After v0.1 Demo

以下能力留到 v0.1 demo 后，只有在 scope 被明确 reopened 后再进入 design / red tests：

- `FileMemoryStore` 或其他 real storage backend。
- successful `write_memory` execution path。
- `memory.record_created` emission from authorized executor。
- memory query ranking and retrieval integration。
- controlled expand with budget and audit events。
- session memory promotion policy。
