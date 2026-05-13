# Docs Inventory

状态：`current`

## 1. Purpose

本文盘点当前 `docs/` 下的 Markdown 文档，说明每份文档的用途、状态和后续整理方向。

本轮不移动、不删除、不合并任何文档。所有迁移建议都只是后续计划，必须另起 docs-only PR / commit 执行，并先维护 redirect / link map，避免 README、AGENTS、current-status、roadmap 或外部读者链接断掉。

盘点基线：

- 盘点前 existing docs Markdown：40 个。
- 加上本文后 docs Markdown：41 个。
- 加上 Track E boundary doc 后 docs Markdown：42 个。
- 加上 v0.2 demo readiness review 后 docs Markdown：43 个。
- 加上 v0.2 demo scenario boundary 后 docs Markdown：44 个。
- 加上 v0.2 demo acceptance 后 docs Markdown：45 个。
- 加上 Track F external ingestion boundary 后 docs Markdown：46 个。
- 加上 post v0.2 tag delta review 后 docs Markdown：47 个。
- 加上 v0.2 cycle closure review 后 docs Markdown：48 个。
- 加上 docs migration plan 后 docs Markdown：49 个。
- 加上 docs migration phase 1 dry-run 后 docs Markdown：50 个。
- Phase 1a 迁移 release draft 后 docs Markdown：51 个，其中旧 `docs/release-draft-v0.1-demo.md` 是 compatibility stub。
- Phase 1b 迁移 v0.1 demo explainer docs 后 docs Markdown：54 个，其中旧 demo explainer paths 是 compatibility stubs。
- Phase 1c 迁移 demo acceptance / readiness / scenario docs 后 docs Markdown：58 个，其中旧 demo acceptance / readiness / scenario paths 是 compatibility stubs。
- Docs migration Phase 1 当前 closed / paused；后续暂不迁移 track / checkpoint / memory / kernel / current-status / roadmap docs，除非用户明确请求。
- 加上 Kernel Gap Review v0.2 后 docs Markdown：59 个。当前下一阶段建议优先补 Agent / worker lifecycle 和 Workspace substrate 设计，而不是继续迁移文档或打开 real integrations。
- 加上 Agent / Worker Lifecycle Boundary v0.2 后 docs Markdown：60 个。
- 加上 Workspace Substrate Boundary v0.2 后 docs Markdown：61 个。当前仍不移动 docs 文件；workspace binding read model / policy boundary first slice 已 complete。
- 加上 Agent Task Queue 后 docs Markdown：62 个。当前用于后续 45-60 分钟批次自动推进，先从 Retry / Cancel / Supersede Boundary Planning 开始。
- 加上 Retry / Cancel / Supersede Boundary v0.2 后 docs Markdown：63 个。当前 first green slice 已 complete。
- 加上 Usability Pressure Test Plan v0.2 后 docs Markdown：64 个。`approval-gated tool runner` first slice 已实现，当前用于记录 pressure test scope、green status 和 exposed API friction。
- 加上 Approval Tool Runner API Friction Review 后 docs Markdown：65 个。当前用于记录 spike 暴露的 developer ergonomics 问题；approval lookup/read helper 已完成。
- 加上 Workspace Binding Helper Friction Review 和 Boundary docs 后 docs Markdown：67 个。workspace binding helper first slice 已完成。
- 加上 Submit Tool Request Friction Review 和 Submit Action Helper Boundary docs 后 docs Markdown：69 个。submit action helper first slice 已完成，remaining pressure-test friction 是 HTTP approval-gated input boundary。
- 加上 Usability Friction Round 1 Review 和 First App Spike Readiness 后 docs Markdown：71 个。第一轮 usability friction 已收口；artifact review flow first slice 后续已实现。
- 加上 Artifact Review Flow Friction Review 后 docs Markdown：72 个。当前建议下一批做 source artifact setup helper，先移除 private `_append(...)` demo glue，不打开 product artifact review facade。
- 加上 Source Artifact Setup Helper Boundary 后 docs Markdown：73 个。source artifact setup helper first slice 已完成，`artifact-review` demo 不再手写 private `_append(...)` source setup glue。
- 加上 Source Artifact Helper Closure Review 后 docs Markdown：74 个。source artifact helper 已 closed。
- 加上 Artifact Review Provenance Helper Boundary 后 docs Markdown：75 个。artifact provenance helper first slice 已完成，`artifact-review` demo 不再扫描 raw events 找 source artifact basis event。
- 加上 Artifact Review Flow Closure Review 后 docs Markdown：76 个。`artifact-review` first app spike 已 complete / closed for now。
- 加上 Second App Spike Selection 后 docs Markdown：77 个。当前推荐 `external snapshot review`，该 second app spike 后续已实现。
- 加上 External Snapshot Review Closure Review 后 docs Markdown：78 个。`external-snapshot-review` second app spike 已 complete / closed for now。
- 加上 App Spike Coverage Review 后 docs Markdown：79 个。该 recommendation 已执行到 `Kernel Gap Review Refresh`。
- 加上 Kernel Gap Review Refresh 后 docs Markdown：80 个。该 recommendation 已执行到 `Workspace Resource Lifecycle Boundary`。
- 加上 Workspace Resource Lifecycle Boundary 后 docs Markdown：81 个。Workspace Resource Lifecycle first green slice 已完成。
- 加上 Workspace Resource Lifecycle Closure Review 后 docs Markdown：82 个。Workspace Resource Lifecycle first slice 已 complete / closed for now；当前建议下一步做 Policy Profile / Action Registry Versioning Boundary，不实现 real filesystem substrate。
- Policy Profile / Action Registry Versioning first slice 已完成后 docs Markdown：83 个。
- 加上 Policy Registry Version Basis Closure Review 后 docs Markdown：84 个。Policy Profile / Action Registry Versioning first slice 已 complete / closed for now；当前建议下一步做 Retry / Cancel / Supersede Runtime Integration Boundary，不实现 plugin marketplace、policy DSL 或 migration framework。
- 加上 Retry / Cancel / Supersede Runtime Integration Boundary 后 docs Markdown：85 个。runtime request acceptance / rejection、logical cancel、replacement identity 和 allowed / disallowed transitions 已定义；runtime helper first green slice 已完成。
- 加上 Retry / Cancel / Supersede Runtime Closure Review 后 docs Markdown：86 个。R/C/S runtime integration first slice 已 complete / closed for now；当时建议下一步做 Event Schema Registry / Compatibility Boundary，不实现 scheduler、process kill、real concurrency、plugin marketplace、policy DSL 或 migration framework。
- 加上 Event Schema Registry / Compatibility Boundary 及旧路径 compatibility stub 后 docs Markdown：88 个。当时建议下一步做 Event Schema Registry / Compatibility Red Tests，不实现 JSON Schema / protobuf / schema migration framework / plugin event system。
- Event Schema Registry / Compatibility green slice 后 docs Markdown 仍为 88 个。新增 code/test 不增加 docs count；当前建议下一步做 Event Schema Registry / Compatibility Closure Review，不实现 JSON Schema / protobuf / schema migration framework / plugin event system。
- 加上 Event Schema Registry / Compatibility Closure Review 后 docs Markdown：89 个。Event Schema Registry / Compatibility first slice 已 complete / closed for now；当前建议下一步做 External Review Package Refresh，不实现 JSON Schema / protobuf / schema migration framework / plugin event system。
- 加上 External Review Package v0.2 后 docs Markdown：90 个。当前外部 reviewer 入口已刷新；下一步建议 External Review Feedback Intake 或用户明确选择下一条 docs-first kernel boundary。
- 加上 Post External Review Checkpoint 后 docs Markdown：91 个。当前已 external review ready；默认建议短暂停止 kernel expansion，让 application-layer prototype 先制造真实 friction。
- 加上 Kernel Mainline Maintenance Mode 后 tracked docs Markdown：92 个。当前主线进入 conservative maintenance mode；默认不主动扩 kernel feature，只接收 application-layer prototype / external review 已证明的 friction。
- 加上 `docs/concepts/` 下早期 Isotope 概念文档中文化迁移和 Hermes Agent 对照文档后 docs Markdown 增加 13 个，tracked docs Markdown 当前为 105 个；这些是 concept / application pressure docs，不是当前实现队列。
- 加上 Public / Internal Docs Boundary 后 tracked docs Markdown：106 个。该文档只定义 public / internal / concept / archive 分类边界，不移动、不删除、不隐藏任何文档。
- 加上 Mainline Idle Checkpoint 后 tracked docs Markdown：107 个。当前主线停在 idle / maintenance / friction-intake 状态；默认等待 app-layer friction report 或只做 periodic verification。
- 加上 Tool Protocol Boundary 后 tracked docs Markdown：108 个。该文档定义 tool invocation / result / error / grants / provenance / registry relationship；first green slice 已补上最小 `ToolInvocation` / `ToolResult` / `ToolError` models、artifact event provenance 和 structured `action.failed` error，仍不实现 plugin marketplace、remote tool、sandboxed process、streaming output 或 public SDK。
- 加上 Tool Protocol Closure Review 后 tracked docs Markdown：109 个。Tool Protocol first slice 已 complete / closed for now；closure 明确当前是 model / event-shape slice，不是 fully wired executor invocation runtime。
- 加上 Worker Handoff Helper Boundary 后 tracked docs Markdown：110 个。该文档把 aggressive branch `private_append_worker_handoff` evidence 收进 mainline boundary；当前 `InProcessServer.submit_worker_handoff(...)` first green slice 已实现，仍不实现 real concurrency、process spawn、remote worker、container、git worktree、real HTTP、LLM、provider 或 public SDK。
- 加上 Worker Handoff Helper Closure Review 后 tracked docs Markdown：111 个。该文档标记 worker handoff helper first slice complete / closed for now，并明确 `_derive_worker_handoff_grants(...)` 是 first-slice local grant derivation，不是完整 delegation policy engine。
- 加上 Worker Handoff App Spike Selection 后 tracked docs Markdown：112 个。该文档选择 red-tests-only `Worker Handoff App Spike` 作为下一步 bounded pressure test，不打开 real worker runtime / scheduler / process spawn / remote worker / container / git worktree / real HTTP / LLM / provider / public SDK。
- 加上 Session / Run Lifecycle Boundary 后 tracked docs Markdown：113 个。该文档定义 session identity、run lifecycle status transition、terminal-state behavior、replay 和 checkpoint 的最小 kernel contract，不实现 product session UX、auth、real HTTP server、scheduler、process kill、real concurrency 或 run graph。
- Session / Run Lifecycle first slice 已 green；tracked docs Markdown 数量不变。当前实现补上 `session.created` canonical event、`get_session_state(...)` event-backed read helper、`RunState` lifecycle fields、checkpoint field sync，以及 terminal ordinary-input no-side-effect guard。
- 加上 Error Taxonomy Boundary 后 tracked docs Markdown：114 个。该文档定义 direct helper / HTTP facade structured kernel error contract，建议后续 `KernelError(ValueError)` 保持 legacy message compatibility 同时暴露 stable `code` / `category` / `retryable` / `http_status` / `details`；不实现 product error UX、public SDK、real HTTP server、provider/process/container/git-worktree errors 或 release/tag。
- Error Taxonomy first slice 已 green；tracked docs Markdown 数量不变。当前实现补上 `src/isotope_kernel/errors.py`、`KernelError(ValueError)`、helper / HTTP mapping first paths 和 structured `not_enabled` result shape。
- 加上 Error Taxonomy Closure Review 后 tracked docs Markdown：115 个。Error Taxonomy first slice 已 complete / closed for now；当前建议回到 application-layer friction intake，让 aggressive-dev 消费 stable `KernelError` 行为后再决定是否重开 mainline。
- Worker Handoff Error Taxonomy slice 已 green；tracked docs Markdown 数量不变。当前实现把 worker handoff malformed intent、forged grants、unknown artifact ref 和 policy denied rejection 纳入 structured error taxonomy，同时保留 policy denial `PermissionError` compatibility 和 no partial delegation / worker events。
- 加上 Current Docs Map 后 tracked docs Markdown：116 个。该文档是当前 `docs/` 的短索引和读者路径归纳，不移动、不删除、不合并文档。
- Delegation Decision Read Model slice 已 green；tracked docs Markdown 数量不变。当前实现新增 `RunState.delegations`，把 delegation proposal / decision / worker linkage 投影到 read model，支持 replay 和 checkpoint-assisted rebuild，使 app shell 不再需要 raw event scan 审计 worker handoff decision；不改变 event append semantics。
- Workspace Lifecycle Helper slice 已 green；tracked docs Markdown 数量不变。当前实现新增 `InProcessServer.create_workspace_lease(...)`、`capture_workspace_artifact(...)`、`release_workspace(...)`，把 app-local private `_append(...)` workspace lifecycle glue 收口为既有 canonical events helper；不打开 real filesystem / container / git worktree / remote executor。
- 加上 VCS / Git Optional Boundary 后 tracked docs Markdown：120 个。该文档记录 Git / VCS 是 optional capability，不是 kernel 基础依赖；没有 Git 的电脑应走 `no_vcs` / `snapshot_only` fallback，不打开 branch / commit / git worktree / filesystem mutation 实现。
- Capability Hub Core first slice 已 green；tracked docs Markdown 数量不变。当前实现新增 `isotope_kernel.capability_catalog`，只接收 metadata / shelf / manifest / status 小核心和三个 product-candidate built-ins，不整体合并 aggressive capability hub、diagnostics、self-evolution、provider 或 product shell。
- 加上 Capability Hub Core Merge Readiness Review 后 tracked docs Markdown：122 个。该文档记录 capability catalog branch 已 rebase 到当前 `origin/main`，且只包含 catalog-only extraction，推荐 fast-forward / rebase 后合并。
- 加上 Agent Loop Run Control / Step Driver boundary docs 后 tracked docs Markdown：124 个。当前 integration branch 新增 summary-only control read model 和 one-step public-helper driver，不实现 automatic loop、scheduler、real LLM planner、provider adapter、real worker runtime 或 product shell。
- 合入 `feature/controlled-terminal-exec` 后 tracked docs Markdown 当前为 `144` 个。新增 controlled terminal / Codex-as-tool / model-tool bridge / LLM provider / terminal backend 等 boundary docs；这些文档描述 existing-code integration scope，不代表已打开 interactive shell、process supervisor、real listening HTTP server、provider product、container、git worktree 或 product shell。

