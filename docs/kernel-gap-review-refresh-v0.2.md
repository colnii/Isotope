# Kernel Gap Review Refresh v0.2

状态：`current refresh; policy/profile versioning first slice complete`

## 1. Purpose

本文在 `artifact-review` 和 `external-snapshot-review` 两个 app spike 之后刷新 kernel gap 列表。目标不是宣布 kernel complete，而是把当前已经足够 first-slice 的边界、仍然属于 kernel-level 的缺口、明确不该现在打开的 product / integration gap，以及下一步推荐顺序写清。

输入依据：

- `docs/kernel-gap-review-v0.2.md`
- `docs/app-spike-coverage-review.md`
- `docs/usability-pressure-test-plan-v0.2.md`
- `docs/current-status.md`
- 当前 `src/isotope_kernel/` 实现
- 当前 demo scenarios: v0.1, v0.2, `approval-tool-runner`, `artifact-review`, `external-snapshot-review`

当前 baseline：`959 passed`。

## 2. Gaps Now First-Slice Enough

这些原 kernel gaps 已经不是 purely paper design。它们仍不是 production-complete，但足够作为下一批 review / pressure test 的 hard boundary。

| Area | Current first-slice status | Evidence | Still not included |
| --- | --- | --- | --- |
| Agent / worker lifecycle | `RunState.agents` / `RunState.workers` read model、supervisor projection、delegation proposal / policy gate、worker lifecycle events、worker grants 和 checkpoint support 已有 | `projector.py` 投影 agents/workers；tests 覆盖 delegation policy、replay、checkpoint；docs/agent-worker-lifecycle-boundary-v0.2.md | real concurrency、process spawn、remote worker、model planning loop |
| Workspace substrate | `RunState.workspaces`、canonical `workspace.bound`、grants-bound `shared_ro` binding、server `bind_workspace(...)` helper、workspace lease / release / artifact-capture first slice、replay / checkpoint 已有 | workspace tests、approval-tool-runner spike、docs/workspace-substrate-boundary-v0.2.md、docs/workspace-resource-lifecycle-boundary-v0.2.md | path-safety engine、write mode、cleanup scheduler、container / git worktree |
| Retry / cancel / supersede | action lifecycle read models、canonical slice events、basis linkage validation、replacement identity validation、checkpoint support 已有 | `RunState.action_retries` / `action_cancellations` / `action_supersessions`；docs/retry-cancel-supersede-boundary-v0.2.md | automatic retry engine、scheduler、process kill、tool-level cancellation、runtime orchestration |
| HTTP facade | in-process `HttpApiApp` route inventory、request validation、stable error shape、deferred routes、approval/read helper routes 已有 | Track A tests and v0.2 demo scenario | real listening server、framework choice、auth、SSE / streaming |
| Approval pause / resume | `approval.requested` / `approval.resolved`、approved resume、denied no-execute、duplicate conflict、read helpers、HTTP in-process resolve/read routes 已有 | Track E tests、approval-tool-runner spike | product UI、identity/auth、notification、timeout scheduler、full approval state machine |
| External ingestion boundary | `ingestion.py` fail-closed boundary、`ImportedSnapshot` slice model、`snapshot.imported` -> `RunState.external_observations`、conflict diagnostics、native state priority、checkpoint support 已有 | Track F tests、external-snapshot-review spike | provider adapter、webhook、external ingestion product API、reconciliation engine |
| Artifact content read policy | summary default、structured `ResourceRef`、explicit grants + caller context + purpose for content retrieval、HTTP full-content route disabled 已有 | Track C tests、artifact-review spike | hosted content API、semantic retrieval / ranking、broad retrieval policy engine |
| Policy profile / action registry versioning | `registry_id` / `registry_version` and `policy_profile_id` / `policy_version` basis metadata now flows through proposal / decision / events / `RunState.actions` | `tests/isotope_kernel/test_action_registry_version_basis.py`、`tests/isotope_kernel/test_policy_profile_version_basis.py` | plugin marketplace、remote registry loading、policy DSL、migration framework |

## 3. Still-Open Kernel-Level Gaps

这些不是 product polish；如果后续继续做 kernel work，应在真实集成前补 boundary / tests。

