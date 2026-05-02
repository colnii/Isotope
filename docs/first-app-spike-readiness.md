# First App Spike Readiness

状态：`artifact review flow first slice complete`

## 1. Purpose

本文判断当前 kernel 是否已经足够进入 first app spike（第一个小应用尖刺验证），并选择下一批 red tests 的候选。

它最初不是 implementation plan，也不授权直接实现 app。后续 package 已明确允许 red -> green，因此本文现在同时记录 first-slice outcome。

## 2. Current Kernel Readiness

当前可用边界：

- deterministic in-process demo runtime
- `HttpApiApp` in-process facade
- `ActionCompiler -> PolicyEngine -> Executor`
- `PolicyDecision.grants`
- approval pause / resume
- approval lookup helper
- submit action helper
- workspace binding helper
- artifact store
- artifact summary
- structured `ResourceRef`
- controlled artifact content retrieval boundary
- replay and checkpoint-assisted rebuild
- memory `boundary_only`

当前仍 deferred：

- real HTTP server
- real LLM
- real filesystem mutation
- provider adapter / webhook
- memory query engine
- container / git worktree / process spawn
- product UI
- production auth / identity

## 3. Candidate Comparison

| Candidate | Uses existing boundaries | Risk | Product overclaim risk | In-process test fit | Judgment |
| --- | --- | --- | --- | --- | --- |
| approval-gated tool runner extension | high: approval / workspace / action / artifact | medium: keeps expanding same spike | medium: can look like real tool runner | high | do not keep expanding by default |
| artifact review flow | high: artifact / `ResourceRef` / retrieval policy / HTTP facade / checkpoint | low | low-medium: content policy must stay explicit | high | recommended |
| file summarizer without real filesystem mutation | medium: artifact / workspace / retrieval | medium-high: users expect real files and LLM summary | high | medium | defer |
| research assistant mini flow without real web/network | medium: artifact / memory / external observation | high: implies real web, ranking, model loop | high | low-medium | defer |

## 4. Recommendation

Choose `artifact review flow` for the next app spike.

Reasons:

- It exercises a different kernel surface than `approval-tool-runner`.
- It validates Track C without opening HTTP full-content route.
- It can use existing artifact summary / `ResourceRef` / provenance.
- It can demonstrate controlled full-content retrieval only through explicit grants + caller context + purpose.
- It can include optional approval checks later without making approval the whole demo again.
- It is fully in-process and deterministic.
- It does not need real filesystem mutation or real LLM.
- It avoids the product overclaim risk of “file summarizer” and “research assistant”.

## 5. Proposed Red-Test Scope

Original suggested batch name:

- `First App Spike Red Tests`

Suggested test file:

- `tests/isotope_kernel/test_app_spike_artifact_review_flow.py`

Red-test goals:

- new scenario shape is defined, likely `python -m isotope_kernel.demo --scenario artifact-review`
- JSON scenario includes `scenario: "artifact-review"`
- default artifact summary path is readable
- default response does not include full artifact content
- controlled retrieval succeeds only with structured `ResourceRef`, grants, caller context, and purpose
- HTTP full-content route remains `not_enabled`
- no real HTTP server / network listener
- no real LLM
- no real filesystem mutation
- replay and checkpoint remain valid
- default v0.1 / v0.2 / approval-tool-runner demos remain compatible

## 6. Non-Goals

Original red-tests-only non-goals before implementation authorization:

- app scenario implementation
- real file reader
- real summarizer
- real LLM
- ranking / semantic retrieval
- HTTP full-content route
- real HTTP server
- product UI
- new dependency

## 7. User Decision

The candidate choice does not require further product judgment for red tests because:

- the user already gave `artifact review flow` as the default recommendation
- repo evidence supports it as the lowest-risk next app-shaped pressure test
- the next step is only red tests, not implementation

Green implementation was explicitly allowed by the follow-up package and is now complete.

## 8. Implementation Outcome

Implemented scenario:

```bash
python -m isotope_kernel.demo --scenario artifact-review
python -m isotope_kernel.demo --scenario artifact-review --json
```

The first slice proves:

- existing artifact summary / `ResourceRef` can seed an app-shaped review flow
- reviewer action still uses canonical action chain
- review result handoff uses artifact / `ResourceRef` / canonical events
- controlled full-content retrieval is only used inside retrieval layer with grants + caller context + purpose
- demo / helper output does not expose full artifact content
- HTTP full-content route remains `not_enabled`
- replay and checkpoint restore review artifact summaries

Friction review is complete: `docs/artifact-review-flow-friction-review.md`.

Source artifact setup helper is complete: `docs/source-artifact-setup-helper-boundary-v0.2.md`.

Source artifact helper closure review is complete: `docs/source-artifact-helper-closure-review.md`.

Remaining recommended work: run a docs-only artifact review flow second friction review before expanding the scenario.
