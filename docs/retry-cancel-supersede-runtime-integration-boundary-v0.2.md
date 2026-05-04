# Retry / Cancel / Supersede Runtime Integration Boundary v0.2

状态：`first slice complete / closed for now`

## 1. Purpose

当前 Retry / Cancel / Supersede 已有 projector-level canonical events、read model、basis linkage hardening、replay 和 checkpoint-assisted rebuild。Runtime integration（运行时集成）first slice 已实现并完成 closure review：`InProcessServer.request_retry(...)`、`request_cancel(...)` 和 `request_supersede(...)` 提供最小 in-process helpers。

本文定义最小 runtime contract，并记录 first green slice / closure evidence。目标不是实现 scheduler、process kill、automatic retry engine 或 real concurrency，而是先明确 server / helper / runtime facade 如何把 request 变成 canonical events，同时保持 executor grants、event store append-only 和 projector-only read model contract。

## 2. Definitions

### retry request

`retry request` 是对既有 action / execution 发起新的 attempt（尝试）的请求。Retry 不修改原 execution；它必须保留原 action / execution lineage，并创建新的 proposal / decision / execution path，或在 canonical event 中明确引用 replacement execution。

### cancel request

`cancel request` 是对 pending / running / otherwise cancellable lifecycle 发出的 logical stop（逻辑停止）请求。Cancel request 本身是 canonical event-backed request；是否最终进入 cancelled state 必须由后续 canonical event 表达。

### supersede request

`supersede request` 是用 replacement action / proposal / execution 取代 old action / proposal 的请求。Supersede 不是 retry，也不是原地 edit；它必须保留 old / replacement linkage。

### logical cancellation

`logical cancellation` 表示 kernel read model 认为 action 不应继续产生后续 side effect。它不等于 process kill、thread interruption、tool-level cancellation hook 或 workspace cleanup。

### replacement proposal / replacement execution

`replacement proposal` / `replacement execution` 是 retry 或 supersede 后的新 identity。它们不得复用 old proposal id / execution id。

### basis action / basis execution

`basis action` / `basis execution` 是 retry / cancel / supersede request 所引用的 canonical source。Runtime helper 必须能把 request 绑定到明确的 proposal / execution / decision / event basis，不能靠当前 in-memory state 暗示。

## 3. Hard Contracts

当前 runtime integration helper slice 必须遵守：

- retry / cancel / supersede request must be canonical event-backed.
- request 不得直接 mutate existing action / execution / `RunState` / `SessionState`。
- event store append-only semantics 不变。
- executor grants semantics 不变；executor 仍只执行 effective `PolicyDecision.grants` snapshot。
- projector derives retry / cancel / supersede state only from canonical events。
- cancel in v0.2 is logical cancel, not process kill。
- retry must create a new proposal / execution path, or explicitly reference a replacement execution in canonical events。
- supersede must link old proposal / action / execution and replacement proposal / action / execution。
- runtime helper 不能隐式放大 workspace / tool / budget grants。
- no hidden scheduler state, queue state, timeout state, process state, or filesystem side state.
- malformed request 或 invalid state transition 必须 fail fast，并且不产生 partial lifecycle state。

## 4. Allowed / Disallowed Transitions

这些是 v0.2 runtime boundary candidates，不是永久协议。

| Basis state | Retry | Cancel | Supersede | Notes |
| --- | --- | --- | --- | --- |
| `pending_user_approval` | disallowed by default | allowed as logical request | allowed only with explicit replacement proposal | Cancel should not auto-deny approval unless a future approval-cancel contract says so. |
| `denied` | allowed only as explicit revised request / new proposal | disallowed | allowed with replacement proposal | Denied action has no execution to kill; retry must not reuse denied decision grants. |
| `running` | disallowed until running attempt is terminal or explicitly superseded | `cancel_requested` allowed; actual kill deferred | allowed with explicit replacement proposal and logical cancel/supersede semantics | Running cancel is logical only in v0.2. |
| `failed` | allowed | disallowed | allowed with replacement proposal | Retry from failed is the primary happy path. |
| `completed` | allowed only as explicit re-run with new proposal / execution | disallowed | allowed only as explicit replacement with preserved old artifact provenance | Completed state cannot be rewritten into cancelled. |
| `cancelled` | allowed only as explicit retry with new proposal / execution | disallowed | allowed only with replacement proposal | Cancelled state remains historical fact. |
| `superseded` | disallowed unless target is replacement lineage | disallowed | disallowed unless a new supersession targets the current replacement | Avoid chains that erase the original lineage. |

