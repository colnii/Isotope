# ActionTypeRegistry v0.1

状态：draft

本文定义 `ActionTypeRegistry` 的最小边界。当前已实现 minimal registry module，并已接入 `ActionCompiler`、`PolicyEngine` requirement lookup、`Executor` handler lookup 和 `InProcessServer` wiring；不引入 plugin system，不改变现有 action chain。

## Purpose

`ActionTypeRegistry` 的目的，是让 runtime 知道某个 `action_type` / tool 是否存在、需要什么最小 payload shape、需要哪些 capability grants、由哪个 executor / tool handler 处理。

它服务于当前 action path：

- `ActionProposal -> PolicyDecision -> ActionExecution -> canonical events`

它不是：

- plugin marketplace。
- public extension API。
- remote tool registry。
- schema registry 总线。
- policy engine 替代品。
- executor 替代品。
- real LLM tool calling integration。

## Current State

当前实现里：

- `ActionCompiler` 可以把 compact intent 编译为 canonical `ActionProposal`，并已使用 registry lookup 校验 compact tool / action type / payload requirements。
- `PolicyEngine` 已使用 registry requirement lookup，但仍自己决定 grants。
- `Executor` 已使用 registry handler lookup，但当前仍只执行 deterministic `write_artifact_tool` handler。
- `ActionProposal -> PolicyDecision -> ActionExecution -> canonical events` 已有最小链路。
- action/tool metadata 已有最小集中 registry module：`src/isotope_kernel/action_registry.py`。
- `ActionTypeEntry` 是当前 v0 slice 的最小 metadata model。
- `ActionTypeRegistry.default()` 当前只包含 `call_tool` + `write_artifact_tool`。
- `registry.tool_names()` 返回 `["write_artifact_tool"]`。
- `registry.get_tool("write_artifact_tool")` 返回 metadata entry。
- unknown tool lookup fail closed，抛 `KeyError`。
- malformed registry entry fail fast。
- registry entry 只包含 metadata，不携带 executable side-effect callback 字段。
- registry 已接入 `ActionCompiler`。
- `ActionCompiler(registry=...)` 可显式传入 registry。
- 不传 registry 时，`ActionCompiler` 使用 `ActionTypeRegistry.default()`。
- `ActionCompiler` 支持 registry-backed non-`call_tool` action type，只要 `intent.action` 与 registry entry `action_type` 匹配。
- `ActionCompiler` 会检查 registry `payload_requirements.required`。
- valid `write_memory` intent 会保留 structured payload：`content`、`summary`、`source_refs`、`provenance`。
- unknown compact tool 当前先在 compiler boundary 受控 `ValueError` fail closed。
- disabled registry entry 会被 compiler 拒绝。
- compiler 仍只生成 requested capabilities，不生成 grants。
- runtime identity 仍只来自 runtime context。
- registry 已接入 `PolicyEngine` requirement lookup。
- `PolicyEngine(registry=...)` 可显式传入 registry。
- 不传 registry 时，`PolicyEngine` 使用 `ActionTypeRegistry.default()`。
- `PolicyEngine` 不再硬编码只接受 `call_tool`；registry-backed `write_memory` proposal 可以进入 policy decision。
- registry-known tool 只有在 proposal requested capabilities 请求该 tool 时才可能被 policy approve。
- registry 不能自动批准 action，也不能扩大 `PolicyDecision.grants`。
- policy 仍负责缩权：extra tool、更高 workspace request、超额 budget 会被 reduced / modified。
- registry 已接入 `Executor` handler lookup。
- `Executor(..., registry=...)` 可显式传入 registry。
- 不传 registry 时，`Executor` 使用 `ActionTypeRegistry.default()`。
- executor 仍只能使用 `PolicyDecision.grants`。
- registry 不能替代 grants，也不能提供 executable callback。
- 当前 executor 仍只有 deterministic `write_artifact_tool` handler。
- registry-known tools without a current slice handler fail closed as unsupported handler.
- registry 已接入 `InProcessServer` wiring。
- `InProcessServer(root, registry=...)` 可显式传入 registry。
- 不传 registry 时，`InProcessServer` 创建一个 shared default registry，并传给 compiler / policy / executor。
- custom registry 可以贯穿 compiler / policy / executor，但 server 不会动态执行未知工具。
- registry-known tools without a current slice handler still fail controlled at executor boundary.
- checkpoint v0.1 已 frozen for current kernel slice；下一阶段建议先做 deferred boundary review，决定转向 memory write/query boundary 还是 external ingestion / `ImportedSnapshot` boundary，而不是继续深挖 checkpoint。

