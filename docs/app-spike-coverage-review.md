# App Spike Coverage Review

状态：`complete; Kernel Gap Review Refresh executed`

## 1. Purpose

本文横向盘点当前 app spikes（应用尖刺验证）已经覆盖的 kernel surfaces（内核面），识别仍缺少 app-level pressure test（应用级压力测试）的部分，并决定下一步是继续 app spike、回 kernel gap，还是暂停实现进入 review mode。

本轮是 docs-only review，不新增实现、不新增测试、不打开 tag / release。

## 2. Completed App Spikes

### `artifact-review`

状态：`first app spike complete / closed for now`

已证明：

- artifact summary / structured `ResourceRef` 不是纸面设计。
- controlled artifact content retrieval policy 可以在 app-shaped flow 中使用。
- reviewer action 仍走 action chain / policy / executor。
- review artifact handoff 使用 artifact / `ResourceRef` / provenance。
- replay 和 checkpoint-assisted rebuild 可恢复 review summary。
- HTTP full-content route remains `not_enabled`。
- source artifact setup helper 和 provenance helper 已移除主要 demo glue。

### `external-snapshot-review`

状态：`second app spike complete / closed for now`

已证明：

- `ImportedSnapshot` slice model 可以进入 deterministic in-process flow。
- canonical `snapshot.imported` event 可以投影到 `RunState.external_observations`。
- conflict diagnostics 可进入 read model。
- imported observation 不覆盖 native `RunState.status` / action status。
- replay 和 checkpoint-assisted rebuild 可恢复 external observations。
- HTTP `/external-ingestion` remains `not_enabled`。
- JSON / trace 不输出 raw external content 或 artifact full content。

## 3. What Is No Longer Just Paper

当前 app spikes 已把这些 kernel design 从文档验证推进到可运行路径：

- canonical event log + projector replay + checkpoint-assisted rebuild。
- action chain / policy / executor path。
- `PolicyDecision.grants` 在 controlled retrieval 和 approval/tool flow 中的约束。
- artifact summary / `ResourceRef` / provenance。
- controlled full-content retrieval boundary。
- external observation read model。
- conflict diagnostics and native state priority。
- in-process `HttpApiApp` facade 作为 contract facade，而不是 real HTTP server。
- deterministic demo trace / JSON outputs that avoid full-content leakage。

此外，`approval-tool-runner` 虽不是本轮 two-app-spike coverage 的 closure target，但它已经补充证明：

- approval pause / resume。
- approval lookup helper。
- workspace binding helper。
- submit action helper。
- artifact / `ResourceRef` handoff。
- replay / checkpoint for approval + workspace read models。

## 4. Still Missing App-Level Pressure

这些 kernel surfaces 已有 boundary / tests / read model，但还缺更真实的 app-shaped composition pressure：

| Surface | Current status | App-level gap | Risk if next app spike targets it now |
| --- | --- | --- | --- |
| worker / delegation | first slice read model and policy gate exist | no app spike forces worker handoff / delegated result path | may imply real concurrency or multi-agent product behavior too early |
| workspace beyond binding helper | `shared_ro` binding and helper exist | no app flow exercises lease lifecycle, path safety, write intent, cleanup, or artifact capture from workspace | may pull in filesystem mutation, container, git worktree, or rollback prematurely |
| retry / cancel / supersede | projector/read-model slices exist | no app flow exercises user-visible retry/cancel/supersede decisions | may require scheduler/process kill semantics if framed as real task control |
| memory boundary | boundary/read-model/checkpoint exist | no app flow uses memory as an app-visible review object | high risk of reopening memory query/storage/promotion prematurely |
| approval beyond tool runner | approval resolution and read helpers exist | no app flow covers approval policy variants, timeout, multi-user, UI, or scheduler | product approval system risk |
| HTTP facade ergonomics | in-process facade exists | app helpers mostly live on `InProcessServer`; HTTP routes still intentionally minimal | product API design could expand too early |

## 5. Blockers Versus Polish

No blocker-level friction currently prevents pausing implementation or doing a kernel gap refresh.

Real blockers before product-like pressure would be:

- unclear worker / delegation lifecycle if the next spike needs handoff semantics。
- unclear workspace lease / path-safety boundary if the next spike needs write-like behavior。
- unclear retry / cancel / supersede user intent boundary if the next spike needs task-control semantics。

Product polish / deferred integration, not blockers:

- real provider adapter / webhook。
- real HTTP server。
- real LLM。
- real filesystem mutation / upload / binary streaming。
- memory storage / query engine。
- approval UI / notification / scheduler。
- product artifact review facade。
- external ingestion product API。
- semantic retrieval / ranking。

## 6. Recommendation

Recommendation: **B. Kernel Gap Review Refresh**.

Reasoning:

- The first two app spikes already cover two different kernel areas: artifact / content policy and external observations。
- `approval-tool-runner` already covered approval + workspace binding + action submission ergonomics enough for the current phase。
- The biggest uncovered app-level surfaces are worker/delegation, workspace beyond binding, and retry/cancel/supersede composition。
- Those surfaces are kernel-design-sensitive; a third spike would likely force product-shaped choices unless the kernel gaps are refreshed first。

Option C, pause implementation and enter docs cleanup / external review mode, is also safe if the goal is to stabilize the current story for reviewers.

Option A, a third app spike, should wait until after Kernel Gap Review Refresh unless the user explicitly wants more usability pressure now. That refresh has now landed in `docs/kernel-gap-review-refresh-v0.2.md` and recommends `Workspace Resource Lifecycle Boundary` next.

## 7. If A Third App Spike Is Requested Later

Best candidate after a refresh: `worker handoff task`.

Why:

- It targets the largest remaining uncovered kernel surface: agent / worker lifecycle and delegated result handoff。
- It can be deterministic / in-process。
- It can remain no real concurrency / process spawn if explicitly scoped。
- It can exercise worker result handoff through artifact / `ResourceRef` / canonical event。

Stop conditions for that future spike:

- requires real concurrency / process spawn / remote worker。
- requires filesystem mutation / container / git worktree。
- requires real LLM planning loop。
- requires changing event store append-only semantics or executor grants semantics。
- requires product/user decision about multi-agent behavior。

Do not start this third spike from this review.

## 8. Follow-Up

Follow-up executed: `Kernel Gap Review Refresh`, docs-only.

Refresh outcome:

- `docs/kernel-gap-review-refresh-v0.2.md` now records first-slice enough surfaces and still-open kernel-level gaps。
- Recommended next batch is `Workspace Resource Lifecycle Boundary`。
- Worker handoff app spike should wait until workspace lifecycle and policy/profile boundaries are clearer。

Do not open real provider adapter, real HTTP server, real LLM, memory query engine, filesystem mutation, container, git worktree, tag, or release work.