## 2. Current entrypoints

这些文件是当前读者或 agent 应优先进入的文档，不建议近期移动：

- `docs/current-status.md`：当前状态入口，开始新任务前先读。
- `docs/current-docs-map.md`：当前文档地图，归纳读者路径、文档层级、current truth / concept / archive / stub 边界。
- `docs/v0.2-roadmap.md`：v0.2 track 状态和推荐顺序。
- `docs/agent-task-queue.md`：主线 agent task queue，记录 Current Batch、Stop Conditions 和后续 batch 建议。
- `docs/docs-migration-plan.md`：docs directory migration execution plan；Phase 1a release draft migration、Phase 1b demo explainer migration 和 Phase 1c demo acceptance/readiness/scenario migration 已执行；Phase 1 closed / paused。
- `docs/docs-migration-phase-1-dry-run.md`：Phase 1 dry-run checklist；Phase 1a / 1b / 1c 已执行；Phase 1 closed / paused。
- `docs/demo/v0.2-demo-readiness.md`：v0.2 developer demo readiness review，记录此前 demo 展示范围和已关闭的 Track A / C / E scenario gap。
- `docs/demo/v0.2-demo-scenario.md`：v0.2 demo scenario boundary / status，记录 implemented `--scenario v0.2` scope。
- `docs/demo/v0.2-demo-acceptance.md`：v0.2 developer demo acceptance，记录 `v0.2-demo` tag 状态和 non-goals。
- `docs/post-v0.2-tag-delta.md`：记录 `v0.2-demo` tag 之后 `main` 的 Track F / Agent Worker / Workspace 增量，以及暂不创建 `v0.2.1-demo` 的判断。
- `docs/post-external-review-checkpoint.md`：external review ready checkpoint，记录当前 baseline、passing demos、stable review surfaces、不要 overclaim 的 product gaps 和下一阶段选项。
- `docs/mainline-idle-checkpoint.md`：mainline idle checkpoint，记录 idle / maintenance / friction-intake 状态、reopen conditions 和 periodic verification next action。
- `docs/kernel-mainline-maintenance-mode.md`：kernel mainline conservative maintenance mode，记录 stability / review / application-layer friction intake 规则。
- `docs/public-internal-docs-boundary.md`：public / internal docs boundary，记录 public-ready、reviewer-facing、internal/dev-process、concept/application-pressure 和 historical/archive 分类。
- `docs/concepts/README.md`：早期 Isotope 概念文档和应用层设想索引，当前已改为中文主叙述；这些文档用于 pressure test，不是实现队列。
- `docs/v0.2-cycle-closure-review.md`：记录当前 v0.2 implementation cycle closure，建议进入 cleanup / docs organization / external review mode。
- `docs/kernel-gap-review-v0.2.md`：v0.2 kernel gap review，记录稳定子系统、kernel gaps、优先级和下一步设计建议。
- `docs/kernel-gap-review-refresh-v0.2.md`：app spike 后的 kernel gap refresh，记录 first-slice enough surfaces、still-open kernel gaps 和 External Review Package Refresh next-step recommendation。
- `docs/external-review-package-v0.2.md`：外部 reviewer 入口，说明 Isotope 是什么、能跑什么、已证明什么、哪些仍不是产品能力，以及推荐阅读路径。
- `docs/event-schema-registry-compatibility-boundary-v0.2.md`：Event schema registry / compatibility boundary，记录 payload schema version、unknown event fail-closed behavior、compatibility rules 和 first green slice evidence。
- `docs/event-schema-registry-closure-review.md`：Event schema registry / compatibility closure review，记录 first slice complete / closed for now 判断、registry behavior、remaining deferred schema work 和 next path。
- `docs/capability-hub-core-boundary-v0.2.md`：Capability Hub Core boundary，记录 aggressive branch 不能整体 merge、mainline 只抽取 capability metadata / shelf / manifest / status core 的范围和 first green slice evidence。
- `docs/capability-hub-core-merge-readiness-review.md`：Capability Hub Core merge readiness review，记录 rebase 结果、verification、merge 注意事项和仍然 deferred 的 capability execution / LLM route / product shell。
- `docs/tool-protocol-boundary-v0.2.md`：Tool protocol boundary，记录 tool invocation / result / error / capability / provenance / budget、executor grants hard contract、artifact / `ResourceRef` handoff 和 first red tests recommendation。
- `docs/tool-protocol-closure-review.md`：Tool protocol closure review，记录 first slice complete / closed for now、scope note、verification evidence、remaining friction 和 next path。
- `docs/controlled-terminal-execution-boundary-v0.2.md`：Controlled terminal execution boundary，记录 argv-only terminal tool path、policy / artifact / provenance boundary 和 deferred interactive shell / process supervisor / filesystem substrate。
- `docs/codex-as-tool-boundary-v0.2.md`：Codex-as-tool boundary，记录 Codex task route / approval-gated action handoff 的 in-process scope。
- `docs/model-tool-call-bridge-boundary-v0.2.md`：Model tool-call bridge boundary，记录 model-facing tool catalog / selected tool call / existing action-chain handoff。
- `docs/llm-provider-tool-call-boundary-v0.2.md`：LLM provider tool-call boundary，记录 provider route / tool-result loop / artifact-ref-only handoff scope。
- `docs/terminal-backend-adapter-contract-v0.2.md`、`docs/terminal-backend-selection-boundary-v0.2.md`、`docs/real-terminal-backend-boundary-v0.2.md`、`docs/terminal-capacity-system-runner-boundary-v0.2.md`、`docs/terminal-backend-closure-review.md`：terminal backend 相关 boundary / closure docs，记录 backend contract 和仍 deferred 的 real substrate / shell surfaces。
- `docs/worker-handoff-app-spike-selection.md`：Worker handoff app spike selection，记录下一步 red-tests-only pressure test 选择、scope、first red tests recommendation 和 stop conditions。
- `docs/session-run-lifecycle-boundary-v0.2.md`：Session / Run lifecycle boundary，记录 session/run identity、status transitions、terminal-state behavior、event/read-model shape 和 first green slice status。
- `docs/error-taxonomy-boundary-v0.2.md`：Error taxonomy boundary，记录 structured kernel error shape、HTTP facade mapping、first green slice 和 deferred product / integration error surfaces。
- `docs/error-taxonomy-closure-review.md`：Error taxonomy closure review，记录 first slice complete / closed for now。
- `docs/agent-worker-lifecycle-boundary-v0.2.md`：Agent / Worker lifecycle boundary，记录 supervisor / worker / delegation / worker read model / workspace binding / result handoff 的 first-slice design。
- `docs/workspace-substrate-boundary-v0.2.md`：Workspace substrate boundary，记录 workspace as policy-bound execution resource、binding / lease / path safety / artifact capture / deferred substrate 的 first-slice complete 状态。
- `docs/workspace-resource-lifecycle-boundary-v0.2.md`：Workspace resource lifecycle boundary，记录 binding vs lease、candidate events、read-model shape、artifact capture boundary 和 first-slice evidence。
- `docs/workspace-resource-lifecycle-closure-review.md`：Workspace resource lifecycle closure review，记录 first slice complete / closed for now 判断、read-model fields、remaining deferred substrate 和 next path。
- `docs/policy-profile-action-registry-versioning-boundary-v0.2.md`：Policy Profile / Action Registry Versioning boundary，记录 registry/profile basis metadata、stable reason code 和 first green slice evidence。
- `docs/policy-registry-version-basis-closure-review.md`：Policy Registry Version Basis closure review，记录 first slice complete / closed for now 判断、basis metadata summary、remaining friction 和 next path。
- `docs/retry-cancel-supersede-boundary-v0.2.md`：Retry / Cancel / Supersede boundary，记录 action lifecycle retry / cancel / supersede 的 first-slice contract 和 green status。
- `docs/retry-cancel-supersede-runtime-integration-boundary-v0.2.md`：Retry / Cancel / Supersede runtime integration boundary，记录 runtime request contract、logical cancel、replacement identity、state transition rules、first green slice evidence 和 closure-review next step。
- `docs/retry-cancel-supersede-runtime-closure-review.md`：Retry / Cancel / Supersede runtime closure review，记录 first slice complete / closed for now 判断、helper summary、remaining friction 和 next path。
- `docs/usability-pressure-test-plan-v0.2.md`：Kernel usability pressure test plan，记录 tiny app spike candidate review、approved `approval-gated tool runner` first slice 和 API friction。
- `docs/approval-tool-runner-friction-review.md`：Approval-gated tool runner API friction review，记录 `submit_tool_request(...)` friction、approval lookup helper、workspace binding helper 和 `submit_action(...)` outcome。
- `docs/workspace-binding-helper-friction-review.md`：Workspace binding helper friction review，记录 manual `workspace.bound` glue 的分层和 helper outcome。
- `docs/workspace-binding-helper-boundary-v0.2.md`：Workspace binding helper boundary，记录 `InProcessServer.bind_workspace(...)` first-slice contract。
- `docs/submit-tool-request-friction-review.md`：Submit tool request friction review，记录 raw `submit_tool_request(...)` demo glue 的分层和 helper outcome。
- `docs/submit-action-helper-boundary-v0.2.md`：Submit action helper boundary，记录 `InProcessServer.submit_action(...)` first-slice contract。
- `docs/usability-friction-round-1-review.md`：Usability friction round 1 closure review，记录 approval-tool-runner 第一轮 helper friction 收口。
- `docs/first-app-spike-readiness.md`：First app spike readiness review，选择并记录 `artifact review flow` first slice outcome。
- `docs/artifact-review-flow-friction-review.md`：Artifact review flow friction review，记录 source artifact setup glue 分层和 source artifact setup helper recommendation。
- `docs/artifact-review-flow-closure-review.md`：Artifact review flow closure review，记录 first app spike complete / closed for now 判断和 remaining optional friction。
- `docs/second-app-spike-selection.md`：Second app spike selection，记录 `external snapshot review` recommendation 和 red-test-only next batch。
- `docs/external-snapshot-review-closure-review.md`：External snapshot review closure review，记录 second app spike complete / closed for now 判断和 Track F coverage。
- `docs/app-spike-coverage-review.md`：App spike coverage review，记录两个 completed app spikes 的 kernel coverage、uncovered surfaces 和 `Kernel Gap Review Refresh` recommendation。
- `docs/source-artifact-setup-helper-boundary-v0.2.md`：Source artifact setup helper boundary，记录 `InProcessServer.create_source_artifact(...)` first-slice contract。
- `docs/source-artifact-helper-closure-review.md`：Source artifact helper closure review，记录 closure 判断、coverage note 和 remaining artifact-review friction。
- `docs/artifact-review-provenance-helper-boundary-v0.2.md`：Artifact review provenance helper boundary，记录 `InProcessServer.get_artifact_record(...)` first-slice contract。
- `docs/v0.2-mid-cycle-review.md`：mid-cycle decision，曾推荐进入 Track E；该 recommendation 已执行到 closure。
- `docs/v0.2-next-track-selection.md`：Track C selection 的历史决策记录，已执行到 closure。
- `docs/README.md`：kernel current-truth 文档包的阅读顺序入口。