## Hard Boundaries

- registry 不能绕过 action chain。
- registry 不能直接批准 action。
- registry 不能扩大 `PolicyDecision.grants`。
- executor 仍只能使用 `PolicyDecision.grants`。
- policy decision 仍是最终授权边界。
- registry 只能描述 action/tool capability requirement，不能代替 policy。
- registry entry 不能直接修改 event log。
- registry entry 不能直接写 memory / artifact / workspace。
- 实际 side effect 仍必须由 executor 在 grants 下执行。
- unknown action/tool 必须 fail closed。
- malformed registry entry 必须 fail fast。
- registry 不定义永久 public protocol；当前只是 v0 implementation boundary。

## v0 Candidate

最小 registry entry 可以包含：

- `action_type`
- `tool_name` 或 handler id
- `payload_requirements`
- `required_capabilities`
- `default_workspace_mode`
- `result_kind`
- `enabled`

这些字段名只是 v0 candidate / schema sketch，不是稳定协议。

当前第一轮 implementation 已覆盖：

- `call_tool` + `write_artifact_tool`
- unknown tool fail-closed lookup
- malformed registry entry fail-fast
- metadata-only registry entry without executable side-effect callbacks

当前 compiler lookup integration 已覆盖：

- `ActionCompiler` 用 registry 校验 action/tool 是否存在。
- `ActionCompiler` 允许 registry-backed non-`call_tool` action type，只要 compact intent action 匹配 registry entry `action_type`。
- `ActionCompiler` 执行 registry `payload_requirements.required` 校验。
- `ActionCompiler` 对 valid `write_memory` intent 保留 structured `content`、`summary`、`source_refs`、`provenance` payload。
- unknown compact tool 在 compiler boundary fail closed。
- compiler 仍只能产出 canonical `ActionProposal`，不能让 raw intent 绕过 action chain。
- explicit registry dependency injection and default registry fallback.
- disabled registry entry rejection.

当前 policy lookup integration 已覆盖：

- `PolicyEngine` 读取 registry required capabilities。
- `PolicyEngine` 允许 registry-backed non-`call_tool` proposal 进入 policy decision，只要 proposal action_type 与 registry entry action_type 匹配。
- policy 仍由自己决定 grants，不能因为 registry entry 存在就自动 approve。
- unknown registry tool 在 policy boundary denied，不抛未受控异常。
- disabled registry entry 不会被 policy approve。
- registry 不能凭空把未 requested 的 tool 加入 grants。

当前 executor lookup integration 已覆盖：

- `Executor` 使用 registry 做 handler lookup。
- executor 仍只能使用 `PolicyDecision.grants`。
- registry entry 不能携带 executable side-effect callback。
- unknown granted tool 在 executor boundary fail closed，不继续使用 hardcoded tool error。
- disabled registry entry 不会被 executor 执行。
- registry-known tool 如果没有当前 slice handler，会受控 fail closed。
- successful `write_artifact_tool` execution event order remains `action.started`, `artifact.created`, `action.completed`.

当前 server wiring integration 已覆盖：

- `InProcessServer` 可显式接收 registry。
- `InProcessServer` 不传 registry 时使用一个 shared default registry，而不是让 compiler / policy / executor 各自隐式创建不同 registry。
- server 将同一个 registry 传给 `ActionCompiler` / `PolicyEngine` / `Executor`。
- disabled registry entry 在 compiler boundary fail closed，不写 action lifecycle events 或 artifact。
- custom registry-known tool 可以贯穿 compiler / policy / executor；如果没有当前 executor handler，会受控 `action.failed`，不会写 `artifact.created` / `action.completed` / `run.completed`。
- server 不把 registry 变成 dynamic plugin system。

