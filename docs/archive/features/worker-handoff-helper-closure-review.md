# Worker Handoff Helper Closure Review

状态：`first slice complete / closed for now`

## 1. Closure Judgment

`InProcessServer.submit_worker_handoff(...)` closes the `private_append_worker_handoff` friction from aggressive branch commit `1950e32`.

The original problem was that app-shaped worker handoff could be represented by existing canonical events and projected read models, but app code had to know `delegation.*` / `worker.*` payload details and call private `server._append(...)` to assemble the sequence. The helper now provides a narrow in-process path for that sequence.

This is sufficient to mark Worker Handoff Helper first slice complete / closed for now.

## 2. Verified Behavior

- accepts structured delegation intent plus an existing artifact `ResourceRef`
- rejects forged `decision`, forged `grants`, or app-supplied effective grants
- rejects malformed delegation intent before appending worker events
- rejects malformed or unknown artifact refs before appending worker events
- records denied policy decisions as canonical `delegation.proposed` + `delegation.decided(outcome=denied)` audit entries while preserving structured `KernelPermissionError`
- denied policy decisions do not append `worker.*` events and do not create worker read-model entries
- validates the candidate event sequence with `RunProjector` before append
- appends canonical `delegation.proposed`, `delegation.decided`, `worker.created`, `worker.started`, `worker.result_handed_off`, and `worker.completed`
- returns copied projected worker summary and result ref
- preserves replay and checkpoint-assisted rebuild behavior
- does not expose full artifact content
- does not append `run.completed`

## 3. Boundary Kept

The slice did not add:

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
- new dependency

Event store append-only semantics and executor grants semantics remain unchanged.

## 4. Important Limitation

`_derive_worker_handoff_grants(...)` is a first-slice local grant derivation used only to keep this helper deterministic and bounded. It is not a full delegation policy engine.

Future delegation policy integration should decide whether worker handoff should reuse `PolicyEngine`, introduce a delegation-specific policy profile, or compile delegation intent through a broader action-like policy path. That work is deferred until application pressure requires it.

## 5. Remaining Friction

- aggressive-dev should update `worker-handoff-gap` to use `submit_worker_handoff(...)` and prove `private_append_required` becomes false
- delegation policy remains local/minimal for this helper
- worker handoff is still in-process only
- no scheduler / real worker runtime / process lifecycle exists

## 6. Recommended Next Path

Next recommended mainline action is not a deeper worker runtime. Prefer one of:

- `Aggressive Worker Handoff Follow-up Review`: wait for aggressive-dev to consume `submit_worker_handoff(...)` and report whether friction is closed in the app spike
- `Session / Run Lifecycle Boundary`: if continuing core gap work
- `Error Taxonomy Boundary`: if helper/client error handling becomes the next friction

Do not proceed to real worker runtime, process management, remote workers, real HTTP, real LLM, provider adapters, or public SDK without a new bounded batch.
