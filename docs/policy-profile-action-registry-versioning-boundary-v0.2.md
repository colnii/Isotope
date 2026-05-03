# Policy Profile / Action Registry Versioning Boundary v0.2

状态：`first slice complete / closed for now; plugin / policy DSL / migration deferred`

## 1. Purpose

当前 Isotope 已有 `ActionTypeRegistry`、`ActionCompiler(registry=...)`、`PolicyEngine(registry=...)`、`Executor(registry=...)` 和 `InProcessServer` registry wiring。它证明了 action / tool metadata 可以被 compiler、policy 和 executor 共享，而 executor 仍只执行 `PolicyDecision.grants`。

随着 action types、tools、helpers 和 policy rules 增多，kernel 需要回答：

- 某次 `ActionProposal` 是按哪个 registry version 编译的？
- 某次 `PolicyDecision` 是按哪个 policy profile / policy version 作出的？
- registry entry 变更后，旧 event log / checkpoint 如何解释？
- modified / denied decision 的 `reason_codes` 是否足够稳定？
- demo / tests 如何避免隐式依赖当前 global default registry？

本文定义最小 kernel contract（内核契约）。当前 first slice 已实现并通过 closure review：registry/profile basis metadata 已进入 proposal / decision / canonical event payload / action read model，但仍不引入 plugin system、marketplace、policy DSL 或 migration framework。

## 2. Definitions

### `ActionTypeRegistry`

`ActionTypeRegistry` 是 action / tool metadata registry（元数据注册表）。当前实现位于 `src/isotope_kernel/action_registry.py`，用于让 compiler、policy 和 executor 查询 tool 是否存在、payload requirements、required capabilities、default workspace mode、result kind 和 enabled 状态。

它不是：

- dynamic plugin loader
- marketplace
- executor callback registry
- policy engine replacement
- remote tool discovery surface

### `registry_version`

`registry_version` 是 registry snapshot 的稳定标识。它回答“当前 proposal 编译时使用哪一版 action type registry”。

最小形态可以是 string，例如：

- `action_registry@v0.1`
- `default-action-registry@2026-05-03`
- content-addressed digest in a future slice

First slice 不要求实现 content digest，但要求 event payload / read model 有地方记录版本 basis。

### `ActionTypeEntry`

`ActionTypeEntry` 是 registry 内单个 action / tool 的 metadata entry。当前字段包括：

- `action_type`
- `tool_name`
- `payload_requirements`
- `required_capabilities`
- `default_workspace_mode`
- `result_kind`
- `enabled`

Future versioning boundary 可增加 `entry_version` 或 `schema_version`，但不应把 executable callback 放进 entry。

### `PolicyProfile`

`PolicyProfile` 是 policy rules / defaults / caps 的 named profile（命名策略配置）。它回答“这次 decision 使用哪个 policy set 来把 requested capabilities 缩减成 grants”。

当前 `PolicyEngine` 是 slice-level fixed rules，还没有 first-class `PolicyProfile` model。

### `policy_profile_id`

`policy_profile_id` 是 policy profile identity，例如：

- `default`
- `demo-strict`
- `approval-required-demo`

它不等于 user identity、tenant identity 或 auth identity。

### `policy_version`

`policy_version` 是 policy profile 的 stable version。它回答“同一个 `policy_profile_id` 在这次 decision 时是哪一版 rules”。

### `reason_code`

`reason_code` 是 stable machine-readable reason identifier（稳定机器可读原因码），不是 free-form prose（自由文本）。

Examples:

- `capabilities_reduced`
- `unsupported_tool`
- `disabled_tool`
- `tool_not_requested`
- `approval_required`
- `workspace_mode_not_supported`

Free-form explanation 可以另存为 `message` / `detail`，但不能替代 `reason_code`。

## 3. Current Implementation Facts

当前事实：

