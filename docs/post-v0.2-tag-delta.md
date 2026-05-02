# Post v0.2 Tag Delta

状态：`current`

## 1. Purpose

本文记录 `v0.2-demo` tag 之后 `main` 的增量，避免把 tag anchor 和 tag 后 mainline 状态混在一起。

本文件不创建 tag、不发布 GitHub Release，也不移动既有 tag。

## 2. Anchors

- `v0.2-demo` tag: `09319e7407116d9f99f4a18853d4df23a8714720`
- current `main` after this delta review: `68ea007bff9a1c7f44dff6b6806939eeec1b4eb9`
- current baseline: `765 passed`
- GitHub Release: not published
- release meaning: developer demo only, not product release

## 3. Delta Since `v0.2-demo`

`main` is ahead of `v0.2-demo`.

Commits included in `v0.2-demo..main` at this review:

- `0c0898c` docs: record v0.2 demo tag
- `f36db26` docs: define external ingestion boundary
- `909ce95` feat: add external ingestion boundary
- `59dd5cf` docs: sync external ingestion boundary status
- `a2099c0` feat: add external observation read model invariants
- `2a877a2` docs: sync external observation status
- `8474d78` docs: close external ingestion boundary track
- `68ea007` docs: review post v0.2 tag delta

The main technical delta is Track F: External Ingestion / `ImportedSnapshot` Boundary.

## 4. What Track F Adds

Current `main` adds boundary / read-model / checkpoint support for external observations:

- `ingestion.py` fail-closed / not-enabled boundary.
- `ImportedSnapshot` slice model.
- canonical `snapshot.imported` projection into `RunState.external_observations`.
- external observation read-model invariants.
- replay and checkpoint-assisted rebuild for `external_observations`.
- native canonical state priority over imported observations.
- explicit conflict marking for conflicting snapshots.

This does not implement real provider ingestion.

## 5. What Remains Deferred

Still deferred after the tag delta:

- real provider adapter
- external webhook / callback handling
- network listener
- public external ingestion HTTP API
- OpenAI / Responses / GitHub provider integration
- imported-observation-driven native state updates
- GitHub Release publication

HTTP `/external-ingestion` remains `501 not_enabled`.

## 6. Tag Recommendation

Do not move or force-update `v0.2-demo`.

Default recommendation: do not create `v0.2.1-demo` yet. Keep `v0.2-demo` as the accepted developer demo anchor and document that `main` is ahead of the tag with Track F boundary work.

Create a future `v0.2.1-demo` only if a reviewer or external reader needs a fixed tag that includes Track F external ingestion boundary / read-model / checkpoint support.

## 7. Verification Scope

The post-tag mainline is expected to keep passing:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope_kernel -q
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --json
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario v0.2
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario v0.2 --json
```

At this review, the expected full regression baseline is `765 passed`.

## 8. Cycle Closure

`docs/v0.2-cycle-closure-review.md` records the current v0.2 cycle closure decision.

Default next mode is cleanup / docs organization / external review, not additional runtime implementation. `v0.2.1-demo` remains optional and should only be prepared if an external reviewer needs a fixed tag that includes Track F.
