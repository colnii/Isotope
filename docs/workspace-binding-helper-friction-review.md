# Workspace Binding Helper Friction Review

状态：`implemented`

## 1. Purpose

本文 review `approval-gated tool runner` spike 暴露的 workspace binding friction。

目标不是实现真实 workspace substrate，也不是打开 filesystem mutation / container / git worktree。目标是判断当前 manual `workspace.bound` glue 是否应该收敛成最小 helper。

Pre-helper evidence and current outcome：

- `WorkspaceManager` 已存在，只支持 `shared_ro`。
- executor 使用 `PolicyDecision.grants` 调用 workspace manager。
- projector 已支持 canonical `workspace.bound` -> `RunState.workspaces`。
- `approval-tool-runner` demo previously called `_append_workspace_binding_event(...)` directly。
- current demo calls `InProcessServer.bind_workspace(...)` instead。

## 2. Friction Summary

| Friction | Evidence | Classification | Impact | Suggested action |
| --- | --- | --- | --- | --- |
| demo manually appends `workspace.bound` | demo previously called `_append_workspace_binding_event(...)`; current tests assert it is not called | helper/facade gap | medium-high | fixed by minimal server helper |
| helper ownership unclear | `WorkspaceManager` validates grants, but does not append canonical events | kernel/server boundary gap | medium | keep helper in `InProcessServer` first |
| HTTP workspace route absent | no workspace binding HTTP route exists | acceptable v0 shape | low | keep out of scope |
| real workspace substrate absent | no filesystem mutation, container, git worktree, or path engine | intentional deferred area | none for this slice | do not implement |

No correctness bug was found. The manual event append was explicit and still canonical, but it was too awkward for repeated usability spikes. The first helper slice now replaces that demo glue with `InProcessServer.bind_workspace(...)`.

## 3. Layering

Kernel / server issue:

- Something should own canonical `workspace.bound` event creation after a policy decision grants workspace access.
- That owner must use `PolicyDecision.grants`, not requested workspace capabilities.
- The helper must not modify `RunState` directly; projector remains the only read-model writer.

Helper/facade issue:

- Demo code should not need to know the exact `workspace.bound` payload shape.
- A server helper can translate policy grants into the canonical event and return the projected workspace binding summary.

Demo-only glue:

- `_append_workspace_binding_event(...)` is acceptable as evidence from the first pressure test, but should not be copied into future demos.

Acceptable v0 shape:

- Only `shared_ro` is supported.
- No HTTP route is required for the helper.
- No real filesystem, container, git worktree, path safety engine, cleanup scheduler, or artifact capture from real files is opened.

## 4. Implemented Recommendation

Implemented slice: minimal `InProcessServer` workspace binding helper.

Suggested shape:

- `bind_workspace(run_id, decision, bound_to=None)` or equivalent.
- Validate the run exists.
- Validate the decision has policy grants.
- Call `WorkspaceManager.get_binding(decision.grants)` so mode cannot exceed grants.
- Append canonical `workspace.bound`.
- Return copied `RunState.workspaces[workspace_id]` summary.
- Do not expose an HTTP route in this slice.

Do not implement in this slice:

- workspace write / isolated mode
- filesystem mutation
- path validation engine
- container / git worktree / remote executor
- artifact capture from real workspace files
- product workspace API

## 5. Implemented First Slice

Implemented helper:

- `InProcessServer.bind_workspace(run_id, decision, bound_to=None)`
- validates the run exists
- requires a `PolicyDecision`
- calls `WorkspaceManager.get_binding(decision.grants)`
- appends canonical `workspace.bound`
- returns copied projected `RunState.workspaces[workspace_id]`
- leaves approval-tool-runner demo free of manual `workspace.bound` payload glue

Verification:

- targeted helper tests: `6 passed`
- full regression: `859 passed`
- v0.1 / v0.2 / approval-tool-runner demos plain and JSON pass

Still deferred:

- HTTP workspace route
- product workspace API
- real filesystem mutation
- path validation engine
- container / git worktree / remote executor
- process spawn / real concurrency
