# Kernel Gap Review Refresh v0.2

状态：`current refresh; tool protocol first slice closed for now`

## 1. Purpose

本文在 `artifact-review` 和 `external-snapshot-review` 两个 app spike 之后刷新 kernel gap 列表。目标不是宣布 kernel complete，而是把当前已经足够 first-slice 的边界、仍然属于 kernel-level 的缺口、明确不该现在打开的 product / integration gap，以及下一步推荐顺序写清。

输入依据：

- `kernel-gap-review-v0.2.md`
- `app-spike-coverage-review.md`
- `../features/usability-pressure-test-plan-v0.2.md`
- `../current/status.md`
- 当前 `src/isotope_kernel/` 实现
- 当前 demo scenarios: v0.1, v0.2, `approval-tool-runner`, `artifact-review`, `external-snapshot-review`

当前 baseline：`1003 passed`。

## 2. Gaps Now First-Slice Enough

这些原 kernel gaps 已经不是 purely paper design。它们仍不是 production-complete，但足够作为下一批 review / pressure test 的 hard boundary。

| Area | Current first-slice status | Evidence | Still not included |
| --- | --- | --- | --- |
| Agent / worker lifecycle | `RunState.agents` / `RunState.workers` read model、supervisor projection、delegation proposal / policy gate、worker lifecycle events、worker grants 和 checkpoint support 已有 | `projector.py` 投影 agents/workers；tests 覆盖 delegation policy、replay、checkpoint；../architecture/agent-worker-lifecycle-boundary-v0.2.md | real concurrency、process spawn、remote worker、model planning loop |
| Workspace substrate | `RunState.workspaces`、canonical `workspace.bound`、grants-bound `shared_ro` binding、server `bind_workspace(...)` helper、workspace lease / release / artifact-capture first slice、replay / checkpoint 已有 | workspace tests、approval-tool-runner spike、../architecture/workspace-substrate-boundary-v0.2.md、../architecture/workspace-resource-lifecycle-boundary-v0.2.md | path-safety engine、write mode、cleanup scheduler、container / git worktree |
| Retry / cancel / supersede | action lifecycle read models、canonical slice events、basis linkage validation、replacement identity validation、checkpoint support 已有；runtime integration first slice 已完成 closure review | `RunState.action_retries` / `action_cancellations` / `action_supersessions`；`InProcessServer.request_retry(...)` / `request_cancel(...)` / `request_supersede(...)`；../architecture/retry-cancel-supersede-boundary-v0.2.md；../architecture/retry-cancel-supersede-runtime-integration-boundary-v0.2.md；retry-cancel-supersede-runtime-closure-review.md | automatic retry engine、scheduler、process kill、tool-level cancellation、runtime orchestration |
| HTTP facade | in-process `HttpApiApp` route inventory、request validation、stable error shape、deferred routes、approval/read helper routes 已有 | Track A tests and v0.2 demo scenario | real listening server、framework choice、auth、SSE / streaming |
| Approval pause / resume | `approval.requested` / `approval.resolved`、approved resume、denied no-execute、duplicate conflict、read helpers、HTTP in-process resolve/read routes 已有 | Track E tests、approval-tool-runner spike | product UI、identity/auth、notification、timeout scheduler、full approval state machine |
| External ingestion boundary | `ingestion.py` fail-closed boundary、`ImportedSnapshot` slice model、`snapshot.imported` -> `RunState.external_observations`、conflict diagnostics、native state priority、checkpoint support 已有 | Track F tests、external-snapshot-review spike | provider adapter、webhook、external ingestion product API、reconciliation engine |
| Artifact content read policy | summary default、structured `ResourceRef`、explicit grants + caller context + purpose for content retrieval、HTTP full-content route disabled 已有 | Track C tests、artifact-review spike | hosted content API、semantic retrieval / ranking、broad retrieval policy engine |
| Policy profile / action registry versioning | `registry_id` / `registry_version` and `policy_profile_id` / `policy_version` basis metadata now flows through proposal / decision / events / `RunState.actions`; first slice closed for now | `tests/isotope_kernel/test_action_registry_version_basis.py`、`tests/isotope_kernel/test_policy_profile_version_basis.py`、`../architecture/policy-registry-version-basis-closure-review.md` | plugin marketplace、remote registry loading、policy DSL、migration framework |
| Event schema registry / compatibility | static `EventSchemaRegistry` lists known canonical event types, separates envelope/schema versions, and makes unknown event types / unsupported payload schema versions fail closed; legacy/current known events missing `event_schema_version` use explicit compatibility mapping; first slice closed for now | `tests/isotope_kernel/test_event_schema_registry_boundary.py`、`tests/isotope_kernel/test_event_schema_version_compatibility.py`、`../architecture/event-schema-registry-closure-review.md` | JSON Schema / protobuf / Avro、remote/plugin registry、schema migration framework、multi-version projector matrix |

