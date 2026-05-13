# Tool Protocol Boundary v0.2

状态：`first slice complete / closed for now`

## 1. Purpose

本文定义 v0.2 后续 Tool Protocol（工具协议）的最小 kernel contract。目标不是实现 plugin system、remote tool、sandboxed process 或 public tool SDK，而是在更多 application-layer tools 出现前，先固定工具如何被授权、调用、记录结果、表达错误、绑定 artifact / workspace / provenance，以及如何继续遵守 canonical event log 和 projector-only read model 边界。

当前已有：

- `ActionCompiler`
- `ActionTypeRegistry`
- `PolicyEngine`
- `Executor`
- deterministic `write_artifact_tool`
- controlled `terminal_exec` first slice, documented separately in `docs/controlled-terminal-execution-boundary-v0.2.md`
- `InProcessServer.create_source_artifact(...)`
- `InProcessServer.submit_action(...)`
- `approval-tool-runner` / `artifact-review` demos

Closure review: `docs/tool-protocol-closure-review.md`.

Scope note: 当前 closure 只关闭 **tool protocol model + event-shape first slice**。`Executor` 还没有把 `ToolInvocation` 对象作为 runtime invocation object 传给 tool implementation；当前 successful paths 是 deterministic `write_artifact_tool` handler 和 separately bounded controlled `terminal_exec` handler。不要把本 slice 写成 plugin system、remote tool、sandboxed process、streaming output、public SDK 或 fully wired tool runtime。

当前缺口：

- tool input validation 还主要散落在 action compiler / executor handler 中。
- tool output 到 artifact / event / read model 的边界还没有单独命名。
- tool error 需要固定为 controlled action failure，而不是半写 artifact 或隐藏 side effect。
- budget / grants / workspace binding 如何传给 tool 还没有统一 shape。
- tool implementation registry 和 `ActionTypeRegistry` 的关系需要先定义，避免把 metadata registry 误解成 plugin marketplace。

## 2. Definitions

### Tool

`Tool` 是由 executor 在 approved action path 下调用的 deterministic 或 side-effect-capable unit。Tool 不是 agent identity，也不是 product plugin。Tool 只能在已有 action / policy / executor chain 下运行。

### Tool Invocation

`Tool Invocation` 是一次具体工具调用。它必须来源于 canonical `ActionProposal`、`PolicyDecision` 和 `ActionExecution`，并携带：

- tool name
- input payload
- effective grants snapshot
- optional workspace binding
- budget
- provenance basis

### Tool Result

`Tool Result` 是 tool 成功后的受控输出。它可以包含 result summary、artifact refs、diagnostics 和 provenance，但不能直接修改 `RunState` / `SessionState`。

### Tool Error

`Tool Error` 是 tool failure 的结构化表达。它应进入 controlled `action.failed` / structured error path，并带 stable reason code；不能留下半写 artifact 或 hidden native state。

### Tool Capability

`Tool Capability` 是 policy 可判断和 grant 的能力，例如允许某个 tool、workspace mode、artifact write、content retrieval 或 budget class。Tool 可以请求 capability，但 executor 只能使用 `PolicyDecision.grants` 中的 effective capabilities。

### Tool Provenance

`Tool Provenance` 是 tool invocation / result / error 的来源链。最小应能追到：

- `execution_id`
- `proposal_id`
- `decision_id`
- `action_type`
- `tool_name`
- registry basis
- policy profile basis

### Tool Budget

`Tool Budget` 是传给 tool 的显式限制，例如 items、bytes、time slice、token-like quota 或 retry count。v0.2 中 budget 只是 invocation data；它不代表 scheduler、timeout engine、retry backoff engine 或 process control 已实现。

## 3. Hard Contracts

Tool protocol 必须遵守：

- Executor 只能通过 `PolicyDecision.grants` 调 tool。
- Tool 不能直接修改 `RunState` / `SessionState`。
- Tool output 必须通过 canonical events / artifact store / `ResourceRef` 进入 read model。
- Tool failure 必须变成 controlled `action.failed` / structured error，不允许半写 artifact。
- Tool input / output schema 是 implementation shape，不是永久 public protocol。
- Tool 不能自己扩大 workspace / memory / external ingestion / artifact content 权限。
- Tool provenance 必须能追到 `execution_id` / `proposal_id` / `decision_id`。
- Tool 不能绕过 event store append-only semantics。
- Tool 不能直接写 checkpoint 或 projector native state。
- Unknown / disabled / ungranted tool 必须 fail closed。
- Tool result 中的 artifact refs 必须是 structured `ResourceRef`，不是 raw file path 或 full content blob。

## 4. Minimal v0.2 Shape

最小 `ToolInvocation` shape 可以包含：

| Field | Meaning |
| --- | --- |
| `tool_name` | executor-visible tool identity |
| `input_payload` | compiler-validated payload passed to tool |
| `grants_snapshot` | effective `PolicyDecision.grants` snapshot |
| `workspace_binding` | optional projected binding / lease summary if grants allow workspace access |
| `budget` | explicit limits passed as data |
| `provenance` | execution / proposal / decision / registry / policy basis |

最小 success `ToolResult` shape 可以包含：

| Field | Meaning |
| --- | --- |
| `result_summary` | human / client readable summary without hidden raw content |
| `artifact_refs` | structured `ResourceRef` list created or handed off by tool |
| `diagnostics` | optional bounded diagnostics |
| `provenance` | same invocation basis plus result event basis |

最小 failure `ToolError` shape 可以包含：