根目录入口也仍然有效，但不计入 `docs/` 文件数量：

- `README.md`：外部 quick start 和短状态。
- `AGENTS.md`：agent workflow / repo boundary contract。

## 3. Active track docs

当前没有默认打开的 implementation track。Track F external ingestion 当前已完成 boundary 和 external observation read-model invariant green slices，并已 effectively complete / closed for now；`external-snapshot-review` second app spike 已 closed for now，不要直接实现 provider adapter / ingestion API。

当前默认下一步是 `Application-Layer Friction / External Feedback Intake`，不是 plugin marketplace、policy DSL、migration framework、scheduler、process kill 或 real filesystem substrate。`docs/external-review-package-v0.2.md` 已提供外部 reviewer 入口，`docs/post-external-review-checkpoint.md` 已记录 external review ready checkpoint；`docs/kernel-gap-review-refresh-v0.2.md` 已刷新 app spike 后的 kernel gaps；`docs/workspace-resource-lifecycle-boundary-v0.2.md` 已定义并实现 workspace lease / release / artifact-capture first green slice；`docs/workspace-resource-lifecycle-closure-review.md` 已标记该 slice complete / closed for now；`docs/policy-profile-action-registry-versioning-boundary-v0.2.md` 已定义并实现 registry/profile basis first slice；`docs/policy-registry-version-basis-closure-review.md` 已标记该 slice complete / closed for now；`docs/retry-cancel-supersede-runtime-integration-boundary-v0.2.md` 已定义并实现 runtime integration helper first green slice；`docs/retry-cancel-supersede-runtime-closure-review.md` 已标记该 slice complete / closed for now；`docs/event-schema-registry-compatibility-boundary-v0.2.md` 已定义并实现 event payload schema compatibility green slice；`docs/event-schema-registry-closure-review.md` 已标记该 slice complete / closed for now；`docs/tool-protocol-boundary-v0.2.md` 已定义并实现 first green slice；`docs/tool-protocol-closure-review.md` 已标记该 slice complete / closed for now；`docs/agent-worker-lifecycle-boundary-v0.2.md`、`docs/workspace-substrate-boundary-v0.2.md` 和 `docs/retry-cancel-supersede-boundary-v0.2.md` 三者 first slice 均已 complete。

