# Workspace Substrate Boundary v0.2

状态：`first slice complete`

## 1. Purpose

Workspace substrate 是 Agent / Worker lifecycle first slice 之后的下一块 kernel design。原因不是要马上实现 container、git worktree 或 remote executor，而是要先固定 execution resource（执行资源）边界：

- worker、action 和 tool 都需要一个可被 policy 约束的 execution resource。
- workspace 是 policy-bound resource（受 policy 约束的资源），不是 agent identity（agent 身份）。
- 真实 usability pressure test 会很快碰到文件读写、path safety、artifact capture、cleanup 和 rollback / diff tracking。
- 如果 workspace substrate 晚于 tool protocol 或 real executor 设计，后续 executor、artifact provenance、policy profile 和 worker lifecycle 都容易返工。

本文件定义 v0.2 / v0.3 的最小边界。第一批 slice 已完成 workspace binding read model 和 policy boundary；它仍不实现真实 substrate。

后续 resource lifecycle boundary 已单独定义在 `workspace-resource-lifecycle-boundary-v0.2.md`，closure review 见 `workspace-resource-lifecycle-closure-review.md`。该文档只定义 lease / release / artifact-capture 边界，不代表真实 filesystem substrate 已实现。

## 2. Current Capabilities

当前已有能力仍然很窄：

- `WorkspaceManager` 存在。
- 当前 binding 是 no-op / shared read-only shape。
- 当前只支持 `workspace.mode == "shared_ro"`。
- workspace access 必须来自 `PolicyDecision.grants`。
- executor 调用 workspace manager 时使用 decision grants，不使用 action requested capabilities。
- 未授权或 unsupported workspace mode 会 fail closed。
- `RunState.workspaces` read model 已存在。
- canonical `workspace.bound` slice event 已可投影。
- `InProcessServer.bind_workspace(...)` helper 已存在，用于从 `PolicyDecision.grants` 创建 canonical binding event。
- workspace binding 进入 checkpoint state，并可通过 event replay / checkpoint-assisted rebuild 恢复。
- malformed `workspace.bound` / malformed grant provenance 会 fail fast。

这些能力足够证明 executor 不会直接使用 requested broad workspace，且 workspace binding 状态来自 canonical event；但还不足以支撑真实文件读写、isolated substrate 或 worker workspace lease lifecycle。

## 3. Current Gaps

当前缺口：

- workspace lease lifecycle 已有 first green slice：`workspace.lease_created` / `workspace.released` 可投影、replay 和 checkpoint。
- path safety 规则尚未定义。
- write permission / read-only enforcement 还没有真实 substrate。
- artifact capture from workspace 已有 first green slice：`workspace.artifact_captured` 只链接 artifact `ResourceRef`，不读取 workspace files。
- workspace cleanup 尚未定义。
- isolated workspace substrate 尚未实现。
- rollback / diff tracking 尚未定义。

这些 gap 不代表当前 demo 失败；它们说明 Workspace substrate 仍是 boundary-only / sketch，不能被宣传成可用 sandbox 或真实文件系统执行环境。

## 4. Hard Boundaries

后续实现必须遵守：

- Workspace is execution resource, not agent identity.
- Workspace binding must be policy-granted.
- Executor / worker cannot request broader workspace than `PolicyDecision.grants`.
- Write mode requires explicit grant; it must never be implicit.
- `shared_ro` cannot be upgraded to write / isolated by executor, worker, tool, or request body.
- Artifact capture must go through artifact / provenance path.
- Projector must not read workspace files to advance native state.
- Workspace files are not canonical state.
- Path access must be mediated by workspace handle / binding, not raw string paths from model output.
- Workspace binding state must be replayable from canonical events if it enters `RunState`.

## 5. Completed First Slice

当前 first slice includes：

- `RunState.workspaces` read model。
- canonical `workspace.bound` slice event。
- binding fields: `workspace_id`, `run_id`, `mode`, `bound_to`, `lease_status`, `provenance`, `basis_event_id`。
- binding validation requires policy grant provenance。
- only `shared_ro` is accepted。
- write / shared_rw / isolated modes fail closed。
- worker / executor cannot upgrade requested workspace beyond grants。
- replay restores the same workspace binding read model。
- checkpoint state includes `workspaces`。
- checkpoint-assisted rebuild restores `workspaces`。
- projector does not read filesystem / workspace path content。
- workspace binding does not modify native run / action status。
- server helper returns projected workspace binding summary without exposing product workspace API。

## 6. Remaining Minimal Target

v0.2 / v0.3 minimal target should stay small:

- implement lease create / release / expiry lifecycle only after red tests。
- keep first substrate no-op / `shared_ro` only。
- define path safety checks before any file mutation。
- implement artifact capture linkage without making workspace files native state。
- decide whether lease release belongs in `RunState.workspaces` or separate diagnostics。

This is a kernel boundary slice, not an execution sandbox.

## 7. Deferred

Explicitly deferred:

- container substrate
- git worktree substrate
- remote executor
- real file diff / rollback engine
- cleanup scheduler
- binary artifact streaming
- hosted workspace service
- multi-user workspace isolation
- path virtualization beyond first safety checks

These should not be pulled into the completed first slice.

## 8. First Tests

Implemented first test files:

- `tests/isotope_kernel/test_workspace_binding_read_model.py`
- `tests/isotope_kernel/test_workspace_policy_boundary.py`

Suggested coverage:

| Test area | Expected boundary |
| --- | --- |
| Workspace binding projection | binding is projected from canonical events |
| Binding shape | includes `workspace_id`, `mode`, `run_id`, `agent_id` or `execution_id`, and lease status |
| Policy requirement | binding requires policy grants |
| No implicit write | write mode cannot be granted implicitly |
| No upgrade | worker / executor cannot upgrade `shared_ro` to write / isolated |
| Malformed events | malformed workspace event fails fast |
| Checkpoint | workspace binding enters checkpoint if it becomes part of `RunState` |
| Projector safety | projector does not read filesystem |
| Deferred substrate | no container / git worktree / remote executor in first slice |

## 9. First Green Shape

The implemented green slice is:

- `workspace.bound` slice-only event。
- `RunState.workspaces` read model。
- validation that `workspace.mode` comes from policy grants。
- `shared_ro` remains the only accepted mode。
- write / isolated requests fail closed。
- checkpoint state includes workspace binding。
- `InProcessServer.bind_workspace(...)` reduces manual `workspace.bound` glue for pressure-test scenarios。
- no actual filesystem reads from projector。
- no real process, thread, container, worktree, or remote executor。

The slice should not turn workspace into product infrastructure. It should only make later worker / tool execution pressure tests safer.

## 10. Non-Goals

- real sandbox
- real filesystem mutation
- broad path allowlist engine
- external mount management
- tool protocol implementation
- artifact content streaming from workspace
- rollback product feature
- cleanup daemon
- remote execution

## 11. Status For Current Repo

Current repo status remains:

- current repo baseline: `942 passed`
- current workspace implementation: `WorkspaceManager` shared read-only / grants validation, `RunState.workspaces` projection, `InProcessServer.bind_workspace(...)`, and first-slice lease / release / artifact-capture read-model support
- no real substrate implementation from this document
- first tests are implemented and green
- workspace resource lifecycle closure review: `first slice complete / closed for now`
- next step, if requested: Policy Profile / Action Registry Versioning Boundary, not real filesystem substrate
