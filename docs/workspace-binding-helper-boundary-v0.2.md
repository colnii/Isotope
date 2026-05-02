# Workspace Binding Helper Boundary v0.2

状态：`first slice complete`

## 1. Purpose

Workspace binding helper 的目标是减少 demo / client 手写 `workspace.bound` event 的 glue，同时保持 workspace substrate 仍是 boundary-only。

它不是 workspace product API，不是 sandbox，也不是 real filesystem execution。

## 2. Current Inputs

当前已有：

- `WorkspaceManager.get_binding(grants)` validates `workspace.mode == "shared_ro"`。
- executor 使用 `PolicyDecision.grants`，不使用 requested workspace capabilities。
- `workspace.bound` canonical event 可投影到 `RunState.workspaces`。
- `RunState.workspaces` 可 replay / checkpoint-assisted rebuild。
- `approval-tool-runner` 已使用 `InProcessServer.bind_workspace(...)`，不再手写 `workspace.bound` payload。

## 3. Minimal Helper Target

v0.2 helper 只做一件事：

- 从已有 policy decision grants 创建 canonical workspace binding event。

最小 API shape 可以是：

```python
InProcessServer.bind_workspace(
    run_id,
    decision,
    bound_to={"agent_id": "agent_supervisor"},
)
```

返回：

- workspace binding summary from projected `RunState.workspaces`
- JSON-compatible copy
- no internal Python object repr

## 4. Hard Boundaries

- helper must validate run exists。
- helper must use `WorkspaceManager.get_binding(decision.grants)`。
- helper must not use requested workspace capabilities。
- helper must not upgrade `shared_ro` to write / isolated。
- helper must append canonical `workspace.bound` instead of mutating `RunState` directly。
- helper must return projected read model after event append。
- helper must not read or mutate filesystem。
- helper must not create container, git worktree, process, thread, or remote executor。
- helper must not alter event store append-only semantics。
- helper must not alter executor grants semantics。

## 5. Out Of Scope

- HTTP workspace route
- product workspace API
- write / shared_rw / isolated workspace
- path safety engine
- artifact capture from real workspace files
- cleanup scheduler
- rollback / diff engine
- container / git worktree / remote executor
- binary artifact streaming

## 6. First Red Tests

First tests should cover:

- helper creates `workspace.bound` from existing `PolicyDecision.grants`。
- helper returns workspace binding summary。
- helper refuses missing / malformed grants。
- helper refuses unsupported modes such as write / shared_rw / isolated。
- helper cannot use requested workspace mode to upgrade beyond grants。
- helper appends canonical event and projector remains event-sourced。
- helper does not mutate native `RunState` directly。
- helper does not read / write filesystem。
- helper does not add HTTP route unless a later task explicitly opens that scope。

Implemented test file:

- `tests/isotope_kernel/test_workspace_binding_helper.py`

Red result:

- targeted: `6 failed`
- full with red tests: `6 failed, 853 passed`
- failures were from missing `bind_workspace(...)` and demo still calling manual workspace event glue

Green result:

- targeted: `6 passed`
- full regression: `859 passed`

## 7. Implemented First Slice

Implemented API:

```python
InProcessServer.bind_workspace(
    run_id,
    decision,
    bound_to=None,
    lease_status="active",
)
```

Behavior:

- validates run existence
- requires `PolicyDecision`
- validates `bound_to` includes `agent_id` or `execution_id`
- uses `WorkspaceManager.get_binding(decision.grants)`
- refuses unsupported modes before appending events
- appends canonical `workspace.bound`
- returns copied projected workspace binding summary
- does not mutate native run / action status
- does not create artifact
- does not mutate filesystem
- does not open HTTP route

The helper is still a kernel/server facade boundary, not a product workspace API.
