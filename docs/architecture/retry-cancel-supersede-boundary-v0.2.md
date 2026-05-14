# Retry / Cancel / Supersede Boundary v0.2

状态：`first slice complete; stabilization complete; runtime integration first slice closed`

## 1. Purpose

Retry / cancel / supersede 是 Workspace substrate first slice 之后需要补齐的 action lifecycle boundary。它不是为了马上实现 job scheduler、real concurrency 或 long-running worker runtime，而是为了先固定失败恢复、用户停止和替换动作的最小 kernel contract。

当前 kernel 已经有 `action.proposed`、`action.decided`、`action.started`、`action.completed`、`action.failed` 和 `run.completed` 的最小生命周期约束。随着 approval、worker 和 workspace read model 进入 checkpoint，action lifecycle 也需要明确：

- failed action 能否 retry，以及 retry 如何保留 lineage。
- running / pending action 能否 cancel，以及 cancel 是否阻止后续 execution。
- 一个 proposal / action 被 replacement 取代时，old / new action 如何在 event log 中表达。
- retry / cancel / supersede 是否能绕过 `PolicyDecision.grants`。
- checkpoint-assisted rebuild 是否能恢复这些 lifecycle read model。

## 2. Current Capabilities

当前已实现能力：

- `ActionCompiler -> PolicyEngine -> Executor` action chain。
- `PolicyDecision.grants` enforcement。
- canonical event log append-only。
- `RunProjector` action lifecycle ordering validation。
- `action.started` 只能在 approved / modified policy decision 后出现。
- denied / pending approval decision 不能进入 execution。
- `action.failed` / `action.completed` 已有 executor-owned event boundary。
- `run.completed` 不能覆盖 running / failed / pending approval state。
- checkpoint state 已包含 `actions`、`approvals`、`agents`、`workers`、`workspaces`、`memory_records` 和 `external_observations` 等 read model。

这些能力支撑了 retry / cancel / supersede 的第一批 green slice。当前已实现 action-level retry / cancel / supersede read model，并已完成 stabilization hardening：basis event linkage、replacement identity、cancel request ordering、projector reuse state reset，以及 checkpoint-assisted rebuild 等关键不变量都有测试覆盖。runtime integration follow-up 已单独定义、实现并完成 closure review，见 `retry-cancel-supersede-runtime-integration-boundary-v0.2.md` 和 `../reviews/retry-cancel-supersede-runtime-closure-review.md`：它提供 in-process `request_retry(...)` / `request_cancel(...)` / `request_supersede(...)` helpers，不实现 scheduler、process kill 或 automatic retry engine。

## 3. Boundary Definitions

### 3.1 Retry

Retry 指对已经失败或可重试终止的 action 创建一个新的 action attempt。Retry 不应直接改旧 action 的 final state。

最小边界：

- retry 必须保留 `retry_of` / `original_proposal_id` / `original_execution_id` lineage。
- retry 必须形成新的 proposal / decision / execution lifecycle。
- retry 不能复用 failed execution id。
- retry 不能绕过 policy；新的 attempt 仍必须经过 policy decision。
- retry metadata 可以进入 `RunState` read model，但不能成为第二事实源。

### 3.2 Cancel

Cancel 指对 pending / running lifecycle 发出停止请求，并通过 canonical event 表达结果。

最小边界：

- cancel 必须 append canonical event，不得直接修改 materialized `RunState`。
- cancel allowed state 必须明确；completed / failed / already cancelled action 不能被静默取消。
- cancel 后不能再出现新的 execution side effect，除非后续 event 明确表达 retry / supersede。
- cancel 不等于 denial；它是 action lifecycle transition。
- cancel 不能删除既有 action / execution / artifact history。

### 3.3 Supersede

Supersede 指一个 action proposal / attempt 被 replacement proposal 取代。它不是 retry，也不是简单 cancel。

最小边界：

- supersede 必须链接 old proposal / action 和 replacement proposal。
- old action 应保留 readable final state，例如 `superseded`。
- replacement action 仍必须走 proposal / policy / executor chain。
- supersede 不能合成假确定状态；old / new lineage 必须可 replay。
- supersede 不能覆盖既有 completed artifact provenance。

## 4. Candidate Canonical Events

这些 event names 是 v0.2 boundary candidates，不是永久协议：

- `action.retry_requested`
- `action.retry_created`
- `action.cancel_requested`
- `action.cancelled`
- `action.superseded`

最小 payload 方向：

| Event | Required shape |
| --- | --- |
| `action.retry_requested` | `retry_id`, `run_id`, `original_proposal_id`, `original_execution_id`, `reason`, `requested_by` |
| `action.retry_created` | `retry_id`, `new_proposal_id`, `original_proposal_id`, `basis_event_id`, `policy_basis` |
| `action.cancel_requested` | `cancel_id`, `run_id`, `proposal_id`, `execution_id` if running, `reason`, `requested_by` |
| `action.cancelled` | `cancel_id`, `proposal_id`, `execution_id`, `status`, `basis_event_id`, `reason` |
| `action.superseded` | `supersession_id`, `old_proposal_id`, `new_proposal_id`, `reason`, `basis_event_id` |

如果 implementation slice 选择更小 event set，也必须保留 lineage、policy basis、basis refs 和 replayability。

