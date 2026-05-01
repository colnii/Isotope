# Approval Pause / Resume Boundary v0.2

状态：`run-state read model slice complete`

## 1. Purpose

本文定义 Track E: Minimal Approval Pause / Resume Boundary 的 v0.2 最小边界。

目标不是实现完整 approval product，而是把 action chain 中的 human gate（人工确认门）钉成可 replay、可 checkpoint、可测试的 kernel contract：action 可以被 policy 暂停，resolution 必须通过 canonical events 表达，approved path 只能通过现有 execution boundary 恢复执行，denied path 不能执行。

## 2. Why Track E Now

Track E 当前值得做，因为 approval 是 action chain / policy / blocked run / resume 的关键 contract：

- 它能验证 pending action 不会被 executor 隐式推进。
- 它能验证 resume 不会绕过 `PolicyDecision.grants`。
- 它能让 v0.2 demo 展示 success path 之外的 blocked / resolved lifecycle。
- 它可以继续保持 in-process、no network、no real LLM、no new dependencies。
- 它比 real HTTP server 更能验证 kernel contract，而不是引入 transport lifecycle。
- 它比 memory query engine 更不容易误导成 product memory capability。
- 它比 external ingestion implementation 更少牵涉 provider-specific quality / freshness / coverage semantics。

## 3. Current Surface

当前仓库已经有最小 approval pause / resolve / resume surface：

- `PolicyDecision` outcome 已支持 `pending_user_approval`。
- `InProcessServer.submit_tool_request(..., requires_approval=True)` 可以产生 pending approval path。
- canonical `approval.requested` event boundary 已存在。
- `InProcessServer.resolve_approval(...)` 已支持 minimal explicit resolution。
- approved resolution 会 append canonical `approval.resolved`，然后通过现有 executor path resume。
- approved resume 使用原 `PolicyDecision.grants`，不会使用 resolution body 中的 forged grants。
- denied resolution 会 append canonical `approval.resolved`，但不创建 execution / artifact。
- duplicate resolution 受控 conflict：server 抛 `ValueError("approval already resolved")`，HTTP facade 返回 `409 approval_already_resolved`。
- `RunState.approvals` 已作为最小 approval read model 落地。
- projector 能记录 pending / approved / denied approval summary。
- projector replay 能恢复 pending / resolved approval state。
- checkpoint-assisted rebuild 能恢复 approval read model。
- pending approval 不创建 `ActionExecution`。
- pending approval 不创建 artifact。
- pending approval 可从 event log rebuild。
- HTTP `GET /runs/{run_id}` 暴露 JSON-compatible approval read model，不暴露 internal Python object repr。
- HTTP API 目前仍是 in-process facade，已提供 minimal approval resolve route。

当前仍不是完整 approval product：

- 没有 approval UI。
- 没有 auth / identity。
- 没有 notification。
- 没有 timeout scheduler。
- 没有 complex approval policy DSL。
- 没有 real HTTP network server。

## 4. Non-Goals

Track E v0.2 不做：

- 完整 approval product UI。
- multi-user identity / auth。
- notification / email / webhook。
- timeout scheduler。
- complex approval policy DSL。
- real HTTP network server。
- hosted approval workflow。
- external approval provider integration。
- long-running distributed workflow engine。

## 5. Minimal v0.2 Goal

Track E 的最小目标：

- action can pause as `pending_user_approval`。已完成。
- canonical `approval.requested` 继续作为 pending request event。已完成。
- 增加 explicit resolve path。已完成。
- approved resolution appends canonical event and resumes execution through existing action / executor boundary。已完成。
- denied resolution appends canonical event and does not execute。已完成。
- projector state can be rebuilt from event log。已完成。
- projector state can be rebuilt from checkpoint + suffix events。已完成。
- duplicate resolve is controlled as conflict。已完成。
- resolving unknown / stale / malformed approval fails closed。已完成。
- HTTP approval resolve route remains in-process。已完成。

`approval.resolved` 已作为 v0.2 slice event 落地，但仍不是永久协议承诺。

## 6. Hard Boundaries

必须守住：

