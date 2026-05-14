# Worker Handoff Helper Boundary v0.2

状态：`first green slice complete / closed for now`

## 1. Purpose

本文把 aggressive branch 暴露的 `private_append_worker_handoff` friction 收进 mainline boundary。目标不是实现 real worker runtime，而是定义一个最小 in-process helper contract，让 app / demo 不必了解 `delegation.*` / `worker.*` canonical payload，也不必触碰 private `server._append(...)` 才能表达 delegated worker result handoff。

来源证据：

- aggressive commit: `1950e32` (`feat: add worker handoff gap spike`)
- scenario: `worker-handoff-gap`
- targeted test: `tests/isotope/test_worker_handoff_gap_spike.py` -> `5 passed`
- observed friction: app-shaped worker handoff can replay / checkpoint, but currently requires private append glue.

## 2. Selection

推荐的 mainline slice 是 `Worker Handoff Helper Red Tests -> Green Slice`。当前 red tests 已补齐 artifact existence hardening，并已通过最小 green implementation。

Why this slice:

- It is a real kernel helper gap, not app-local formatting.
- The existing projector already validates `delegation.proposed`, `delegation.decided`, `worker.created`, `worker.started`, `worker.result_handed_off`, and worker terminal events.
- The missing boundary is a public in-process server helper that can assemble the canonical event sequence safely.
- The slice can be tested deterministically without real concurrency, process spawn, remote workers, provider adapters, or real HTTP.

## 3. Definitions

- Worker handoff helper: an `InProcessServer` helper that accepts a structured delegation intent and a worker result artifact `ResourceRef`, then appends the canonical worker/delegation event sequence through existing event-store and projector validation.
- Delegation intent: structured input describing parent agent, requested worker role, requested capabilities, and optional workspace/grant expectations.
- Worker result handoff: a canonical `worker.result_handed_off` event that references an artifact `ResourceRef` plus summary metadata, without mutating `RunState` directly.
- Projected worker summary: copied `RunState.workers[worker_id]` read-model summary returned after candidate replay / append.

## 4. Hard Contracts

- Helper must be deterministic and in-process.
- Helper must append canonical events; it must not mutate `RunState`, `SessionState`, workers, artifacts, or checkpoints directly.
- Helper must use existing event-store append-only semantics.
- Helper must use projector validation before or during append so malformed sequences fail closed without partial worker state.
- Helper must preserve delegation / worker / result provenance.
- Worker result handoff must use structured artifact `ResourceRef`.
- Helper must not return full artifact content.
- Helper must not bypass delegation policy semantics or executor grants semantics.
- Current `_derive_worker_handoff_grants(...)` is first-slice local grant derivation, not a full delegation policy engine.
- Helper must not create real workers, threads, processes, containers, git worktrees, remote executors, real HTTP routes, provider adapters, real LLM calls, scheduler state, or public SDK surface.

## 5. Minimal Shape Candidate

Possible helper name:

- `InProcessServer.submit_worker_handoff(...)`
- or `InProcessServer.create_worker_handoff(...)`

Candidate input:

- `run_id`
- `parent_agent_id`
- `requested_worker_role`
- `requested_capabilities`
- `artifact_ref`
- `summary`
- optional `workspace`
- optional caller/request metadata

Candidate output:

- `delegation_id`
- `decision_id`
- `worker_id`
- `result_ref`
- copied projected worker summary
- canonical basis event ids, if already available from local append helpers

The exact name and object shape should be locked by red tests, not by this document.

## 6. Implemented First Slice

Current helper:

- `InProcessServer.submit_worker_handoff(...)`

Current coverage:

- helper accepts structured delegation intent plus an existing artifact `ResourceRef`
- helper rejects forged decision / grants in app input
- helper rejects malformed intent and malformed or unknown artifact refs without partial worker events
- denied policy path appends canonical `delegation.proposed` + `delegation.decided(outcome=denied)` for audit while preserving structured error compatibility
- helper appends canonical `delegation.proposed`, `delegation.decided`, `worker.created`, `worker.started`, `worker.result_handed_off`, and `worker.completed`
- helper returns copied projected worker summary and result ref
- replay and checkpoint-assisted rebuild restore worker handoff summary
- helper does not expose full content and does not append `run.completed`

This is still only an in-process helper. It does not create real workers, threads, processes, containers, git worktrees, remote executors, real HTTP routes, provider adapters, scheduler state, or public SDK surface.

Closure review: `../features/worker-handoff-helper-closure-review.md`.

## 7. Red Tests

Suggested file:

- `tests/isotope/test_worker_handoff_helper.py`

Test goals:

- helper exists on `InProcessServer`.
- helper accepts structured delegation intent plus artifact `ResourceRef`.
- helper appends canonical delegation / worker / result handoff events.
- helper returns projected worker summary with result refs.
- helper preserves parent agent / delegation / decision / worker provenance.
- helper rejects malformed delegation intent.
- helper rejects malformed artifact ref.
- helper does not expose full artifact content.
- helper fails closed without partial worker state on invalid input.
- denied policy path is auditable through `RunState.delegations` without `worker.*` events.
- replay restores worker handoff summary.
- checkpoint-assisted rebuild restores worker handoff summary.
- demo / app layer no longer needs private `server._append(...)` for worker handoff setup.

## 8. Deferred

- real concurrency
- process spawn / process kill
- scheduler / queue runner
- remote worker
- container / git worktree automation
- real filesystem workspace substrate
- real HTTP route
- real LLM / provider adapter
- public worker SDK
- product UX for worker delegation

## 9. Stop Conditions

Stop before implementation if red tests require:

- changing event store append-only semantics
- changing executor grants semantics
- implementing real concurrency, process spawn, remote workers, containers, git worktrees, real HTTP, real LLM, provider adapters, or new dependencies
- deciding product UX for worker delegation
- broad redesign of existing `delegation.*` / `worker.*` canonical events
