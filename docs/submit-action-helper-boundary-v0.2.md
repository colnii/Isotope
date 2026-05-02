# Submit Action Helper Boundary v0.2

状态：`first slice complete`

## 1. Purpose

`submit_action(...)` 是一个 in-process server helper，用来降低 `approval-tool-runner` spike 里 raw `submit_tool_request(...)` 的 friction。

它不是 product API，不是 real HTTP route，也不是新的 action engine。它只是把 compact action intent（紧凑动作意图）送进现有 canonical action chain（标准动作链）。

## 2. Current Problem

helper 落地前，demo/client 为了表达 approval-gated action，需要调用：

```python
server.submit_tool_request(
    run_id,
    tool="write_artifact_tool",
    text="...",
    requires_approval=True,
)
```

这条路径语义正确，但 developer ergonomics 不理想：

- helper name 太 tool-specific。
- caller 需要知道 tool request 低层参数。
- pending approval result 不直接暴露 compact id summary。
- demo JSON 需要把 raw helper friction 记录出来。

## 3. Proposed Minimal Helper

```python
server.submit_action(
    run_id,
    {
        "action": "call_tool",
        "tool": "write_artifact_tool",
        "text": "approval-gated tool output",
    },
    requires_approval=True,
)
```

第一 slice 只支持现有 `call_tool` compact intent。不要泛化成 product action API。

当前实现：

- `InProcessServer.submit_action(...)`
- `submit_tool_request(...)` 保持兼容，并共用内部 submission path
- `approval-tool-runner` demo 已改用 `submit_action(...)`
- full regression after green: `865 passed`

## 4. Required Semantics

`submit_action(...)` must:

- validate `run_id`
- validate compact intent through `ActionCompiler`
- append canonical `action.proposed`
- call `PolicyEngine.decide(...)`
- use `PolicyDecision.grants`, not requested capabilities
- append canonical `action.decided`
- if outcome is `denied`, return denied summary and create no execution / artifact
- if `requires_approval=True` and policy did not deny, append `approval.requested`
- if pending approval, return `approval_id` and do not execute
- if approved / modified, execute through existing `Executor`
- if execution succeeds, return `execution_id` and artifact `ResourceRef`
- if execution fails, return controlled failed summary based on executor-owned failure event

## 5. Return Shape

Minimum useful result:

```python
{
    "status": "pending_user_approval" | "completed" | "failed" | "denied",
    "proposal_id": "...",
    "decision_id": "...",
    "approval_id": "...",      # pending only
    "execution_id": "...",     # execution path only
    "artifact_ref": ...,       # artifact path only
    "decision": ...,           # in-process compatibility object, if needed
    "run_state": ...,
}
```

The stable part of the helper contract is the canonical ids and status. Any in-process object returned for compatibility must not leak into demo JSON or HTTP responses as Python repr.

## 6. Compatibility

`submit_tool_request(...)` remains supported.

It may delegate to the same internal path as `submit_action(...)`, but existing callers must still be able to call:

```python
server.submit_tool_request(
    run_id,
    tool="write_artifact_tool",
    text="...",
    requires_approval=True,
)
```

No existing approval resolution, workspace binding, executor, or event store semantics should change.

## 7. Approval Tool Runner Usage

`approval-tool-runner` now uses:

- `submit_action(...)` for approval-gated submission
- `get_pending_approvals(...)` / `get_approval(...)` for approval lookup
- `bind_workspace(...)` for grants-derived workspace binding

The demo should no longer need:

- event scanning for `approval_id`
- manual `workspace.bound` payload append
- raw `submit_tool_request(...)` for approval-gated submission

## 8. Hard Boundaries

The helper must not:

- bypass policy
- bypass approval
- bypass executor
- mutate `RunState` directly
- append non-canonical shortcuts
- use requested capabilities as grants
- open a real HTTP server
- implement real LLM / provider adapter
- mutate filesystem
- spawn process / thread / container / git worktree
- change event store append-only semantics
- change executor grants semantics

## 9. Deferred

Still deferred:

- HTTP product route for approval-gated input
- full tool protocol
- real process execution
- tool cancellation
- scheduler
- approval UI / auth / notification
- provider-backed model loop
- workspace filesystem substrate

## 10. First Slice Test Targets

- compact intent creates canonical `action.proposed` / `action.decided`
- pending approval returns proposal / decision / approval ids
- pending approval creates no execution / artifact
- modified policy uses grants, not requested capabilities
- completed path returns execution id and artifact ref
- existing `submit_tool_request(...)` remains compatible
- `approval-tool-runner` demo uses `submit_action(...)` instead of raw `submit_tool_request(...)`

Current test file:

- `tests/isotope_kernel/test_submit_action_helper.py`
