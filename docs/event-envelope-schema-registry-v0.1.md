# Event Envelope Schema Registry v0.1

状态：draft

本文定义 event envelope schema registry（事件信封 schema 注册表）的 v0.1 边界：未来如何把 `event_envelope_version` 映射到明确的 event envelope shape、serialization rules（序列化规则）和 digest representation rules（摘要表示规则），同时不把 registry 误用成 event migration、payload schema registry 或第二事实源。

本文件仍只描述 envelope registry 设计说明，不实现 envelope registry、registry lookup、event migration 或 public inspection API。event payload schema registry 的 first green slice 已在 `docs/event-schema-registry-compatibility-boundary-v0.2.md` / `src/isotope_kernel/event_schema.py` 中单独实现。

## Purpose

Event envelope schema registry 的目的，是在出现多个 event envelope version 时，为 projector 和 digest validation 提供明确、受控的 interpretation boundary（解释边界）。

它不是 event payload schema registry，不解释每个 `event_type` 的业务 payload，也不生成 `RunState`。Event payload schema / compatibility 的后续 v0.2 边界见 `docs/event-schema-registry-compatibility-boundary-v0.2.md`。

## Current State

当前实现状态：

- 当前只有单一 event envelope version：`canonical_event_slice@v0`。
- 当前 `CanonicalEvent` 是 slice-only implementation shape，不是最终 protocol。
- 当前 envelope 包含 `event_id`、`run_id`、`event_type`、`payload`、`created_at`、`event_envelope_version`。
- 当前没有 event envelope schema registry。
- 当前没有 registry lookup。
- 当前 unknown event envelope version 会 fail fast。
- 当前 event prefix digest 已绑定 event envelope version。
- 当前 `FileCheckpointStore` 仍保持 opaque，不解释 event envelope schema。
- Event payload schema registry / compatibility first green slice 已独立实现：known canonical event type metadata、unknown event fail-closed、unsupported payload schema version fail-closed；它不改变本 envelope registry 边界。
- 当前 full regression：`986 passed`。

## Decision

v0.1 design decision：

- 暂不实现 event envelope schema registry。
- 当前 `canonical_event_slice@v0` 仍由 `CanonicalEvent` / `RunProjector` 的最小 slice validation 直接处理。
- 未来如果引入 registry，它只能描述 event envelope representation，不能解释业务 payload。
- registry 不能改变 append-only canonical event log 的 source-of-truth 边界。
- registry mismatch 只能导致 fail fast 或 checkpoint fallback，不能静默猜测。
- registry 不能让 checkpoint 成为第二事实源。

## Hard Boundaries

- schema registry 不能重写 canonical event log。
- schema registry 不能删除、压缩、裁剪或迁移 canonical events。
- schema registry 不能让 malformed event 变合法。
- schema registry 不能绕过 projector validation。
- schema registry 不能绕过 lifecycle validation。
- schema registry 不能绕过 event prefix digest validation。
- schema registry 不能绕过 checkpoint state schema validation。
- schema registry 不能绕过 prefix consistency validation。
- schema registry 不能让 checkpoint 成为第二事实源。
- server 不能直接用 registry 解释 event 并生成 state，仍必须走 projector-owned boundary。
- checkpoint store 不能直接用 registry 解释 event 或 checkpoint state，仍必须保持 opaque。
- registry mismatch 只能导致 fail fast 或 checkpoint fallback，不能静默猜测。
- registry 不能接收 public client 提交的 version override。

## v0 Candidate / Sketch

未来 registry 可以把 event envelope version 映射到：

- required envelope fields
- allowed / known envelope fields
- serialization rules
- digest representation rules
- legacy compatibility rules

Registry sketch：

```python
EVENT_ENVELOPE_SCHEMAS = {
    "canonical_event_slice@v0": {
        "required_fields": [
            "event_id",
            "run_id",
            "event_type",
            "payload",
            "created_at",
            "event_envelope_version",
        ],
        "serialization": "deterministic_json@v0",
        "digest_representation": "event_prefix_digest_slice@v0",
        "legacy_without_version": True,
    }
}
```

这只是 v0 candidate / schema sketch，不是当前实现契约。

实现形态可以先是 in-process static map，不需要动态插件。`canonical_event_slice@v0` 可以作为第一条 registry entry，但本轮不实现。

event payload schema per `event_type` 暂时不归这个 registry 处理，避免把 envelope registry 和 payload registry 混在一起。

## Interaction With Event Prefix Digest

event prefix digest 已经绑定当前 event envelope version。未来如果 registry 存在，digest metadata 可以记录所用 registry entry 或 representation version。

最低要求仍然不变：

- digest input 必须保留 event append order。
- digest input 必须明确绑定 event representation version。
- digest mismatch 只能让 checkpoint invalid，并 fallback full rebuild。
- digest match 后仍必须执行 event validation、lifecycle validation、checkpoint state schema validation 和 prefix consistency validation。

Registry 不能让 digest match 替代 canonical event replay。

## Open Questions

以下问题当前不定为 Hard Contract：

- registry 是代码内 static map，还是外部 schema 文件。
- registry 是否参与 event prefix digest metadata。
- unknown event envelope version 是 fail fast，还是允许 explicit migrator。
- legacy no-version event 是否作为 registry entry 表示。
- registry 如何和 future event migration / migrator registry 协作。
- registry 是否需要 public inspection API。
- registry 是否需要 version 自身的 schema。
- registry entry 是否应包含 deprecated / supported-until metadata。

## Invalid Uses

以下用法明确无效：

- 用 registry 修复坏 event。
- 用 registry 猜测 unknown event envelope version。
- 用 registry 重写 canonical event log。
- 用 registry 跳过 event validation 或 lifecycle validation。
- 用 registry 替代 event prefix digest validation。
- 用 registry 让 checkpoint 覆盖 event log。
- 把 payload schema per `event_type` 混进 event envelope schema registry。
- 让 server 或 checkpoint store 直接根据 registry 生成 `RunState`。
- 让 public client 上传 registry entry 或 version override。

## Deferred

当前仍不实现：

- event envelope schema registry。
- event envelope registry lookup。
- event schema migration framework。
- payload schema migration framework。
- migrator registry。
- event migration。
- content-addressed event ids。
- event log compaction。
- public inspection API。
- dynamic plugin registry。

## Future TDD Notes

后续如继续推进，应先写 red tests，优先覆盖：

- `canonical_event_slice@v0` 作为第一条 in-process registry entry。
- legacy no-version event 的 registry compatibility rule。
- unknown event envelope version fail-fast。
- registry mismatch 不能隐藏 malformed / lifecycle-invalid event log。
- event prefix digest metadata 绑定 registry entry 或 representation version。
- `FileCheckpointStore` 仍不解释 registry。
- server 仍只能通过 projector-owned boundary 读取 state。

不要直接实现 event migration、payload schema registry、migrator registry、content-addressed event ids、event log compaction 或 public inspection API。