| Field | Meaning |
| --- | --- |
| `error_reason_code` | stable identifier such as `tool_input_invalid`, `tool_not_granted`, `tool_execution_failed` |
| `message` | bounded human-readable detail |
| `partial_artifact_refs` | should normally be empty; if ever non-empty it must be explicitly event-backed and tested |
| `provenance` | invocation basis and failure event basis |

First-slice recommendation:

- keep successful tool implementations explicitly bounded: deterministic `write_artifact_tool` and controlled `terminal_exec`.
- do not introduce streaming output.
- do not introduce arbitrary filesystem / general process / remote side effects beyond the controlled `terminal_exec` first slice.
- do not expose public tool SDK.

## 5. Registry Relationship

`ActionTypeRegistry` and a future tool implementation registry have different jobs.

`ActionTypeRegistry` declares whether an action / tool type can be recognized by compiler / policy / executor. It may record metadata such as:

- `action_type`
- `tool_name`
- payload requirements
- required capabilities
- default workspace mode
- result kind
- enabled / disabled
- registry basis

It must not:

- contain executable plugin callbacks.
- grant permissions.
- bypass `ActionCompiler`.
- bypass `PolicyEngine`.
- bypass `Executor`.
- mutate event log / artifact store / workspace / memory.

A future tool implementation registry, if introduced, should be a narrow in-process map from `tool_name` to a vetted implementation function. That registry still must not be a plugin marketplace, remote loader, dynamic package loader, public extension API, or policy engine.

Registry basis remains important:

- `ActionProposal` records action registry basis.
- `PolicyDecision` records policy profile basis.
- executor executes the decision grants snapshot.
- replay should interpret events from recorded basis metadata, not from whatever default registry happens to exist later.

## 6. Interaction With Existing Boundaries

### Policy

Policy decides effective grants. Tool implementation receives grants as a snapshot and cannot re-query mutable policy to expand authority.

### Workspace

Tool receives workspace access only if grants and read model binding allow it. Tool cannot upgrade `shared_ro` to write / isolated mode. Real filesystem workspace remains deferred.

### Artifact

Tool result handoff must use artifact summary / `ResourceRef` / provenance. Full content does not enter native `RunState`, and HTTP full-content route remains `not_enabled` unless Track C is explicitly reopened.

### Approval

Approval-gated tool action remains pending until approval resolves. Tool cannot execute pending / denied action.

### Retry / Cancel / Supersede

Tool protocol does not implement scheduler, process kill, timeout engine, or cancellation hooks. R/C/S runtime helpers may mark logical lifecycle state, but tool-level cancellation remains deferred.

### Event Schema

Tool result / error currently uses existing canonical `artifact.created` and `action.failed` event paths. Unknown future tool event types must fail closed unless the event schema registry explicitly supports them.

## 7. Deferred

Explicitly deferred:

- plugin marketplace
- dynamic plugin loading
- remote tools
- public tool SDK
- tool discovery API
- streaming tool output
- sandboxed tool process
- real filesystem tool substrate
- binary file streaming
- tool cancellation hook
- tool retry / backoff engine
- timeout engine
- distributed tool execution
- real LLM tool calling integration
- product tool UI / auth / marketplace

## 8. First Red Tests Recommendation

Recommended new test files:

- `tests/isotope_kernel/test_tool_protocol_boundary.py`
- `tests/isotope_kernel/test_tool_result_event_boundary.py`

Recommended coverage for `test_tool_protocol_boundary.py`:

- executor invokes a tool only when `PolicyDecision.grants` include the required tool capability.
- tool receives effective grants snapshot, not requested capabilities.
- unknown / disabled / ungranted tool fails closed.
- tool invocation carries `tool_name`, input payload, budget and provenance.
- tool cannot mutate `RunState` / `SessionState` directly.
- tool cannot upgrade workspace / memory / external ingestion / artifact content permissions.
- current implementation does not expose plugin marketplace, remote registry, public SDK, sandbox process or new dependency.

Recommended coverage for `test_tool_result_event_boundary.py`:

- successful tool result enters read model through canonical artifact / event / `ResourceRef` path.
- failure appends controlled `action.failed` with stable reason code.
- failed tool does not leave half-written artifact or `action.completed`.
- malformed tool output fails fast.
- artifact refs are structured and do not embed full content.
- replay and checkpoint-assisted rebuild preserve result summaries from canonical events.
- projector never reads workspace files or raw tool output to advance native state.

## 9. Stop Conditions For Implementation

Stop before implementation if a future slice requires:

- plugin marketplace or dynamic plugin loading.
- remote tool execution.
- real sandbox / process isolation.
- real filesystem mutation.
- streaming tool output.
- public tool SDK.
- policy DSL or new permission language.
- changing event store append-only semantics.
- changing executor grants semantics.
- letting tools mutate `RunState` / `SessionState`.
- new dependency.

## 10. Current Decision

Tool Protocol first slice is now complete / closed for now at the minimal in-process boundary:

- `src/isotope_kernel/tool_protocol.py` defines `ToolInvocation`, `ToolResult` and `ToolError` validation models.
- `artifact.created` event provenance now includes `execution_id`, `proposal_id` and `decision_id`.
- `action.failed` now carries `error_reason_code` and `structured_error`.
- executor still uses only `PolicyDecision.grants`, and ungranted / unsupported tools fail closed before successful side effects.
- closure review records this as a model / event-shape first slice, not a fully wired executor invocation runtime.

Still not implemented:

- plugin marketplace
- dynamic plugin loading
- remote tools
- sandboxed tool process
- streaming output
- public tool SDK
- new dependency

Recommended next step:

1. Return to application-layer friction intake / external review feedback intake.
2. Reopen tool runtime wiring only if concrete friction proves executor should construct and pass `ToolInvocation` objects to handlers.
