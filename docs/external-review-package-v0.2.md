# External Review Package v0.2

状态：`current`

## 1. One-Paragraph Summary

Isotope 是一个 event-sourced agent kernel prototype（事件溯源的 agent 内核原型），目标是验证 agent runtime 的硬边界：action chain、policy grants、append-only event log、artifact provenance、projector replay、checkpoint-assisted rebuild、approval pause/resume、workspace read model、external observation boundary 和 schema/version basis。它现在能跑多个 deterministic / in-process developer demos，但它还不是完整产品：没有 real LLM loop、真实 HTTP server、provider adapter、UI、auth、多用户、真实 workspace filesystem 或 scheduler。

## 2. What Can Be Run

从仓库根目录运行：

```bash
cd /home/lumber/Github/isotope

PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --json

PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario v0.2
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario v0.2 --trace
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario v0.2 --json

PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario approval-tool-runner
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario approval-tool-runner --trace
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario approval-tool-runner --json

PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario artifact-review
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario artifact-review --trace
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario artifact-review --json

PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario external-snapshot-review
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario external-snapshot-review --trace
PYTHONPATH=src .venv/bin/python -m isotope_kernel.demo --scenario external-snapshot-review --json
```

`--trace` 是 human-readable trace，用来给 reviewer 看 runtime steps；`--json` 是 machine-readable summary。两者都不应输出 artifact full content 或 raw external content。

## 3. What The Demos Prove

- The default demo proves a minimal deterministic kernel loop: session/run creation, action proposal, policy decision, execution, artifact summary, event replay, checkpoint-assisted rebuild, and memory `boundary_only` status.
- `--scenario v0.2` proves the v0.2 developer demo surface: in-process HTTP facade shape, approval pause/resume, controlled artifact content policy, checkpoint, and no real HTTP server.
- `--scenario approval-tool-runner` proves a small approval-gated workflow: `submit_action(...)`, pending approval lookup/read helper, workspace binding helper, artifact / `ResourceRef` handoff, replay, and checkpoint.
- `--scenario artifact-review` proves the first app spike: source artifact setup helper, artifact summary / structured `ResourceRef`, controlled full-content retrieval policy, reviewer action chain, review artifact provenance, replay, and checkpoint.
- `--scenario external-snapshot-review` proves the second app spike: deterministic `ImportedSnapshot`, canonical `snapshot.imported`, `RunState.external_observations`, conflict diagnostics, native state priority, replay, and checkpoint.
- The kernel now has first-slice coverage for append-only event log, projector read models, checkpoint-assisted rebuild, approval pause/resume, workspace lifecycle read model, retry/cancel/supersede logical runtime helpers, policy/profile basis metadata, action registry version basis, and event schema compatibility fail-closed behavior.

## 4. What Is Deliberately Not Implemented

- Real listening HTTP server or hosted API.
- Real LLM loop, provider adapter, webhook, or external network listener.
- Memory storage / query engine / promotion policy.
- Real filesystem workspace, container, git worktree, remote executor, file diff / rollback engine, or binary streaming.
- Product UI, auth, multi-user identity, notification, or approval dashboard.
- Scheduler, process kill, tool-level cancellation hooks, retry backoff engine, timeout engine, or real concurrency.
- Plugin marketplace, remote registry loading, policy DSL, schema migration framework, JSON Schema / protobuf / Avro dependency, or product policy UI.
- GitHub Release publishing. `v0.1-demo` and `v0.2-demo` are developer demo tags, not product releases.

## 5. Reviewer Reading Path

Recommended short path:

1. `README.md` for quick start and the shortest current-state summary.
2. `docs/current-status.md` for the authoritative current truth.
3. `docs/app-spike-coverage-review.md` for what the app spikes actually pressure-tested.
4. `docs/kernel-gap-review-refresh-v0.2.md` for what remains kernel-level vs product-level.
5. `docs/artifact-review-flow-closure-review.md` for the first app spike closure.
6. `docs/external-snapshot-review-closure-review.md` for the second app spike closure.
7. `docs/workspace-resource-lifecycle-closure-review.md` for workspace lifecycle read-model closure.
8. `docs/policy-registry-version-basis-closure-review.md` for registry/profile basis metadata closure.
9. `docs/event-schema-registry-closure-review.md` for event schema compatibility closure.

Optional deep dives:

- `docs/http-api-minimal-surface-v0.2.md`
- `docs/artifact-content-read-policy-v0.2.md`
- `docs/approval-pause-resume-boundary-v0.2.md`
- `docs/external-ingestion-boundary-v0.2.md`
- `docs/retry-cancel-supersede-runtime-closure-review.md`
- `docs/agent-worker-lifecycle-boundary-v0.2.md`
- `docs/workspace-substrate-boundary-v0.2.md`

## 6. Suggested Reviewer Questions

- Does the kernel boundary make sense as an event-sourced agent runtime prototype?
- Are the event-sourced contracts too strict, not strict enough, or strict in the wrong places?
- Which helpers feel like legitimate kernel/server facade helpers, and which still feel like app-layer glue?
- Are `PolicyDecision.grants`, registry/profile basis metadata, and event schema fail-closed behavior understandable?
- Which deferred area should be next: Tool Protocol Boundary, Worker Handoff App Spike, Session / Run Lifecycle, Error Taxonomy, or external review feedback cleanup?
- Is this understandable as a developer demo without overselling product readiness?

## 7. Current Recommendation

Use this package for external review before opening another runtime feature. The best immediate next step is to send the package to a reviewer and collect feedback. If development resumes without external feedback, prefer another bounded docs-first boundary such as Tool Protocol Boundary rather than jumping to real HTTP server, real LLM, provider adapter, memory query engine, filesystem sandbox, scheduler, plugin marketplace, or schema migration framework.
