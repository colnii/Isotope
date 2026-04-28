# ActionTypeRegistry v0.1

状态：draft

本文定义 `ActionTypeRegistry` 的最小边界。当前已实现 minimal registry module，但尚未接入 `ActionCompiler` / `PolicyEngine` / `Executor`；仍不引入 plugin system，不改变现有 action chain。

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

- `ActionCompiler` 可以把 compact intent 编译为 canonical `ActionProposal`。
- `PolicyEngine` 当前知道 `write_artifact_tool` 等有限工具。
- `Executor` 当前能执行 deterministic `write_artifact_tool`。
- `ActionProposal -> PolicyDecision -> ActionExecution -> canonical events` 已有最小链路。
- action/tool metadata 已有最小集中 registry module：`src/isotope_kernel/action_registry.py`。
- `ActionTypeEntry` 是当前 v0 slice 的最小 metadata model。
- `ActionTypeRegistry.default()` 当前只包含 `call_tool` + `write_artifact_tool`。
- `registry.tool_names()` 返回 `["write_artifact_tool"]`。
- `registry.get_tool("write_artifact_tool")` 返回 metadata entry。
- unknown tool lookup fail closed，抛 `KeyError`。
- malformed registry entry fail fast。
- registry entry 只包含 metadata，不携带 executable side-effect callback 字段。
- registry 尚未接入 `ActionCompiler` / `PolicyEngine` / `Executor`。
- checkpoint v0.1 已 frozen for current kernel slice；下一阶段建议先推进 registry boundary，而不是继续深挖 checkpoint。

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

下一轮 implementation 应只推进 compiler lookup：

- `ActionCompiler` 用 registry 校验 action/tool 是否存在。
- unknown compact tool 在 compiler boundary fail closed。
- compiler 仍只能产出 canonical `ActionProposal`，不能让 raw intent 绕过 action chain。

仍然不引入：

- 不引入 dynamic loading
- 不引入 third-party plugins
- 不引入 remote execution

## Module Boundary

registry 可能被三个模块读取，但职责不同：

- `ActionCompiler`：用 registry 校验 action/tool 是否存在、payload 是否足够形成 proposal。
- `PolicyEngine`：用 registry 读取 required capabilities，但仍由 policy 决定 grants。
- `Executor`：用 registry 解析 handler，但只能执行 grants 允许的 handler。

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

下一轮 red tests 建议优先覆盖：

- `ActionCompiler` accepts an optional registry or otherwise uses the default registry.
- compiler rejects unknown compact `tool` via registry lookup.
- compiler rejects unsupported compact `action` without bypassing canonical `ActionProposal`.
- compiler keeps runtime identity sourced from runtime context, not intent.
- compiler does not grant capabilities; it only forms requested capabilities.
- registry remains limited to `call_tool` + `write_artifact_tool` for this slice.
- `PolicyEngine` uses registry requirements but still produces grants itself.
- `Executor` uses registry handler lookup but still executes only with `PolicyDecision.grants`.
- no dynamic loading, no plugin discovery, no public extension API.

不要在没有 red tests 前直接实现 full plugin system、remote registry、schema registry、real LLM tool calling 或 third-party tool loading。
