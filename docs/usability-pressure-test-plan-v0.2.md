# Usability Pressure Test Plan v0.2

状态：`artifact review flow, demo trace, and source artifact setup helper closed`

## 1. Purpose

本文定义第一个 usability pressure test（可用性压力测试）候选范围。它不是 implementation plan，也不是产品路线承诺。

目标是回答一个窄问题：在 Track A / C / E / F、Agent / Worker lifecycle first slice、Workspace substrate first slice 和 Retry / Cancel / Supersede stabilization slice 已完成后，Isotope 是否已经足够开始一个 tiny app spike（小应用尖刺验证），用来检验 kernel boundary 在更接近真实使用路径里的可读性和组合性。

原 planning 阶段不新增实现、不新增测试、不打开真实集成。用户已确认选择 `approval-gated tool runner` 后，first slice 已按 TDD 落地为 deterministic in-process demo scenario。

新增命令：

```bash
python -m isotope_kernel.demo --scenario approval-tool-runner
python -m isotope_kernel.demo --scenario approval-tool-runner --trace
python -m isotope_kernel.demo --scenario approval-tool-runner --json
python -m isotope_kernel.demo --scenario artifact-review
python -m isotope_kernel.demo --scenario artifact-review --trace
python -m isotope_kernel.demo --scenario artifact-review --json
python -m isotope_kernel.demo --scenario v0.2 --trace
```

## 2. Current Kernel Readiness

当前可以被 pressure test 使用的 kernel slice：

- deterministic in-process runtime。
- `HttpApiApp` facade，不监听端口。
- action chain: `ActionCompiler -> PolicyEngine -> Executor`。
- `PolicyDecision.grants` enforcement。
- artifact / `ResourceRef` / provenance。
- controlled artifact content retrieval boundary。
- approval pause / resume boundary。
- external observation boundary。
- Agent / Worker lifecycle read model。
- Workspace `shared_ro` binding read model。
- Retry / Cancel / Supersede read model。
- event replay and checkpoint-assisted rebuild。

当前 baseline：`892 passed`。

## 3. Hard Boundaries

第一个 tiny app spike 必须遵守：

- no real HTTP server / network listener。
- no real LLM。
- no provider adapter / webhook / external callback。
- no durable memory storage / query engine。
- no new dependency。
- no container / git worktree / remote executor。
- no product UI。
- no tag / GitHub Release。
- 不绕过 action chain / policy / event log / projector。
- 不把 artifact full content、workspace file content 或 external raw input 当成 native state。

## 4. Candidate Comparison

| Candidate | Visible value | Kernel contracts exercised | Risk | Product judgment needed? | Fit |
| --- | --- | --- | --- | --- | --- |
| file summarizer | 容易理解，外部读者能快速感知用途 | workspace binding、artifact capture、retrieval policy | 容易暗示 real file IO、path safety、LLM summary 已可用；当前 workspace 仍是 `shared_ro` boundary | medium | not first |
| artifact review flow | 很适合验证 artifact summary / full-content policy / provenance | artifact / `ResourceRef` / controlled content retrieval / checkpoint | 可见价值偏窄，较少压力测试 worker、workspace、approval、retry / cancel / supersede 的组合 | low | acceptable but shallow |
| approval-gated tool runner | 能清楚展示 action chain、policy grants、approval pause / resume、workspace grant、artifact handoff、HTTP facade 和 replay / checkpoint | Track A / C / E、Agent / Workspace、RCS read model 都能被窄范围触达 | 需要谨慎避免被理解为真实 tool runner、real filesystem mutation 或 process execution | medium | recommended |
| research assistant mini flow | 对外展示价值高 | 可能触达 memory、retrieval、external observation、artifact review | 容易牵出 real LLM、semantic retrieval、ranking、provider adapter 和 memory query，当前风险最高 | high | defer |

## 5. Recommendation

推荐候选：`approval-gated tool runner`。

原因：