- `ActionTypeRegistry.default()` 当前只包含 deterministic `write_artifact_tool` slice，并 exposes `registry_id="default"` / `registry_version="v0.2"`。
- custom `ActionTypeRegistry(...)` 可显式传入 `registry_id` / `registry_version`；malformed metadata fail fast。
- `ActionCompiler(registry=...)` 可显式传入 registry；不传时使用 default registry。
- `ActionCompiler` 生成的 `ActionProposal` 携带 `registry_id` / `registry_version` / `registry_basis`。
- canonical `action.proposed` payload 包含 registry basis metadata。
- `PolicyEngine(registry=..., policy_profile_id=..., policy_version=...)` 可显式传入 registry 和 policy metadata；不传时使用 default registry / profile。
- `PolicyEngine` 默认 exposes `policy_profile_id="default"` / `policy_version="v0.2"`；malformed metadata fail fast。
- `PolicyDecision` 携带 `policy_profile_id` / `policy_version` / `policy_basis`。
- canonical `action.decided` payload 包含 policy basis metadata。
- `Executor(..., registry=...)` 可显式传入 registry；不传时使用 default registry。
- `InProcessServer(root, registry=...)` 创建 shared registry，并注入 compiler / policy / executor。
- compiler 只生成 requested capabilities，不生成 grants。
- policy 负责生成 `PolicyDecision.grants`，并可 approved / modified / denied。
- executor 只使用 effective grants snapshot，不使用 proposal requested capabilities 扩权。
- registry-known-but-unsupported handler fail closed。
- projector validation 要求 `action.proposed` / `action.decided` payload 携带 basis metadata。
- `RunState.actions` summaries 可从 canonical events 展示 registry / policy basis，replay / checkpoint-assisted rebuild 不依赖 current default registry / policy profile。
- existing handwritten test fixtures 已最小同步默认 basis metadata；malformed missing-basis tests 仍验证 fail-fast。

当前缺口：

- `reason_codes` 已是 stable identifiers，但还没有完整 taxonomy / compatibility contract。
- 仍没有 registry/profile migration framework、bundle store、remote loading、policy DSL 或 product policy UI。
- event schema registry / compatibility engine 仍属于后续单独 boundary。

## 4. Hard Contracts

后续实现必须继续遵守：

- `ActionProposal` records registry/version basis.
- `PolicyDecision` records policy profile/version basis.
- canonical `action.proposed` event carries enough registry basis to explain old proposals after registry defaults change.
- canonical `action.decided` event carries enough policy basis to explain old decisions after policy defaults change.
- executor must execute effective grants snapshot, not re-query mutable policy.
- event replay must not depend on current default registry / policy profile.
- registry/profile changes must be append/new-version, not silent mutation for old runs.
- unknown future action type must fail closed unless the selected registry version explicitly supports it.
- disabled action type / tool must fail closed.
- reason codes must be stable identifiers, not prose.
- tests and demos should prefer explicit registry/profile setup when the behavior depends on non-default entries.
- checkpoint-assisted rebuild should recover action / policy basis from checkpoint state or event payloads, not from mutable process globals.

Invalid shapes:

- registry entry directly grants tool execution.
- registry entry carries executable side-effect callback.
- policy profile is inferred from user / tenant identity without event basis.
- executor re-runs policy during replay.
- changed default registry silently changes old event interpretation.
- reason code is only a human sentence.

## 5. Minimal Event / Read Model Implications

### `action.proposed`

Candidate event payload additions:

- `registry_id` or `registry_name`
- `registry_version`
- optional `action_type_entry_version`
- optional `registry_basis_ref`

The first green slice can keep this metadata small. It does not need a registry bundle store.

### `action.decided`

Candidate event payload additions:

- `policy_profile_id`
- `policy_version`
- optional `policy_basis_ref`
- stable `reason_codes`

`PolicyDecision.grants` remains the effective authorization snapshot. Replay and executor must use the recorded grants snapshot, not call current policy again.

