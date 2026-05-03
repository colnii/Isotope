# Event Schema Compatibility Boundary v0.2

状态：draft

## 1. Purpose

本文定义 Isotope 事件模式（event schema）的兼容性边界：当前 canonical event envelope、event type、payload shape 与 replay/checkpoint 在演进时必须遵守的最低兼容性契约。

它不定义具体的事件 payload schema，也不实现 schema registry；它只记录当前硬性约束，确保未来任何 form 的事件模式变更都不会静默破坏 event log 的可重播性与 checkpoint 可用性。

## 2. Current State

- 当前 canonical event envelope 由 `CanonicalEvent` 定义，固定字段：`event_id`、`run_id`、`event_type`、`payload`、`created_at`、`event_envelope_version`。
- `event_envelope_version` 唯一允许值：`"canonical_event_slice@v0"`。任何其他版本（包括缺少该字段的旧格式事件会被填入该默认值）均被 `CanonicalEvent.__post_init__` 拒绝。
- 当前事件类型（`event_type`）集合由 `RunProjector` 的实现隐式定义，包括但不限于：
  - `run.created`、`run.completed`
  - `action.proposed`、`action.decided`、`action.started`、`action.completed`、`action.failed`
  - `artifact.created`
  - `approval.requested`、`approval.resolved`
  - `memory.record_created`、`memory.record_superseded`
  - `snapshot.imported`
  - `agent.created`、`worker.created`（以及相关 lifecycle events）
  - `workspace.bound`、`workspace.lease_created`、`workspace.released`、`workspace.artifact_captured`
  - `action.retry_requested`、`action.retry_created`、`action.cancel_requested`、`action.cancelled`、`action.superseded`
  - 更多事件类型参见 projector 实现与测试覆盖。
- 当前 projector 对未知 `event_type` 的行为是 **fail-fast**（抛出受控 `ValueError`），不会跳过或静默忽略。
- 当前 event prefix digest 已绑定 `event_envelope_version`，checkpoint integrity 记录 `event_digest_event_envelope_version`。
- 当前没有 event envelope schema registry、payload schema registry 或 event migration 机制。

## 3. Hard Compatibility Contract

以下约束是 **不可妥协的兼容性边界**，未来任何版本演进都必须遵守：

| 约束 | 说明 |
|------|------|
| **Append-only log** | Canonical event log 是唯一事实源，不能被重写、删除、压缩或裁剪。 |
| **Version gateway** | `CanonicalEvent` 始终验证 `event_envelope_version`；未知版本 = 拒绝（`ValueError`）。 |
| **No silent fallback** | 版本不匹配或缺失不能由 caller/server/checkpoint 猜测含义。 |
| **Event type surface** | 新增 `event_type` 或修改已有 event 的 payload schema 不得影响已有 event log 的重播（即 projector 必须能继续处理旧事件，新事件若未知则 fail-fast，不能静默跳过）。 |
| **Projector ownership** | 所有 event validation、lifecycle validation、state projection 都由 `RunProjector` 控制；server / checkpoint store 不能绕过 projector 解释 event 或生成 state。 |
| **Checkpoint binding** | 检查点必须绑定其所覆盖的事件流的 `event_envelope_version`；版本变更会导致旧检查点失效（fallback 至全量重建）。 |
| **Event prefix digest** | Digest 始终包含 `event_envelope_version`；版本变更会导致 digest 不匹配，从而安全地拒绝过期的检查点。 |
| **No event repair** | 版本机制不能用来“修复”畸形的 event；畸形 event 始终 fail-fast。 |
| **No bypass** | 新增的兼容性层（如 schema registry、migrator）不能绕过现有的验证链（validation、lifecycle、checkpoint state schema、prefix consistency、digest integrity）。 |
| **Legacy rule** | 若未来出现无 `event_envelope_version` 的旧事件，必须有唯一的、显式的 legacy interpretation（例如认定为 `canonical_event_slice@v0`），且不能由外部覆盖。 |

## 4. Allowed Evolution Paths (Future)

未来若要演进事件模式，必须通过以下受控路径之一：

- **新增 event envelope version**：引入新的 `event_envelope_version` 字符串，同时 projector 必须能识别并处理该版本（可能通过内部的 static map）。旧版本继续原生支持，不重写日志。
- **新增 event type**：向 projector 注册新 `event_type`，新事件携带当前支持的 envelope version。旧日志不受影响。
- **弃用 event type**：projector 保留对旧事件的处理能力，但新事件不再产生该类型。不能从日志中删除历史事件。
- **Payload 字段演进**：通过新增 optional 字段，projector 必须向后兼容旧 payload；必填字段变更需要新 event type 或新 version。

未允许路径：直接修改 `CanonicalEvent` 的字段定义（如删除 `event_id`）、改变现有事件的语义、通过后台脚本改写 `.jsonl` 文件。

## 5. Interaction with Checkpoint & Digest

- 每个 checkpoint 通过 `integrity.event_digest_event_envelope_version` 记录其创建时的事件 envelope version。
- 当使用 checkpoint 辅助重建时，projector 会比较当前事件流的 envelope version 与 checkpoint 中记录的版本；若不一致，checkpoint 被判定为无效，回退至全量事件日志重播。
- 这意味着：一旦事件 envelope version 发生变更，所有历史 checkpoint 将自动失效，需重新生成。
- 这是设计意图：防止 checkpoint 在版本迁移后错误地加速 replay。

## 6. Current Non-Contract (Deferred)

以下能力不属于当前兼容性契约，也未实现，未来如要引入需先进行独立设计：

- event envelope schema registry（`event-envelope-schema-registry-v0.1.md`）
- payload schema per `event_type` registry
- event migration / migrator registry
- event log compaction
- content-addressed event ids
- public event inspection API
- automatic checkpoint migration
- 多版本事件流共存（同一 run 内混合 envelope version）
- legacy event 长期支持策略（当前仅默认填入 `canonical_event_slice@v0`）

## 7. Relationship to Existing Design Notes

本文是对以下设计笔记中已列边界的高层汇总与固化为兼容性契约：

- `docs/event-envelope-versioning-v0.1.md`
- `docs/event-envelope-schema-registry-v0.1.md`
- `docs/event-prefix-digest-v0.1.md`
- `docs/checkpoint-schema-version-fields-v0.1.md`

本契约不替代它们，而是声明所有事件模式演进必须通过上述约束来保持整体系统的一致性。后续的 Event Schema Registry 实现（若开启）必须在本契约的框架内进行。

## 8. Future TDD Notes

若将来要实现事件模式变更或 schema registry，应首先编写 red tests 覆盖：

- 新 `event_envelope_version` 被 `CanonicalEvent` 拒绝（未注册）
- 注册后的版本可正常构造和重播
- 旧版本事件流不受新 projector 影响
- 未知 `event_type` fail-fast
- checkpoint event envelope version 不匹配导致回退
- 多版本混合事件流（若支持）的行为
- schema registry 不能修复畸形事件
- schema registry 不能绕过 projector validation chain