- 它最能验证当前 kernel 已完成的组合边界，而不是只展示单点 capability。
- 可以保持 deterministic / in-process / no-network / no-real-LLM。
- 可以通过 approval gate 明确展示 user decision boundary，但不需要 product UI。
- 可以要求 tool action 只在 policy grants 允许后执行，并通过 artifact / `ResourceRef` handoff 结果。
- 可以确认 HTTP facade、event replay、checkpoint-assisted rebuild 和 read model 在同一 tiny app flow 中协同工作。

但该选择仍包含产品/用户判断：这个 spike 会把 Isotope 展示成“approval-gated tool runner”方向，而不是 artifact review 或 research assistant 方向。按 `docs/agent-task-queue.md` stop condition，本轮不把它正式选为 next implementation batch。

## 6. Implemented First Slice

用户已确认选择 `approval-gated tool runner`。

已新增测试文件：

- `tests/isotope_kernel/test_usability_spike_approval_tool_runner.py`
- `tests/isotope_kernel/test_usability_spike_approval_tool_runner_read_model.py`

当前 green scope：

- spike 使用 in-process server / `HttpApiApp`，不监听端口。
- create session / run / read run state / read events 通过 HTTP facade 可走通。
- deterministic `write_artifact_tool` action 先进入 pending approval。
- approved resolution 通过现有 executor path resume。
- action 使用原 `PolicyDecision.grants`。
- workspace binding 通过 canonical `workspace.bound` 进入 `RunState.workspaces`。
- workspace binding 由 `InProcessServer.bind_workspace(...)` helper 创建 canonical `workspace.bound`，demo 不再手写 event payload。
- workspace binding 仍是 `shared_ro`，没有 filesystem mutation。
- result handoff 使用 artifact summary / structured `ResourceRef` / provenance。
- JSON / read model 不包含 artifact full content。
- HTTP full-content route 仍 `501 not_enabled`。
- event replay 和 checkpoint-assisted rebuild 得到同等 read model。
- 不实现 real scheduler、process kill、tool-level cancellation、real concurrency、real LLM、provider adapter 或 memory query。

## 7. API Friction Exposed

这个 spike 有意记录当前 kernel API awkwardness（不顺手处），不要把它隐藏成假 product API：

- approval-gated input 已改用 `server.submit_action(..., requires_approval=True)`；`POST /runs/{run_id}/input` 仍没有 approval flag。
- workspace binding helper 已改用 `InProcessServer.bind_workspace(...)`；demo 不再手写 canonical `workspace.bound` payload。
- `approval_id` discovery 已改用 approval lookup/read helper；demo 不再扫描 canonical events 找 approval id。

这些是后续 API ergonomics（易用性）候选，不是本 slice 要补的功能。

## 8. Friction Review

API friction review 已落文档：`docs/approval-tool-runner-friction-review.md`。

结论：

- `server.submit_tool_request(..., requires_approval=True)` 曾暴露 facade/helper gap，但不是 kernel correctness bug；当前已由 `InProcessServer.submit_action(...)` first slice 降低。
- `approval_id` discovery 扫描 canonical events 的 read-model helper gap 已处理。
- manual `workspace.bound` 暴露 workspace binding ownership / server integration gap；该 gap 已用最小 server helper first slice 降低，但仍不代表真实 workspace substrate。
- 不建议直接产品化 HTTP input、real tool runner、workspace filesystem mutation 或 approval UI。

已完成：`Approval Lookup Helper Boundary`。

## 9. Closure

当前判断：`approval-gated tool runner` first slice complete。

仍不包含：

- real HTTP server / network listener
- real LLM
- external provider
- real filesystem mutation
- container / process spawn
- product UI
- automatic retry / scheduler / process kill

approval lookup/read helper 已降低 demo/client event-scan glue；workspace binding helper 已降低 manual `workspace.bound` glue；submit action helper 已降低 raw `submit_tool_request(...)` glue。remaining API friction 是 HTTP `/runs/{run_id}/input` 仍没有 approval flag；不要直接产品化 HTTP input、workspace filesystem mutation 或 real tool runner。

## 10. Round 1 Closure And Next Spike

Round 1 closure review 见 `docs/usability-friction-round-1-review.md`。

当前判断：