### `RunState` action summaries

Action summaries should expose enough basis metadata for debugging:

- proposal registry basis
- decision policy profile / version basis
- reason codes
- grants snapshot summary

This metadata belongs in read model / diagnostics, not as a second source of truth.

### Checkpoints

Checkpoint state can either:

- include the projected basis metadata in action summaries, or
- rely on canonical event payloads and replay after `basis_event_id`.

If `RunState.actions` exposes registry / policy basis, checkpoint state should preserve it consistently, following the existing pattern for `approvals`, `external_observations`, `agents`, `workers`, `workspaces`, and retry/cancel/supersede read models.

## 6. Versioning Rules

Minimal rules:

- Registry changes are new versions.
- Policy profile changes are new versions.
- Old events keep their original `registry_version` / `policy_version`.
- A run should not silently switch registry/profile versions mid-action.
- If a run intentionally switches versions, that switch must be canonical-event visible.
- Unknown version during replay should fail closed or enter controlled compatibility path, not silently use current defaults.

## 7. Reason Code Boundary

`reason_codes` should become stable identifiers:

- lower_snake_case strings
- documented in a small taxonomy
- stable across prose wording changes
- safe for tests and clients to assert

Allowed:

- `reason_codes: ["capabilities_reduced"]`
- `reason_codes: ["unsupported_tool"]`

Not enough:

- `reason: "the tool was not okay because ..."` as the only machine-readable reason
- localized prose as reason code
- exception repr as reason code

## 8. Deferred

Explicitly deferred:

- full migration framework
- plugin marketplace
- dynamic plugin loading
- remote registry loading
- signed registry bundles
- policy DSL
- product policy UI
- multi-tenant policy profile management
- backward-compatible schema migration engine
- content-addressed registry bundle store
- hosted registry service
- real LLM tool calling integration
- domain pack / tool pack marketplace

## 9. First Green Slice Evidence

Implemented test files:

- `tests/isotope_kernel/test_action_registry_version_basis.py`
- `tests/isotope_kernel/test_policy_profile_version_basis.py`

Coverage in `test_action_registry_version_basis.py`:

- `ActionProposal` or equivalent proposed action summary records registry basis.
- `action.proposed` canonical event includes registry version metadata.
- custom registry version appears in projected `RunState.actions`.
- replay recovers the same registry basis.
- checkpoint-assisted rebuild recovers the same registry basis if `RunState.actions` exposes it.
- unknown action type still fail closed.
- changing current default registry does not alter old event replay.
- registry entry version is metadata-only and cannot carry executable callback.

Coverage in `test_policy_profile_version_basis.py`:

- `PolicyDecision` records `policy_profile_id` and `policy_version` or equivalent basis metadata.
- `action.decided` canonical event includes policy profile/version metadata.
- approved / modified / denied decisions expose stable `reason_codes`.
- executor uses decision grants snapshot, not current mutable policy profile.
- replay recovers policy basis and reason codes.
- checkpoint-assisted rebuild recovers policy basis if action summaries expose it.
- changing current default policy profile does not alter old event replay.
- unknown future policy profile fails closed or returns controlled compatibility error.

## 10. Stop Conditions For Implementation

Stop before implementation if a future slice requires:

- real plugin system / marketplace
- remote registry loading
- policy DSL
- full schema migration framework
- changing executor grants semantics
- changing event store append-only semantics
- dynamic action execution from registry entries
- product policy UI / auth / tenant management

## 11. Decision

Policy Profile / Action Registry Versioning first slice is now complete / closed for now at metadata / event payload / read-model validation scope. Closure review is recorded in `docs/policy-registry-version-basis-closure-review.md`.

The safe next step is Retry / Cancel / Supersede Runtime Integration Boundary if continuing kernel work. Do not move from this slice into plugin loading, policy DSL, marketplace, remote registry loading, product policy UI, or migration framework without a new explicit boundary.
