# Workspace Resource Lifecycle Boundary v0.2

状态：`first slice complete / closed for now; real substrate deferred`

## 1. Purpose

本文把 Workspace 从已实现的 binding read model 推进到 resource lifecycle contract（资源生命周期契约）的设计边界。目标不是实现真实 filesystem、container、git worktree 或 remote executor，而是先定义 workspace resource 如何被创建、绑定、释放、诊断和用于 artifact capture。

当前已实现：

- `RunState.workspaces`
- canonical `workspace.bound`
- canonical `workspace.lease_created`
- canonical `workspace.released`
- canonical `workspace.artifact_captured` as artifact-ref linkage
- `InProcessServer.bind_workspace(...)` helper
- grants-driven `shared_ro` workspace mode
- replay / checkpoint-assisted rebuild for workspace lifecycle read model
- no real filesystem mutation / no container / no git worktree

当前缺口：

- mode 是否可以升级 / 降级。
- workspace resource identity 如何表达。
- `workspace.release_failed` / cleanup diagnostics。
- path-safety / write-mode behavior。
- real workspace substrate identity beyond deterministic `shared_ro`。

## 2. Definitions

Workspace 是 policy-bound execution resource（受 policy 约束的执行资源），不是 agent identity（agent 身份）。

Binding 和 lease 必须区分：

- Binding: 某 action / agent / worker 在某次 policy grants 下获得 workspace access。它回答“谁在什么 grants 下可以访问哪种 workspace mode”。
- Lease: workspace resource 的生命周期占用 / 释放状态。它回答“这个 workspace resource 是否被创建、是否仍 active、是否 released / expired / revoked”。

当前已实现的 `workspace.bound` 更接近 binding event。它不是完整 lease lifecycle，也不代表真实 workspace substrate 已存在。

## 3. Minimal Canonical Events Candidate

这些 event names 是 slice candidate，不是最终 protocol 承诺。

| Event | Purpose | First-slice stance |
| --- | --- | --- |
| `workspace.lease_created` | 创建 workspace resource lifecycle record，固定 `workspace_id`、`run_id`、initial mode、policy basis 和 creator basis | implemented in first green slice |
| `workspace.bound` | 把 existing workspace resource 或 current shared resource 绑定给 agent / worker / execution | already implemented as binding first slice |
| `workspace.released` | 通过 append-only event 表达 release / revoke / expired 等终止状态 | implemented in first green slice for released status |
| `workspace.release_failed` | 记录 release / cleanup 尝试失败的 diagnostics，不改变 hidden state | deferred unless cleanup attempt exists |
| `workspace.artifact_captured` | 只记录 workspace resource 到 artifact / `ResourceRef` 的 linkage；artifact 本体仍必须是 `artifact.created` / artifact provenance path | implemented in first green slice as linkage only |

First-slice decision:

- New lifecycle paths use `workspace.lease_created -> workspace.bound -> workspace.released`.
- Existing `workspace.bound` remains a compatibility shortcut for the earlier binding first slice.
- `workspace.artifact_captured` requires a prior `artifact.created` event and only links a structured artifact `ResourceRef`; it does not replace the artifact event path.

## 4. Minimal Read Model Candidate

如果 lease lifecycle 进入 `RunState.workspaces`，每个 entry 至少应表达：

| Field | Meaning |
| --- | --- |
| `workspace_id` | deterministic workspace resource identity |
| `run_id` | owning run |
| `mode` | policy-derived mode, initially still `shared_ro` only |
| `lease_status` | `created`, `bound`, `released`, `expired`, `revoked`, or `release_failed` |
| `bound_to` | `{type, agent_id/execution_id/worker_id}` style binding target |
| `granted_by` | policy `decision_id` that authorized access |
| `created_by` | `execution_id` / `proposal_id` / setup basis that created resource lifecycle |
| `released_by` | release actor / execution / system reason if released |
| `released_at` | timestamp from release event, not hidden clock mutation |
| `artifact_refs` | list of structured `ResourceRef` values captured from this workspace |
| `provenance` | structured provenance, including policy and basis event refs |
| `last_event_id` | most recent canonical event that updated this read model |

The read model must not include:

- workspace file content
- raw filesystem path contents
- binary blobs
- mutable hidden cleanup state
- product UI state

## 5. Hard Contracts

Workspace lifecycle must follow these contracts:

- executor only gets workspace access from `PolicyDecision.grants`.
- no implicit mode upgrade.
- `write`, `shared_rw`, and `isolated` modes remain fail-closed until explicitly implemented.
- a caller, worker, model output, request body, or demo helper cannot upgrade `shared_ro` to write / isolated.
- workspace identity is not agent identity.
- projector does not read workspace filesystem.
- workspace files are not native state.
- artifact capture must become artifact / `ResourceRef` / provenance event, not direct native state mutation.
- cleanup / release must append canonical event, not mutate hidden state.
- release failure must be diagnostics / event-sourced, not silent hidden retry.
- checkpoint-assisted rebuild must recover lifecycle read model only from canonical events.
- resource lifecycle must remain compatible with existing append-only event store semantics.