General rules:

- retry from `failed` is allowed and must create replacement identity.
- retry from `completed` is a re-run, not a mutation of completed state.
- cancel of `running` may be accepted as logical `cancel_requested`, but process kill remains deferred.
- cancel of `completed` / `failed` / `denied` / already `cancelled` is rejected.
- supersede always requires replacement proposal identity.
- supersede must not delete or overwrite old artifacts / provenance.
- pending approval supersede must not reuse the old approval for the replacement proposal.

## 5. Runtime Surface Candidate

Potential helper names:

- `request_retry(...)`
- `request_cancel(...)`
- `request_supersede(...)`

Candidate helper contract:

- accept structured request with `run_id`, basis proposal / execution ids, reason, requester identity, and optional replacement intent.
- validate basis state from projected `RunState` plus canonical basis events.
- append canonical request event on accepted request.
- for retry / supersede, create or reference replacement proposal / decision / execution only through existing action chain and policy boundary.
- return stable summary including request id, basis ids, accepted / rejected status, and replacement ids when applicable.
- reject invalid transition without appending partial retry / cancel / supersede read model state.

Open design choice for first implementation slice:

- retry / supersede helpers may use existing `submit_action(...)` style action submission to create replacement proposal / decision.
- cancel helper may be event-only if the target is pending / running and no replacement action is needed.
- all helpers should remain in-process server helpers first, not HTTP product routes.

## 6. Event Implications

Existing first slice event candidates remain valid:

- `action.retry_requested`
- `action.retry_created`
- `action.cancel_requested`
- `action.cancelled`
- `action.superseded`

Runtime integration may need additional fields:

- request source: `requested_by`, `requester_type`, or equivalent.
- runtime helper basis: `basis_event_id`, `basis_proposal_id`, `basis_execution_id`, `basis_decision_id`.
- accepted / rejected request summary, if rejected requests become canonical.
- replacement proposal / execution ids for retry / supersede.
- policy basis for replacement action path.

Rejected request handling should be explicit in the first red tests:

- either reject before appending events, or
- append a canonical rejected request event with no state-changing accepted lifecycle event.

The first implementation slice should choose one behavior and document it; it must not silently mutate hidden runtime state.

## 7. Read Model Implications

`RunState.action_retries`, `RunState.action_cancellations`, and `RunState.action_supersessions` already exist. Runtime integration should preserve:

- original proposal / execution lineage.
- replacement proposal / execution linkage.
- requester / reason metadata.
- accepted / rejected request status if rejected requests are canonicalized.
- basis refs to canonical events.
- checkpoint-assisted rebuild equivalence.

`RunState.actions` should not be rewritten in place to hide old action status. It may show derived status summaries only if the source canonical events make the relationship explicit.

## 8. Interactions

### Policy / registry basis

- retry and supersede replacement actions must carry current proposal registry basis and policy profile basis.
- executor still uses replacement decision grants snapshot.
- old decision grants cannot be silently reused unless the retry event explicitly records that grants snapshot as basis and tests pin that behavior.

### Approval

- pending approval cancellation needs a future explicit contract if it should also resolve or invalidate approval.
- for v0.2 runtime boundary, cancel can mark the action lifecycle, but it should not pretend to be user approval denial.
- replacement proposal must not inherit the old approval id.

### Worker

- worker-created actions must still go through worker action grants.
- worker cancellation is not action cancellation unless canonical events link the two.
- worker handoff artifacts remain historical facts even if source action is superseded.