## 3. Still-Open Kernel-Level Gaps

这些不是 product polish；如果后续继续做 kernel work，应在真实集成前补 boundary / tests。

| Gap | Why it is kernel-level | Risk if deferred | Suggested next action |
| --- | --- | --- | --- |
| Workspace resource lifecycle | first slice 已 closed for now，覆盖 `workspace.lease_created`、`workspace.released`、`workspace.artifact_captured` read model；仍缺 path-safety intent、write/read mode contract 和 cleanup / release failure diagnostics | worker handoff、tool protocol 和 retry/cancel runtime 后续仍会依赖 workspace lifecycle；如果现在打开真实 substrate 会过早产品化 | closed for now; defer real substrate |
| Worker handoff app composition | worker lifecycle read model 已有，但 app-level composition 还没证明 worker result handoff、workspace grants、delegation policy 和 artifact refs 在一个 scenario 中自然协作 | 继续做 worker demo 可能暴露 workspace / policy / RCS contract gaps；若现在直接做 product multi-agent，会过早膨胀 | after workspace lifecycle boundary, consider `Worker Handoff App Spike` |
| Retry / cancel / supersede runtime integration | helper first slice 已完成并 closed for now：request helpers append canonical events, preserve old action state, reject terminal cancel, and expose replacement identity；仍缺 scheduler / process integration by design | 长任务、worker handoff、approval denial 后的 recovery 都会继续依赖这个 contract；若直接做 scheduler/process kill 会破坏边界 | closed for now; no scheduler/process kill |
| Policy profile / action registry versioning | first slice 已完成并 closed for now；后续仍缺 reason-code taxonomy 和 broader compatibility / migration story | helper / demo 越多，requested capabilities、grants、workspace modes 和 action schemas 越容易漂移 | closed for now; defer plugin / DSL / migration |
| Session / run lifecycle | session/run 能创建和 replay，但 multi-run continuity、run pause/finalization/cancel/supersede、session history visibility 仍未成 contract | app spikes 目前多是 single-run；一旦做 app-like workflow，run boundaries 会变成 hidden glue | docs-only lifecycle review; do not mix with memory promotion |
| Error taxonomy | server/helper/HTTP/projector 都有 controlled errors，但 error code taxonomy 还不是统一 kernel contract | facade/helper 增长后，客户端难以稳定处理 unknown / malformed / conflict / not_enabled / policy denied | small docs/red-test slice after next boundary |
| Event schema registry / migration | Event Schema Registry / Compatibility first slice 已完成并 closed for now，见 `../architecture/event-schema-registry-compatibility-boundary-v0.2.md` 和 `../architecture/event-schema-registry-closure-review.md`；仍缺 schema migration policy 和 multi-version projector matrix | read model fields 越多，future breaking change 成本越高 | closed for now; no migration framework |
| Tool protocol | first slice 已 closed for now：最小 `ToolInvocation` / `ToolResult` / `ToolError` models、artifact event provenance 和 structured `action.failed` error 已固定 | future tool examples still risk coupling executor, artifact store, workspace and policy if they bypass the boundary; executor still does not pass `ToolInvocation` as a runtime object to handlers | application-layer friction intake; no plugin / remote / sandbox / streaming / public SDK |

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
| C. Retry/Cancel/Supersede Runtime Integration Boundary | first slice closed for now | Needed for longer-running workflows, and policy/profile basis is now closed enough to make action lifecycle runtime semantics inspectable. |
| D. Policy/Profile Versioning Boundary | first slice closed for now | It now prevents missing basis metadata in proposals / decisions / events; future work is taxonomy / compatibility, not plugin or DSL. |
| E. Pause implementation and prepare external review package | safe alternative | If the goal is external communication rather than kernel progress, current docs + demos are enough for a review package. It should not block B if continuing kernel work. |

Recommended order:

1. `Application-Layer Friction Intake` / external review feedback intake
2. `Worker Handoff App Spike Selection` only if concrete app-layer friction asks for more kernel pressure
3. `Tool Invocation Runtime Wiring Boundary` only if application-layer friction proves executor should construct `ToolInvocation` as a runtime object

## 6. Next Batch Shape

Completed follow-up:

- Batch name: `Workspace Resource Lifecycle Closure Review`
- Type: docs-only closure review
- Result: `first slice complete / closed for now`
- Closure doc: `../architecture/workspace-resource-lifecycle-closure-review.md`

Completed follow-up:

- Batch name: `Policy Profile / Action Registry Versioning Boundary`
- Type: docs-only boundary
- Result: boundary defined in `../architecture/policy-profile-action-registry-versioning-boundary-v0.2.md`

Completed follow-up:

- Batch name: `Policy Registry Version Basis Green Slice`
- Type: red -> green implementation
- Result: `ActionTypeRegistry` / `ActionProposal` / `PolicyEngine` / `PolicyDecision` / canonical action events / `RunState.actions` now carry registry and policy basis metadata.

Completed follow-up:

- Batch name: `Policy Registry Version Basis Closure Review`
- Type: docs-only closure review
- Result: `first slice complete / closed for now`
- Closure doc: `../architecture/policy-registry-version-basis-closure-review.md`

Completed follow-up:

- Batch name: `Retry / Cancel / Supersede Runtime Integration Boundary`
- Type: docs-only boundary
- Result: boundary defined in `../architecture/retry-cancel-supersede-runtime-integration-boundary-v0.2.md`

Completed follow-up:

- Batch name: `Retry / Cancel / Supersede Runtime Integration Closure Review`
- Type: docs-only closure review
- Result: `first slice complete / closed for now`
- Closure doc: `retry-cancel-supersede-runtime-closure-review.md`

Completed follow-up:

- Batch name: `Event Schema Registry / Compatibility Closure Review`
- Type: docs-only closure review
- Result: `first slice complete / closed for now`
- Closure doc: `../architecture/event-schema-registry-closure-review.md`

Completed follow-up:

- Batch name: `Tool Protocol Green Slice`
- Type: red -> green implementation
- Result: implemented `../architecture/tool-protocol-boundary-v0.2.md` first green slice
- Implementation stance: minimal in-process `ToolInvocation` / `ToolResult` / `ToolError` models only; no plugin marketplace, remote tool, sandboxed process, streaming output, public SDK, or new dependency.
- First red tests recommendation: `tests/isotope_kernel/test_tool_protocol_boundary.py` and `tests/isotope_kernel/test_tool_result_event_boundary.py`

Completed follow-up:

- Batch name: `Tool Protocol Closure Review`
- Type: docs-only closure review
- Result: first slice complete / closed for now
- Closure doc: `../architecture/tool-protocol-closure-review.md`
- Scope note: model / event-shape first slice only; executor does not yet wire `ToolInvocation` as the handler runtime object.

Recommended next batch:

- Batch name: `Application-Layer Friction Intake`
- Type: review / triage only
- Goals:
  - wait for application-layer prototype or external review feedback
  - convert concrete friction into docs clarification, helper/API gap, replay/checkpoint gap, or app-layer glue
  - avoid implementing further tool runtime wiring unless friction is concrete or the user explicitly opens that batch
  - keep tag / release, real server, real LLM, provider adapters, migration framework, plugin marketplace, sandboxed tools, and product APIs out of scope unless explicitly requested

Follow-up: `../architecture/workspace-resource-lifecycle-boundary-v0.2.md` / `../architecture/workspace-resource-lifecycle-closure-review.md` and `../architecture/policy-registry-version-basis-closure-review.md` now record the closed first slices. The next implementation-facing step should not be real filesystem substrate or plugin/policy infrastructure unless a new boundary explicitly asks for it.

Stop conditions:

- any need for real filesystem mutation, container, git worktree, process spawn, remote executor, or cleanup scheduler
- any need to modify executor grants semantics
- any need to make workspace identity equal agent identity
- any pressure to let projector read workspace files
- any product decision about hosted workspace UX

## 7. Decision

Kernel is not complete, but the current boundary package is no longer blocked by artifact/external-observation proof gaps. Workspace Resource Lifecycle, Policy Profile / Action Registry Versioning, Retry / Cancel / Supersede Runtime Integration, Event Schema Registry / Compatibility, and Tool Protocol now have closed first-slice boundaries. Tool Protocol first slice has minimal in-process models, complete artifact event provenance, and structured `action.failed` errors; it deliberately does not wire `ToolInvocation` into executor handlers yet. The next useful default step is application-layer friction intake / external review feedback intake, not plugin marketplace, policy DSL, migration framework, real workspace substrate, sandboxed tools, scheduler/process kill, real HTTP server, or real LLM.