## 6. Mode Boundary

Current implementation supports only:

- `shared_ro`

Future modes may be named, but remain fail-closed until separately designed and tested:

- `shared_rw`
- `isolated_ro`
- `isolated_rw`
- `ephemeral`

No future mode should be granted by string request alone. Mode must be derived from policy profile / `PolicyDecision.grants`, and later tied to policy profile / action registry versioning.

## 7. Artifact Capture Boundary

Artifact capture from workspace is a provenance boundary, not a shortcut into native state.

Allowed shape:

1. action / execution has grants to use workspace.
2. capture operation produces canonical artifact event path.
3. artifact summary / structured `ResourceRef` / provenance enter read model.
4. optional `workspace.artifact_captured` links `workspace_id` to artifact `ResourceRef`.
5. projector reads only canonical events and structured refs.

Disallowed shape:

- projector reads workspace files.
- workspace path string becomes native state.
- full file content appears in `RunState.workspaces`.
- workspace capture bypasses artifact store / provenance.
- capture opens HTTP full-content route.

## 8. Deferred

Explicitly deferred:

- real filesystem sandbox
- container
- git worktree
- remote executor
- binary streaming
- cleanup scheduler
- file diff / rollback engine
- path virtualization
- hosted workspace service
- product workspace API
- multi-user isolation
- process kill / tool-level cancellation

## 9. First Green Slice Evidence

Implemented tests:

- `tests/isotope_kernel/test_workspace_lease_lifecycle_boundary.py`
- `tests/isotope_kernel/test_workspace_artifact_capture_boundary.py`

Current behavior:

- `workspace.lease_created` projects a lifecycle entry into `RunState.workspaces`.
- `workspace.bound` preserves grants / creator basis when lifecycle context exists, while keeping the earlier direct-binding compatibility path.
- `workspace.released` updates `lease_status`, `released_by`, `released_at`, `last_event_id`, and release basis metadata.
- `workspace.artifact_captured` links a workspace to a structured artifact `ResourceRef` after the canonical `artifact.created` event exists.
- malformed lease / release / capture payloads fail fast with controlled exceptions.
- unknown or already released workspace release fails fast.
- replay and checkpoint-assisted rebuild restore the same lifecycle read model.
- unsupported workspace modes remain fail-closed.

Still not implemented:

- real filesystem reads / writes
- product workspace file/content API
- container / git worktree / remote executor
- cleanup scheduler
- binary streaming
- `workspace.release_failed`

Closure review:

- `docs/workspace-resource-lifecycle-closure-review.md`
- judgment: `first slice complete / closed for now`
- next recommended kernel path: `Policy Profile / Action Registry Versioning Boundary`

## 10. Original First Red Tests (Implemented)

Implemented files:

- `tests/isotope_kernel/test_workspace_lease_lifecycle_boundary.py`
- `tests/isotope_kernel/test_workspace_artifact_capture_boundary.py`

Recommended coverage for `test_workspace_lease_lifecycle_boundary.py`:

- `workspace.lease_created` projects a workspace lifecycle entry.
- lifecycle entry includes `workspace_id`, `run_id`, `mode`, `lease_status`, `granted_by`, `created_by`, `last_event_id`, and provenance.
- `workspace.bound` can bind only an existing or compatibility workspace resource.
- `workspace.released` appends canonical release and updates `lease_status`.
- release / cleanup does not mutate hidden state.
- replay restores the same workspace lifecycle read model.
- checkpoint-assisted rebuild restores the same workspace lifecycle read model.
- malformed lease / release events fail fast with controlled `ValueError`.
- unsupported modes remain fail-closed.
- workspace identity is not agent identity.

Recommended coverage for `test_workspace_artifact_capture_boundary.py`:

- artifact capture from workspace produces artifact summary / structured `ResourceRef` / provenance.
- optional `workspace.artifact_captured` links workspace to artifact ref without embedding content.
- projector does not read filesystem or workspace file content.
- full content is not returned by workspace lifecycle read model.
- capture cannot bypass artifact event / provenance path.
- HTTP full-content route remains `not_enabled`.
- no real filesystem mutation / container / git worktree / process spawn.

## 11. Stop Conditions For Implementation

Stop before implementation if a future slice requires:

- deciding whether workspace represents a real directory, container, git worktree, or remote executor.
- mutating real filesystem state.
- adding sandbox / container machinery.
- changing executor grants semantics.
- changing event store append-only semantics.
- making projector read workspace files.
- product workspace upload / browse / cleanup API.

## 12. Decision

Workspace resource lifecycle first slice is complete / closed for now at read-model / validation scope. The next safe kernel step is Policy Profile / Action Registry Versioning Boundary, not real filesystem or sandbox behavior.