当前自动推进入口是 `docs/agent-task-queue.md`。`Approval-Gated Tool Runner Spike` 已完成，API friction review 已落文档，approval lookup/read helper、workspace binding helper 和 submit action helper 已完成；artifact review flow first slice、friction review、source artifact setup helper closure review、artifact provenance helper first slice、artifact review flow closure review、second app spike selection、external snapshot review closure review 和 app spike coverage review 已完成。

- `docs/agent-task-queue.md`：active queue，Current Batch complete；Next Suggested Batch is merge integration branch, then return to existing-code integration intake。
- `docs/usability-pressure-test-plan-v0.2.md`：current pressure-test planning doc，`approval-gated tool runner` first slice complete and friction reviewed。
- `docs/second-app-spike-selection.md`：second app spike selection；recommended `external snapshot review`。
- `docs/external-snapshot-review-closure-review.md`：current external snapshot review closure review；second app spike complete / closed for now。
- `docs/app-spike-coverage-review.md`：app spike coverage review；recommendation executed by Kernel Gap Review Refresh。
- `docs/kernel-gap-review-refresh-v0.2.md`：current kernel gap refresh；after policy/profile first slice closure, RCS runtime closure review, and event schema compatibility closure review, recommends External Review Package Refresh next。
- `docs/external-review-package-v0.2.md`：current external review package；summarizes runnable demos, proven kernel surfaces, deferred product surfaces, reading path, and reviewer questions。
- `docs/post-external-review-checkpoint.md`：current external review ready checkpoint；records next-stage options and default recommendation to pause kernel expansion until app-layer friction appears。
- `docs/policy-profile-action-registry-versioning-boundary-v0.2.md`：current policy/profile versioning boundary；records first green slice for registry / policy basis metadata。
- `docs/policy-registry-version-basis-closure-review.md`：current policy/profile versioning closure review；records first slice complete / closed for now。
- `docs/workspace-resource-lifecycle-boundary-v0.2.md`：current workspace lifecycle boundary；first slice complete / closed for now。
- `docs/workspace-resource-lifecycle-closure-review.md`：current workspace lifecycle closure review；records first slice complete / closed for now。
- `docs/artifact-review-flow-friction-review.md`：artifact review flow friction review；source artifact setup and provenance helpers closed。
- `docs/artifact-review-flow-closure-review.md`：current artifact review closure review；first app spike complete / closed for now。
- `docs/source-artifact-setup-helper-boundary-v0.2.md`：current source artifact setup helper boundary；closed。
- `docs/source-artifact-helper-closure-review.md`：current source artifact helper closure review；closed。
- `docs/artifact-review-provenance-helper-boundary-v0.2.md`：current artifact provenance helper boundary；first slice complete。
- `docs/approval-tool-runner-friction-review.md`：current API ergonomics review；approval lookup/read, workspace binding, and submit action helper slices are complete。
- `docs/workspace-binding-helper-friction-review.md`：current workspace helper friction review；implemented。
- `docs/workspace-binding-helper-boundary-v0.2.md`：current workspace helper boundary；first slice complete。
- `docs/submit-tool-request-friction-review.md`：current submit tool request friction review；implemented。
- `docs/submit-action-helper-boundary-v0.2.md`：current submit action helper boundary；first slice complete。
- `docs/usability-friction-round-1-review.md`：current round 1 friction closure review；closed。
- `docs/first-app-spike-readiness.md`：current app spike readiness review；artifact review flow first slice complete。
- `docs/retry-cancel-supersede-boundary-v0.2.md`：Retry / Cancel / Supersede boundary，first slice complete。
- `docs/retry-cancel-supersede-runtime-integration-boundary-v0.2.md`：Retry / Cancel / Supersede runtime integration boundary，first green slice complete。
- `docs/retry-cancel-supersede-runtime-closure-review.md`：Retry / Cancel / Supersede runtime integration closure review，first slice closed for now。
- `docs/tool-protocol-boundary-v0.2.md`：Tool protocol boundary，first slice closed for now。
- `docs/tool-protocol-closure-review.md`：Tool protocol closure review，first slice closed for now。
- `docs/worker-handoff-helper-boundary-v0.2.md`：Worker handoff helper boundary，记录 `private_append_worker_handoff` friction、helper hard contracts 和下一批 red tests recommendation。
- `docs/worker-handoff-helper-closure-review.md`：Worker handoff helper closure review，记录 first slice complete / closed for now、remaining friction 和 deferred delegation policy integration。
- `docs/agent-worker-lifecycle-boundary-v0.2.md`：Agent / Worker lifecycle boundary，first slice complete。
- `docs/workspace-substrate-boundary-v0.2.md`：Workspace substrate boundary，first slice complete。
- `docs/vcs-git-optional-boundary-v0.2.md`：VCS / Git optional boundary，记录 Git 只作为 future optional adapter / capability diagnosis，不是 kernel baseline dependency。
- `docs/external-ingestion-boundary-v0.2.md`：Track F external ingestion / `ImportedSnapshot` boundary，closed for now。
- `docs/approval-pause-resume-boundary-v0.2.md`：Track E approval pause / resume boundary，closed for now。
- Supporting current docs:
  - `docs/v0.2-mid-cycle-review.md`
  - `docs/v0.2-roadmap.md`
  - `docs/current-status.md`
  - `docs/deferred-boundary-review-v0.1.md`
  - `docs/kernel-spec-v0.1.md`
  - `docs/kernel-architecture-v0.1.md`
  - `docs/kernel-living-spec.md`

