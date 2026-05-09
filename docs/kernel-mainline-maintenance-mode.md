# Kernel Mainline Maintenance Mode

状态：`active / conservative maintenance`

## 1. Current Mode

Isotope mainline is now in conservative maintenance mode.

The current stable checkpoint is:

- External review package: `docs/external-review-package-v0.2.md`.
- Post external review checkpoint: `docs/post-external-review-checkpoint.md`.
- Full regression baseline: `986 passed`.
- Passing demos:
  - `python -m isotope_kernel.demo --scenario artifact-review --trace`
  - `python -m isotope_kernel.demo --scenario external-snapshot-review --trace`
  - `python -m isotope_kernel.demo --scenario approval-tool-runner --trace`
- No GitHub Release has been published for this checkpoint.
- `main` remains ahead of the existing `v0.2-demo` tag; do not move that tag unless explicitly requested.

This mode means the kernel mainline should stay stable, reviewable, and ready to absorb proven friction. It should not keep expanding kernel features just because a next track exists.

## 2. Operating Rule

Default behavior:

- Do not start new kernel features, tests, or docs tracks unless the user explicitly asks.
- Treat application-layer prototype work on the aggressive branch / separate app-layer track as the source of new friction.
- Only reopen kernel work when application-layer or external-review evidence shows a concrete helper, boundary, replay, checkpoint, or API ergonomics gap.
- Keep `README.md`, `AGENTS.md`, `docs/current-status.md`, `docs/v0.2-roadmap.md`, and `docs/agent-task-queue.md` aligned when the mode changes.

This is not a freeze. It is a stricter intake rule: kernel work must now be justified by observed pressure, not speculative platform design.

## 3. Accepted Friction Intake

Kernel mainline may accept a new batch when there is concrete evidence such as:

- A deterministic app-layer scenario needs awkward raw event scanning or private helper access.
- A helper is missing but the required boundary is already proven by an app spike.
- Replay, checkpoint-assisted rebuild, or read-model behavior fails to represent an app-layer lifecycle.
- A docs/status statement conflicts with actual implemented behavior.
- An external reviewer identifies a specific kernel contract ambiguity that blocks understanding or adoption.

Each accepted batch should still be bounded: docs-only boundary first when design is unclear, red tests before implementation, then the smallest green slice and docs/status sync.

## 4. Not Accepted By Default

Do not use maintenance mode as permission to open product surfaces.

Still deferred unless explicitly requested:

- Real listening HTTP server / hosted API.
- Real LLM loop or provider adapter.
- Provider webhook / network listener / external ingestion product API.
- Memory storage, query engine, retrieval ranking, or promotion policy.
- Real workspace filesystem, container, git worktree, remote executor, file diff / rollback engine, or binary streaming.
- Product UI, auth, multi-user identity, notifications, or approval dashboard.
- Scheduler, process kill, tool-level cancellation hooks, retry backoff engine, timeout engine, or real concurrency.
- Plugin marketplace, policy DSL, remote registry loading, schema migration framework, or product policy UI.
- Tag movement or GitHub Release publication.

## 5. Next Options

Default next mode: application-layer friction intake or external review feedback intake.

If the user explicitly asks to continue kernel work, likely candidates are:

- `Tool Protocol Boundary`: docs-only first, because tool description / invocation / versioning is still a kernel-level gap.
- `Worker Handoff App Spike Selection`: usability pressure if application-layer work needs worker/delegation coverage.
- `External Review Package Refresh`: if reviewer feedback changes the handoff package.

Do not start these automatically. The queue should remain parked until the user supplies a concrete app-layer friction report, external reviewer feedback, or an explicit kernel batch request.