## 5. Projector / Checkpoint Expectations

如果 retry / cancel / supersede 进入 `RunState` read model，则必须满足：

- read model 只来自 canonical events。
- checkpoint state 包含对应 read model 字段。
- checkpoint-assisted rebuild 与 full event replay 等价。
- malformed lifecycle events fail fast。
- lifecycle-invalid sequence fail fast。
- retry / cancel / supersede basis refs must point at the expected canonical event.
- read model 不读取 executor/server in-memory state。
- read model 不读取 artifact full content 或 workspace filesystem。

First slice 已新增：

- `RunState.action_retries`
- `RunState.action_cancellations`
- `RunState.action_supersessions`

这些字段已经进入 checkpoint state，并可通过 checkpoint-assisted rebuild 恢复。Existing `RunState.actions` 仍保留 execution-level status；retry / cancel / supersede lineage 保存在单独 read model 中。

## 6. Interaction Risks

### Approval

- cancel pending approval 是否关闭 approval，需要单独定义。
- approved resume 后是否还能 cancel，需要明确 allowed state。
- supersede pending approval 的 proposal 时，旧 approval 不能被误用到 replacement proposal。

### Worker

- worker-created action 的 retry / cancel / supersede 仍必须走 worker policy grants。
- worker cancellation 与 action cancellation 不能互相隐式替代。
- worker result handoff 已经发生后，supersede 不能删除 artifact provenance。

### Workspace

- retry 不得扩大 workspace grants。
- cancel 不得清理或删除 workspace 文件，除非未来 cleanup lifecycle 明确。
- supersede replacement proposal 不能继承 broader workspace than policy granted。

### Checkpoint

- retry / cancel / supersede read model 一旦进入 `RunState`，就必须进入 checkpoint state。
- checkpoint mismatch fallback 不能隐藏 malformed retry / cancel / supersede event。

## 7. Hard Boundaries

- Retry / cancel / supersede must be event-sourced.
- They must not mutate `RunState` / `SessionState` directly.
- They must not modify event store append-only semantics.
- They must not bypass `PolicyDecision.grants`.
- They must not reopen denied execution or completed run implicitly.
- They must not delete prior events / artifacts / provenance.
- They must not require real concurrency, scheduler, queue, or process manager.

## 8. Non-Goals

本阶段不做：

- distributed retry semantics
- exponential backoff / scheduler
- async cancellation of real subprocesses
- process / thread interruption
- worker pool cancellation
- UI stop button
- approval timeout / expiry
- rollback / workspace cleanup
- real job queue
- product-level audit dashboard

## 9. First Green Slice

第一批 tests 已落地并通过：

- `tests/isotope/test_action_retry_boundary.py`
- `tests/isotope/test_action_cancel_boundary.py`
- `tests/isotope/test_action_supersede_boundary.py`

测试重点：

| Test area | Expected boundary |
| --- | --- |
| Retry lineage | retry preserves original proposal / execution lineage |
| Retry policy | retry creates a new action path and cannot bypass policy |
| Cancel event sourcing | cancel appends canonical lifecycle event, not direct state mutation |
| Cancel allowed state | completed / failed / already cancelled cancel is controlled |
| Cancel side effects | cancelled action cannot later execute without explicit retry / supersede |
| Supersede linkage | old and replacement proposals remain linked |
| Supersede policy | replacement proposal still goes through policy |
| Replay | retry / cancel / supersede read model rebuilds from event log |
| Checkpoint | read model survives checkpoint-assisted rebuild if included in `RunState` |
| No product runtime | no scheduler / process kill / real concurrency in first slice |

## 10. Stabilization Slice

当前 stabilization batch 已补充并通过：

- malformed / inconsistent retry created events fail fast：
  - `action.retry_created.basis_event_id` 必须指向对应 `action.retry_requested` event。
  - retry replacement proposal 必须使用新的 proposal identity。
  - projector reuse 不得携带 stale retry request internal state。
- malformed / inconsistent cancel events fail fast：
  - `action.cancel_requested.proposal_id` 必须匹配 running execution 的 proposal。
  - `action.cancelled` 必须有对应 `action.cancel_requested`。
  - `action.cancelled.basis_event_id` 必须指向对应 request event。
- malformed / inconsistent supersede events fail fast：
  - `action.superseded.basis_event_id` 必须指向 old action start event。
  - replacement proposal 必须使用新的 proposal identity。
- retry / cancel / supersede read-model fields all match full replay after checkpoint-assisted rebuild。

这些 hardening 仍保持 projector-level boundary；没有新增 scheduler、process kill、tool-level cancellation、real concurrency、event store semantic change 或 executor grants semantic change。

## 11. Status For Current Repo

Current repo status:

- tests baseline after runtime integration helper slice: `974 passed`
- retry / cancel / supersede first slice: complete
- retry / cancel / supersede stabilization slice: complete
- runtime integration helper slice: complete in `retry-cancel-supersede-runtime-integration-boundary-v0.2.md`
- runtime integration closure review: complete in `../reviews/retry-cancel-supersede-runtime-closure-review.md`
- runtime integration tests: `15 passed`
- current implementation: projector-level canonical event validation, read model, replay, checkpoint support, and in-process runtime helpers
- not implemented: scheduler, automatic retry engine, process kill, tool-level cancellation, real concurrency
