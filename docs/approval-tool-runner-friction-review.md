# Approval Tool Runner API Friction Review

状态：`current; approval lookup helper implemented`

## 1. Purpose

本文 review `approval-gated tool runner` usability pressure test 暴露的 API friction（开发者易用性摩擦）。

本轮结论不是要把 spike 变成 product API，也不打开真实 HTTP server、real LLM、provider adapter 或 filesystem substrate。目标是把 awkward glue code 分层，判断下一步最小优化应该落在哪里。

当前 evidence：

- `python -m isotope_kernel.demo --scenario approval-tool-runner`
- `python -m isotope_kernel.demo --scenario approval-tool-runner --json`
- full regression after helper slice: `853 passed`
- spike 仍 deterministic / in-process / no real HTTP server / no real LLM / no provider adapter / no filesystem mutation

## 2. Friction Summary

| Friction | Evidence | Classification | Impact | Suggested action |
| --- | --- | --- | --- | --- |
| approval-gated input uses `server.submit_tool_request(...)` | demo cannot express `requires_approval=True` through current HTTP `/runs/{run_id}/input` path | facade / helper gap | medium | do after approval lookup helper, unless the next spike needs this first |
| approval id lookup scans canonical events | demo used to find `approval_id` by scanning events after pending approval | read-model helper gap | medium-high | fixed by approval lookup helper |
| workspace binding uses explicit `workspace.bound` | demo manually appends a canonical workspace binding event for the spike | kernel / server integration gap | high, but broader | design separately before implementation |

No correctness bug was found in the current spike. The awkwardness is useful evidence that the kernel surface is still too raw for developer ergonomics, not evidence that the event-sourced contracts are broken.

## 3. Answers

### Does `server.submit_tool_request(...)` show a missing approval-gated helper?

Yes, but this is primarily a facade/helper gap, not a kernel contract bug.

The kernel already supports pending approval, canonical `approval.requested`, `approval.resolved`, resume through the executor path, and original `PolicyDecision.grants` preservation. The awkward part is that the demo needs to call the server helper directly because the current HTTP facade input route only models plain text input.

What is missing is a natural helper such as a server-level approval-gated action submission API, or an explicit facade option that can request approval without bypassing action chain / policy / event log. This should not be rushed into the HTTP route shape until tests define whether the helper belongs in `InProcessServer`, `HttpApiApp`, or a scenario-oriented facade.

### Should approval id scanning become a read helper?

Yes. This is the lowest-risk next improvement.

The read model already carries approval state in `RunState.approvals`. A client or demo should not need to scan canonical events just to discover the pending approval created by a submission. Event scanning is acceptable for diagnostics, but awkward for normal use.

The minimal helper now exposes pending approvals from the projected read model:

- `InProcessServer.get_pending_approvals(run_id)`
- `InProcessServer.get_approval(run_id, approval_id)`
- in-process HTTP lookup routes for `GET /runs/{run_id}/approvals` and `GET /runs/{run_id}/approvals/{approval_id}`

The helper reads projected approval summaries, does not append events, and does not change approval resolution semantics. The `approval-tool-runner` demo now uses the helper instead of scanning canonical events for `approval_id`.

### Does manual `workspace.bound` show missing workspace binding integration?

Yes, but this is a larger kernel / server integration gap.

`workspace.bound` is already the correct canonical event shape for the first workspace substrate slice. The friction is ownership: the spike currently creates the binding explicitly, while a real developer path would expect a policy-granted workspace binding helper or server boundary to create it.

This should be solved carefully because it touches policy grants, worker / execution binding, artifact capture expectations, and eventual path-safety semantics. It should not silently become filesystem mutation, container setup, git worktree creation, or remote executor integration.

## 4. Layering

Kernel-layer issues:

- Workspace binding ownership is not yet integrated into a server / execution boundary.
- Future approval-gated action submission must still prove it cannot bypass action chain, policy, or canonical events.
- Any workspace helper must prove requested mode cannot exceed `PolicyDecision.grants`.

Facade/helper issues:

- Approval lookup should use projected `RunState.approvals` instead of event scans.
- A narrow helper can hide common read-model plumbing without changing kernel semantics.
- An approval-gated submission helper may be useful later, but should be tested separately from read lookup.

Demo glue issues:

- The spike previously had `_latest_approval_id(...)` event scan glue; the current demo uses approval lookup/read helper instead.
- The spike currently has explicit `workspace.bound` append glue.
- These are acceptable in a pressure test only because the JSON output records the friction instead of hiding it.

Acceptable v0 shape for now:

- `server.submit_tool_request(..., requires_approval=True)` is explicit and still goes through policy / approval / executor boundaries.
- Manual `workspace.bound` is tolerable in a spike because workspace substrate is still first-slice read model only.
- No product-facing approval API, workspace API, real filesystem mutation, or real HTTP server is implied.

## 5. Candidate Next Steps

### A. Add ergonomic server helper for approval-gated action submission

Useful, but not first.

This would make scenario code cleaner, but it risks mixing two concerns: action submission semantics and approval lookup ergonomics. It should follow a smaller read-helper slice unless a future pressure test specifically needs a one-call submit-and-return-approval shape.

### B. Add approval lookup/read helper

Implemented.

This is the smallest clear win. It removes event scan glue, uses existing projected approval state, and does not require changing event store append-only semantics, executor grants semantics, workspace binding ownership, HTTP route inventory, or action lifecycle rules.

Implemented first slice:

- red / green tests for `get_pending_approvals(run_id)` and `get_approval(run_id, approval_id)`
- helper reads projected `RunState.approvals`
- unknown run / approval returns controlled errors
- lookup does not append events
- helper returns copied JSON-compatible summaries
- in-process HTTP lookup route exists, but the supported route inventory still does not productize approval collection routes

### C. Add workspace binding helper

Important, but should be a separate design slice.

This likely belongs closer to kernel/server integration because it decides who owns `workspace.bound` event creation. It should stay constrained to `shared_ro` / no filesystem mutation until path safety and substrate design are reopened.

### D. Keep spike as-is and move to another pressure test

Not recommended yet.

The spike exposed concrete ergonomics gaps. Moving on immediately would leave the next pressure test with the same event scan and workspace binding glue, reducing the signal from future spikes.

## 6. Recommendation

Recommended next batch after this helper: reassess remaining spike friction before choosing between approval-gated submission helper and workspace binding helper.

Rationale:

- approval id event-scan glue is now removed.
- `server.submit_tool_request(..., requires_approval=True)` remains a facade/helper gap.
- explicit `workspace.bound` remains the broader kernel / server integration gap.
- workspace binding integration should still be protected by a dedicated boundary before implementation.

Do not solve in the next batch:

- real HTTP server
- approval product UI
- auth / identity
- notification / scheduler
- workspace filesystem mutation
- container / git worktree / remote executor
- provider adapter
- memory query engine