- approval resolution must not mutate `RunState` / native state directly。
- approval resolution must append canonical events。
- executor cannot run before approval is resolved。
- approved resume must use existing executor boundary。
- denied resolution must not create execution or artifact。
- resolved grants must remain policy-derived, not user-invented。
- approval resolution cannot expand `PolicyDecision.grants`。
- approval resolution cannot change the original proposal payload。
- resume lifecycle must keep canonical order: decision pending -> approval resolved -> execution started -> action completed / failed。
- duplicate / stale approval resolution must be controlled and side-effect safe。
- HTTP route, if opened later, must remain in-process unless Track B real HTTP server is explicitly reopened。

## 7. Event / State Candidate

Existing event:

- `approval.requested`

Candidate future event:

- `approval.resolved`

`approval.resolved` candidate payload should include at least:

- `approval_id`
- `run_id`
- `proposal_id`
- `decision_id`
- `resolution`: `approved` or `denied`
- `resolved_at`
- `resolver`
- `reason`
- provenance / basis information, such as `basis_event_id`

The projector may expose pending / resolved approval state in `RunState`, but it must derive that state only from canonical events. It must not read an approval store, HTTP facade cache, executor memory, or client request body directly.

Current `RunState.approvals` read model is deliberately minimal:

- pending approval entries contain `approval_id`, `run_id`, `proposal_id`, `decision_id`, `status: pending`, `reason_codes`, and `requested_action_summary`。
- approved entries keep the approval identity and record `status: approved`, `resolution`, `reason`, `resolver`, `resolved_event_id`, and `basis_event_id`。
- denied entries use the same resolved shape with `status: denied` and do not create execution / artifact summaries。
- checkpoint state includes `approvals` and validates approval shape before using checkpoint-assisted rebuild。

## 8. Server / HTTP Boundary

Future server work may add a minimal in-process resolve method, but it must:

- validate the approval exists and is still pending。
- validate the resolution body。
- append canonical resolution event。
- on approval, resume via the existing action / executor path。
- on denial, record denial and stop without execution。
- preserve `PolicyDecision.grants` as the only execution grants。

Future HTTP work may add an in-process approval endpoint, but it must:

- reuse the existing `HttpApiApp` response contract。
- reuse request validation and no-side-effect error boundary。
- not become a real network server。
- not introduce FastAPI / Flask / new dependencies。
- not imply multi-user auth or product approval workflow。

## 9. First Tests

第一批 tests 已落地并通过：

- `tests/isotope_kernel/test_approval_resolution_boundary.py`
- `tests/isotope_kernel/test_http_api_approval_boundary.py`

第一批测试应覆盖：

- pending approval 不创建 execution / artifact。
- `approval.requested` event 有 `approval_id` / `run_id` / `proposal_id` / `decision_id`。
- approve resolution appends canonical event and resumes execution through existing executor boundary。
- deny resolution appends canonical event and does not execute。
- duplicate resolution is controlled。
- resolving unknown approval returns controlled error。
- malformed approval resolution returns controlled error。
- projector rebuild can restore pending / resolved approval state。
- approval resolution does not bypass `PolicyDecision.grants`。
- approved resume cannot invent grants。
- denied approval cannot create artifact。
- server / HTTP approval route remains in-process; no real network listener。
- HTTP approval collection route remains deferred / `501 not_enabled`。

第二批 run-state invariants tests 已落地并通过：

- `tests/isotope_kernel/test_approval_run_state_invariants.py`
- `tests/isotope_kernel/test_http_api_approval_state_read_model.py`

第二批测试覆盖：

- pending approval 后 `RunState` 有 explicit approval read model。
- pending approval 不把 run 标成 completed，不创建 execution / artifact。
- approved resolution 后 pending signal 变成 approved summary，execution / artifact summary 出现，run 可 completed。
- denied resolution 后 approval summary 变成 denied，不创建 execution / artifact，run state 稳定为 denied。
- duplicate resolution 不改变 projected state。
- replay from event log 和 checkpoint-assisted rebuild 都能恢复 approval read model。
- HTTP `GET /runs/{run_id}` 暴露 approval read model，`GET /runs/{run_id}/events` 仍返回 canonical events。

## 10. Deferred After This Boundary

继续 deferred：

- approval UI。
- multi-user identity / auth。
- notification / timeout scheduler。
- complex approval policy DSL。
- real HTTP server。
- real LLM approval prompts。
- external approval provider integration。
- distributed idempotency / durable approval queue。