### Workspace

- retry / supersede cannot upgrade workspace mode beyond policy grants.
- cancel does not clean or delete workspace resources.
- any future cleanup must append workspace lifecycle events.

## 9. Deferred

Explicitly deferred:

- scheduler
- automatic retry engine
- retry backoff policy
- timeout engine
- process kill
- thread interruption
- tool-level cancellation hooks
- concurrent execution coordination
- distributed locks
- queue worker / job runner
- UI stop / retry / supersede controls
- product HTTP routes
- workspace cleanup / rollback side effects

## 10. First Green Slice Evidence

当前 green slice 已实现：

- `InProcessServer.request_retry(...)`
  - accepts failed action retry.
  - accepts completed action retry only when `explicit_rerun=True`.
  - appends `action.retry_requested` and `action.retry_created`.
  - returns retry id, basis proposal / execution ids, and replacement proposal / execution ids.
  - does not mutate the old execution state in place.
- `InProcessServer.request_cancel(...)`
  - accepts pending-approval logical cancel request.
  - rejects completed / failed terminal action cancellation without partial events.
  - appends `action.cancel_requested`.
  - returns `logical_only=True` and `process_kill=False`.
- `InProcessServer.request_supersede(...)`
  - requires replacement intent or replacement proposal identity.
  - appends `action.superseded`.
  - links old proposal / execution to replacement proposal / execution identity.
  - preserves completed old action status instead of rewriting it in place.

Verification evidence:

- targeted runtime tests: `15 passed`.
- full regression: `974 passed`.

Still absent by design:

- scheduler / retry backoff policy engine.
- timeout engine.
- process kill / thread interruption.
- tool-level cancellation hooks.
- product HTTP retry / cancel / supersede routes.
- real concurrency / distributed locks.

Closure review:

- `docs/retry-cancel-supersede-runtime-closure-review.md`
- conclusion: `first slice complete / closed for now`
- next recommended boundary at the time: `Event Schema Registry / Compatibility Boundary`
- follow-up status: boundary is now defined in `docs/event-schema-registry-compatibility-boundary-v0.2.md`; next suggested step is `Event Schema Registry / Compatibility Red Tests`

## 11. First Red Tests Recommendation

Suggested files:

- `tests/isotope_kernel/test_retry_runtime_integration_boundary.py`
- `tests/isotope_kernel/test_cancel_runtime_integration_boundary.py`
- `tests/isotope_kernel/test_supersede_runtime_integration_boundary.py`

Recommended coverage:

- `request_retry(...)` helper exists or equivalent runtime surface is explicitly available.
- retry from failed action creates replacement proposal / execution identity.
- retry from failed action goes through policy decision and executor grants snapshot.
- retry does not mutate failed execution status.
- retry from completed action is explicit re-run and preserves old artifact provenance.
- cancel request is canonical event-backed.
- cancel pending approval / running action is logical cancel only, not process kill.
- cancel completed / failed / denied action is rejected without partial read-model mutation.
- supersede requires replacement proposal identity.
- supersede links old and replacement proposal / execution lineage.
- supersede does not overwrite completed artifact provenance.
- rejected retry / cancel / supersede request behavior is controlled and documented.
- replay and checkpoint-assisted rebuild recover runtime request read models.
- no scheduler / process kill / real concurrency / product HTTP route / dependency appears.

These tests now exist and pass:

- `tests/isotope_kernel/test_retry_runtime_integration_boundary.py`
- `tests/isotope_kernel/test_cancel_runtime_integration_boundary.py`
- `tests/isotope_kernel/test_supersede_runtime_integration_boundary.py`

## 12. Stop Conditions For Future Implementation

Stop before implementation if the slice requires:

- scheduler or timeout engine.
- process kill / thread interruption.
- tool-level cancellation hooks.
- real concurrency / queue worker.
- changing event store append-only semantics.
- changing executor grants semantics.
- mutating `RunState` / `SessionState` directly.
- deleting old events / artifacts / provenance.
- product UI or hosted HTTP route.
