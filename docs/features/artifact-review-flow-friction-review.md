# Artifact Review Flow Friction Review

状态：`complete; artifact-review first app spike closed for now`

## 1. Purpose

本文复盘 `artifact-review` usability pressure test（可用性压力测试）暴露的 developer ergonomics（开发者易用性）问题。

目标不是继续实现新 helper，而是把 friction 分层：哪些是 kernel design issue（内核设计问题）、哪些是 facade / helper gap（门面 / 辅助接口缺口）、哪些只是 demo glue（演示胶水代码），以及下一步是否需要用户 / 产品判断。

## 2. Reviewed Evidence

审查对象：

- `src/isotope/demo.py`
- `tests/isotope/test_artifact_review_flow_spike.py`
- `tests/isotope/test_artifact_review_flow_read_model.py`
- `../current/status.md`
- `../architecture/v0.2-roadmap.md`
- `usability-pressure-test-plan-v0.2.md`
- `../current/agent-task-queue.md`

当前 `artifact-review` scenario 已证明：

- flow 是 deterministic / in-process。
- 不使用 real LLM。
- 不使用 real HTTP server / network listener。
- 不使用 real filesystem mutation。
- 从 artifact summary / structured `ResourceRef` 开始。
- reviewer action 走 canonical action chain。
- review result 通过 artifact / `ResourceRef` / canonical events handoff。
- controlled full-content retrieval 只在 retrieval layer 使用 grants + caller context + purpose。
- HTTP full-content route 仍 `not_enabled`。
- replay / checkpoint 可恢复 review summary。

## 3. Observed Friction

| Friction | Classification | Why it matters | Suggested action |
| --- | --- | --- | --- |
| Source artifact setup used to hand-write `action.proposed`, `action.decided`, `action.started`, `artifact.created`, and `action.completed` via `server._append(...)`. | facade / helper gap | Demo used private server API and manual event sequencing to prepare a normal source artifact. That was awkward for app spikes and easy to copy incorrectly. | Implemented by `InProcessServer.create_source_artifact(...)`. |
| Source artifact setup used to directly combine `artifact_store.create_artifact(...)` with manual canonical event append. | facade / helper gap | Artifact persistence and provenance event ownership were correct, but caller knew too much event plumbing. | Helper now owns the minimal canonical event sequence and returns summary / ref / provenance. |
| Source artifact basis event lookup scanned raw events in demo glue. | read helper gap | Review provenance needed the source `artifact.created` basis event, but demo should not need to walk raw event logs for that. | Implemented by `InProcessServer.get_artifact_record(...)`. |
| Controlled full-content retrieval requires explicit `get_artifact_content(ref, grants, caller_context, purpose)`. | acceptable v0 shape / future helper ergonomics | The explicit call is intentionally strict and protects Track C boundaries. It is verbose but not wrong. | Keep as-is for now; optionally wrap later only if repeated app spikes need it. |
| Review action handoff uses `submit_action(...)` and returns artifact ref / ids. | acceptable current helper | This is the desired pattern after submit-action helper work. | Keep as-is. |
| Review summary is deterministic and fixed text. | demo-only | It proves flow shape without real LLM. | Keep as-is until a later spike explicitly needs richer deterministic review logic. |

## 4. Kernel-Level Findings

No kernel correctness bug was found.

The current kernel boundaries are working as intended:

- projector consumes canonical events, not artifact full content.
- review result is represented through artifact / `ResourceRef` / event handoff.
- full content is not exposed through HTTP.
- event replay and checkpoint-assisted rebuild recover the review read model.

The main awkwardness is not the event-sourced contract itself. It is that preparing a source artifact for a demo currently requires a caller to manually stitch together private event plumbing.

## 5. Helper / Facade-Level Findings

The clearest helper gap was source artifact setup.

A minimal helper should:

