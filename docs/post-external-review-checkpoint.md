# Post External Review Checkpoint

状态：`external review ready`

## 1. Current Checkpoint

Current checkpoint: Isotope is ready for external review as a developer-facing kernel prototype.

- External review package is readable: `docs/external-review-package-v0.2.md`.
- Full regression baseline: `986 passed`.
- Demo traces pass:
  - `python -m isotope_kernel.demo --scenario artifact-review --trace`
  - `python -m isotope_kernel.demo --scenario external-snapshot-review --trace`
  - `python -m isotope_kernel.demo --scenario approval-tool-runner --trace`
- No tag or GitHub Release was created for this checkpoint.
- `main` is ahead of the existing `v0.2-demo` tag. The tag remains the original developer demo anchor; do not move it unless explicitly requested.

This checkpoint is a review handoff point, not a product release.

## 2. Stable Enough For Review

The following surfaces are stable enough to ask an external reviewer to critique the shape, naming, strictness, and boundaries:

- Event-sourced kernel shape: canonical events are the source of projected state.
- Action / policy / executor chain: action proposals go through policy decisions and executor-owned lifecycle events.
- Append-only event log: lifecycle changes append events rather than rewriting old state.
- Projector / replay / checkpoint: `RunState` can be rebuilt from events and checkpoint-assisted rebuilds.
- Artifact / `ResourceRef` / provenance: artifact summaries and handoffs use refs and provenance instead of raw content in native state.
- Approval / workspace / external observation: approval state, workspace binding/lifecycle read model, and imported snapshot observations are event-sourced.
- Retry / cancel / supersede logical helpers: runtime helpers append canonical request events without scheduler, process kill, or hidden concurrency.
- Registry / policy / event schema version basis: action registry basis, policy profile basis, and event schema compatibility are explicit enough for replay and review.

## 3. What Should Not Be Overclaimed

Do not present this checkpoint as a product or production runtime.

Not implemented:

- Real listening HTTP server / hosted API.
- Real LLM loop or provider adapter.
- Provider webhook / network listener / external ingestion product API.
- Memory storage, memory query engine, retrieval ranking, or promotion policy.
- Real workspace filesystem, container, git worktree, remote executor, file diff / rollback engine, or binary streaming.
- Product UI, auth, multi-user identity, notification, or approval dashboard.
- Scheduler, process kill, tool-level cancellation hooks, retry backoff engine, timeout engine, or real concurrency.
- Plugin marketplace, policy DSL, remote registry loading, JSON Schema / protobuf / Avro dependency, or schema migration framework.

## 4. Recommended Next Options

Option A: pause kernel implementation and let application-layer prototype pressure-test the kernel.

- Best default if the goal is to find real ergonomics friction.
- Keeps the kernel from expanding based on imagined product needs.
- Any future kernel work should be backed by concrete app-layer pain.

Option B: continue kernel with `Tool Protocol Boundary`.

- Best if the next review question is how tools should be described, invoked, versioned, and constrained.
- Should start docs-only, then red tests, before any implementation.

Option C: continue usability with `Worker Handoff App Spike Selection`.

- Best if the next pressure test should exercise worker lifecycle, delegation policy, workspace grants, and result handoff.
- Must remain deterministic / in-process and avoid real concurrency.

Option D: prepare resume / tag / review handoff.

- Best if an external reviewer needs a fixed anchor or a clean resume note.
- Do not create or move a tag unless the user explicitly asks.

## 5. Recommendation

Default recommendation: pause kernel expansion briefly and let application-layer work create real friction.

Keep kernel work limited to friction that application layer proves necessary. If no concrete friction appears, stay in external review / feedback intake rather than opening real HTTP server, real LLM, provider adapter, memory query engine, filesystem substrate, scheduler, plugin marketplace, policy DSL, or schema migration framework.
