# Workspace Resource Lifecycle Closure Review

状态：`first slice complete / closed for now`

## 1. Scope Reviewed

本轮 review 只检查 Workspace Resource Lifecycle first slice 是否已经足够 closed for now，不扩大到真实 workspace substrate（工作区底座）实现。

检查对象：

- `workspace.lease_created`
- `workspace.bound`
- `workspace.released`
- `workspace.artifact_captured`
- `RunState.workspaces`
- replay / checkpoint-assisted rebuild
- no real filesystem / container / git worktree / remote executor boundary

## 2. Closure Judgment

Workspace Resource Lifecycle first slice 可以标为 `first slice complete / closed for now`。

理由：

- `workspace.lease_created` 已可投影到 `RunState.workspaces`，并保留 policy / creator provenance。
- `workspace.bound` 仍保持 earlier binding compatibility，同时能保留 lease 上下文中的 grants / creator basis。
- `workspace.released` 已通过 append-only canonical event 更新 lease status，并拒绝 unknown workspace、already released workspace 和 stale basis event。
- `workspace.artifact_captured` 只把 workspace 和 structured artifact `ResourceRef` 关联起来，不读取 workspace file，也不把 full content 放进 native read model。
- replay 和 checkpoint-assisted rebuild 都能恢复 workspace lifecycle read model。
- 当前实现没有打开真实 filesystem mutation、container、git worktree、remote executor、product workspace file/content API，也没有修改 executor grants 或 event store append-only 语义。

## 3. Read Model Shape

当前 `RunState.workspaces` entry 已覆盖 first-slice lifecycle fields：

- `workspace_id`
- `run_id`
- `mode`
- `bound_to`
- `lease_status`
- `granted_by`
- `created_by`
- `released_by`
- `released_at`
- `artifact_refs`
- `provenance`
- `basis_event_id`
- `last_event_id`

Implementation notes:

- `workspace.lease_created` initializes lifecycle fields.
- `workspace.bound` can move a workspace into active binding state.
- `workspace.released` sets release actor / timestamp / reason and updates event basis.
- `workspace.artifact_captured` appends artifact refs and capture provenance only after canonical `artifact.created` exists.

## 4. Test Evidence

Implemented boundary tests:

- `tests/isotope/test_workspace_lease_lifecycle_boundary.py`
- `tests/isotope/test_workspace_artifact_capture_boundary.py`

Coverage includes:

- lease create projection
- binding preservation of policy / creator basis
- release projection without deleting workspace history
- replay equality
- checkpoint-assisted rebuild equality
- malformed lease / release fail-fast
- unknown release fail-fast
- duplicate release fail-fast
- unsupported modes fail closed
- artifact capture requires prior `artifact.created`
- artifact capture requires structured artifact `ResourceRef`
- artifact capture rejects full-content payloads
- projector does not read workspace filesystem
- workspace capture does not mutate native run / action status
- no product workspace file content route
- no container / git worktree / remote executor / binary streaming surface

Current verification baseline remains `942 passed`.

## 5. Boundary Confirmations

Still true after this slice:

- Workspace is policy-bound execution resource, not agent identity.
- `shared_ro` remains the only supported mode.
- write / shared_rw / isolated modes remain fail-closed.
- projector consumes canonical events only.
- projector does not read workspace files.
- workspace file content is not native state.
- artifact capture stays artifact / `ResourceRef` / provenance linkage.
- release / cleanup state must be canonical-event backed, not hidden mutation.
- HTTP product workspace file/content API remains absent.
- no dependency, real filesystem substrate, container, git worktree, remote executor, cleanup scheduler, or binary streaming was introduced.

## 6. Remaining Friction / Deferred Work

These are not blockers for closing the first slice:

- `workspace.release_failed` diagnostics remain deferred until a cleanup attempt exists.
- path-safety rules remain deferred until a real path substrate is designed.
- write / shared_rw / isolated mode behavior remains fail-closed.
- real filesystem sandbox / container / git worktree / remote executor remains deferred.
- file diff / rollback engine remains deferred.
- product workspace browse / upload / content API remains deferred.
- workspace artifact capture helper ergonomics can be revisited later, but current read-model boundary is sufficient.

## 7. Recommended Next Path

Recommended kernel path:

- `Policy Profile / Action Registry Versioning Boundary`

Reason:

- workspace modes, action schemas, helper APIs, worker delegation, approval gates, and retry / cancel / supersede behavior all rely on stable grants / action type contracts.
- defining profiles and registry versioning next reduces schema drift before adding more app-facing helpers or runtime integration.

Alternative paths:

- If continuing usability pressure tests: `Worker Handoff App Spike Selection`.
- If pausing implementation: `External Review Package Refresh`.

Do not start real workspace substrate, real HTTP server, real LLM, provider adapter, memory query engine, container, git worktree, remote executor, or product workspace API from this closure review.
