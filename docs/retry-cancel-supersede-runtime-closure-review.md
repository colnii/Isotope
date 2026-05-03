# Retry / Cancel / Supersede Runtime Closure Review

状态：`first slice complete / closed for now`

## 1. Scope Reviewed

本文审查 Retry / Cancel / Supersede runtime integration helper slice 是否可以关闭。范围只包括 in-process `InProcessServer` helpers、canonical request events、projector/read-model integration、tests evidence 和 deferred runtime boundary。

本轮不扩大到 scheduler、process kill、tool-level cancellation hooks、real concurrency、product HTTP routes、retry backoff policy engine 或 timeout engine。

## 2. Closure Judgment

结论：R/C/S Runtime Integration first slice 可以标为 `first slice complete / closed for now`。

理由：

- `InProcessServer.request_retry(...)` validates the basis execution, appends canonical `action.retry_requested` and `action.retry_created`, returns replacement proposal / execution identity, and preserves the old failed / completed execution status.
- `InProcessServer.request_cancel(...)` is logical cancellation only: it appends `action.cancel_requested`, returns `logical_only=True` / `process_kill=False`, rejects completed / failed terminal states, and does not remove existing execution or artifact events.
- `InProcessServer.request_supersede(...)` requires a replacement intent or replacement proposal id, appends `action.superseded`, links old and replacement identities, and preserves completed old action status instead of rewriting it in place.
- `RunProjector` validates retry / cancel / supersede event basis, projects read-model state from events only, and keeps old action history visible.
- Existing runtime tests cover malformed / unknown basis, terminal-state rejection, replacement identity, old-state preservation, no hidden scheduler/process/concurrency surfaces, and no product HTTP routes.

No correctness bug was found in this closure review.

## 3. Helper Summary

| Helper | Current behavior | Closed boundary |
| --- | --- | --- |
| `request_retry(...)` | accepts failed action retry; accepts completed rerun only with `explicit_rerun=True`; appends retry request / created events; returns replacement ids | no automatic retry engine, no scheduler/backoff state, no old execution mutation |
| `request_cancel(...)` | accepts pending approval or running action as logical cancel request; appends cancel request event; rejects terminal actions | no process kill, no tool-level cancellation hook, no event deletion |
| `request_supersede(...)` | links old proposal/execution to replacement proposal/execution; records provenance / reason code; preserves completed old action status | no in-place rewrite, no real concurrency, no replacement execution side effect |

## 4. Evidence Checklist

| Check | Result | Evidence |
| --- | --- | --- |
| Canonical retry events | pass | `request_retry(...)` appends `action.retry_requested` and `action.retry_created` |
| Retry old-state preservation | pass | failed action remains failed; completed rerun keeps completed old state |
| Retry replacement identity | pass | helper returns new proposal / execution ids distinct from basis ids |
| Cancel logical-only boundary | pass | result includes `logical_only=True` and `process_kill=False` |
| Cancel terminal rejection | pass | completed / failed action cancel is rejected without partial cancellation |
| Cancel history preservation | pass | existing execution / artifact events remain in the event log |
| Supersede linkage | pass | helper records old proposal/execution and replacement proposal/execution identities |
| Supersede old-state preservation | pass | completed old action remains completed |
| Fail-closed malformed basis | pass | unknown retry / cancel / supersede basis raises controlled `ValueError` before append |
| No product HTTP route | pass | runtime tests check route inventory for no retry / cancel / supersede product routes |
| No scheduler / process manager | pass | runtime tests check no scheduler, backoff, timeout, process manager, queue worker, or concurrency runtime surfaces |
| Event-sourced projection | pass | projector derives `RunState.action_retries`, `action_cancellations`, and `action_supersessions` from canonical events |

## 5. Deferred / Non-Goals

Still deferred:

- scheduler
- automatic retry engine
- retry backoff policy
- timeout engine
- process kill / thread interruption
- tool-level cancellation hooks
- concurrent execution coordination
- queue worker / job runner
- distributed locks
- product HTTP retry / cancel / supersede routes
- UI stop / retry / supersede controls
- workspace cleanup / rollback side effects

## 6. Remaining Friction

Remaining friction is not blocker-level:

- Retry / supersede helpers create or reference replacement proposal / execution identity, but they do not execute the replacement action. That is intentional for this first slice; automatic retry execution belongs to a future scheduler/runtime boundary.
- Cancel of pending approval is represented as logical action cancellation, but it does not resolve or invalidate the approval. A future approval-cancel contract can define that interaction if needed.
- Rejected requests are fail-closed before append rather than represented as canonical rejected-request events. This is acceptable until a product audit trail requires rejected request history.
- Runtime helpers are in-process only; no HTTP product route exists.

## 7. Recommended Next Path

Recommended kernel path: `Event Schema Registry / Compatibility Boundary`.

Reason:

- action lifecycle events now include more basis metadata and runtime request shapes.
- registry / policy basis, workspace lifecycle, external observations, and R/C/S runtime helpers all depend on stable event payload interpretation.
- a compatibility boundary should be docs-only first and should not implement a migration framework.

Alternatives:

- `Worker Handoff App Spike Selection` if the goal is app-level usability pressure.
- `External Review Package Refresh` if the goal is reviewer handoff instead of more kernel design.

Do not start scheduler, process kill, real concurrency, product HTTP routes, plugin marketplace, policy DSL, schema migration framework, real HTTP server, real LLM, provider adapter, or memory query engine from this closure review.

## 8. Verification

Closure verification:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel -q
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario artifact-review --trace
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario external-snapshot-review --trace
rg -n '(^|\s)(from|import) x_agent\b' src/isotope_kernel tests/isotope_kernel
git diff -- src tests .github pyproject.toml
```
