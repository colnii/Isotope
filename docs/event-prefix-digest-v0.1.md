# Event Prefix Digest v0.1

状态：draft

本文定义 event prefix digest（事件前缀摘要）的 v0.1 边界：checkpoint 如何绑定到某个 canonical event log prefix，同时不把 digest 误用成新的 source of truth。

当前已实现最小 event prefix digest validation；`FileCheckpointStore` 仍保持 opaque，`InProcessServer` 没有 digest-specific 行为。

## Purpose

event prefix digest 的目的，是在 checkpoint 被用作 replay basis 之前，额外确认它声称覆盖的 event-log prefix 没有被意外改动、替换或重排。

它只用于 checkpoint availability validation（可用性校验）。digest mismatch 只能让 checkpoint 失效，并 fallback 到 canonical event log full rebuild；digest 不能产生 `RunState`，也不能证明业务状态正确。

## Current State

当前实现状态：

- checkpoint 已有自身 `sha256` integrity/hash。
- checkpoint hash 只校验 checkpoint blob 是否自洽、是否被改动。
- checkpoint 已有 prefix consistency validation，会比较 checkpoint state 与 `basis_event_id` 对应的 prefix projection。
- checkpoint 已有最小 event prefix digest validation。
- 当前 event prefix digest 绑定的是当前 slice canonical event representation。
- 当前 `CanonicalEvent` 已有 `event_envelope_version`，默认值为 `canonical_event_slice@v0`。
- event prefix digest input 已包含 `event_envelope_version`。
- checkpoint integrity metadata 已记录 digest 绑定的 event envelope version：`event_digest_event_envelope_version`。
- event envelope versioning design note 已落文档，边界见 `docs/event-envelope-versioning-v0.1.md`。
- 当前 full regression：`352 passed`。

已有边界仍然有效：

- canonical event log 是唯一 source of truth。
- checkpoint 是 derived object。
- `FileCheckpointStore` 仍是 opaque storage。
- `RunProjector` 负责决定 checkpoint 是否可用。

## Decision

v0.1 decision：

- event prefix digest 是 checkpoint 可用性校验的一部分。
- event prefix digest 用于把 checkpoint 绑定到 run 内从第一条 event 到 `basis_event_id` 的 canonical event prefix。
- event prefix digest 用于检测 checkpoint basis 之前的 event log 是否被改动、替换或重排。
- digest mismatch 只能让 checkpoint invalid，并 fallback 到 full event-log rebuild。
- digest match 不能证明业务状态正确，只能说明参与 digest 的 prefix bytes / canonical event representation 一致。
- digest metadata 必须明确绑定当前 event representation version。
- legacy checkpoint 没有 prefix digest 时，仍按当前兼容路径处理，不能直接判 malformed。

## Hard Boundaries

- event prefix digest 不是 source of truth。
- digest 不能替代 canonical event replay。
- digest 不能替代 event validation。
- digest 不能替代 lifecycle validation。
- digest 不能替代 checkpoint state schema validation。
- digest 不能替代 prefix projection consistency validation。
- digest 不能让 checkpoint 覆盖 canonical event log。
- digest 不能修复 event log。
- digest 不能修复 checkpoint state。
- digest mismatch 不能产生 state，只能让 checkpoint 失效并 fallback full rebuild。
- digest match 后仍必须继续执行现有 checkpoint validation chain。
- digest 不能替代 event envelope versioning boundary。
- malformed / lifecycle-invalid event log 不能因为 digest match 或 mismatch 被隐藏。

## v0 Candidate Shape

event prefix digest 当前作为 checkpoint `integrity` 下的额外字段。

Schema sketch：

```json
{
  "integrity": {
    "algorithm": "sha256",
    "checkpoint_hash": "...",
    "event_digest_algorithm": "sha256",
    "event_prefix_digest": "...",
    "event_digest_basis_event_id": "event_123",
    "event_digest_event_count": 42,
    "event_digest_event_envelope_version": "canonical_event_slice@v0"
  }
}
```

这些字段名是当前 v0 implementation shape，不是永久协议。

digest input 的当前 v0 implementation shape：