- create a deterministic source artifact through the existing artifact store.
- append canonical action / artifact lifecycle events in the existing order.
- return artifact summary, structured `ResourceRef`, provenance, and useful ids.
- avoid returning full content.
- avoid reading filesystem files.
- avoid real LLM, real HTTP server, provider adapter, semantic retrieval, ranking, memory query, container, git worktree, or process spawn.
- preserve event store append-only semantics and executor grants semantics.

The implemented helper reduces demo glue without changing the kernel truth model.

## 6. Demo-Only Findings

The deterministic review body and hard-coded review outcome are acceptable for this spike.

They intentionally avoid implying:

- real LLM review quality.
- semantic retrieval / ranking.
- product review UI.
- real filesystem integration.

## 7. Is Artifact Review A Useful First App Spike?

Yes.

It complements `approval-tool-runner` by pressure testing a different path:

- artifact summary / `ResourceRef`
- controlled content policy
- review artifact handoff
- replay / checkpoint
- HTTP full-content route staying disabled

It also exposed a concrete API friction: source artifact setup was too manual for repeated app spikes.

## 8. Next Step Recommendation

Recommendation: **A. source artifact setup helper**.

Why not B. review artifact helper:

- `submit_action(...)` already makes review artifact handoff reasonably natural.
- Adding a review-specific helper would risk prematurely productizing one app flow.

Why not C. artifact review facade:

- A full facade would hide useful kernel boundaries too early.
- The only clear repeated pain is source artifact preparation.

Why not D. leave as-is:

- Continuing app spikes with private `_append(...)` setup glue would make demos brittle and encourage callers to bypass intended server-level helpers.

No product / user decision was needed for the helper slice because it stayed limited to source artifact setup and did not define a product-level artifact review API.

## 9. Source Helper Outcome

The first helper slice is complete and closure-reviewed.

Implemented helper:

- `InProcessServer.create_source_artifact(...)`

Closure review:

- `source-artifact-helper-closure-review.md`

Current behavior:

- validates `run_id`, `summary`, `content`, and `artifact_type` before side effects。
- uses existing compiler / policy / executor path。
- appends canonical action + artifact lifecycle events。
- returns status, proposal id, decision id, execution id, artifact ref, artifact summary, artifact type, provenance, and run state。
- does not return artifact full content。
- does not append `run.completed` during source setup。
- is replayable and checkpoint-assisted rebuildable。
- leaves HTTP full-content route `not_enabled`。

`artifact-review` demo now uses this helper instead of private `server._append(...)` source setup glue.

This remains a deterministic in-process setup helper, not a product artifact upload API.

## 10. Artifact Provenance Helper Outcome

`InProcessServer.get_artifact_record(...)` now returns summary / structured ref / provenance / source `artifact.created` basis event metadata without returning full content or appending events.

`artifact-review` now uses that helper to construct review provenance. Demo/client code no longer scans raw events for the source artifact created event.

## 11. Flow Closure

Closure review: `artifact-review-flow-closure-review.md`

Current closure judgment:

- `artifact-review` no longer uses private `server._append(...)` source setup glue。
- `artifact-review` no longer scans raw events to find the source artifact basis event。
- source artifact setup uses `InProcessServer.create_source_artifact(...)`。
- review provenance uses `InProcessServer.get_artifact_record(...)`。
- the flow still covers action chain, policy / grants, artifact summary / `ResourceRef` / provenance, controlled retrieval policy, replay, checkpoint, and disabled HTTP full-content route。
- the first app spike is complete / closed for now。

## 12. Remaining Friction

Source artifact setup is closed.

Remaining `artifact-review` friction:

- controlled retrieval remains explicit by design。
- product-level artifact review facade remains intentionally deferred。

Next suggested batch: `Second App Spike Selection`, docs-only by default.

Stop if the next slice requires product review semantics, real filesystem mutation, real LLM, real HTTP server, provider adapter, memory query engine, event store semantic changes, executor grants semantic changes, new dependency, or `/home/lumber/Github/x-agent` changes.
