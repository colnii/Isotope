# Kernel Gap Review v0.2

状态：`current review`

## 1. Purpose

本文回看 v0.2 暂停点之后 Isotope kernel 还缺什么。目标不是宣布 kernel 完成，而是把已稳定边界、仍然半完成的子系统、主要风险和下一步设计 backlog 固化下来，避免继续盲目加 feature。

当前基线：

- tests: `786 passed`
- `v0.2-demo` tag 已存在，指向 `09319e7407116d9f99f4a18853d4df23a8714720`
- 当前 `main` 已在 tag 后完成 Track F External Ingestion / `ImportedSnapshot` boundary
- Track D / A / C / E / F 已 effectively complete / closed for now
- docs migration Phase 1 已 closed / paused

## 2. Stable Kernel Subsystems

这些子系统已经有可运行实现、测试和当前文档支撑。它们不是 production-complete，但已足够作为下一阶段设计的 hard boundary。

| Subsystem | Current status | Evidence |
| --- | --- | --- |
| Session / Run boundary | implemented | `InProcessServer` 可创建 session / run，HTTP facade 和 demo scenario 已覆盖 |
| Action chain | implemented | `ActionCompiler -> PolicyEngine -> Executor` 路径已被 demo / HTTP / approval slices 复用 |
| `PolicyDecision.grants` | implemented | executor 使用 policy-derived grants；approval resume 不接受 forged resolution grants |
| Canonical event log | implemented | file event store、event envelope validation、append-only assumptions 和 replay tests 已覆盖 |
| Projector / `RunState` | implemented | run/action/artifact/memory/approval/external observation read model 都来自 canonical events |
| Checkpoint | implemented boundary | projector-owned checkpoint creation / save / rebuild / integrity / prefix consistency 已覆盖 |
| Artifact / `ResourceRef` | implemented boundary | artifact persistence、summary retrieval、controlled content retrieval boundary 已覆盖 |
| Approval boundary | implemented boundary | requested / resolved / approved resume / denied no-execute / duplicate conflict / replay / checkpoint read model 已覆盖 |
| External observation boundary | implemented boundary | `ImportedSnapshot` / `snapshot.imported` / `external_observations` / conflict / checkpoint support 已覆盖 |
| Memory boundary | boundary-only | memory records/read model/checkpoint boundary exists；durable storage/query/promotion 仍 deferred |
| In-process HTTP facade | implemented boundary | `HttpApiApp` / `create_http_app(...)` 支持 minimal route inventory、validation、idempotency、deferred route contract |

## 3. Gap Review

| Area | Current status | Risk if deferred | Refactor difficulty if wrong | Blocks usability pressure test? | Suggested next action |
| --- | --- | --- | --- | --- | --- |
| Agent / worker lifecycle | first slice complete | 中高：已有 `RunState.agents` / `RunState.workers`、delegation policy gate、event-sourced lifecycle 和 checkpoint support，但仍没有 real worker runtime / concurrency | 高 | 部分阻塞；workspace substrate 现在是更直接 blocker | keep slice narrow, move to workspace boundary |
| Delegation loop | missing | 中高：没有 delegation contract 时，多 worker / child task 容易变成 ad hoc server calls | 高 | 是，阻塞复杂 scenario | defer until agent / worker lifecycle drafted |
| Real model loop | missing | 中：过早接 real LLM 会掩盖 kernel contract 缺口 | 中高 | 不阻塞当前 in-process pressure test | defer |
| Workspace substrate | boundary-only | 高：当前只支持 `shared_ro` grants binding；真实 workspace read/write/isolation 如果晚设计，会影响 executor/tool/artifact/policy 边界 | 高 | 是，阻塞真实 tool pressure test | docs-only boundary, then red tests for workspace grants and isolation |
| Action type registry versioning | partial / boundary | 中高：当前 registry 是固定 minimal entries，缺少 action schema evolution / compatibility contract | 中高 | 部分阻塞 | docs-only design tied to policy profile |
| Tool protocol | sketch | 中高：tool result/error/resource contract 不清会污染 event schema 和 executor ownership | 高 | 是，阻塞 external tool pressure test | docs-only protocol note after workspace boundary |
| Retry / cancel / supersede | missing | 高：失败恢复、user stop、replacement action 都会影响 lifecycle ordering、run status 和 checkpoint consistency | 高 | 是，阻塞 longer-running usability pressure test | docs-only event/state machine design, then red tests |
| Approval full state machine | boundary-only | 中：minimal approve/deny 已有，但 timeout, withdrawn, superseded, expired, audit identity 都未定义 | 中 | 不阻塞 current demo；阻塞 product-like approval | defer beyond minimal pressure test |
| Memory storage / query / promotion | boundary-only | 中：长期 deferred 会限制 continuity；过早实现又会误导为 memory product | 高 | 不阻塞 kernel boundary pressure test | defer; keep memory promotion separate from session continuity design |
| Retrieval ranking / budget / slicing | missing | 中：controlled artifact content read 已有，但 ranking/budget 会影响 future memory/search UX | 中高 | 不阻塞 current pressure test | defer until retrieval use case exists |
| External ingestion adapter lifecycle | boundary-only | 中：Track F 已锁 boundary，但 provider adapter lifecycle、raw capture retries、webhook auth 都未定义 | 高 | 不阻塞 no-network pressure test | defer; no provider adapter yet |
| Event schema migration | partial / boundary | 中高：event envelope/versioning docs exist，但 live schema migration policy across projector versions remains thin | 高 | 部分阻塞 | docs-only migration review before breaking changes |
| Checkpoint migration | partial / boundary | 中：checkpoint version/hash/fallback exists，但 multi-version migration policy still narrow | 中 | 不阻塞 current pressure test | defer until event schema migration review |
| Session continuity / multi-run behavior | sketch | 中高：session exists, but cross-run continuity, history visibility, memory promotion and carry-over are not designed | 高 | 部分阻塞 | docs-only boundary after agent lifecycle |
| Policy profile | missing | 高：policy engine validates slice-level decisions, but named profiles/capability sets are not explicit | 高 | 是，for safe pressure tests | docs-only design paired with action registry versioning |
| Domain pack boundary | missing | 低中：domain packs are packaging/composition concerns, not immediate kernel truth | 中 | 不阻塞 | defer |