- 使用 deterministic JSON。
- 使用 UTF-8。
- 使用 `sort_keys=True`。
- 使用 `separators=(",", ":")`。
- 使用 `ensure_ascii=False`。
- 保留 event append order。
- 范围是 run 内从第一条 event 到 `basis_event_id` 的 prefix。
- 至少包含每个 canonical event 的 `event_id`、`run_id`、`event_type`、`payload`、`created_at`、`event_envelope_version`。
- 当前 representation version 是 `canonical_event_slice@v0`，这是当前 slice implementation shape，不是最终 protocol。
- suffix events 仍必须 replay，不能因为 prefix digest 存在而跳过。

digest metadata 记录 event representation version。字段名仍是当前 v0 implementation shape，边界见 `docs/event-envelope-versioning-v0.1.md`。

## Validation Behavior

checkpoint-assisted rebuild 的顺序：

1. 读取 checkpoint。
2. 校验 checkpoint blob integrity/hash。
3. 如果 checkpoint 没有 event prefix digest，按 legacy checkpoint 继续现有 validation。
4. 如果 checkpoint 有 event prefix digest，重新计算 event log prefix digest。
5. 如果 digest mismatch，checkpoint 失效，fallback full event-log rebuild。
6. 如果 digest match，继续执行 checkpoint state schema validation。
7. 继续执行 prefix projection consistency validation。
8. replay `basis_event_id` 之后的 suffix events。

fallback full rebuild 仍必须执行完整 canonical event validation 和 lifecycle validation。

当前已覆盖的最小行为：

- `RunProjector.create_checkpoint(...)` 会在 `integrity` 中生成 event prefix digest metadata。
- 当前字段包括 `event_digest_algorithm: "sha256"`、`event_prefix_digest`、`event_digest_basis_event_id`、`event_digest_event_count`。
- 当前字段还包括 `event_digest_event_envelope_version`，用于记录 digest 绑定的 event envelope version。
- digest 输入使用 deterministic JSON / UTF-8。
- digest 输入覆盖 run 内从第一条 event 到 `basis_event_id` 的 prefix。
- digest 输入包含 canonical event representation，至少包括 `event_id`、`run_id`、`event_type`、`payload`、`created_at`、`event_envelope_version`。
- event append order 会影响 digest。
- prefix event payload 或 event envelope version 改动会改变 digest。
- `rebuild_with_checkpoint(...)` 遇到 event prefix digest mismatch 会让 checkpoint invalid，并 fallback full rebuild。
- `rebuild_with_checkpoint(...)` 遇到 checkpoint event envelope version mismatch 也会让 checkpoint invalid，并 fallback full rebuild，且不会读取 checkpoint state。
- digest mismatch 不能隐藏 lifecycle-invalid event log。
- digest match 后仍执行 checkpoint state schema validation。
- digest match 后仍执行 prefix projection consistency validation。
- legacy checkpoint 无 event prefix digest 仍走兼容路径。
- suffix events 仍会 replay。
- `FileCheckpointStore` 仍保持 opaque，不解释 digest。
- `InProcessServer` 没有 digest-specific 行为。

## Open Questions

以下问题当前不定为 Hard Contract：

- canonical event serialization 的正式版本。
- linear digest 还是 Merkle / chunked digest。
- event migration 后 digest 如何处理。
- 是否需要把 event count / first_event_id / basis_event_id 全部纳入 digest metadata。
- 是否先实现最小 linear digest，还是等 event envelope schema 再实现。

## Deferred

当前仍不实现：

- `FileCheckpointStore` digest-specific behavior。
- `InProcessServer` digest-specific behavior。
- event schema registry。
- payload schema registry。
- signature / MAC / key management。
- checkpoint migration / version negotiation implementation。
- broader checkpoint retention / compaction。
- public checkpoint API / HTTP endpoint。

## Future TDD Notes

后续如继续扩展，应先写 red tests，优先覆盖：

- checkpoint retention / compaction 对 event prefix digest 的影响。
- checkpoint migration / version negotiation 对 digest metadata 的影响；边界见 `docs/checkpoint-migration-versioning-v0.1.md`。
- event envelope schema registry 引入后 digest 输入如何版本化；边界见 `docs/event-envelope-versioning-v0.1.md`。
- Merkle / chunked digest 是否需要替代当前 linear digest。
