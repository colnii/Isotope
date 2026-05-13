# Post External Review Checkpoint

状态：`external review ready`

## 1. Current Checkpoint

Current checkpoint: Isotope is ready for external review as a developer-facing kernel prototype.

- External review package is readable: `docs/external-review-package-v0.2.md`.
- Full regression baseline: `1193 passed, 4 skipped`.
- Demo traces pass:
  - `python -m isotope_kernel.demo --scenario artifact-review --trace`
  - `python -m isotope_kernel.demo --scenario external-snapshot-review --trace`
  - `python -m isotope_kernel.demo --scenario approval-tool-runner --trace`
  - `python -m isotope_kernel.demo --scenario terminal-exec --trace`
  - `python -m isotope_kernel.demo --scenario model-tool-bridge --trace`
  - `python -m isotope_kernel.demo --scenario llm-provider-route --trace`
  - `python -m isotope_kernel.demo --scenario llm-tool-result-loop --trace`
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
- Tool / terminal backend boundary: tool protocol model / event shape, model-facing tool catalog, deterministic model tool call bridge plus runnable `model-tool-bridge` demo, bounded LLM provider tool-call / tool-result-follow-up routes plus runnable `llm-provider-route` / `llm-tool-result-loop` demos, explicit in-process product chat route contract for `POST /runs/{run_id}/llm/chat-turns`, safe tool-result handoff with bounded second approval-gated fake Codex execution, Codex-as-tool adapter boundary, Codex CLI backend first slice, explicit Codex CLI server wiring helper, explicit in-process Codex HTTP facade route, controlled terminal execution sample, and fake-backend terminal adapter / selector / artifact-policy / low-sensitive summary are explicit enough for review without claiming productized live backend integration.

## 3. What Should Not Be Overclaimed

Do not present this checkpoint as a product or production runtime.

Not implemented:

- Real listening HTTP server / hosted API.
- Product-level real LLM loop, automatic multi-step tool execution, or provider router beyond the bounded one-choice / two-step follow-up helpers. `POST /runs/{run_id}/llm/chat-turns` is an explicit in-process first-slice route only: one provider-selected tool request per call, approval pause, later resume with safe tool-result context, and no assistant final answer / streaming / hosted HTTP.
- Hosted/product `codex_task` route; current callable path is explicit helper wiring plus approval, the first `CodexCliBackend` boundary, server wiring helper, and in-process HTTP facade route are tested with fake process runners, and live smoke / diagnosis is a dev-only opt-in helper.
- Provider webhook / network listener / external ingestion product API.
- Memory storage, memory query engine, retrieval ranking, or promotion policy.
- Real workspace filesystem, container, git worktree, remote executor, file diff / rollback engine, or binary streaming.
- Real terminal backend, Codex / opencode / Claude adapter, interactive shell / PTY, streaming terminal output, or product terminal route.
- Product UI, auth, multi-user identity, notification, or approval dashboard.
- Scheduler, process kill, tool-level cancellation hooks, retry backoff engine, timeout engine, or real concurrency.
- Plugin marketplace, policy DSL, remote registry loading, JSON Schema / protobuf / Avro dependency, or schema migration framework.

## 4. Recommended Next Options

Option A: pause kernel implementation and let application-layer prototype pressure-test the kernel.

- Best default if the goal is to find real ergonomics friction.
- Keeps the kernel from expanding based on imagined product needs.
- Any future kernel work should be backed by concrete app-layer pain.

Option B: live `CodexCliBackend` smoke or selected terminal backend adapter spike, only after the user chooses it explicitly.

- Best if the next review question is how Codex / opencode / Claude-style execution should be wrapped by Isotope policy, approval, artifact, audit, checkpoint, and replay.
- Should start with selected-backend design and red tests before any adapter implementation.

Option C: application-layer friction intake.

- Best if the app-layer prototype or aggressive branch reports a concrete helper / read-model / replay / checkpoint gap.
- Mainline should classify the friction first, then do docs-only boundary or red tests before implementation.

Option D: prepare resume / tag / review handoff.

- Best if an external reviewer needs a fixed anchor or a clean resume note.
- Do not create or move a tag unless the user explicitly asks.

## 5. Recommendation

Default recommendation: pause kernel expansion briefly and let application-layer work create real friction.

Keep kernel work limited to friction that application layer proves necessary. If no concrete friction appears, stay in external review / feedback intake rather than opening real HTTP server, product LLM loop, provider router, memory query engine, filesystem substrate, scheduler, plugin marketplace, policy DSL, schema migration framework, or real terminal backend integration.