下一轮 implementation 不应默认继续扩展 registry handler；应先选择：

- deferred boundary review。
- memory write/query boundary。
- external ingestion / `ImportedSnapshot` boundary。

仍然不引入：

- 不引入 dynamic loading
- 不引入 third-party plugins
- 不引入 remote execution

## Module Boundary

registry 可能被三个模块读取，但职责不同：

- `ActionCompiler`：用 registry 校验 action/tool 是否存在、payload 是否足够形成 proposal。
- `PolicyEngine`：用 registry 读取 required capabilities，但仍由 policy 决定 grants。
- `Executor`：用 registry 解析 handler，但只能执行 grants 允许的 handler。
- `InProcessServer`：只负责把同一个 registry 注入 compiler / policy / executor，不直接解释 registry state 或动态执行未知工具。

关键分工：

- compiler 使用 registry 做输入边界，不授予能力。
- policy 使用 registry 做 capability requirement lookup，不自动批准。
- executor 使用 registry 做 handler lookup，不扩大 grants。

## Invalid Uses

以下用法明确无效：

- registry entry 直接产生 `PolicyDecision`。
- registry entry 直接产生 `ActionExecution`。
- registry entry 直接 append canonical events。
- registry entry 直接写 artifact / memory / workspace。
- registry entry 因为 tool exists 就默认 grant tool execution。
- registry 被 server 或 public client 当作 extension API。
- registry 变成 dynamic plugin loader。
- registry 跳过 existing `ActionCompiler` / `PolicyEngine` / `Executor` 边界。
- server 用 registry entry 动态执行未知 tool。

## Deferred

继续 deferred：

- plugin system。
- dynamic action registration。
- third-party tools。
- remote tool discovery。
- schema registry integration。
- per-domain tool pack loading。
- version migration。
- public extension API。
- UI / marketplace。
- real LLM tool calling integration。
- action result schema registry。
- payload schema registry。

## Future TDD Notes

已完成的第一批 tests 覆盖：

- `ActionTypeRegistry` exists with a default v0 registry.
- default registry contains only `call_tool` + `write_artifact_tool` for the current slice.
- malformed registry entries fail fast.
- unknown tool lookup fails closed.
- registry entry does not expose executable side-effect callback fields.

已完成的 compiler integration tests 覆盖：

- `ActionCompiler` accepts an optional registry or otherwise uses the default registry.
- compiler rejects unknown compact `tool` via registry lookup.
- compiler rejects unsupported compact `action` without bypassing canonical `ActionProposal`.
- compiler keeps runtime identity sourced from runtime context, not intent.
- compiler does not grant capabilities; it only forms requested capabilities.
- registry remains limited to `call_tool` + `write_artifact_tool` for this slice.

已完成的 policy integration tests 覆盖：

- `PolicyEngine` uses registry requirements but still produces grants itself.
- `PolicyEngine(registry=...)` accepts an explicit registry or otherwise uses the default registry.
- unknown / disabled registry tools cannot be approved.
- registry cannot auto-approve actions or expand `PolicyDecision.grants`.

已完成的 executor integration tests 覆盖：

- `Executor` accepts an optional registry or otherwise uses the default registry.
- executor uses registry handler lookup but still executes only with `PolicyDecision.grants`.
- unknown / disabled registry tools fail closed at executor boundary.
- registry-known tools without the current deterministic handler fail closed as unsupported handler.
- registry-backed `write_artifact_tool` success keeps executor-owned event order unchanged.

已完成的 server wiring tests 覆盖：

- `InProcessServer` accepts an explicit registry.
- server uses one shared default registry when no registry is passed.
- disabled registry entry fails closed at compiler boundary before action lifecycle events.
- custom registry can flow through compiler / policy / executor.
- registry-known tools without current handler fail controlled and do not create artifacts or complete the run.
- registry does not create a server dynamic plugin system.

下一轮 red tests 建议优先覆盖：

- deferred boundary review before choosing memory write/query or external ingestion.
- no dynamic loading, no plugin discovery, no public extension API.

不要在没有 red tests 前直接实现 full plugin system、remote registry、schema registry、real LLM tool calling 或 third-party tool loading。
