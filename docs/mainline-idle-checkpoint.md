# Mainline Idle Checkpoint

状态：`idle / maintenance / friction intake`

## 1. Current Mainline State

Isotope mainline is currently parked in idle / maintenance / friction-intake mode.

Current checkpoint:

- Kernel mainline maintenance mode is active: `docs/kernel-mainline-maintenance-mode.md`.
- External review package is ready: `docs/external-review-package-v0.2.md`.
- Public / internal docs boundary is defined: `docs/public-internal-docs-boundary.md`.
- Concept docs remain in mainline as concept / application-pressure materials: `docs/concepts/README.md`.
- Full regression baseline: `1193 passed, 4 skipped`.
- Key trace demos pass:
  - `python -m isotope_kernel.demo --scenario artifact-review --trace`
  - `python -m isotope_kernel.demo --scenario external-snapshot-review --trace`
  - `python -m isotope_kernel.demo --scenario approval-tool-runner --trace`
  - `python -m isotope_kernel.demo --scenario terminal-exec --trace`
  - `python -m isotope_kernel.demo --scenario model-tool-bridge --trace`
  - `python -m isotope_kernel.demo --scenario llm-provider-route --trace`
  - `python -m isotope_kernel.demo --scenario llm-tool-result-loop --trace`
- No tag or GitHub Release action is part of this checkpoint.
- Model Tool Catalog, Model Tool Call Bridge, LLM Provider Tool Call, tool-result message / bounded follow-up execution, and Codex-as-tool slices are present: `terminal_exec` is visible as model-facing callable metadata, while default `codex_task` is deferred. An explicit Codex adapter path exists with registry enablement and approval, `CodexCliBackend` defines the first read-only local Codex CLI backend boundary, `create_codex_cli_server(...)` wires it into an in-process server only when explicitly selected, `create_codex_cli_http_app(...)` exposes a dev/test in-process HTTP facade route only when explicitly selected, `submit_model_tool_call(...)` can route a deterministic model-selected `codex_task` call through that facade, `create_llm_provider_http_app(...)` exposes dev/test provider routes only when explicitly selected, including `POST /runs/{run_id}/llm/tool-calls` and `POST /runs/{run_id}/llm/tool-result-followups`, and `create_llm_product_chat_http_app(...)` exposes `POST /runs/{run_id}/llm/chat-turns` only when explicitly selected. Default app and provider route app still keep chat-turns disabled. The product chat route first slice allows one provider-selected tool request per call, stops at approval, and resumes only through a later request with safe tool-result context. `--scenario model-tool-bridge`, `--scenario llm-provider-route`, and `--scenario llm-tool-result-loop` demonstrate the chain with fake providers / runners by default. The tool-result loop demo now proves one bounded second provider choice submitted through the same approval path, not an unbounded automatic loop.

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

- Product-level real LLM loop / automatic multi-step tool execution beyond the bounded one-choice / two-step follow-up provider helpers. The product chat route first slice is not an implementation of that full loop.
- Hosted/product `codex_task` route; the explicit server wiring helper, in-process HTTP facade route, and live Codex smoke / diagnosis remain dev-only / test-only paths, not a real listening product path.
- Provider adapter / webhook / network listener.
- Memory query / storage / retrieval ranking / promotion engine.
- Real workspace filesystem, container, git worktree, remote executor, file diff / rollback engine, or binary streaming.
- Real terminal backend, Codex / opencode / Claude adapter, interactive shell / PTY, streaming terminal output, or product terminal route.
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
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario terminal-exec --trace
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario model-tool-bridge --trace
rg -n '(^|\s)(from|import) x_agent\b' src/isotope_kernel tests/isotope_kernel || true
git diff -- src tests .github pyproject.toml
```

If these checks pass and no concrete friction exists, remain idle.