- `approval-tool-runner` now reasonable as developer demo。
- 第一轮主要 glue friction 已由 approval lookup helper、workspace binding helper 和 submit action helper 收口。
- 不建议继续默认扩展同一个 spike。

First app spike readiness review 见 `docs/first-app-spike-readiness.md`。

下一推荐 candidate：`artifact review flow`。

该 candidate 已在后续 package 中实现为 first slice。

Original red-test goals:

- define scenario shape
- prove summary-only default
- prove controlled full-content retrieval boundary
- keep HTTP full-content route `not_enabled`
- keep no real filesystem / real LLM / real HTTP server
- stop before green unless explicitly authorized

## 11. Artifact Review Flow Spike

状态：`first slice complete`

Commands:

```bash
python -m isotope_kernel.demo --scenario artifact-review
python -m isotope_kernel.demo --scenario artifact-review --json
```

当前展示：

- deterministic / in-process flow
- existing artifact summary / structured `ResourceRef`
- reviewer action through canonical action chain
- review artifact / `ResourceRef` handoff
- controlled full-content retrieval only inside retrieval layer with grants + caller context + purpose
- demo / helper JSON output remains summary / ref / provenance only
- HTTP full-content route remains `not_enabled`
- replay and checkpoint-assisted rebuild recover review artifact summaries
- memory remains `boundary_only`

仍不展示：

- real LLM
- real HTTP server / network listener
- real provider adapter
- real filesystem mutation
- semantic retrieval / ranking
- memory query engine

Friction review: `docs/artifact-review-flow-friction-review.md`。

结论：

- `artifact-review` 是有用的 first app spike。
- 没有发现 kernel correctness bug。
- 原主要 friction 是 source artifact setup 仍需要 demo glue：直接调用 private `server._append(...)` 手工追加 source action / artifact lifecycle events。该 gap 已由 `InProcessServer.create_source_artifact(...)` 解决并 closure-reviewed。
- controlled full-content retrieval 显式传入 grants + caller context + purpose 是可接受 v0 shape，不应为了省参数放松 Track C boundary。
- review artifact handoff 经 `submit_action(...)` 已足够自然。

## 13. Source Artifact Setup Helper

状态：`closed / complete`

Boundary doc: `docs/source-artifact-setup-helper-boundary-v0.2.md`

当前 helper:

- `InProcessServer.create_source_artifact(...)`
- accepts deterministic in-process `summary` / `content` / optional `artifact_type="text"`
- validates before appending events or writing artifact state
- uses existing compiler / policy / executor path
- appends canonical action + artifact lifecycle events
- returns artifact summary / structured `ResourceRef` / provenance
- does not return full content
- does not append `run.completed`, so app-shaped flows can continue through later review actions
- is replayable and checkpoint-assisted rebuildable

`artifact-review` demo now uses this helper instead of private `server._append(...)` source setup glue.

Still not included:

- product artifact upload API
- real filesystem upload
- binary streaming
- real HTTP server
- provider adapter
- memory query engine
- artifact review product facade

Closure review: `docs/source-artifact-helper-closure-review.md`。

Closure result: source artifact setup helper is closed / complete for now.

Remaining friction:

- review provenance still scans events to find the source `artifact.created` basis event。
- controlled full-content retrieval remains intentionally explicit and is acceptable v0 shape。

Next suggested batch: `Artifact Review Flow Second Friction Review`.

## 12. Demo Trace Mode

状态：`first slice complete`

Commands:

```bash
python -m isotope_kernel.demo --scenario artifact-review --trace
python -m isotope_kernel.demo --scenario approval-tool-runner --trace
python -m isotope_kernel.demo --scenario v0.2 --trace
```

当前展示：

- human-readable step trace for session / run / action / policy / artifact / replay / checkpoint.
- default plain output remains unchanged.
- `--json` remains the machine-readable contract and takes precedence over `--trace` when both are passed.
- trace output stays summary / ref / status oriented and does not print artifact full content.

仍不展示：

- real LLM
- real HTTP server / network listener
- real provider adapter
- real filesystem mutation
- semantic retrieval / ranking
- memory query engine