| Gap | Why it is kernel-level | Risk if deferred | Suggested next action |
| --- | --- | --- | --- |
| Workspace resource lifecycle | first slice 已 closed for now，覆盖 `workspace.lease_created`、`workspace.released`、`workspace.artifact_captured` read model；仍缺 path-safety intent、write/read mode contract 和 cleanup / release failure diagnostics | worker handoff、tool protocol 和 retry/cancel runtime 后续仍会依赖 workspace lifecycle；如果现在打开真实 substrate 会过早产品化 | closed for now; defer real substrate |
| Worker handoff app composition | worker lifecycle read model 已有，但 app-level composition 还没证明 worker result handoff、workspace grants、delegation policy 和 artifact refs 在一个 scenario 中自然协作 | 继续做 worker demo 可能暴露 workspace / policy / RCS contract gaps；若现在直接做 product multi-agent，会过早膨胀 | after workspace lifecycle boundary, consider `Worker Handoff App Spike` |
| Retry / cancel / supersede runtime integration | projector-level lifecycle 已稳，但 runtime 何时接受 retry/cancel/supersede request、如何表达 accepted/rejected/effective state 仍薄 | 长任务、worker handoff、approval denial 后的 recovery 都会需要这个 contract；若直接做 scheduler/process kill 会破坏边界 | boundary review after workspace lifecycle; no scheduler/process kill |
| Policy profile / action registry versioning | first green slice 已完成；后续仍缺 reason-code taxonomy、event schema registry 和 compatibility / migration story | helper / demo 越多，requested capabilities、grants、workspace modes 和 action schemas 越容易漂移 | closure review; defer plugin / DSL / migration |
| Session / run lifecycle | session/run 能创建和 replay，但 multi-run continuity、run pause/finalization/cancel/supersede、session history visibility 仍未成 contract | app spikes 目前多是 single-run；一旦做 app-like workflow，run boundaries 会变成 hidden glue | docs-only lifecycle review; do not mix with memory promotion |
| Error taxonomy | server/helper/HTTP/projector 都有 controlled errors，但 error code taxonomy 还不是统一 kernel contract | facade/helper 增长后，客户端难以稳定处理 unknown / malformed / conflict / not_enabled / policy denied | small docs/red-test slice after next boundary |
| Event schema registry / migration | event envelope/versioning docs 已有，但 actual event payload schema registry、compatibility policy、projector version migration 仍薄 | read model fields 越多，future breaking change 成本越高 | docs-only refresh before any incompatible schema change |
| Tool protocol | action chain 可执行 deterministic tools，但 tool result/error/resource contract、streaming absence、artifact capture ownership 仍是 sketch | future tool examples may accidentally couple executor, artifact store, workspace and policy | defer until workspace lifecycle is clearer |

## 4. Not-Now Product / Integration Gaps

这些仍重要，但现在做会把 kernel review 推向 product implementation 或 real integration，风险高于收益。

- real HTTP server / network listener / ASGI or WSGI framework
- real LLM loop / model-driven planner / hosted tool calling
- provider adapters, webhooks, external callbacks, OpenAI / Responses / GitHub integration
- memory storage / query engine / promotion / embeddings / ranking
- filesystem sandbox, container, git worktree, process spawn, remote executor
- approval UI, auth / identity, notification, timeout scheduler
- semantic retrieval / ranking / budgeted slicing
- domain pack system or plugin marketplace
- tag / GitHub Release work

## 5. Recommendation Options

| Option | Judgment | Reason |
| --- | --- | --- |
| A. Worker Handoff App Spike | useful but not first | It would pressure a valuable untested surface, but it depends on workspace lifecycle and policy/profile clarity. Doing it now risks making a demo-specific worker composition API. |
| B. Workspace Resource Lifecycle Boundary | complete / closed for now | It clarified lease, release, artifact-capture linkage and checkpoint/replay without opening real filesystem substrate. |
| C. Retry/Cancel/Supersede Runtime Integration Boundary | third | Needed for longer-running workflows, but runtime integration should follow policy/profile versioning because cancel/supersede effects depend on action schema and grants semantics. |
| D. Policy/Profile Versioning Boundary | first slice complete | It now prevents missing basis metadata in proposals / decisions / events; future work is taxonomy / compatibility, not plugin or DSL. |
| E. Pause implementation and prepare external review package | safe alternative | If the goal is external communication rather than kernel progress, current docs + demos are enough for a review package. It should not block B if continuing kernel work. |

Recommended order:

1. `Policy Registry Version Basis Closure Review`
2. `Retry/Cancel/Supersede Runtime Integration Boundary`
3. `Worker Handoff App Spike`
4. optional external review package, if the near-term goal is reviewer handoff instead of more kernel design

## 6. Next Batch Shape

Completed follow-up:

- Batch name: `Workspace Resource Lifecycle Closure Review`
- Type: docs-only closure review
- Result: `first slice complete / closed for now`
- Closure doc: `docs/workspace-resource-lifecycle-closure-review.md`

Completed follow-up:

- Batch name: `Policy Profile / Action Registry Versioning Boundary`
- Type: docs-only boundary
- Result: boundary defined in `docs/policy-profile-action-registry-versioning-boundary-v0.2.md`

Completed follow-up:

- Batch name: `Policy Registry Version Basis Green Slice`
- Type: red -> green implementation
- Result: `ActionTypeRegistry` / `ActionProposal` / `PolicyEngine` / `PolicyDecision` / canonical action events / `RunState.actions` now carry registry and policy basis metadata.

Recommended next batch:

- Batch name: `Policy Registry Version Basis Closure Review`
- Type: docs-only closure review
- Goals:
  - confirm basis metadata first slice can close for now
  - confirm no plugin loading, policy DSL, marketplace, product policy UI, or migration framework was introduced

Follow-up: `docs/workspace-resource-lifecycle-boundary-v0.2.md` and `docs/workspace-resource-lifecycle-closure-review.md` now record the closed first slice. The next implementation-facing step should not be real filesystem substrate unless a new boundary explicitly asks for it.

Stop conditions:

- any need for real filesystem mutation, container, git worktree, process spawn, remote executor, or cleanup scheduler
- any need to modify executor grants semantics
- any need to make workspace identity equal agent identity
- any pressure to let projector read workspace files
- any product decision about hosted workspace UX

## 7. Decision

Kernel is not complete, but the current boundary package is no longer blocked by artifact/external-observation proof gaps. Workspace Resource Lifecycle now has a closed first slice, and Policy Profile / Action Registry Versioning now has a first green slice. The next useful step is closure review, not plugin marketplace, policy DSL, migration framework, or real workspace substrate.
