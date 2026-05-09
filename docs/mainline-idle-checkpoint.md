# Mainline Idle Checkpoint

状态：`idle / maintenance / friction intake`

## 1. Current Mainline State

Isotope mainline is currently parked in idle / maintenance / friction-intake mode.

Current checkpoint:

- Kernel mainline maintenance mode is active: `docs/kernel-mainline-maintenance-mode.md`.
- External review package is ready: `docs/external-review-package-v0.2.md`.
- Public / internal docs boundary is defined: `docs/public-internal-docs-boundary.md`.
- Concept docs remain in mainline as concept / application-pressure materials: `docs/concepts/README.md`.
- Full regression baseline: `986 passed`.
- Key trace demos pass:
  - `python -m isotope_kernel.demo --scenario artifact-review --trace`
  - `python -m isotope_kernel.demo --scenario external-snapshot-review --trace`
  - `python -m isotope_kernel.demo --scenario approval-tool-runner --trace`
- No tag or GitHub Release action is part of this checkpoint.

This checkpoint is a parking point, not a new implementation milestone.

## 2. What Happens While Idle

Default behavior:

- Do not proactively expand kernel features.
- Do not add tests just to open a new kernel track.
- Do not add docs that imply a new active kernel direction unless the user explicitly asks.
- Keep mainline stable, reviewable, and easy to resume.
- Let application-layer prototype work on the aggressive branch / separate session produce concrete friction first.
- Accept future kernel work only when app-layer work or external review proves a bounded helper, boundary, replay, checkpoint, read-model, or API ergonomics gap.

Periodic verification-only checks are acceptable when requested.

## 3. Reopen Conditions

Reopen kernel mainline only when there is concrete evidence such as:

- An app-layer scenario needs private event-log scanning, private `_append(...)`, or raw projector access to do normal work.
- A deterministic app spike cannot express a lifecycle with existing canonical events and read models.
- Replay or checkpoint-assisted rebuild fails to preserve app-layer state that should be kernel-owned.
- Existing helper APIs force clients to bypass policy, grants, provenance, or canonical event boundaries.
- External review identifies a specific contract ambiguity that blocks understanding or safe use.

When reopening, keep the usual sequence:

1. Docs-only boundary if the contract is unclear.
2. Red tests if behavior needs to be fixed.
3. Smallest green implementation slice.
4. Docs/status sync.
5. Commit / push after verification.

## 4. Do Not Open From Idle By Default

Do not start these from idle without explicit user instruction and a bounded batch:

- Real LLM loop.
- Provider adapter / webhook / network listener.
- Memory query / storage / retrieval ranking / promotion engine.
- Real workspace filesystem, container, git worktree, remote executor, file diff / rollback engine, or binary streaming.
- Real HTTP server / hosted API.
- UI / auth / multi-user / notification surfaces.
- Scheduler, process kill, timeout engine, retry backoff engine, tool-level cancellation hooks, or real concurrency.
- Plugin marketplace, policy DSL, remote registry, or schema migration framework.
- Tag movement, new demo tag, GitHub Release, or release packaging.

## 5. Next Suggested Action

Default next action: wait for an application-layer friction report or external review feedback.

Alternative low-risk action: run periodic verification only:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel -q
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario artifact-review --trace
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario external-snapshot-review --trace
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario approval-tool-runner --trace
rg -n '(^|\s)(from|import) x_agent\b' src/isotope_kernel tests/isotope_kernel || true
git diff -- src tests .github pyproject.toml
```

If these checks pass and no concrete friction exists, remain idle.