Track E / Track F 后续只在明确 reopen 时继续扩展。Track F 后续应按 TDD 先写新的 red tests。不要直接实现完整 approval product 或 external ingestion provider adapter。

## 4. Closed track docs

这些文档对应已经收口或冻结的 tracks。它们仍是当前 truth 的一部分，但不应默认继续扩展。

### v0.1 Demo / Demo Docs

- `docs/demo/demo-entrypoint-v0.1.md`：demo entrypoint 设计，已实现。
- `docs/demo/demo-walkthrough-v0.1.md`：demo walkthrough，current。
- `docs/demo/demo-architecture-v0.1.md`：demo architecture diagram，current。
- `docs/demo-entrypoint-v0.1.md`：demo entrypoint compatibility stub。
- `docs/demo-walkthrough-v0.1.md`：demo walkthrough compatibility stub。
- `docs/demo-architecture-v0.1.md`：demo architecture compatibility stub。
- `docs/demo/v0.1-demo-acceptance.md`：developer demo acceptance，closed。
- `docs/demo/v0.2-demo-acceptance.md`：v0.2 developer demo acceptance，accepted / tagged。
- `docs/demo/v0.2-demo-readiness.md`：v0.2 developer demo readiness review，current。
- `docs/demo/v0.2-demo-scenario.md`：v0.2 demo scenario boundary / status，implemented。
- `docs/v0.1-demo-acceptance.md`：v0.1 demo acceptance compatibility stub。
- `docs/v0.2-demo-acceptance.md`：v0.2 demo acceptance compatibility stub。
- `docs/v0.2-demo-readiness.md`：v0.2 demo readiness compatibility stub。
- `docs/v0.2-demo-scenario.md`：v0.2 demo scenario compatibility stub。
- `docs/release/release-draft-v0.1-demo.md`：GitHub Release draft，未发布。
- `docs/release-draft-v0.1-demo.md`：release draft compatibility stub，保留旧入口避免链接断裂。