## 4. Priority Judgement

### 4.1 Agent / Worker Lifecycle

优先级：最高。

原因：

- 这是后续 real model loop、delegation、retry/cancel、workspace use 和 pressure test 的上游 contract。
- 当前 `agent_runtime.py` 只是 boundary placeholder；如果先做 real HTTP server 或 provider adapter，runtime orchestration 会在没有 contract 的情况下扩散。
- 设计应先回答：worker identity、run ownership、step loop、who proposes action、who waits、who resumes、who records lifecycle events。

当前设计入口：`docs/agent-worker-lifecycle-boundary-v0.2.md`。第一批 red tests 已 green，first slice 可标为 complete：supervisor / worker read model、delegation policy gate、worker lifecycle event sourcing、worker workspace grants、result handoff、replay 和 checkpoint support 均已锁住。下一步不要实现 real model loop，应转入 Workspace substrate boundary。

### 4.2 Workspace Substrate

优先级：第二。

原因：

- 当前 workspace 只支持 shared read-only binding。
- 一旦进入真实 tool / file / sandbox pressure test，workspace grants、read/write modes、path scope、artifact handoff 和 cleanup 都会成为 hard boundary。
- 如果 workspace substrate 设计错误，后续 executor、tool protocol、artifact provenance 和 policy profile 都要返工。

建议：在 Agent / Worker Lifecycle 后做 workspace boundary 设计与 red tests。

### 4.3 Retry / Cancel / Supersede

优先级：第三。

原因：

- 这是 run/action lifecycle 的缺口，直接影响 projector invariants、checkpoint prefix consistency 和 approval/external observation read model。
- 不应直接实现；先定义 event/state machine，尤其是 cancel 是否可关闭 pending approval、supersede 是否保留 old proposal lineage。

建议：docs-only state machine review，然后 red tests。

### 4.4 Policy Profile / Action Registry Versioning

优先级：第四。

原因：

- `PolicyDecision.grants` 已稳定，但 profile-level capability sets 尚未定义。
- action registry 仍是 minimal static registry；缺少 registry version、schema compatibility、tool capability gating 和 migration stance。
- 这会影响 pressure test 的安全边界，但可以在 agent/workspace 之后做。

建议：合并成一个 docs-only boundary：policy profile + action registry versioning。

### 4.5 Session Continuity / Memory Promotion

优先级：延后。

原因：

- session continuity 重要，但如果直接和 memory promotion 绑定，会过早打开 durable memory query/storage/promotion 产品问题。
- 当前 memory boundary 是 deliberate freeze：boundary/read-model/checkpoint only。
- 可先设计 multi-run/session history visibility，不要实现 memory promotion。

建议：defer memory promotion；session continuity 可在 worker/workspace/retry 之后做 docs-only boundary。

## 5. Recommended Next Design

下一块 kernel design 建议优先做：

1. Workspace substrate boundary
2. Retry / cancel / supersede lifecycle boundary
3. Policy profile / action registry versioning boundary
4. Session continuity / multi-run boundary, without memory promotion

不要先做：

- real HTTP server / network listener
- real LLM loop
- memory storage / query / promotion
- real provider adapter / webhook
- retrieval ranking / semantic search
- domain pack system

## 6. Usability Pressure Test Readiness

可以开始一个很窄的 usability pressure test plan，但不建议立即做 broad external usability test。

可接受的 pressure test 形态：

- in-process only
- deterministic or mock model only
- no network listener
- no real LLM
- no durable memory query/storage
- explicitly checks action chain, policy grants, workspace grants, event replay, checkpoint and read models

阻塞 broad pressure test 的 kernel gaps：

- Workspace substrate 仍只有 shared_ro boundary
- Retry / cancel / supersede lifecycle 未定义
- Policy profile / action registry versioning 未定义

结论：Agent / Worker Lifecycle first slice 已 complete；下一步应继续补 Workspace Substrate 设计，再进入更真实的 usability pressure test。

## 7. Non-Goals For This Review

- 不打开 implementation track。
- 不新增 red tests。
- 不重排 docs 目录。
- 不创建新 tag。
- 不发布 GitHub Release。
- 不声明 kernel complete。
