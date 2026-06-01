# Tool Protocol Closure Review

状态：`first slice complete / closed for now`

本文记录 Tool Protocol first slice 的 closure review。目标是确认当前 slice 是否足以关闭为 v0.2 kernel boundary，同时避免把它误写成完整 tool runtime、plugin system 或 public SDK。

## Closure Judgment

Tool Protocol first slice 可以标为 `first slice complete / closed for now`。

当前 slice 已覆盖：

- `src/isotope/tool_protocol.py` 提供最小 `ToolInvocation` / `ToolResult` / `ToolError` validation models。
- `ToolInvocation` 固定 tool name、input payload、execution / proposal / decision provenance、effective grants snapshot、optional budget 和 optional workspace binding shape。
- `ToolResult` 固定 summary / structured artifact `ResourceRef` / diagnostics / provenance shape。
- `ToolError` 固定 stable `error_reason_code`、message、partial artifact refs 和 provenance shape。
- `Executor` 仍只使用 `PolicyDecision.grants`，requested capabilities 不能提升实际执行权限。
- successful deterministic tool path 仍通过 `artifact.created` / `action.completed` canonical events handoff。
- `artifact.created` provenance 现在包含 `execution_id`、`proposal_id` 和 `decision_id`。
- failed tool path 现在通过 structured `action.failed` 记录 `error_reason_code` 和 `structured_error`。
- malformed artifact refs、ungranted tools、unsupported tools 和 overreach surfaces fail closed。

## Important Scope Note

不要 overclaim runtime integration。

当前 slice 是 **tool protocol model + event-shape first slice**，不是 fully wired tool invocation runtime。

Specifically:

- `Executor` 尚未构造 `ToolInvocation` 对象并把它传入 tool implementation。
- current successful execution paths are deterministic `write_artifact_tool` and separately bounded controlled `terminal_exec` handlers。
- `ToolResult` / `ToolError` 当前是 bounded model shape，用于固定未来 helper / runtime boundary，不是 public SDK。
- tool implementation registry 仍未实现，也不应被 `ActionTypeRegistry` 替代。
- `terminal_exec` 是 allowlisted argv-only local subprocess first slice，不是 interactive shell、general process tool、sandbox/container、remote executor 或 product terminal route；边界见 `controlled-terminal-execution-boundary-v0.2.md`。

这不是 correctness bug；这是本 slice 的有意边界。未来只有当 application-layer friction 证明需要时，才应该把 `ToolInvocation` wiring 作为新 batch。

## Evidence

Implementation evidence:

- `src/isotope/tool_protocol.py`
- `src/isotope/executor.py`
- `src/isotope/artifact_store.py`
- `src/isotope/projector.py`
- `tests/isotope/test_tool_protocol_boundary.py`
- `tests/isotope/test_tool_result_event_boundary.py`

Verification evidence on the Mac mini checkout:

```bash
export DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}

.venv/bin/python -m pytest \
  tests/isotope/test_tool_protocol_boundary.py \
  tests/isotope/test_tool_result_event_boundary.py \
  -q
# 17 passed

.venv/bin/python -m pytest tests/isotope -q
# 1003 passed

.venv/bin/python -m isotope.demo --scenario artifact-review --trace
.venv/bin/python -m isotope.demo --scenario approval-tool-runner --trace
```

Both trace demos passed and kept deferred routes / full-content boundaries closed.

## Boundary Confirmations

No overreach was found:

- No plugin marketplace.
- No dynamic plugin loading.
- No remote tool execution.
- No sandboxed tool process.
- No streaming tool output.
- No public tool SDK.
- No new project dependency.
- No real LLM tool-calling integration.
- No product tool route.

No kernel semantics were changed outside the intended boundary:

- Event store append-only semantics remain unchanged.
- Executor grants semantics remain unchanged.
- Projector still derives native state from canonical events only.
- Artifact full content still does not enter native `RunState`.
- HTTP full-content route remains `not_enabled`.

## Remaining Friction

Remaining friction is intentionally deferred:

- executor does not yet build and pass a `ToolInvocation` object to handler code.
- `ToolResult` is not yet the executor's internal success return object.
- `ToolError` is not yet the executor's internal exception / failure transport object.
- reason-code taxonomy is still narrow: `tool_execution_failed` covers current controlled failure path.
- future tools may need stricter input/output schemas, but that should be driven by real app-layer pressure.

## Next Suggested Path

Default next path: return to `Application-Layer Friction Intake`.

If continuing kernel work explicitly, prefer one of:

- `Worker Handoff App Spike Selection`, because worker handoff will pressure tool / artifact / workspace / delegation together.
- `Tool Invocation Runtime Wiring Boundary`, but only if app-layer or worker-handoff friction proves that executor should construct `ToolInvocation` as a runtime object.

Do not start plugin marketplace, remote tools, sandboxed process, streaming output, public SDK, real filesystem tool substrate, real LLM tool calling, real HTTP server, or tag/release work from this closure review.