### Track A: HTTP API Minimal Surface

- `docs/http-api-minimal-surface-v0.2.md`：closed for now。当前 HTTP API 是 in-process facade，不是 real listening HTTP server。

### Track C: Artifact Content Read Policy

- `docs/artifact-content-read-policy-v0.2.md`：closed for now。controlled full-content retrieval 只在 retrieval layer；HTTP full-content route 仍 `501 not_enabled`。

### Checkpoint v0.1 Frozen Surface

- `docs/checkpoint-v0.1-scope-freeze.md`
- `docs/checkpoint-ownership-v0.1.md`
- `docs/checkpoint-integrity-v0.1.md`
- `docs/checkpoint-history-fallback-v0.1.md`
- `docs/checkpoint-history-index-retention-v0.1.md`
- `docs/checkpoint-history-save-boundary-v0.1.md`
- `docs/checkpoint-history-save-integration-v0.1.md`
- `docs/checkpoint-migration-versioning-v0.1.md`
- `docs/checkpoint-retention-compaction-v0.1.md`
- `docs/checkpoint-save-trigger-v0.1.md`
- `docs/checkpoint-schema-version-fields-v0.1.md`
- `docs/server-checkpoint-boundary-v0.1.md`

### Memory v0.1 Frozen Surface

- `docs/memory-v0.1-scope-freeze.md`
- `docs/memory-write-query-boundary-v0.1.md`
- `docs/memory-record-persistence-boundary-v0.1.md`

Memory 当前只展示 boundary / read-model / checkpoint，不代表 durable memory storage 或 query engine 已实现。

## 5. Kernel Design Notes

这些是长期 design / architecture / implementation notes。部分是 current-truth 包，部分是 historical-but-still-useful notes。

- `docs/README.md`
- `docs/kernel-one-pager.md`
- `docs/commitment-levels.md`
- `docs/kernel-spec-v0.1.md`
- `docs/kernel-architecture-v0.1.md`
- `docs/kernel-gap-review-v0.2.md`
- `docs/kernel-decision-log.md`
- `docs/kernel-living-spec.md`
- `docs/implementation-plan-v0.1.md`
- `docs/coding-plan-v0.1.md`
- `docs/action-type-registry-v0.1.md`
- `docs/event-envelope-versioning-v0.1.md`
- `docs/event-envelope-schema-registry-v0.1.md`
- `docs/event-prefix-digest-v0.1.md`
- `docs/deferred-boundary-review-v0.1.md`

## 6. Inventory By File

