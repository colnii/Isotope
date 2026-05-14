# Tool Invocation Runtime Wiring Boundary v0.2

状态：`green slice complete / pushed`

本文记录从 aggressive-dev `tool.protocol.runtime.review` 回流的 bounded `kernel_friction`：`tool_invocation_runtime_missing`。

## Accepted Friction

此前 mainline 已有 `ToolInvocation` / `ToolResult` / `ToolError` model 和 event-shape first slice，但 `Executor.execute(...)` 成功路径只 special-case `write_artifact_tool`。当 app-layer 注册 metadata-only `app_probe_tool` 时，即使 policy grants 已包含该 tool，executor 仍以 `unsupported handler for tool app_probe_tool` fail closed。

这说明缺口不是 plugin marketplace、remote executor 或 public SDK，而是一个更窄的 runtime wiring gap：

- executor 能接收 optional explicit deterministic in-process handler map：`tool_handlers={...}`。
- `InProcessServer` facade 能接收同一 `tool_handlers` map 并转发给 `Executor`。
- executor 从 `ActionProposal`、`PolicyDecision`、execution id、effective grants、budget 和 workspace binding 构造 `ToolInvocation`。
- handler 只收到 capped effective capabilities，不能从 `requested_capabilities` 扩权。
- ungranted / disabled / unknown tool 仍在 handler 运行前 fail closed。
- empty `ToolResult.artifact_refs` 不能让 facade response 泄漏同一 run 里较早 artifact 的 stale `artifact_ref`。

## Verification

Red-to-green path:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_tool_invocation_runtime_wiring.py -q
# before implementation: 2 failed, 1 passed
# after implementation: 3 passed
```

Focused regression:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/isotope/test_tool_invocation_runtime_wiring.py \
  tests/isotope/test_tool_protocol_boundary.py \
  tests/isotope/test_tool_result_event_boundary.py \
  tests/isotope/test_executor_registry_integration.py \
  -q
# 27 passed
```

Full local regression should still be run before commit / push.

## Non-Goals

This slice must not introduce:

- plugin marketplace
- dynamic plugin loading
- remote tool execution
- sandboxed process
- public SDK
- provider adapter
- real HTTP route
- filesystem / container / git worktree substrate
- new dependency
- tag or release

## Implemented Slice

Implemented:

- add optional `tool_handlers` to `Executor`.
- add optional `tool_handlers` to `InProcessServer` and forward it to `Executor`.
- preserve existing deterministic `write_artifact_tool` behavior.
- for non-`write_artifact_tool` registered tools, require an explicit handler.
- construct and pass `ToolInvocation` with decision grants snapshot, capped requested capabilities, budget, provenance, and projected workspace binding.
- convert `ToolResult` to controlled `ActionExecution` completion without native read-model mutation outside canonical events.
- derive facade `artifact_ref` response from the current `action.completed.artifact_refs`, not from latest artifact in the whole run.
