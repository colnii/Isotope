# Session / Run Lifecycle Boundary v0.2

状态：`boundary defined; red tests recommended`

## 1. Purpose

本文定义 session / run lifecycle 的最小 kernel contract。当前 Isotope 已经可以创建 session / run，并通过 `run.created`、action / approval / retry / cancel / supersede / checkpoint 等事件投影 `RunState`。但 session 仍主要是 in-process server metadata，run lifecycle 也还缺少统一的 status transition contract。

本边界只做 docs-only planning，不实现代码、不新增测试、不打开 product workflow。

## 2. Current Shape

当前已有：

- `InProcessServer.create_session()`
- `InProcessServer.create_run(session_id, goal)`
- canonical `run.created`
- `RunState.status`
- `run.completed`
- pending approval / denied / failed / completed projection rules
- HTTP in-process session / run routes
- event replay and checkpoint-assisted rebuild for `RunState`

当前缺口：

- `session` 不是 event-sourced read model。
- session 与 run 的生命周期关系只靠 server-local `_sessions` / `_runs` metadata 和 `run.created.session_id` 表达。
- run status transition rules 分散在 action / approval / executor / projector validation 中。
- run terminal states、pause/resume、cancel/supersede 和 multi-run history 没有统一 kernel contract。
- checkpoint 覆盖 `RunState`，但没有 `SessionState` / session checkpoint contract。

## 3. Definitions

- Session: user / application interaction container that can own one or more runs.
- Run: event-sourced execution timeline with its own canonical event log.
- SessionState: future projected read model for session metadata and run index; not implemented in current first slice.
- RunState: current projected read model for a single run.
- Run lifecycle event: canonical event that changes run status or links run to session lifecycle.
- Terminal run state: completed / failed / denied / cancelled-style state where ordinary action append should fail closed.
- Pause state: logical state such as pending approval; not process suspension.

## 4. Hard Contracts

- `RunState` must remain derived only from canonical run events.
- `run.created` must remain the basis event for a run and must include structured `run_id`, `session_id`, and goal metadata.
- Session lifecycle, if promoted to first-class kernel state, must become event-backed; it must not be hidden server-local mutable state.
- Run status transitions must be append-only; helpers must not mutate old run/action/execution state in place.
- Terminal run states must fail closed for ordinary new action input unless an explicit recovery/retry/supersede contract allows it.
- Approval pause is logical state, not scheduler/process state.
- Run cancel / supersede must not imply process kill in v0.2.
- Checkpoint schema/version remains separate from event schema/version and any future `SessionState`.
- HTTP facade may expose read helpers, but no real HTTP server, auth, UI, scheduler, or product workflow is implied.

## 5. Minimal Event / Read-Model Candidate

Candidate canonical events:

- `session.created`
- `session.closed`
- `run.created` (already implemented)
- `run.completed` (already implemented)
- `run.failed` or structured failure via existing `action.failed` plus derived run status
- `run.cancel_requested` or reuse existing action cancel events until run-level cancel is proven necessary
- `run.paused` / `run.resumed` only if approval and runtime helpers cannot express the state cleanly

Candidate `SessionState` fields:

- `session_id`
- `status`
- `run_ids`
- `created_at` / `closed_at`
- `last_event_id`

Candidate `RunState` lifecycle fields:

- `run_id`
- `session_id`
- `goal`
- `status`
- `status_reason_code`
- `terminal_reason`
- `created_event_id`
- `completed_event_id`
- `failed_event_id`
- `cancelled_event_id`
- `last_event_id`

## 6. Allowed / Disallowed Transitions

Initial candidate rules:

- `unknown -> running` via `run.created`: allowed.
- `running -> pending_user_approval`: allowed via approval request.
- `pending_user_approval -> running`: allowed via approved approval resume.
- `pending_user_approval -> denied`: allowed via denied approval.
- `running -> completed`: allowed only when execution / approval validations allow it.
- `running -> failed`: allowed through controlled execution / tool failure.
- terminal -> ordinary input/action append: rejected.
- completed -> retry/rerun: allowed only through explicit retry / rerun helper, not by mutating old run state.
- running/pending -> run-level cancel: deferred until a run-level cancel contract is proven necessary.

## 7. Deferred

- product session UX
- multi-user session ownership / auth
- real HTTP server routes beyond the in-process facade
- scheduler / timeout / process kill
- real concurrency
- cross-run memory promotion
- durable session store outside canonical event logs
- run graph / workflow DAG
- session archival / retention policy

## 8. First Red Tests Recommendation

Suggested tests:

- `tests/isotope_kernel/test_session_lifecycle_boundary.py`
- `tests/isotope_kernel/test_run_lifecycle_boundary.py`

Initial red-test coverage:

1. session lifecycle should be representable by canonical events or a clearly documented controlled setup path.
2. run.created payload must expose stable `run_id`, `session_id`, goal, and basis metadata.
3. replay should restore run lifecycle fields without server-local `_runs`.
4. checkpoint-assisted rebuild should restore run lifecycle fields.
5. ordinary input after terminal run state should fail closed.
6. malformed lifecycle event payloads should fail-fast.
7. session read model, if introduced, must not be mutated directly.
8. no real HTTP server / auth / UI / scheduler / process kill / real concurrency.

## 9. Decision

Session / Run Lifecycle Boundary is the next safe kernel-forward planning target after worker handoff pressure was covered by aggressive-dev. It is kernel-level because session/run identity and terminal-state rules affect every app spike, but the next step should be red tests only. Do not implement product session workflow or run graph behavior until a red-testable contract is accepted.