| File | Primary use | Current status |
| --- | --- | --- |
| `docs/README.md` | Kernel current-truth reading order | current entrypoint |
| `docs/action-type-registry-v0.1.md` | Action registry design/status | closed / reference |
| `docs/agent-task-queue.md` | Mainline agent batch queue | active |
| `docs/agent-worker-lifecycle-boundary-v0.2.md` | Agent / Worker lifecycle boundary | first slice complete |
| `docs/approval-pause-resume-boundary-v0.2.md` | Track E approval pause / resume boundary | closed for now |
| `docs/artifact-content-read-policy-v0.2.md` | Track C boundary | closed for now |
| `docs/artifact-review-provenance-helper-boundary-v0.2.md` | Artifact review provenance helper boundary | first slice complete |
| `docs/artifact-review-flow-closure-review.md` | Artifact review flow closure review | first app spike closed for now |
| `docs/artifact-review-flow-friction-review.md` | Artifact review flow friction review | closed / reference |
| `docs/second-app-spike-selection.md` | Second app spike selection | closed / reference |
| `docs/external-snapshot-review-closure-review.md` | External snapshot review closure review | second app spike closed for now |
| `docs/app-spike-coverage-review.md` | App spike coverage review | closed / reference |
| `docs/checkpoint-history-fallback-v0.1.md` | Checkpoint fallback boundary | closed / frozen |
| `docs/checkpoint-history-index-retention-v0.1.md` | Checkpoint history index / retention boundary | closed / frozen |
| `docs/checkpoint-history-save-boundary-v0.1.md` | Checkpoint history save boundary | closed / frozen |
| `docs/checkpoint-history-save-integration-v0.1.md` | Checkpoint history save integration boundary | closed / frozen |
| `docs/checkpoint-integrity-v0.1.md` | Checkpoint integrity boundary | closed / frozen |
| `docs/checkpoint-migration-versioning-v0.1.md` | Checkpoint migration/versioning boundary | closed / frozen |
| `docs/checkpoint-ownership-v0.1.md` | Checkpoint ownership boundary | closed / frozen |
| `docs/checkpoint-retention-compaction-v0.1.md` | Checkpoint retention/compaction boundary | closed / frozen |
| `docs/checkpoint-save-trigger-v0.1.md` | Checkpoint save trigger boundary | closed / frozen |
| `docs/checkpoint-schema-version-fields-v0.1.md` | Checkpoint schema/version fields | closed / frozen |
| `docs/checkpoint-v0.1-scope-freeze.md` | Checkpoint scope freeze | closed / frozen |
| `docs/coding-plan-v0.1.md` | Initial coding plan | historical / reference |
| `docs/commitment-levels.md` | Contract commitment levels | current reference |
| `docs/current-docs-map.md` | Docs map / reader paths / current truth boundaries | current entrypoint |
| `docs/current-status.md` | Current repo status | current entrypoint |
| `docs/deferred-boundary-review-v0.1.md` | Deferred surface review | current reference |
| `docs/demo/demo-architecture-v0.1.md` | Demo architecture diagram | current demo doc |
| `docs/demo/demo-entrypoint-v0.1.md` | Demo entrypoint design | closed / implemented |
| `docs/demo/demo-walkthrough-v0.1.md` | Demo walkthrough | current demo doc |
| `docs/demo-architecture-v0.1.md` | Demo architecture compatibility stub | stub / keep for one cycle |
| `docs/demo-entrypoint-v0.1.md` | Demo entrypoint compatibility stub | stub / keep for one cycle |
| `docs/demo-walkthrough-v0.1.md` | Demo walkthrough compatibility stub | stub / keep for one cycle |
| `docs/docs-migration-phase-1-dry-run.md` | Docs migration phase 1 dry-run checklist | current plan |
| `docs/docs-migration-plan.md` | Docs directory migration execution plan | current plan |
| `docs/event-envelope-schema-registry-v0.1.md` | Event schema registry boundary | closed / reference |
| `docs/event-envelope-versioning-v0.1.md` | Event envelope versioning boundary | closed / reference |
| `docs/event-prefix-digest-v0.1.md` | Event prefix digest boundary | closed / reference |
| `docs/event-schema-compatibility-boundary-v0.2.md` | Event schema compatibility old-path stub | stub / keep for one cycle |
| `docs/event-schema-registry-closure-review.md` | Event schema registry / compatibility closure review | first slice closed for now |
| `docs/event-schema-registry-compatibility-boundary-v0.2.md` | Event schema registry / compatibility boundary | first slice closed for now |
| `docs/error-taxonomy-boundary-v0.2.md` | Error taxonomy boundary | first slice closed for now |
| `docs/error-taxonomy-closure-review.md` | Error taxonomy closure review | first slice closed for now |
| `docs/external-ingestion-boundary-v0.2.md` | Track F external ingestion boundary | closed for now |
| `docs/external-review-package-v0.2.md` | External reviewer package / reading path | current review package |
| `docs/http-api-minimal-surface-v0.2.md` | Track A HTTP API boundary | closed for now |
| `docs/implementation-plan-v0.1.md` | Initial implementation plan | historical / reference |
| `docs/kernel-architecture-v0.1.md` | Kernel architecture draft | current reference |
| `docs/kernel-decision-log.md` | Decision log | current reference |
| `docs/kernel-gap-review-v0.2.md` | Kernel gap review / next design backlog | historical review |
| `docs/kernel-gap-review-refresh-v0.2.md` | Kernel gap refresh after app spikes | current review |
| `docs/kernel-living-spec.md` | Living spec draft | current reference |
| `docs/kernel-one-pager.md` | Kernel one-pager | current reference |
| `docs/kernel-spec-v0.1.md` | Kernel spec draft | current reference |
| `docs/memory-record-persistence-boundary-v0.1.md` | Memory persistence boundary | closed / frozen |
| `docs/memory-v0.1-scope-freeze.md` | Memory scope freeze | closed / frozen |
| `docs/memory-write-query-boundary-v0.1.md` | Memory write/query boundary | closed / frozen |
| `docs/post-v0.2-tag-delta.md` | Post-tag mainline delta review | current review |
| `docs/post-external-review-checkpoint.md` | Post external review checkpoint | current checkpoint |
| `docs/mainline-idle-checkpoint.md` | Mainline idle / friction-intake checkpoint | current checkpoint |
| `docs/public-internal-docs-boundary.md` | Public / internal docs classification boundary | current docs boundary |
| `docs/policy-profile-action-registry-versioning-boundary-v0.2.md` | Policy profile / action registry versioning boundary | first slice closed for now |
| `docs/policy-registry-version-basis-closure-review.md` | Policy registry version basis closure review | first slice closed for now |
| `docs/release/release-draft-v0.1-demo.md` | Release draft text | draft / not published |
| `docs/release-draft-v0.1-demo.md` | Release draft compatibility stub | stub / keep for one cycle |
| `docs/retry-cancel-supersede-boundary-v0.2.md` | Retry / cancel / supersede action lifecycle boundary | first slice complete |
| `docs/retry-cancel-supersede-runtime-integration-boundary-v0.2.md` | Retry / cancel / supersede runtime integration boundary | first green slice complete |
| `docs/retry-cancel-supersede-runtime-closure-review.md` | Retry / cancel / supersede runtime integration closure review | first slice closed for now |
| `docs/server-checkpoint-boundary-v0.1.md` | Server checkpoint boundary | closed / frozen |
| `docs/source-artifact-helper-closure-review.md` | Source artifact helper closure review | closed |
| `docs/source-artifact-setup-helper-boundary-v0.2.md` | Source artifact setup helper boundary | closed |
| `docs/tool-protocol-boundary-v0.2.md` | Tool protocol boundary | first slice closed for now |
| `docs/tool-protocol-closure-review.md` | Tool protocol closure review | first slice closed for now |
| `docs/usability-pressure-test-plan-v0.2.md` | Kernel usability pressure test / spike status | two app spikes closed for now |
| `docs/workspace-binding-helper-boundary-v0.2.md` | Workspace binding helper boundary | first slice complete |
| `docs/workspace-binding-helper-friction-review.md` | Workspace binding helper friction review | implemented |
| `docs/workspace-resource-lifecycle-boundary-v0.2.md` | Workspace resource lifecycle boundary | first slice closed for now |
| `docs/workspace-resource-lifecycle-closure-review.md` | Workspace resource lifecycle closure review | first slice closed for now |
| `docs/demo/v0.1-demo-acceptance.md` | Demo acceptance record | closed |
| `docs/v0.2-cycle-closure-review.md` | v0.2 cycle closure decision | current review |
| `docs/demo/v0.2-demo-acceptance.md` | v0.2 demo acceptance record | accepted / tagged |
| `docs/demo/v0.2-demo-readiness.md` | v0.2 demo readiness review | current review |
| `docs/demo/v0.2-demo-scenario.md` | v0.2 demo scenario boundary / status | implemented |
| `docs/v0.1-demo-acceptance.md` | v0.1 demo acceptance compatibility stub | stub / keep for one cycle |
| `docs/v0.2-demo-acceptance.md` | v0.2 demo acceptance compatibility stub | stub / keep for one cycle |
| `docs/v0.2-demo-readiness.md` | v0.2 demo readiness compatibility stub | stub / keep for one cycle |
| `docs/v0.2-demo-scenario.md` | v0.2 demo scenario compatibility stub | stub / keep for one cycle |
| `docs/v0.2-mid-cycle-review.md` | v0.2 next-track review | current decision |
| `docs/v0.2-next-track-selection.md` | Track C selection record | historical decision |
| `docs/v0.2-roadmap.md` | v0.2 roadmap | current entrypoint |

