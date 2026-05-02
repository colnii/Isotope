# Source Artifact Helper Closure Review

状态：`closed / complete`

## 1. Closure Judgment

`InProcessServer.create_source_artifact(...)` 可以标为 closed / complete for now。

它解决了 `artifact-review` demo 的 source artifact setup friction：demo 不再手写 private `server._append(...)` source action / artifact lifecycle events，也不再直接组合 `artifact_store.create_artifact(...)` 和 manual `artifact.created` payload。

未发现需要修改 `src/` 或 `tests/` 的 bug。

## 2. Verified Boundary

当前 helper:

- validates `run_id` / `summary` / `content` / `artifact_type` before appending events。
- compiles a compact `write_artifact_tool` intent through `ActionCompiler`。
- obtains a `PolicyDecision` through `PolicyEngine`。
- appends canonical `action.proposed` and `action.decided` events。
- executes through the existing `Executor` path。
- creates artifact via `ArtifactStore` and canonical `artifact.created` event。
- returns status, proposal id, decision id, execution id, artifact summary, structured `ResourceRef`, artifact type, provenance, and projected run state。
- does not return artifact full content。
- does not append `run.completed` during source setup。
- does not open HTTP full-content route。

## 3. Demo Review

`artifact-review` now calls:

- `app.server.create_source_artifact(...)`

The `artifact-review` scenario no longer uses:

- `app.server._append(...)` for source artifact setup。
- hard-coded source proposal / decision / execution ids。
- direct source `artifact_store.create_artifact(...)` setup glue。

The demo still uses controlled full-content retrieval only at the retrieval layer with explicit grants, caller context, and purpose. It does not expose content in JSON / plain / trace output.

## 4. Test Coverage Review

Covered by `tests/isotope_kernel/test_source_artifact_setup_helper.py`:

- helper creates source artifact with summary / structured ref / provenance。
- helper public return does not contain full content fields or durable content string。
- helper appends canonical events and does not append `run.completed`。
- replay restores source artifact read model。
- checkpoint-assisted rebuild restores source artifact read model。
- `artifact-review` uses helper instead of private append glue。
- HTTP full-content route remains `501 not_enabled`。
- binary / file-like input is rejected without partial artifact state。
- malformed request fails fast without partial artifact state。

Policy coverage note:

- Generic policy tests cover approved / modified / denied `PolicyDecision` behavior.
- The source helper does not expose requested capability knobs, so the normal helper path requests the exact `write_artifact_tool` capability and does not naturally create a helper-specific `modified` decision.
- A helper-specific denied / modified test is not a closure blocker for this slice because the helper has no public capability-upgrade surface. If the helper later accepts requested capabilities, add red tests before expanding it.

## 5. Non-Goals Still Intact

Still not implemented:

- product artifact upload API。
- file upload / file picker。
- binary streaming。
- real filesystem mutation outside existing artifact store persistence。
- real HTTP server / product HTTP artifact creation route。
- provider adapter。
- memory query engine。
- semantic retrieval / ranking。
- product artifact review facade。

## 6. Remaining Friction

The source artifact setup friction is closed.

Remaining `artifact-review` friction after this closure was narrower:

- review provenance still found the source `artifact.created` basis event by scanning run events in demo glue。

That follow-up has now been handled by `InProcessServer.get_artifact_record(...)`; see `docs/artifact-review-provenance-helper-boundary-v0.2.md`.

Still intentionally not solved:

- controlled full-content retrieval remains verbose but explicitly grants-bound for Track C。
- there is still no product-level artifact review facade, by design。