## 7. Candidates For Future Subdirectories

未来可以考虑这些目录，但本轮不移动文件：

- `docs/tracks/`
  - `http-api-minimal-surface-v0.2.md`
  - `artifact-content-read-policy-v0.2.md`
  - `approval-pause-resume-boundary-v0.2.md`
  - `v0.2-roadmap.md`
  - `v0.2-mid-cycle-review.md`
  - `v0.2-next-track-selection.md`
- `docs/kernel/`
  - `agent-worker-lifecycle-boundary-v0.2.md`
  - `kernel-*.md`
  - `kernel-gap-review-v0.2.md`
  - `kernel-gap-review-refresh-v0.2.md`
  - `commitment-levels.md`
  - `action-type-registry-v0.1.md`
  - `event-envelope-*.md`
  - `event-prefix-digest-v0.1.md`
- `docs/checkpoint/`
  - all `checkpoint-*.md`
  - `server-checkpoint-boundary-v0.1.md`
- `docs/memory/`
  - all `memory-*.md`
- `docs/demo/`
  - `demo-*.md`
  - `v0.1-demo-acceptance.md`
  - `v0.2-demo-acceptance.md`
  - `v0.2-demo-readiness.md`
  - `v0.2-demo-scenario.md`
- `docs/release/`
  - `release-draft-v0.1-demo.md`
- `docs/status/`
  - `docs-migration-phase-1-dry-run.md` later, after phase 1 execution docs settle
- `docs/archive/` or `docs/history/`
  - `implementation-plan-v0.1.md`
  - `coding-plan-v0.1.md`
  - old selection / review docs only after current-status and roadmap no longer link them directly

## 8. Do-not-move-yet list

Do not move these files until a dedicated migration pass updates links and validates them:

- `docs/current-status.md`
- `docs/v0.2-roadmap.md`
- `docs/docs-migration-phase-1-dry-run.md`
- `docs/v0.2-mid-cycle-review.md`
- `docs/v0.2-next-track-selection.md`
- `docs/agent-worker-lifecycle-boundary-v0.2.md`
- `docs/http-api-minimal-surface-v0.2.md`
- `docs/artifact-content-read-policy-v0.2.md`
- `docs/approval-pause-resume-boundary-v0.2.md`
- `docs/kernel-spec-v0.1.md`
- `docs/kernel-architecture-v0.1.md`
- `docs/kernel-gap-review-v0.2.md`
- `docs/kernel-gap-review-refresh-v0.2.md`
- `docs/kernel-living-spec.md`

Reasons:

- README / AGENTS / current-status / roadmap link to these paths directly.
- Several files were recently shared or used as active task entrypoints.
- Moving them without redirects would break current onboarding and agent workflow.

## 9. Safe Migration Plan

Recommended future migration sequence:

1. Phase 1a has executed: `docs/release/release-draft-v0.1-demo.md` is the full release draft, and `docs/release-draft-v0.1-demo.md` is a stub.
2. Phase 1b has executed: `docs/demo/demo-entrypoint-v0.1.md`, `docs/demo/demo-walkthrough-v0.1.md`, and `docs/demo/demo-architecture-v0.1.md` are full docs; old paths are stubs.
3. Phase 1c has executed: `docs/demo/v0.1-demo-acceptance.md`, `docs/demo/v0.2-demo-readiness.md`, `docs/demo/v0.2-demo-scenario.md`, and `docs/demo/v0.2-demo-acceptance.md` are full docs; old paths are stubs.
4. Phase 1 is closed / paused. Do not continue track / checkpoint / memory / kernel / status-entrypoint migrations unless explicitly requested.
5. Kernel Gap Review has started in `docs/kernel-gap-review-v0.2.md`; refresh lives in `docs/kernel-gap-review-refresh-v0.2.md`; Agent / Worker lifecycle boundary design now lives in `docs/agent-worker-lifecycle-boundary-v0.2.md`.
6. If migration is reopened, move closed Track A / C / E docs to `docs/tracks/` and leave stubs.
7. Add target subdirectories only in the migration commit that needs them.
8. Update README / AGENTS / current-status / roadmap links in the same patch as any move.
9. Leave short stub files at old paths for at least one cycle, or add a compatibility index if stubs are not desired.
10. Run link checks with `rg` for every old basename and ensure no stale references remain.
11. Run the normal verification suite.
12. Commit moves separately from content rewrites to keep review clean.

Do not combine directory migration with implementation work.
